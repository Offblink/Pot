"""Board access, role-session mounting, and card dispatch (spec §3.1/§3.3).

Host side of 「常驻角色 + 主动认领」: after a turn the dispatcher looks for todo
cards a resident role may claim, resolves the role's long-term session
(definition on disk in data/roles, memory in sessions/ with the role badge),
and runs one turn there with the card brief. Inside that turn the role claims,
executes, and reports; the card then waits for a human.

Eligibility here MIRRORS board.claim's gates — the authoritative check still
runs inside `pot_board_claim`; this pass only decides whose turn to wake.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from pot import runlog, session
from pot.board import Board
from pot.config import PROJECT_ROOT
from pot.roles import Role, RoleRepo

ROLES_DIR = PROJECT_ROOT / "data" / "roles"
BOARD_DB = PROJECT_ROOT / "data" / "board.sqlite"

# The Planner as a system role (spec §3.3): creates cards, claims nothing.
# Seeded once — a human may edit the file live; deleting it just re-seeds.
_PLANNER_SEED = {
    "id": "planner",
    "name": "Planner",
    "mission": "",
    "tools": [],
    "model": None,
    "wip": 1,
    "canClaim": False,
    "canCreateCard": True,
    "template": None,
    "createdBy": "human",
    "isTemplate": False,
}

# Singletons live in a dict (mutated, never rebound) — no global statements.
# RLock, not Lock: board() seeds by calling roles_repo() while holding this
# lock (first use in a fresh process) — a plain Lock self-deadlocks the very
# first turn (real-machine finding, 2026-11-04).
_SINGLETONS: dict = {}
_CREATE_LOCK = threading.RLock()
_CYCLE = threading.Lock()
# 裁决 39: concurrent model turns per cycle. Covers one role's default three
# instances plus one; queued plans still run inside the same cycle (joined
# before _CYCLE releases), this only bounds simultaneous API calls.
_MAX_PARALLEL = 4


def roles_repo() -> RoleRepo:
    if "roles" not in _SINGLETONS:
        with _CREATE_LOCK:  # first call may race; seed exactly once
            if "roles" not in _SINGLETONS:
                repo = RoleRepo(ROLES_DIR)
                if not (ROLES_DIR / "planner.json").is_file():
                    repo.create(dict(_PLANNER_SEED), creator="human")
                _SINGLETONS["roles"] = repo
    return _SINGLETONS["roles"]


def board() -> Board:
    if "board" not in _SINGLETONS:
        with _CREATE_LOCK:
            if "board" not in _SINGLETONS:
                _SINGLETONS["board"] = Board(BOARD_DB, roles_repo())
    return _SINGLETONS["board"]


def reset_for_tests(*, roles: RoleRepo | None = None, board_obj: Board | None = None) -> None:
    """Test seam: point the module at tmp dirs (None clears back to defaults)."""
    if roles is None:
        _SINGLETONS.pop("roles", None)
    else:
        _SINGLETONS["roles"] = roles
    if board_obj is None:
        _SINGLETONS.pop("board", None)
    else:
        _SINGLETONS["board"] = board_obj


def role_instances(role: Role) -> list[dict]:
    """The role's mounted instance sessions, numbered (裁决 33).

    One instance = one session carrying the role key; sessions written before
    the `instance` field existed count as #1.
    """
    rows = [s for s in session.list_sessions() if s.get("role") == role.id]
    rows.sort(key=lambda s: (int(s.get("instance") or 1), str(s.get("created") or "")))
    return rows


def ensure_instance(role: Role) -> str:
    """Mount the next numbered instance of the role (auto-growth, 裁决 33).

    Called under dispatch's cycle lock, so numbering cannot race itself.
    """
    rows = role_instances(role)
    number = max((int(r.get("instance") or 1) for r in rows), default=0) + 1
    sid = session.new_session_id()
    # The turn runner rewrites the system row from the live role definition on
    # every turn (mission edits apply without re-mounting).
    session.save_session(
        sid,
        role.name or role.id,
        [{"role": "system", "content": ""}],
        role=role.id,
    )
    session.set_key(sid, "instance", number)
    runlog.note("mounted %s instance #%d (%s)", role.id, number, sid)
    return sid


def role_session(role: Role) -> str:
    """The role's first instance (created on first use) — the stable handle
    tests and one-off callers expect (spec §3.1: definition and memory apart)."""
    rows = role_instances(role)
    if rows:
        return str(rows[0]["id"])
    return ensure_instance(role)


def role_may_take(role: Role, card: dict) -> bool:
    """Role-level claim gates (labels / canClaim / card.role). The WIP gate is
    per instance and lives in `_held_by_instance` (裁决 33)."""
    if role.canClaim is False:
        return False
    if (
        isinstance(role.canClaim, list)
        and role.canClaim
        and not set(card.get("labels") or []) <= set(role.canClaim)
    ):
        return False
    return not card.get("role") or card["role"] == role.id


def eligible(role: Role, card: dict, held: int) -> bool:
    """Mirror of board.claim's role gates (the claim itself re-checks)."""
    return role_may_take(role, card) and held < role.wip


