"""Dispatch (M2b): role-session mounting and claimable-card walking (spec §3.3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pot import dispatch, session
from pot.board import Board
from pot.roles import Actor, RoleRepo


@pytest.fixture()
def env(tmp_path, monkeypatch) -> SimpleNamespace:
    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path / "sessions")
    roles = RoleRepo(tmp_path / "roles")
    roles.create({"id": "exec", "name": "执行者", "canClaim": ["coding"], "wip": 1}, "human")
    roles.create({"id": "docs", "name": "写手", "canClaim": ["docs"]}, "human")
    board = Board(tmp_path / "board.sqlite", roles)
    dispatch.reset_for_tests(roles=roles, board_obj=board)
    yield SimpleNamespace(roles=roles, board=board)
    dispatch.reset_for_tests()


def _card(env, **kw) -> dict:
    return env.board.human_create(kw.pop("title", "task"), **kw)


def _recorder() -> tuple[list, object]:
    calls: list[tuple[str, str]] = []

    def run_turn(sid: str, msg: str) -> None:
        calls.append((sid, msg))

    return calls, run_turn


# ---- mounting ----


def test_role_session_mounts_once_and_carries_the_role_key(env):
    role = env.roles.get("exec")
    first = dispatch.role_session(role)
    second = dispatch.role_session(role)
    assert first == second
    stored = session.load_session(first)
    assert stored is not None and stored.get("role") == "exec"
    assert stored["title"] == "执行者"


# ---- eligibility mirror ----


def test_eligible_mirrors_claim_gates():
    from pot.roles import Role

    exec_role = Role(id="exec", canClaim=["coding"], wip=1)
    assert dispatch.eligible(exec_role, {"labels": ["coding"]}, held=0)
    assert not dispatch.eligible(exec_role, {"labels": ["docs"]}, held=0)  # label gate
    assert not dispatch.eligible(exec_role, {"labels": ["coding"]}, held=1)  # wip gate
    assert not dispatch.eligible(exec_role, {"labels": ["coding"], "role": "docs"}, held=0)
    barred = Role(id="planner", canClaim=False, canCreateCard=True)
    assert not dispatch.eligible(barred, {"labels": []}, held=0)


# ---- the walk ----


def test_dispatch_runs_one_turn_in_the_matching_role_session(env):
    _card(env, title="code it", labels=["coding"])
    calls, run_turn = _recorder()
    ran = dispatch.dispatch_pending(run_turn)
    assert ran == 1
    sid, msg = calls[0]
    assert session.load_session(sid)["role"] == "exec"  # woke the coding role
    assert "code it" in msg and "[board]" in msg


def test_dispatch_skips_cards_no_role_may_take(env):
    _card(env, title="nobody's", labels=["unclaimable"])
    calls, run_turn = _recorder()
    assert dispatch.dispatch_pending(run_turn) == 0
    assert calls == []


def test_card_specific_role_is_preferred(env):
    env.roles.create({"id": "coder2", "name": "C2", "canClaim": ["coding"]}, "human")
    _card(env, title="pick me", labels=["coding"], role="coder2")
    calls, run_turn = _recorder()
    assert dispatch.dispatch_pending(run_turn) == 1
    assert session.load_session(calls[0][0])["role"] == "coder2"


def test_wip_full_role_is_skipped(env):
    held = _card(env, title="already doing", labels=["coding"])
    actor = Actor("exec", "other-session")
    env.board.claim(actor, held["id"], held["ifVersion"])  # exec now holds 1/1
    _card(env, title="second", labels=["coding"])
    calls, run_turn = _recorder()
    assert dispatch.dispatch_pending(run_turn) == 0
    assert calls == []


def test_each_card_dispatched_once_per_cycle_even_if_the_role_no_ops(env):
    _card(env, title="stubborn", labels=["coding"])
    calls, run_turn = _recorder()  # the recorder never claims the card
    assert dispatch.dispatch_pending(run_turn) == 1  # bounded: one wake, no loop
    assert len(calls) == 1


def test_dispatch_is_a_no_op_on_an_empty_board(env):
    calls, run_turn = _recorder()
    assert dispatch.dispatch_pending(run_turn) == 0
    assert calls == []


# ---- review notification (spec §3.3) ----


def test_cards_in_review_tracks_the_column(env):
    card = _card(env, title="wip", labels=["coding"])
    actor = Actor("exec", "s1")
    held = env.board.claim(actor, card["id"], card["ifVersion"])
    env.board.move(actor, card["id"], "review", held["ifVersion"])
    assert dispatch.cards_in_review() == {card["id"]}
    assert dispatch.cards_in_review() - {card["id"]} == set()  # set semantics


def test_review_route_gates_on_a_live_role_less_source(env):
    """裁决 31: only the conversation that dispatched the card gets it back."""
    env.roles.create(
        {"id": "chat", "name": "Chat", "canCreateCard": True, "canClaim": False}, "human"
    )
    session.save_session("chat-1", "chat", [{"role": "user", "content": "hi"}])
    exec_sid = dispatch.role_session(env.roles.get("exec"))  # a role session: never a target

    routed = dispatch.review_route(
        [
            env.board.create(Actor("chat", "chat-1"), "real task"),
            env.board.create(Actor("chat", "gone"), "orphan"),  # source deleted
            env.board.create(Actor("chat", exec_sid), "role-made"),
            env.board.human_create("seed card"),  # human cards carry no source
        ]
    )
    assert list(routed) == ["chat-1"]
    assert [c["title"] for c in routed["chat-1"]] == ["real task"]


def test_review_block_is_the_report_without_the_chatter():
    cards = [
        {
            "id": "p-1",
            "title": "the task",
            "priority": "urgent",
            "role": "executor",
            "report": {"summary": "shipped it"},
        }
    ]
    zh = dispatch.review_block(cards)
    assert "p-1" in zh and "the task" in zh and "shipped it" in zh and "urgent" in zh
    assert "[card review]" not in zh and "This note is for you" not in zh
    en = dispatch.review_block(cards, lang="en")
    assert "Card ready for review" in en and "shipped it" in en


def test_create_stamps_the_dispatching_session_as_source(env):
    """裁决 31: source is what makes 「you dispatched」 true later."""
    env.roles.create(
        {"id": "chat", "name": "Chat", "canCreateCard": True, "canClaim": False}, "human"
    )
    session.save_session("chat-1", "chat", [{"role": "user", "content": "hi"}])
    assert env.board.create(Actor("chat", "chat-1"), "task")["source"] == "chat-1"
    assert env.board.human_create("human card")["source"] is None


# ---- default singleton seeds the system Planner role ----


def test_default_roles_repo_seeds_planner(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch, "ROLES_DIR", tmp_path / "roles")
    monkeypatch.setattr(dispatch, "_SINGLETONS", {})
    planner = dispatch.roles_repo().get("planner")
    assert planner.canCreateCard is True
    assert planner.canClaim is False  # 派活不抢活 (spec §3.3)
    assert planner.createdBy == "human"
