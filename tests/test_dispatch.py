"""Dispatch (M2b): role-session mounting and claimable-card walking (spec §3.3)."""

from __future__ import annotations

import threading
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


def test_instances_are_numbered_and_reused(env):
    """裁决 33: one instance = one numbered session; role_session = the first."""
    role = env.roles.get("exec")
    first = dispatch.role_session(role)
    second = dispatch.ensure_instance(role)
    assert second != first
    assert int(session.load_session(first).get("instance") or 1) == 1
    assert session.load_session(second)["instance"] == 2
    assert [str(r["id"]) for r in dispatch.role_instances(role)] == [first, second]
    assert dispatch.role_session(role) == first  # stable handle, no third mount


def test_dispatch_grows_instances_up_to_max(env):
    """裁决 33: full instances trigger growth until maxInstances, then wait."""
    env.roles.create(
        {"id": "bot", "name": "Bot", "canClaim": ["special"], "wip": 1, "maxInstances": 2},
        "human",
    )
    for title in ("a", "b", "c"):
        _card(env, title=title, labels=["special"])

    calls: list[tuple[str, str]] = []

    def claiming_wake(sid: str, msg: str) -> None:
        calls.append((sid, msg))
        card_id = msg.split(": ", 1)[1].split(" ", 1)[0]
        card = env.board.get(card_id)
        actor = Actor(session.load_session(sid)["role"], sid)
        env.board.claim(actor, card["id"], card["ifVersion"])

    assert dispatch.dispatch_pending(claiming_wake) == 2  # cap: 2 instances × wip 1
    sids = {sid for sid, _ in calls}
    assert len(sids) == 2
    assert sorted(int(session.load_session(sid)["instance"]) for sid in sids) == [1, 2]
    assert len(env.board.list(status="todo")) == 1  # the third card waits its turn


def test_dispatch_wave_runs_instances_concurrently(env):
    """裁决 39: two claimable cards reach two DIFFERENT instances in the same
    wave — the barrier only trips with both turns in flight together, so a
    serial dispatcher would time out and fail the assertions below."""
    env.roles.create(
        {"id": "bot", "name": "Bot", "canClaim": ["special"], "wip": 1, "maxInstances": 3},
        "human",
    )
    _card(env, title="a", labels=["special"])
    _card(env, title="b", labels=["special"])
    barrier = threading.Barrier(2, timeout=10)
    calls: list[tuple[str, str]] = []

    def run_turn(sid: str, msg: str) -> None:
        calls.append((sid, msg))
        barrier.wait()  # both turns must be running simultaneously to pass

    assert dispatch.dispatch_pending(run_turn) == 2
    assert len(calls) == 2
    assert len({sid for sid, _ in calls}) == 2  # one instance per card, not #1 twice


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


def test_instances_at_cap_with_full_wip_are_skipped(env):
    """裁决 33: growth has a ceiling — a capped, saturated role is skipped."""
    env.roles.create(
        {"id": "solo", "name": "Solo", "canClaim": ["solo-label"], "wip": 1, "maxInstances": 1},
        "human",
    )
    sid = dispatch.ensure_instance(env.roles.get("solo"))
    held = _card(env, title="already doing", labels=["solo-label"])
    env.board.claim(Actor("solo", sid), held["id"], held["ifVersion"])  # 1/1, cap reached
    _card(env, title="second", labels=["solo-label"])
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


def test_cards_done_tracks_completed(env):
    card = _card(env, title="wip", labels=["coding"])
    actor = Actor("exec", "s1")
    held = env.board.claim(actor, card["id"], card["ifVersion"])
    env.board.report(actor, card["id"], "shipped", held["ifVersion"])
    assert dispatch.cards_done() == {card["id"]}
    assert dispatch.cards_done() - {card["id"]} == set()  # set semantics


def test_done_route_gates_on_a_live_role_less_source(env):
    """裁决 31: only the conversation that dispatched the card gets it back."""
    env.roles.create(
        {"id": "chat", "name": "Chat", "canCreateCard": True, "canClaim": False}, "human"
    )
    session.save_session("chat-1", "chat", [{"role": "user", "content": "hi"}])
    exec_sid = dispatch.role_session(env.roles.get("exec"))  # a role session: never a target

    routed = dispatch.notify_route(
        [
            env.board.create(Actor("chat", "chat-1"), "real task"),
            env.board.create(Actor("chat", "gone"), "orphan"),  # source deleted
            env.board.create(Actor("chat", exec_sid), "role-made"),
            env.board.human_create("seed card"),  # human cards carry no source
        ]
    )
    assert list(routed) == ["chat-1"]
    assert [c["title"] for c in routed["chat-1"]] == ["real task"]


def test_done_block_is_the_report_without_the_chatter():
    cards = [
        {
            "id": "p-1",
            "title": "the task",
            "priority": "urgent",
            "role": "executor",
            "report": {"summary": "shipped it"},
        }
    ]
    zh = dispatch.done_block(cards)
    assert "p-1" in zh and "the task" in zh and "shipped it" in zh and "urgent" in zh
    assert "[card review]" not in zh and "This note is for you" not in zh
    en = dispatch.done_block(cards, lang="en")
    assert "Card completed" in en and "shipped it" in en


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


def test_builtin_roles_seed_edit_sticks_and_delete_reseeds(tmp_path, monkeypatch):
    """裁决 41: the built-in division of labor seeds beside the Planner —
    five roles on a fresh dir, a human edit survives, a delete re-seeds."""
    monkeypatch.setattr(dispatch, "ROLES_DIR", tmp_path / "roles")
    monkeypatch.setattr(dispatch, "_SINGLETONS", {})
    repo = dispatch.roles_repo()

    ids = {r.id for r in repo.list()}
    assert {"planner", "executor", "writer", "tester", "researcher", "reviewer"} <= ids
    ex = repo.get("executor")
    assert ex.canClaim == ["全部", "coding"] and ex.wip == 1 and ex.canCreateCard is False
    assert repo.get("writer").canClaim == ["docs"]
    assert repo.get("tester").canClaim == ["test"]
    assert repo.get("researcher").tools == ["web", "search", "files"]
    assert repo.get("reviewer").canClaim == ["review"]
    assert all(not r.isTemplate and r.createdBy == "human" for r in repo.list())

    # a human edit sticks: seeding is if-missing, never an overwrite
    repo.update("writer", {"mission": "hand-edited"}, creator="human")
    monkeypatch.setattr(dispatch, "_SINGLETONS", {})
    assert dispatch.roles_repo().get("writer").mission == "hand-edited"

    # a delete re-seeds on the next start (the Planner's semantics)
    (tmp_path / "roles" / "writer.json").unlink()
    monkeypatch.setattr(dispatch, "_SINGLETONS", {})
    assert dispatch.roles_repo().get("writer").mission != "hand-edited"