def _held_by_instance(cards: list[dict], role_id: str, session_id: str) -> int:
    """Cards held by exactly this instance (裁决 33: wip counts per instance)."""
    holder = f"{role_id}:{session_id}"
    return sum(1 for c in cards if c.get("holder") == holder and c.get("status") != "done")


def _next_claimable(seen: set[str], busy: set[str]) -> tuple[dict, Role, str | None] | None:
    """First unvisited todo card an instance may take; urgent cards first.

    Returns (card, role, instance) — instance None means "no live instance has
    a free slot and the role may still grow one" (裁决 33 auto-growth).
    `busy` = instances already planned this cycle (裁决 39): they count as full
    before their turn claims anything, which is what spreads a wave across
    numbered instances instead of stacking every brief on #1.
    """
    b = board()
    repo = roles_repo()
    cards = b.list()
    roles = [r for r in repo.list() if r.id != "planner"]
    order = {"urgent": 0, "normal": 1, "low": 2}
    todos = sorted(
        (c for c in cards if c.get("status") == "todo" and c["id"] not in seen),
        key=lambda c: (order.get(c.get("priority"), 1), c.get("createdAt") or 0),
    )
    for card in todos:
        ordered = [r for r in roles if card.get("role") == r.id] + [
            r for r in roles if card.get("role") != r.id
        ]
        for role in ordered:
            if not role_may_take(role, card):
                continue
            rows = role_instances(role)
            for row in rows:
                sid = str(row["id"])
                if sid in busy:
                    continue
                if _held_by_instance(cards, role.id, sid) < role.wip:
                    return card, role, sid
            if len(rows) < max(1, role.maxInstances):
                return card, role, None  # grow: mount the next numbered instance
    return None


def card_brief(card: dict) -> str:
    return (
        "[board] A task card is waiting for you: "
        f'{card["id"]} "{card["title"]}" '
        f"(priority={card.get('priority')}, labels={card.get('labels')})\n"
        "Use pot_board_get to read the full card (desc, checklist, ifVersion),"
        " then follow your role rules: claim it, do the work, tick the"
        " checklist with evidence, and submit pot_board_report when done."
    )


def dispatch_pending(run_turn) -> int:
    """Wake one role turn per claimable card until the board is quiet.

    `run_turn(session_id, user_msg)` runs one blocking host-side turn (server
    provides it). 裁决 39: the cycle first COLLECTS its assignments — one
    instance per card, planned instances count as full so the walk grows or
    picks the next numbered instance — then runs the wave's turns concurrently
    (bounded pool, _MAX_PARALLEL). The cycle lock stays held until every turn
    joins, so nested dispatch attempts from the turns' own after-hooks fail
    fast on the non-blocking acquire. Bounded per cycle; cards the roles did
    not claim stay in todo and are retried on the next trigger — never in a
    tight loop.
    """
    if not _CYCLE.acquire(blocking=False):
        return 0  # another cycle is already walking the board
    try:
        seen: set[str] = set()
        busy: set[str] = set()  # instances planned in THIS cycle (裁决 39)
        plan: list[tuple[str, str, str]] = []  # (session, "card -> role", brief)
        for _ in range(16):  # hard bound: a cycle must terminate even if roles no-op
            found = _next_claimable(seen, busy)
            if found is None:
                break
            card, role, instance = found
            seen.add(card["id"])
            sid = instance if instance is not None else ensure_instance(role)
            busy.add(sid)
            plan.append((sid, f"{card['id']} -> {role.id}", card_brief(card)))
        if not plan:
            return 0

        def _run_one(sid: str, label: str, brief: str) -> bool:
            try:
                run_turn(sid, brief)
                return True
            except Exception as exc:  # one broken session must not stall the wave
                runlog.problem("dispatch %s failed: %s", label, exc)
                return False

        with ThreadPoolExecutor(max_workers=min(len(plan), _MAX_PARALLEL)) as pool:
            # Materialize the submits FIRST: a lazy generator would block on the
            # first f.result() before submitting the rest — serial, not parallel.
            futures = [pool.submit(_run_one, *a) for a in plan]
            results = [f.result() for f in futures]
        return sum(results)
    finally:
        _CYCLE.release()


