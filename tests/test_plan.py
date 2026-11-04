"""Plan todo tool (spec 裁决 17): full-replace semantics + flip detection for the strikethrough animation."""

import inspect
import json

from pot.plan import TODO_SCHEMA, PlanStore, make_todo_tool


def test_full_replace_and_flip_detection(tmp_path):
    tool = make_todo_tool(PlanStore(tmp_path / "plans"), "sess-1")
    first = json.loads(tool(items=[{"text": "a", "done": False}, {"text": "b", "done": False}]))
    assert first["flipped"] == []

    second = json.loads(tool(items=[{"text": "a", "done": True}, {"text": "b", "done": False}]))
    assert second["flipped"] == ["a"]

    # 同状态重发 = 幂等，不再翻转
    third = json.loads(tool(items=[{"text": "a", "done": True}, {"text": "b", "done": False}]))
    assert third["flipped"] == []


def test_persistence_across_instances(tmp_path):
    make_todo_tool(PlanStore(tmp_path / "plans"), "s1")(items=[{"text": "x", "done": True}])
    assert PlanStore(tmp_path / "plans").get("s1") == [{"text": "x", "done": True}]


def test_bad_items_rejected(tmp_path):
    tool = make_todo_tool(PlanStore(tmp_path / "plans"), "s1")
    assert tool(items=[{"text": "", "done": False}]).startswith("ERROR: bad_item")
    assert tool(items=[{"text": "x"}]).startswith("ERROR: bad_item")
    assert tool(items=[{"text": "x", "done": "yes"}]).startswith("ERROR: bad_item")


def test_schema_matches_tool_signature(tmp_path):
    tool = make_todo_tool(PlanStore(tmp_path / "plans"), "s1")
    required = TODO_SCHEMA["function"]["parameters"].get("required", [])
    assert set(required) <= set(inspect.signature(tool).parameters)
