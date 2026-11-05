"""pot_board_* agent tools — Fungi dispatch shape: fn(**schema kwargs) -> str.

Failures render as "ERROR: <code>: <detail>" (Fungi house style), successes as
JSON. make_tools binds an Actor so M2b can register per-role tool sets.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable

from pot.board import Board
from pot.errors import PotError
from pot.roles import Actor


def schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """OpenAI function-calling def, same shape as Fungi's TOOLS registry."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_ID = {"type": "string"}
_VERSION = {
    "type": "integer",
    "description": "the card's current ifVersion; a mismatch is rejected as stale_version",
}

SCHEMAS: dict[str, dict] = {
    "pot_board_list": schema(
        "pot_board_list",
        "List board cards. Filter by column (status), role (expected role or current"
        " holder), and labels (cards carrying any of them).",
        {
            "status": {"type": "string", "description": "todo|doing|done|blocked"},
            "role": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "include_deleted": {"type": "boolean"},
        },
        [],
    ),
    "pot_board_get": schema(
        "pot_board_get",
        "Read one card in full: desc, comments, checklist, report, lease.",
        {"card_id": _ID},
        ["card_id"],
    ),
    "pot_board_create": schema(
        "pot_board_create",
        "Create a card (needs the creator role's canCreateCard). Lands in todo."
        " desc carries goal + reply_format + constraints.",
        {
            "title": {"type": "string"},
            "desc": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "string", "description": "urgent|normal|low"},
            "role": {"type": "string", "description": "expected role; omit = any"},
            "checklist": {"type": "array", "items": {"type": "string"}, "description": "DoD items"},
        },
        ["title"],
    ),
    "pot_board_claim": schema(
        "pot_board_claim",
        "Claim a todo card. All seven gates run here; on success you hold it and the lease starts.",
        {"card_id": _ID, "if_version": _VERSION},
        ["card_id", "if_version"],
    ),
    "pot_board_move": schema(
        "pot_board_move",
        "Move a card you hold: doing→blocked, blocked→doing. done is reached"
        " only by pot_board_report.",
        {"card_id": _ID, "to": {"type": "string"}, "if_version": _VERSION},
        ["card_id", "to", "if_version"],
    ),
    "pot_board_comment": schema(
        "pot_board_comment",
        "Append a comment to a card (any role).",
        {"card_id": _ID, "text": {"type": "string"}, "if_version": _VERSION},
        ["card_id", "text", "if_version"],
    ),
    "pot_board_checklist": schema(
        "pot_board_checklist",
        "Tick a DoD checklist item (holder only). evidence is mandatory.",
        {
            "card_id": _ID,
            "index": {"type": "integer", "description": "0-based checklist index"},
            "evidence": {"type": "string"},
            "if_version": _VERSION,
        },
        ["card_id", "index", "evidence", "if_version"],
    ),
    "pot_board_report": schema(
        "pot_board_report",
        "Submit the structured report (holder only); the card completes (done)"
        " with the report as the deliverable.",
        {
            "card_id": _ID,
            "summary": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
            "self_test": {"type": "string"},
            "risks": {"type": "string"},
            "if_version": _VERSION,
        },
        ["card_id", "summary", "if_version"],
    ),
    "pot_board_release": schema(
        "pot_board_release",
        "Voluntarily drop a card you hold back to todo, with a reason.",
        {"card_id": _ID, "reason": {"type": "string"}, "if_version": _VERSION},
        ["card_id", "reason", "if_version"],
    ),
    "pot_board_reassign": schema(
        "pot_board_reassign",
        "Planner only (裁决 34): send a live card back to todo under a (possibly"
        " different) role, with a reason. Clears holder and lease; the reason"
        " lands in the card's comments.",
        {
            "card_id": _ID,
            "to_role": {"type": "string", "description": "new expected role; omit to unpin"},
            "reason": {"type": "string"},
            "if_version": _VERSION,
        },
        ["card_id", "reason", "if_version"],
    ),
    "pot_board_retire": schema(
        "pot_board_retire",
        "Planner only (裁决 40): retire (soft-delete) a dead-end LIVE card that"
        " THIS conversation dispatched — superseded work that will never be"
        " claimed. The reason lands in the card's comments. `done` history,"
        " human-created cards, and cards other conversations dispatched are"
        " rejected.",
        {"card_id": _ID, "reason": {"type": "string"}, "if_version": _VERSION},
        ["card_id", "reason", "if_version"],
    ),
}


def _guard(fn: Callable[..., str]) -> Callable[..., str]:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except PotError as exc:
            return f"ERROR: {exc}"

    return wrapper


def _ok(payload: dict) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def make_tools(board: Board, actor: Actor) -> dict[str, Callable[..., str]]:
    """The pot_board_* tools bound to one actor (role + session)."""

    @_guard
    def pot_board_list(
        status: str | None = None,
        role: str | None = None,
        labels: list[str] | None = None,
        include_deleted: bool = False,
    ) -> str:
        cards = board.list(status=status, role=role, labels=labels, include_deleted=include_deleted)
        return _ok({"cards": cards})

    @_guard
    def pot_board_get(card_id: str) -> str:
        return _ok({"card": board.get(card_id)})

    @_guard
    def pot_board_create(
        title: str,
        desc: str = "",
        labels: list[str] | None = None,
        priority: str = "normal",
        role: str | None = None,
        checklist: list[str] | None = None,
    ) -> str:
        card = board.create(
            actor,
            title,
            desc=desc,
            labels=labels,
            priority=priority,
            role=role,
            checklist=checklist,
        )
        return _ok({"card": card})

    @_guard
    def pot_board_claim(card_id: str, if_version: int) -> str:
        return _ok({"card": board.claim(actor, card_id, if_version)})

    @_guard
    def pot_board_move(card_id: str, to: str, if_version: int) -> str:
        return _ok({"card": board.move(actor, card_id, to, if_version)})

    @_guard
    def pot_board_comment(card_id: str, text: str, if_version: int) -> str:
        return _ok({"card": board.comment(actor, card_id, text, if_version)})

    @_guard
    def pot_board_checklist(card_id: str, index: int, evidence: str, if_version: int) -> str:
        return _ok({"card": board.checklist(actor, card_id, index, evidence, if_version)})

    @_guard
    def pot_board_report(
        card_id: str,
        summary: str,
        if_version: int,
        files: list[str] | None = None,
        self_test: str = "",
        risks: str = "",
    ) -> str:
        return _ok(
            {
                "card": board.report(
                    actor,
                    card_id,
                    summary,
                    if_version,
                    files=files,
                    self_test=self_test,
                    risks=risks,
                )
            }
        )

    @_guard
    def pot_board_release(card_id: str, reason: str, if_version: int) -> str:
        return _ok({"card": board.release(actor, card_id, reason, if_version)})

    @_guard
    def pot_board_reassign(
        card_id: str, reason: str, if_version: int, to_role: str | None = None
    ) -> str:
        return _ok({"card": board.reassign(actor, card_id, to_role, reason, if_version)})

    @_guard
    def pot_board_retire(card_id: str, reason: str, if_version: int) -> str:
        return _ok({"card": board.retire(actor, card_id, reason, if_version)})

    bound = (
        pot_board_list,
        pot_board_get,
        pot_board_create,
        pot_board_claim,
        pot_board_move,
        pot_board_comment,
        pot_board_checklist,
        pot_board_report,
        pot_board_release,
        pot_board_reassign,
        pot_board_retire,
    )
    return {fn.__name__: fn for fn in bound}
