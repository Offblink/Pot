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


def role_session(role: Role) -> str:
    """The role's long-term session: found by its `role` key, created on first
    wake (spec §3.1 — definition and memory live apart)."""
    existing = [s for s in session.list_sessions() if s.get("role") == role.id]
    if existing:
        existing.sort(key=lambda s: str(s.get("updated") or ""), reverse=True)
        return str(existing[0]["id"])
    sid = session.new_session_id()
    # The turn runner rewrites the system row from the live role definition on
    # every turn (mission edits apply without re-mounting).
    session.save_session(
        sid,
        role.name or role.id,
        [{"role": "system", "content": ""}],
        role=role.id,
    )
    runlog.note("mounted role session %s for role %s", sid, role.id)
    return sid


def eligible(role: Role, card: dict, held: int) -> bool:
    """Mirror of board.claim's role gates (the claim itself re-checks)."""
    if role.canClaim is False:
        return False
    if (
        isinstance(role.canClaim, list)
        and role.canClaim
        and not set(card.get("labels") or []) <= set(role.canClaim)
    ):
        return False
    if card.get("role") and card["role"] != role.id:
        return False
    return held < role.wip


def _held_by(cards: list[dict], role_id: str) -> int:
    prefix = f"{role_id}:"
    return sum(
        1
        for c in cards
        if c.get("holder") and str(c["holder"]).startswith(prefix) and c.get("status") != "done"
    )


def _next_claimable(seen: set[str]) -> tuple[dict, Role] | None:
    """First unvisited todo card some role may take; urgent cards first."""
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
        held = {r.id: _held_by(cards, r.id) for r in roles}
        for role in roles:  # card-specified role first: it is the intended owner
            if card.get("role") == role.id and eligible(role, card, held[role.id]):
                return card, role
        for role in roles:
            if card.get("role") != role.id and eligible(role, card, held[role.id]):
                return card, role
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
    provides it). Bounded per cycle; cards the roles did not claim stay in todo
    and are retried on the next trigger — never in a tight loop.
    """
    if not _CYCLE.acquire(blocking=False):
        return 0  # another cycle is already walking the board
    ran = 0
    try:
        seen: set[str] = set()
        for _ in range(16):  # hard bound: a cycle must terminate even if roles no-op
            found = _next_claimable(seen)
            if found is None:
                break
            card, role = found
            seen.add(card["id"])
            try:
                sid = role_session(role)
                run_turn(sid, card_brief(card))
                ran += 1
            except Exception as exc:  # one broken session must not stall the board
                runlog.problem("dispatch %s -> %s failed: %s", card["id"], role.id, exc)
        return ran
    finally:
        _CYCLE.release()


# ---- review notification (spec §3.3 / 裁决 30-31) ----


def cards_in_review() -> set[str]:
    return {str(c["id"]) for c in board().list(status="review")}


def review_route(cards: list[dict]) -> dict[str, list[dict]]:
    """Cards to the conversation that dispatched them — and only that one.

    裁决 31: a card created inside a conversation carries `source` = that
    session, and it is notified only while the session still exists and is a
    human conversation (no `role` key). Cards with no source (human/seed) and
    cards sourced to a role session stay off chat entirely — the board already
    shows their review state.
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


def review_block(cards: list[dict], lang: str = "zh") -> str:
    """裁决 30: the report as one host-rendered card block.

    No model turn and no internal-note wording: the executor already wrote the
    structured summary, so the transcript gains the value and none of the
    chatter ("Take as little human attention as possible...").
    """
    zh = lang != "en"
    head = (
        "📋 **卡片待验收** —— 报告已到，去看板验收（✓ 完成 / ✗ 退回）"
        if zh
        else "📋 **Card ready for review** — the report is in; accept or reject it on the board"
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