# ---- completion notification (spec §3.3 / 裁决 30-32) ----


def cards_done() -> set[str]:
    return {str(c["id"]) for c in board().list(status="done")}


def cards_blocked() -> set[str]:
    return {str(c["id"]) for c in board().list(status="blocked")}


def notify_route(cards: list[dict]) -> dict[str, list[dict]]:
    """Cards to the conversation that dispatched them — and only that one.

    裁决 31: a card created inside a conversation carries `source` = that
    session, and it is notified only while the session still exists and is a
    human conversation (no `role` key). Cards with no source (human/seed) and
    cards sourced to a role session stay off chat entirely — the board already
    shows their state.
    """
    buckets: dict[str, list[dict]] = {}
    for card in cards:
        source = str(card.get("source") or "")
        if not source:
            continue
        data = session.load_session(source)
        if data is None or data.get("role"):
            continue
        buckets.setdefault(source, []).append(card)
    return buckets


def done_block(cards: list[dict], lang: str = "zh") -> str:
    """裁决 30: the report as one host-rendered card block.

    No model turn and no internal-note wording: the executor already wrote the
    structured summary, so the transcript gains the value and none of the
    chatter ("Take as little human attention as possible...").
    """
    zh = lang != "en"
    head = (
        "📋 **卡片已完成** —— 报告已到（要重做就去看板重开）"
        if zh
        else "📋 **Card completed** — the report is in (reopen it on the board to redo)"
    )
    parts = [head]
    for card in cards:
        report = card.get("report") or {}
        summary = str(
            report.get("summary") or ("（无结构化摘要）" if zh else "(no structured summary)")
        )[:1500]
        facts = " · ".join(
            fact
            for fact in (str(card.get("priority") or ""), str(card.get("role") or ""))
            if fact and fact != "None"
        )
        parts.append(f"**`{card.get('id')}` · {card.get('title')}**\n{facts}\n\n{summary}")
    return "\n\n".join(parts)


def stuck_note(cards: list[dict], lang: str = "zh") -> str:
    """裁决 34: the planner's wake for blocked cards — an INTERNAL message
    (裁决 35: persisted with the flag, never rendered; the model decides
    whether to say anything, defaulting to `<<SILENT>>`)."""
    zh = lang != "en"
    lines = []
    for card in cards:
        holder = str(card.get("holder") or "")
        who = holder.split(":", 1)[0] + ("#" + holder.split(":", 1)[1][:4] if ":" in holder else "")
        lines.append(f'- {card.get("id")} "{card.get("title")}" (holder: {who or "?"})')
    if zh:
        return (
            "[board] 卡片进受阻（内部消息，用户看不到）：\n"
            + "\n".join(lines)
            + "\n你是 Planner：用 pot_board_reassign 换角色退回 todo 或解阻（reason 必填）；"
            "若它会自愈，直接回复 <<SILENT>>。"
        )
    return (
        "[board] Cards went blocked (internal note, the user never sees it):\n"
        + "\n".join(lines)
        + "\nYou are the Planner: use pot_board_reassign to change role / send back"
        " to todo (reason required), or reply <<SILENT>> if it resolves itself."
    )


def done_note(cards: list[dict], lang: str = "zh") -> str:
    """裁决 38: the planner's wake after a completed card — the visible block
    lands first (裁决 30), then this INTERNAL note (裁决 35: persisted with the
    flag, never rendered) asks the planner to review the report and split the
    follow-ups; default `<<SILENT>>` when nothing follows."""
    zh = lang != "en"
    lines = []
    for card in cards:
        holder = str(card.get("holder") or "")
        who = holder.split(":", 1)[0] + ("#" + holder.split(":", 1)[1][:4] if ":" in holder else "")
        lines.append(f'- {card.get("id")} "{card.get("title")}" (holder: {who or "?"})')
    if zh:
        return (
            "[board] 卡片已完成、报告已写进本会话（内部消息，用户看不到）：\n"
            + "\n".join(lines)
            + "\n你是 Planner：复盘报告是否达成目标；有后续就用 pot_board_create 续拆/建卡、"
            "pot_board_reassign 调整归属；没有就回复 <<SILENT>>。"
        )
    return (
        "[board] Cards completed, the report is in this conversation (internal note,"
        " the user never sees it):\n"
        + "\n".join(lines)
        + "\nYou are the Planner: review the report — split follow-ups with"
        " pot_board_create / reassign with pot_board_reassign, or reply <<SILENT>>"
        " if nothing follows."
    )
