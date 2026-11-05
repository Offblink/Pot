"""裁决 30/31: a review card block is host-written into the dispatching
conversation — no model turn, no `[card review]` note, and no chat anywhere
else (human/seed cards stay board-only)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pot import dispatch, session
from pot import server as webui
from pot.board import Board
from pot.roles import Actor, RoleRepo


@pytest.fixture()
def env(tmp_path, monkeypatch) -> SimpleNamespace:
    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path / "sessions")
    roles = RoleRepo(tmp_path / "roles")
    roles.create({"id": "chat", "name": "Chat", "canCreateCard": True, "canClaim": False}, "human")
    board = Board(tmp_path / "board.sqlite", roles)
    dispatch.reset_for_tests(roles=roles, board_obj=board)
    webui.clear_alerts()
    yield SimpleNamespace(roles=roles, board=board)
    dispatch.reset_for_tests()
    webui.clear_alerts()


def _card(card_id: str = "p-1", title: str = "the task") -> dict:
    return {
        "id": card_id,
        "title": title,
        "priority": "urgent",
        "role": "executor",
        "report": {"summary": "shipped it"},
    }


def test_deliver_appends_the_block_and_rings_the_card_alert(env):
    session.save_session("chat-1", "my chat", [{"role": "user", "content": "ship it"}])

    webui.deliver_card_block("chat-1", [_card()])

    data = session.load_session("chat-1")
    assert data["title"] == "my chat"  # the save must not rename what it inherits
    last = data["messages"][-1]
    assert last["role"] == "assistant"
    assert "p-1" in last["content"] and "the task" in last["content"]
    assert "shipped it" in last["content"]
    assert "[card review]" not in last["content"]  # 裁决 30: no internal note, ever
    assert webui.session_alerts().get("chat-1") == "card"


def test_deliver_to_a_deleted_session_is_silent(env):
    webui.deliver_card_block("gone", [_card()])
    assert session.load_session("gone") is None
    assert webui.session_alerts() == {}


def test_after_turn_delivers_fresh_review_only_to_its_source(env, monkeypatch):
    session.save_session("chat-1", "my chat", [{"role": "user", "content": "ship it"}])
    card = env.board.create(Actor("chat", "chat-1"), "real task")
    human = env.board.human_create("seed card")
    snapshots = iter([set(), {card["id"], human["id"]}])  # before, then after
    monkeypatch.setattr(webui.dispatch, "cards_in_review", lambda: next(snapshots))
    monkeypatch.setattr(webui.dispatch, "dispatch_pending", lambda run: 0)
    monkeypatch.setattr(webui.jobs, "flush", lambda sid: [])
    monkeypatch.setattr(
        webui, "host_turn", lambda *a, **k: pytest.fail("a card block must not wake the model")
    )

    webui._after_turn("executor-sid", aborted=False)

    # _after_turn re-reads the cards from the board, so assert on what the
    # routing guarantees: the source conversation got a block naming ITS card
    # (report content itself is covered by the deliver test above), and the
    # human/seed card never appears anywhere.
    data = session.load_session("chat-1")
    block = data["messages"][-1]["content"]
    assert data["messages"][-1]["role"] == "assistant"
    assert card["id"] in block and "real task" in block
    assert human["id"] not in block  # 裁决 31: the human/seed card is board-only
    assert webui.session_alerts().get("chat-1") == "card"
