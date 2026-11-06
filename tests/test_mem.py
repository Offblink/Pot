"""Role memory + the bounded role-wake context (裁决 43).

Covers both halves of the incident: summaries are index-only (no size
budget), and a role wake re-feeds ZERO transcript rows — while storage
keeps the full history.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from conftest import WebUIHost

from pot import dispatch as dispatch_mod
from pot import mem
from pot import server as server_mod
from pot import session as session_mod
from pot.board import Board
from pot.errors import PotError
from pot.llm import LLMResult
from pot.roles import RoleRepo


@pytest.fixture()
def memdir(tmp_path, monkeypatch):
    monkeypatch.setattr(mem, "MEM_DIR", tmp_path / "mem")
    return tmp_path / "mem"


# ---- summaries: write / read / index ----


def test_write_then_read_roundtrip(memdir):
    name = mem.write("exec", "# 采集配方\nEdge headless 3x renders the page.")
    assert (memdir / "exec" / name).is_file()
    assert "Edge headless" in mem.read("exec", name)


def test_write_rejects_empty_and_oversize(memdir):
    with pytest.raises(PotError, match="bad_value"):
        mem.write("exec", "   \n ")
    with pytest.raises(PotError, match="bad_value"):
        mem.write("exec", "x" * (mem.MAX_SUMMARY_BYTES + 1))
    assert list(memdir.glob("**/*.md")) == []  # nothing landed


def test_read_rejects_traversal_and_missing(memdir):
    with pytest.raises(PotError, match="bad_value"):
        mem.read("exec", "../../roles/executor.json")
    with pytest.raises(PotError, match="no_such_memory"):
        mem.read("exec", "20261106-000000-dead.md")


def test_index_is_newest_first_titles_only(memdir):
    import os
    import time

    old = mem.write("exec", "# 旧结论\nthe very old lesson")
    time.sleep(0.02)
    new = mem.write("exec", "# 新结论\nthe freshest lesson")
    # mtime decides the order (same-second writes stay unambiguous)
    os.utime(memdir / "exec" / old, (1_000_000_000, 1_000_000_000))
    section = mem.index_section("exec")
    assert "memory index" in section and "pot_memory_read" in section
    assert f"- {new}: 新结论" in section and f"- {old}: 旧结论" in section
    assert section.index(new) < section.index(old)  # newest first
    assert "the very old lesson" not in section  # TITLE only, never full text


def test_index_and_recap_absent_when_nothing_there():
    assert mem.index_section("no-such-role") == ""
    assert mem.recap_section([{"role": "user", "content": "hi"}]) == ""


# ---- recap: the previous wake's closing words ----


def test_recap_takes_last_final_text_and_caps():
    rows = [
        {"role": "system", "content": ""},
        {"role": "user", "content": "brief 1"},
        {"role": "assistant", "content": "first closing"},
        {"role": "user", "content": "brief 2"},
        {"role": "assistant", "content": "second closing"},
    ]
    assert "second closing" in mem.recap_section(rows)
    assert "first closing" not in mem.recap_section(rows)

    long = "A" * mem.RECAP_CHARS + "B" * 500
    capped = mem.recap_section([{"role": "assistant", "content": long}])
    assert "A" * mem.RECAP_CHARS in capped  # full head kept
    assert "B" * 500 not in capped  # tail dropped
    assert capped.endswith("…[truncated]")


def test_recap_skips_tool_loops_aborts_errors_and_silence():
    rows = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": "output", "tool_call_id": "1"},
        {"role": "assistant", "content": "(Aborted)"},
        {"role": "assistant", "content": "(LLM error: boom)"},
        {"role": "assistant", "content": "<<SILENT>>"},
        {"role": "assistant", "content": "the real closing"},
    ]
    assert "real closing" in mem.recap_section(rows)

    only_junk = [{"role": "assistant", "content": "<<SILENT>>"}]
    assert mem.recap_section(only_junk) == ""


# ---- the wake itself: bounded model view, full storage ----


class RecorderLLM:
    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    def __call__(self, messages, _tool_defs):
        # snapshot: the live list keeps growing after this call returns
        self.seen.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        return LLMResult(content="done")


def _history() -> list[dict]:
    rows: list[dict] = [{"role": "system", "content": ""}]
    for i in range(30):
        rows.append({"role": "user", "content": f"brief {i}"})
        rows.append({"role": "assistant", "content": f"answer {i}"})
    rows.append({"role": "user", "content": "brief final"})
    rows.append({"role": "assistant", "content": "FINAL: shipped the parser rewrite"})
    return rows


@pytest.fixture()
def room(tmp_path, monkeypatch):
    roles = RoleRepo(tmp_path / "roles")
    roles.create({"id": "exec", "name": "执行者", "canClaim": ["coding"]}, "human")
    board = Board(tmp_path / "board.sqlite", roles)
    dispatch_mod.reset_for_tests(roles=roles, board_obj=board)
    monkeypatch.setattr(mem, "MEM_DIR", tmp_path / "mem")
    rec = RecorderLLM()
    host = WebUIHost.start(session_dir=tmp_path / "sessions", llm=rec)
    try:
        yield SimpleNamespace(host=host, rec=rec)
    finally:
        host.stop()
        dispatch_mod.reset_for_tests()


def test_role_wake_sees_brief_plus_memory_not_the_transcript(room):
    rows = _history()
    session_mod.save_session("exec-1", "执行者", rows, role="exec")
    mem.write("exec", "# 采集配方\nEdge headless 3x renders the page.")

    server_mod.host_turn("exec-1", "[board] A task card is waiting for you")

    seen = room.rec.seen
    assert len(seen) == 1
    model_view = seen[0]
    # bounded: system + this wake's input, ZERO transcript rows
    assert len(model_view) == 2
    assert model_view[1]["content"].startswith("[board]")
    sys_text = model_view[0]["content"]
    assert "pot_memory_write" in sys_text  # the ROLE_SECTION rule
    assert "memory index" in sys_text and "采集配方" in sys_text  # the TITLE line
    assert "Edge headless" not in sys_text  # titles only — full text via pot_memory_read
    assert "Where you left off" in sys_text
    assert "FINAL: shipped the parser rewrite" in sys_text  # previous closing
    assert "brief 0" not in sys_text and "answer 0" not in sys_text  # no replay

    # storage keeps EVERYTHING plus this turn's rows
    stored = session_mod.load_session("exec-1")
    assert len(stored["messages"]) == len(rows) + 2  # + brief + assistant "done"
    assert stored["messages"][1]["content"] == "brief 0"
    assert stored["messages"][-2]["content"].startswith("[board]")
    assert stored["messages"][-1]["content"] == "done"


def test_human_conversation_still_replays_in_full(room):
    rows = _history()
    session_mod.save_session("chat-1", "chat", rows)

    server_mod.host_turn("chat-1", "hello there")

    model_view = room.rec.seen[0]
    assert len(model_view) == len(rows) + 1  # full history + the new message
    assert model_view[-1]["content"] == "hello there"
