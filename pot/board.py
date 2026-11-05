"""Board engine: sqlite card ledger + the seven code-level gates (spec §3.2, §7).

Storage: data/board.sqlite in WAL mode. Every operation opens its own
connection and runs inside one BEGIN IMMEDIATE transaction (single writer),
so concurrent claims serialize to exactly one winner (spec §10-5).

Gate codes from spec §3.2 ("违反返回"): role_mismatch, wip_full,
already_held, stale_version, human_only. Paths the table does not name get:
not_holder, bad_status, bad_transition, cant_create, no_such_card, no_such_role,
need_reason, need_evidence, need_text, need_summary, bad_index, bad_value.

Column lease policy: the lease ticks only while status == doing; entering
review/blocked clears it, re-entering doing re-arms it (spec §3.2 租约).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pot.errors import PotError
from pot.roles import Actor, RoleRepo

STATUSES = ("backlog", "todo", "doing", "review", "done", "blocked")
_PRIORITIES = ("urgent", "normal", "low")
_HUMAN_CREATE_STATUSES = ("backlog", "todo")
_REJECTABLE = ("doing", "review", "blocked")

# Agent transitions between held columns; done only via human ✓ (gate 5),
# todo via release/reject, backlog→todo via planning privilege (canCreateCard).
_AGENT_MOVES: dict[str, frozenset[str]] = {
    "doing": frozenset({"review", "blocked"}),
    "review": frozenset({"doing", "blocked"}),
    "blocked": frozenset({"doing"}),
}


def _row_to_card(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "desc": row["desc"],
        "labels": json.loads(row["labels"]),
        "priority": row["priority"],
        "status": row["status"],
        "role": row["role"],
        "holder": row["holder"],
        "ifVersion": row["if_version"],
        "leaseUntil": row["lease_until"],
        "checklist": json.loads(row["checklist"]),
        "report": json.loads(row["report"]) if row["report"] else None,
        "comments": json.loads(row["comments"]),
        "createdBy": row["created_by"],
        "source": row["source"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "deleted": bool(row["deleted"]),
    }


def _str_list(value: object, key: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise PotError("bad_value", key)
    return list(value)


@contextmanager
def _tx(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


class Board:
    def __init__(self, db_path: Path, roles: RoleRepo, lease_seconds: int = 900) -> None:
        self.roles = roles
        self.lease_seconds = lease_seconds
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.execute("PRAGMA journal_mode=WAL").fetchone()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    "desc" TEXT NOT NULL DEFAULT '',
                    labels TEXT NOT NULL DEFAULT '[]',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL DEFAULT 'backlog',
                    role TEXT,
                    holder TEXT,
                    if_version INTEGER NOT NULL DEFAULT 1,
                    lease_until INTEGER,
                    checklist TEXT NOT NULL DEFAULT '[]',
                    report TEXT,
                    comments TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL,
                    source TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # 裁决 31: source = the conversation that created the card. Databases
            # created before the column keep it via ALTER (CREATE IF NOT EXISTS
            # never re-runs an existing table's definition).
            if not any(col["name"] == "source" for col in conn.execute("PRAGMA table_info(cards)")):
                conn.execute("ALTER TABLE cards ADD COLUMN source TEXT")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
        finally:
            conn.close()

    # -- internals ---------------------------------------------------------

    def _sweep(self, conn: sqlite3.Connection, now: int) -> None:
        """Gate 7: expired leases fall back to todo, holder cleared, commented."""
        rows = conn.execute(
            "SELECT id, holder FROM cards WHERE deleted=0 AND status='doing'"
            " AND lease_until IS NOT NULL AND lease_until <= ?",
            (now,),
        ).fetchall()
        for row in rows:
            comments = json.loads(
                conn.execute("SELECT comments FROM cards WHERE id=?", (row["id"],)).fetchone()[
                    "comments"
                ]
            )
            comments.append(
                {
                    "by": "system",
                    "text": f"租约到期，自动退回待办（原持有：{row['holder']}）",
                    "at": now,
                }
            )
            conn.execute(
                "UPDATE cards SET status='todo', holder=NULL, lease_until=NULL, comments=?,"
                " if_version=if_version+1, updated_at=? WHERE id=?",
                (json.dumps(comments, ensure_ascii=False), now, row["id"]),
            )

    @staticmethod
    def _fetch(conn: sqlite3.Connection, card_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if row is None or row["deleted"]:
            raise PotError("no_such_card", card_id)
        return row

    @staticmethod
    def _check_version(row: sqlite3.Row, if_version: object) -> None:
        if if_version != row["if_version"]:
            raise PotError(
                "stale_version", f"{row['id']}: card is {row['if_version']}, got {if_version}"
            )

    @staticmethod
    def _require_holder(row: sqlite3.Row, actor: Actor) -> None:
        if row["holder"] is None:
            raise PotError("not_holder", row["id"])
        if row["holder"] != actor.holder:
            raise PotError("already_held", f"{row['id']} held by {row['holder']}")

    @staticmethod
    def _apply(conn: sqlite3.Connection, card_id: str, sets: dict[str, object], now: int) -> dict:
        assignments = ", ".join(f"{col}=?" for col in sets)
        conn.execute(
            f"UPDATE cards SET {assignments}, if_version=if_version+1, updated_at=? WHERE id=?",
            (*sets.values(), now, card_id),
        )
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _row_to_card(row)

    def _insert(
        self,
        conn: sqlite3.Connection,
        *,
        title: object,
        desc: object,
        labels: object,
        priority: object,
        role: object,
        checklist: object,
        created_by: str,
        source: str | None = None,
        status: str,
        now: int,
    ) -> dict:
        if not isinstance(title, str) or not title.strip():
            raise PotError("bad_value", "title")
        if not isinstance(desc, str):
            raise PotError("bad_value", "desc")
        if priority not in _PRIORITIES:
            raise PotError("bad_value", f"priority={priority!r}")
        label_list = _str_list(labels, "labels")
        if role is not None:
            self.roles.get(str(role))  # must exist → no_such_role
        items = []
        for entry in _str_list(checklist, "checklist"):
            if not entry.strip():
                raise PotError("bad_value", "checklist")
            items.append({"text": entry, "done": False, "evidence": None})
        card_id = f"p-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO cards (id, title, desc, labels, priority, status, role, holder,"
            " if_version, lease_until, checklist, report, comments, created_by, source,"
            " created_at, updated_at, deleted)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 1, NULL, ?, NULL, '[]', ?, ?, ?, ?, 0)",
            (
                card_id,
                title,
                desc,
                json.dumps(label_list, ensure_ascii=False),
                priority,
                status,
                role,
                json.dumps(items, ensure_ascii=False),
                created_by,
                source,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return _row_to_card(row)

    # -- reads -------------------------------------------------------------

    def get(self, card_id: str) -> dict:
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if row is None:
                raise PotError("no_such_card", card_id)
            return _row_to_card(row)

    def list(
        self,
        status: str | None = None,
        role: str | None = None,
        labels: list[str] | None = None,
        include_deleted: bool = False,
    ) -> list[dict]:
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            rows = conn.execute("SELECT * FROM cards ORDER BY created_at, id").fetchall()
        out = []
        for row in rows:
            card = _row_to_card(row)
            if card["deleted"] and not include_deleted:
                continue
            if status is not None and card["status"] != status:
                continue
            if role is not None:
                holder_role = card["holder"].split(":", 1)[0] if card["holder"] else None
                if role not in (card["role"], holder_role):
                    continue
            if labels is not None and not (set(labels) & set(card["labels"])):
                continue
            out.append(card)
        return out

    # -- agent path (pot_board_*) -----------------------------------------

    def create(
        self,
        actor: Actor,
        title: str,
        desc: str = "",
        labels: list[str] | None = None,
        priority: str = "normal",
        role: str | None = None,
        checklist: list[str] | None = None,
    ) -> dict:
        creator = self.roles.get(actor.role_id)
        if not creator.canCreateCard:
            raise PotError("cant_create", actor.role_id)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            return self._insert(
                conn,
                title=title,
                desc=desc,
                labels=labels,
                priority=priority,
                role=role,
                checklist=checklist,
                created_by=actor.role_id,
                source=actor.session_id,  # 裁决 31: the conversation to report back to
                status="todo",
                now=now,
            )

    def claim(self, actor: Actor, card_id: str, if_version: object) -> dict:
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            holder = row["holder"]
            if holder is not None:
                if holder != actor.holder:
                    raise PotError("already_held", f"{card_id} held by {holder}")
                if row["status"] != "doing":
                    raise PotError("bad_status", row["status"])  # holder re-claim = renew
                return self._apply(conn, card_id, {"lease_until": now + self.lease_seconds}, now)
            if row["status"] != "todo":
                raise PotError("bad_status", row["status"])
            role = self.roles.get(actor.role_id)
            if role.canClaim is False:
                raise PotError("role_mismatch", f"{actor.role_id} is barred from claiming")
            if not isinstance(role.canClaim, list):
                raise PotError("bad_role_file", f"{role.id}.canClaim")
            labels = set(json.loads(row["labels"]))
            if role.canClaim and not labels <= set(role.canClaim):
                raise PotError("role_mismatch", f"{sorted(labels)} not in {role.canClaim}")
            if row["role"] is not None and row["role"] != actor.role_id:
                raise PotError("role_mismatch", f"card wants role {row['role']}")
            held = conn.execute(
                "SELECT COUNT(*) FROM cards WHERE deleted=0 AND status!='done' AND holder GLOB ?",
                (f"{actor.role_id}:*",),
            ).fetchone()[0]
            if held >= role.wip:
                raise PotError("wip_full", f"{actor.role_id} holds {held}/{role.wip}")
            return self._apply(
                conn,
                card_id,
                {
                    "holder": actor.holder,
                    "status": "doing",
                    "lease_until": now + self.lease_seconds,
                },
                now,
            )

    def move(self, actor: Actor, card_id: str, to: str, if_version: object) -> dict:
        if to not in STATUSES:
            raise PotError("bad_status", str(to))
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            if to == "done":
                raise PotError("human_only", "agents can only reach review")
            sets: dict[str, object] = {"status": to}
            if row["holder"] is None:
                if not (row["status"] == "backlog" and to == "todo"):
                    raise PotError("not_holder", card_id)
                if not self.roles.get(actor.role_id).canCreateCard:
                    raise PotError("cant_create", actor.role_id)
            else:
                if row["holder"] != actor.holder:
                    raise PotError("already_held", f"{card_id} held by {row['holder']}")
                if to not in _AGENT_MOVES.get(row["status"], frozenset()):
                    raise PotError("bad_transition", f"{row['status']} → {to}")
            sets["lease_until"] = now + self.lease_seconds if to == "doing" else None
            return self._apply(conn, card_id, sets, now)

    def comment(self, actor: Actor, card_id: str, text: str, if_version: object) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise PotError("need_text", card_id)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            comments = json.loads(row["comments"])
            comments.append({"by": actor.holder, "text": text, "at": now})
            return self._apply(
                conn, card_id, {"comments": json.dumps(comments, ensure_ascii=False)}, now
            )

    def checklist(
        self, actor: Actor, card_id: str, index: object, evidence: str, if_version: object
    ) -> dict:
        if not isinstance(evidence, str) or not evidence.strip():
            raise PotError("need_evidence", card_id)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            self._require_holder(row, actor)
            items = json.loads(row["checklist"])
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
                raise PotError("bad_index", repr(index))
            items[index]["done"] = True
            items[index]["evidence"] = evidence
            return self._apply(
                conn, card_id, {"checklist": json.dumps(items, ensure_ascii=False)}, now
            )

    def report(
        self,
        actor: Actor,
        card_id: str,
        summary: str,
        if_version: object,
        files: list[str] | None = None,
        self_test: str = "",
        risks: str = "",
    ) -> dict:
        if not isinstance(summary, str) or not summary.strip():
            raise PotError("need_summary", card_id)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            self._require_holder(row, actor)
            if row["status"] != "doing":
                raise PotError("bad_transition", f"{row['status']} → review")
            stored = {
                "summary": summary,
                "files": _str_list(files, "files"),
                "selfTest": self_test or "",
                "risks": risks or "",
            }
            return self._apply(
                conn,
                card_id,
                {
                    "report": json.dumps(stored, ensure_ascii=False),
                    "status": "review",
                    "lease_until": None,
                },
                now,
            )

    def release(self, actor: Actor, card_id: str, reason: str, if_version: object) -> dict:
        if not isinstance(reason, str) or not reason.strip():
            raise PotError("need_reason", card_id)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            self._require_holder(row, actor)
            if row["status"] not in _REJECTABLE:
                raise PotError("bad_transition", f"{row['status']} → todo")
            comments = json.loads(row["comments"])
            comments.append({"by": actor.holder, "text": reason, "at": now})
            return self._apply(
                conn,
                card_id,
                {
                    "status": "todo",
                    "holder": None,
                    "lease_until": None,
                    "comments": json.dumps(comments, ensure_ascii=False),
                },
                now,
            )

    # -- human path (launcher board page only, spec §3.5) ------------------

    def human_create(
        self,
        title: str,
        desc: str = "",
        labels: list[str] | None = None,
        priority: str = "normal",
        role: str | None = None,
        checklist: list[str] | None = None,
        status: str = "todo",
    ) -> dict:
        if status not in _HUMAN_CREATE_STATUSES:
            raise PotError("bad_status", status)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            return self._insert(
                conn,
                title=title,
                desc=desc,
                labels=labels,
                priority=priority,
                role=role,
                checklist=checklist,
                created_by="human",
                status=status,
                now=now,
            )

    def human_assign(self, card_id: str, role: str | None, if_version: object) -> dict:
        if role is not None:
            self.roles.get(str(role))  # must exist → no_such_role
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            if row["status"] == "done":
                raise PotError("bad_transition", "done is final")
            if row["holder"] is not None:
                raise PotError("already_held", f"{card_id} held by {row['holder']}")
            return self._apply(conn, card_id, {"role": role}, now)

    def human_complete(self, card_id: str, if_version: object) -> dict:
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            if row["status"] != "review":
                raise PotError("bad_transition", f"{row['status']} → done")
            return self._apply(
                conn, card_id, {"status": "done", "holder": None, "lease_until": None}, now
            )

    def human_reject(self, card_id: str, reason: str, if_version: object) -> dict:
        if not isinstance(reason, str) or not reason.strip():
            raise PotError("need_reason", card_id)
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            if row["status"] not in _REJECTABLE:
                raise PotError("bad_transition", f"{row['status']} → todo")
            comments = json.loads(row["comments"])
            comments.append({"by": "human", "text": reason, "at": now})
            return self._apply(
                conn,
                card_id,
                {
                    "status": "todo",
                    "holder": None,
                    "lease_until": None,
                    "comments": json.dumps(comments, ensure_ascii=False),
                },
                now,
            )

    def human_renew_lease(self, card_id: str, if_version: object) -> dict:
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            if row["holder"] is None:
                raise PotError("no_holder", card_id)
            if row["status"] != "doing":
                raise PotError("bad_transition", f"{row['status']} has no lease")
            return self._apply(conn, card_id, {"lease_until": now + self.lease_seconds}, now)

    def human_delete(self, card_id: str, if_version: object) -> dict:
        now = int(time.time())
        with self._db() as conn, _tx(conn):
            self._sweep(conn, now)
            row = self._fetch(conn, card_id)
            self._check_version(row, if_version)
            return self._apply(conn, card_id, {"deleted": 1}, now)
