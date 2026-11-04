"""pot_board_* tool layer: Fungi dispatch shape (str in/out) + schema contract."""

import inspect
import json

from pot.roles import Actor
from pot.tools import SCHEMAS, make_tools


def _tools(repo, board):
    repo.create({"id": "exec", "wip": 2, "canCreateCard": True}, creator="human")
    return make_tools(board, Actor("exec", "s1"))


def test_full_lifecycle_through_tools(repo, board):
    t = _tools(repo, board)
    created = json.loads(t["pot_board_create"](title="做卡", labels=["coding"], checklist=["跑通"]))
    card = created["card"]
    assert created["ok"] and card["status"] == "todo"

    claimed = json.loads(t["pot_board_claim"](card_id=card["id"], if_version=card["ifVersion"]))
    held = claimed["card"]
    assert held["holder"] == "exec:s1"

    denied = t["pot_board_checklist"](card_id=card["id"], index=0, evidence="", if_version=held["ifVersion"])
    assert denied.startswith("ERROR: need_evidence")

    fresh = json.loads(t["pot_board_get"](card_id=card["id"]))["card"]
    checked = json.loads(
        t["pot_board_checklist"](
            card_id=card["id"], index=0, evidence="pytest green", if_version=fresh["ifVersion"]
        )
    )
    assert checked["card"]["checklist"][0]["done"] is True

    rep = json.loads(
        t["pot_board_report"](card_id=card["id"], summary="完成", if_version=checked["card"]["ifVersion"])
    )
    assert rep["card"]["status"] == "review"

    denied2 = t["pot_board_move"](card_id=card["id"], to="done", if_version=rep["card"]["ifVersion"])
    assert denied2.startswith("ERROR: human_only")

    done = board.human_complete(card["id"], rep["card"]["ifVersion"])
    assert done["status"] == "done"


def test_release_returns_to_todo_with_reason(repo, board):
    t = _tools(repo, board)
    created = json.loads(t["pot_board_create"](title="x"))
    claimed = json.loads(
        t["pot_board_claim"](card_id=created["card"]["id"], if_version=created["card"]["ifVersion"])
    )
    rel = json.loads(
        t["pot_board_release"](
            card_id=created["card"]["id"], reason="等外部依赖", if_version=claimed["card"]["ifVersion"]
        )
    )
    assert rel["card"]["status"] == "todo"
    assert rel["card"]["holder"] is None
    assert any("等外部依赖" in c["text"] for c in rel["card"]["comments"])


def test_create_requires_cancreatecard(repo, board):
    repo.create({"id": "worker"}, creator="human")
    t = make_tools(board, Actor("worker", "s1"))
    assert t["pot_board_create"](title="x").startswith("ERROR: cant_create")


def test_list_filters(repo, board):
    repo.create({"id": "exec", "canClaim": ["coding"], "canCreateCard": True}, creator="human")
    t = make_tools(board, Actor("exec", "s1"))
    json.loads(t["pot_board_create"](title="a", labels=["coding"]))
    json.loads(t["pot_board_create"](title="b", labels=["ui"]))
    coding = json.loads(t["pot_board_list"](status="todo", labels=["coding"]))
    assert [c["title"] for c in coding["cards"]] == ["a"]
    doing = json.loads(t["pot_board_list"](status="doing"))
    assert doing["cards"] == []


def test_schema_matches_tool_signatures(repo, board):
    tools = make_tools(board, Actor("r", "s"))
    assert set(SCHEMAS) == set(tools)
    for name, schema in SCHEMAS.items():
        required = schema["function"]["parameters"].get("required", [])
        assert set(required) <= set(inspect.signature(tools[name]).parameters), name
