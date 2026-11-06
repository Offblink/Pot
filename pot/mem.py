"""Role memory: post-task summaries + the bounded context a role wake gets.

The blow-up this replaces (2026-11-06): a resident role's transcript IS its
working log — two days of executor work reached 10.47 MB (~1.05M tokens) and
every wake replayed all of it, until DeepSeek's 1M window answered HTTP 400.
Storage keeps the full transcript (scrollback + forensics); only the list
sent to the model is rebuilt per wake:

    system prompt + index_section() + recap() + the current brief

- index: ONE line per summary file (first line of each, newest first).
  No size budget: the full text is fetched on demand with `pot_memory_read`
  (裁决 43 — the user's "list only, never the full text" call).
- recap: the previous wake's final assistant text, hard-capped — where it
  left off. In-progress state lives on the CARD (checklist/comments), not
  in the transcript, which is why no history rows are re-fed at all.

Summaries are OPTIONAL: the role writes one after a card completes if the
task produced durable knowledge (`pot_memory_write`). Files:
data/mem/<role>/<YYYYMMDD-HHMMSS>-<hex>.md (data/ is gitignored).
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from pot.config import PROJECT_ROOT
from pot.errors import PotError

if TYPE_CHECKING:
    from pot.agent import BoundTool

MEM_DIR = PROJECT_ROOT / "data" / "mem"
MAX_SUMMARY_BYTES = 32_000  # one write cannot smuggle a transcript into memory
RECAP_CHARS = 4_000  # hard cap on the "where you left off" block
_INDEX_LINE_CHARS = 80
_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_NAME_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}\.md$")
_GUARD = threading.Lock()

_USELESS_RECAPS = ("(Aborted)", "(LLM error", "<<SILENT>>")

MEMORY_WRITE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "pot_memory_write",
        "description": (
            "Persist ONE short summary of what this task taught you (durable knowledge for"
            " future cards: paths, decisions, gotchas, what not to retry). Optional — write"
            " it after pot_board_report when the task produced something worth keeping; not"
            " a step-by-step log. Future wakes list it in your prompt; full text is fetched"
            " back with pot_memory_read."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The summary. Start with a one-line title — that line is your index entry.",
                }
            },
            "required": ["text"],
        },
    },
}

MEMORY_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "pot_memory_read",
        "description": (
            "Read one full summary from your memory index (file name exactly as listed in"
            " your prompt). Read before relying on an index line."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "File name from the index, e.g. 20261106-155239-4f2a.md",
                }
            },
            "required": ["file"],
        },
    },
}

SCHEMAS: dict[str, dict] = {
    "pot_memory_write": MEMORY_WRITE_SCHEMA,
    "pot_memory_read": MEMORY_READ_SCHEMA,
}


def _dir(role_id: str) -> Path:
    if not _ROLE_RE.match(role_id):
        raise PotError("bad_value", f"role={role_id!r}")
    return MEM_DIR / role_id


def write(role_id: str, text: str) -> str:
    """Append one summary file; returns its name."""
    body = (text or "").strip()
    if not body:
        raise PotError("bad_value", "text is empty")
    if len(body.encode("utf-8")) > MAX_SUMMARY_BYTES:
        raise PotError("bad_value", f"summary over {MAX_SUMMARY_BYTES} bytes")
    directory = _dir(role_id)
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}.md"
    with _GUARD:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(body, encoding="utf-8")
    return name


def read(role_id: str, name: str) -> str:
    """One summary's full text; file is matched strictly (no path components)."""
    if not _NAME_RE.match(name or ""):
        raise PotError("bad_value", f"file={name!r}")
    path = _dir(role_id) / name
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PotError("no_such_memory", name) from exc


def _files(role_id: str) -> list[Path]:
    """This role's summary files, newest first (mtime, sub-second safe)."""
    try:
        directory = _dir(role_id)
    except PotError:
        return []
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.md"), key=lambda p: p.stat().st_mtime_ns, reverse=True)


def _first_line(body: str) -> str:
    for raw in body.splitlines():
        line = raw.strip().lstrip("#").strip()
        if line:
            return line[:_INDEX_LINE_CHARS]
    return "(untitled)"


def index_section(role_id: str) -> str:
    """System-prompt block: one index line per summary. Empty when untouched."""
    lines = []
    for path in _files(role_id):
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines.append(f"- {path.name}: {_first_line(body)}")
    if not lines:
        return ""
    return (
        "\n\n## Your memory index (summaries you saved after past tasks)"
        "\nFull text: pot_memory_read(file). Newest first.\n" + "\n".join(lines)
    )


def _last_final_text(rows: list[dict]) -> str:
    """The most recent usable closing text: a plain assistant message (no
    tool_calls), not an abort/error/silence marker."""
    for row in reversed(rows):
        if row.get("role") != "assistant":
            continue
        if row.get("tool_calls"):
            continue
        text = str(row.get("content") or "").strip()
        if not text or any(text.startswith(marker) for marker in _USELESS_RECAPS):
            continue
        if len(text) > RECAP_CHARS:
            return text[:RECAP_CHARS] + "\n…[truncated]"
        return text
    return ""


def recap_section(rows: list[dict]) -> str:
    """System-prompt block: the previous wake's closing words, capped.
    Rows are the FULL stored transcript (the new brief among them); only an
    assistant final text matches, so the brief itself never leaks here."""
    text = _last_final_text(rows)
    if not text:
        return ""
    return (
        "\n\n## Where you left off (your last wake's closing words — the"
        " transcript itself is not re-fed)\n" + text
    )


def make_tools(role_id: str) -> dict:
    """Raw pot_memory_* callables bound to one role (BoundTool args-dict shape,
    the diary precedent — _dispatch also stringifies any raised PotError)."""

    def pot_memory_write(args: dict) -> str:
        try:
            return f"saved {write(role_id, str(args.get('text') or ''))}"
        except PotError as exc:
            return f"ERROR: {exc}"

    def pot_memory_read(args: dict) -> str:
        try:
            return read(role_id, str(args.get("file") or ""))
        except PotError as exc:
            return f"ERROR: {exc}"

    return {"pot_memory_write": pot_memory_write, "pot_memory_read": pot_memory_read}


def bound(role_id: str) -> dict[str, BoundTool]:
    """The memory tools as agent-bound tools (every resident role gets them)."""
    from pot.agent import BoundTool  # noqa: PLC0415 (deferred: agent imports mem)

    return {
        name: BoundTool(schema=SCHEMAS[name], fn=fn) for name, fn in make_tools(role_id).items()
    }
