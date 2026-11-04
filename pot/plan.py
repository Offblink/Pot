"""Plan todo tool (spec 裁决 17): per-session plan list, full-replace semantics.

The host keeps the latest plan per session (data/plans/<sid>.json). WebUI
renders it as an updatable chat card; items whose done flips false→true come
back in "flipped" so the front end can play the strikethrough animation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pot.errors import PotError
from pot.tools.board import schema

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

TODO_SCHEMA = schema(
    "todo",
    "Replace this session's plan list — send the FULL list every time. Items that"
    " just flipped to done are returned in 'flipped' (the UI strikes them through"
    " with an animation). Empty list clears the plan.",
    {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "done": {"type": "boolean"}},
                "required": ["text", "done"],
            },
        }
    },
    ["items"],
)


def _validated_items(items: object) -> list[dict]:
    if not isinstance(items, list):
        raise PotError("bad_item", "items must be a list")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise PotError("bad_item", repr(item))
        text, done = item.get("text"), item.get("done")
        if not isinstance(text, str) or not text.strip():
            raise PotError("bad_item", "text must be a non-empty string")
        if not isinstance(done, bool):
            raise PotError("bad_item", "done must be a boolean")
        out.append({"text": text, "done": done})
    return out


class PlanStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not _SESSION_RE.match(session_id):
            raise PotError("bad_session", repr(session_id))
        return self.root / f"{session_id}.json"

    def get(self, session_id: str) -> list[dict]:
        path = self._path(session_id)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def apply(self, session_id: str, items: object) -> tuple[list[dict], list[str]]:
        plan = _validated_items(items)
        old_done = {it["text"] for it in self.get(session_id) if it["done"]}
        flipped = [it["text"] for it in plan if it["done"] and it["text"] not in old_done]
        path = self._path(session_id)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return plan, flipped


def make_todo_tool(store: PlanStore, session_id: str):
    def todo(items: list) -> str:
        try:
            plan, flipped = store.apply(session_id, items)
        except PotError as exc:
            return f"ERROR: {exc}"
        return json.dumps({"ok": True, "plan": plan, "flipped": flipped}, ensure_ascii=False)

    return todo
