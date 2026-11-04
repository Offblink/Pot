"""Human board routes (spec §3.5): GET /board, /board/complete, /board/reject,
plus the new /jobs and re-armed /background-tool shapes. Loopback server, no
network beyond 127.0.0.1."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from pot.board import Board
from pot.roles import Actor, RoleRepo
from pot.server import WebUIRuntime, make_webui_server


@pytest.fixture()
def host(tmp_path):
    roles = RoleRepo(tmp_path / "roles")
    roles.create({"id": "exec", "name": "执行者"}, "human")
    # The system Planner role the default repo seeds (dispatch.roles_repo);
    # seeded here so /board's role listing can be asserted against a tmp repo.
    roles.create(
        {"id": "planner", "canCreateCard": True, "canClaim": False, "isTemplate": False},
        "human",
    )
    board = Board(tmp_path / "board.sqlite", roles)
    runtime = WebUIRuntime(board=board, roles=roles)
    server = make_webui_server(0, runtime)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield SimpleNamespace(base=base, board=board, roles=roles)
    server.shutdown()
    server.server_close()


def _json(method: str, path: str, obj: dict | None = None, base: str = "") -> tuple[int, dict]:
    data = json.dumps(obj or {}).encode()
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _review_card(host) -> dict:
    """A card pushed to review through the real agent-side gates."""
    card = host.board.human_create("ship it", labels=["coding"])
    actor = Actor("exec", "s1")
    held = host.board.claim(actor, card["id"], card["ifVersion"])
    return host.board.move(actor, card["id"], "review", held["ifVersion"])


def test_board_route_lists_cards_and_roles(host):
    host.board.human_create("one", labels=["coding"])
    status, body = _json("GET", "/board", base=host.base)
    assert status == 200
    assert [c["title"] for c in body["cards"]] == ["one"]
    assert body["cards"][0]["ifVersion"] >= 1  # the write token the UI needs
    assert any(r["id"] == "exec" for r in body["roles"])
    assert any(r["id"] == "planner" for r in body["roles"])  # system seed


def test_complete_is_human_only_through_review(host):
    card = _review_card(host)
    status, body = _json(
        "POST",
        "/board/complete",
        {"card_id": card["id"], "if_version": card["ifVersion"]},
        host.base,
    )
    assert status == 200 and body["ok"]
    assert host.board.get(card["id"])["status"] == "done"


def test_complete_rejects_a_stale_version(host):
    card = _review_card(host)
    status, body = _json(
        "POST", "/board/complete", {"card_id": card["id"], "if_version": 999}, host.base
    )
    assert status == 400 and "error" in body
    assert host.board.get(card["id"])["status"] == "review"  # untouched


def test_complete_refuses_a_card_not_in_review(host):
    card = host.board.human_create("still todo")
    status, _body = _json(
        "POST",
        "/board/complete",
        {"card_id": card["id"], "if_version": card["ifVersion"]},
        host.base,
    )
    assert status == 400
    assert host.board.get(card["id"])["status"] == "todo"


def test_reject_returns_to_todo_with_the_reason_in_comments(host):
    card = _review_card(host)
    status, body = _json(
        "POST",
        "/board/reject",
        {"card_id": card["id"], "if_version": card["ifVersion"], "reason": "needs tests"},
        host.base,
    )
    assert status == 200 and body["ok"]
    stored = host.board.get(card["id"])
    assert stored["status"] == "todo"
    assert stored["holder"] is None
    assert any(c["by"] == "human" and c["text"] == "needs tests" for c in stored["comments"])


def test_reject_needs_a_reason(host):
    card = _review_card(host)
    status, _body = _json(
        "POST",
        "/board/reject",
        {"card_id": card["id"], "if_version": card["ifVersion"], "reason": "  "},
        host.base,
    )
    assert status == 400
    assert host.board.get(card["id"])["status"] == "review"


def test_jobs_route_answers_empty_without_a_turn(host):
    status, body = _json("GET", "/jobs?sessionId=nope", base=host.base)
    assert status == 200 and body == {"jobs": []}


def test_background_tool_arms_only_when_a_turn_is_running(host):
    # No turn → no detach event for that session → ok:false (the button is a
    # no-op rather than a lie).
    status, body = _json("POST", "/background-tool", {"sessionId": "ghost"}, host.base)
    assert status == 200 and body == {"ok": False}
