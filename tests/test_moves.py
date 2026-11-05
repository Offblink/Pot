"""Transition rules beyond the seven gates: who may move what (spec §3.2/§3.5)."""

import pytest

from pot.errors import PotError
from pot.roles import Actor


def test_unheld_move_needs_claim_first(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    with pytest.raises(PotError, match="not_holder"):
        board.move(Actor("r1", "s1"), c["id"], "blocked", c["ifVersion"])


def test_third_party_move_blocked(repo, board):
    repo.create({"id": "r1"}, creator="human")
    repo.create({"id": "r2"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    with pytest.raises(PotError, match="already_held"):
        board.move(Actor("r2", "s1"), c["id"], "blocked", claimed["ifVersion"])


def test_blocked_roundtrip_by_holder(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    blocked = board.move(Actor("r1", "s1"), c["id"], "blocked", claimed["ifVersion"])
    resumed = board.move(Actor("r1", "s1"), c["id"], "doing", blocked["ifVersion"])
    assert resumed["status"] == "doing"
    assert resumed["leaseUntil"] is not None  # 回 doing 重新起租


def test_claim_only_from_todo(repo, board):
    """backlog 退役（裁决 32）：human_create 拒绝非 todo 状态。"""
    repo.create({"id": "r1"}, creator="human")
    with pytest.raises(PotError, match="bad_status"):
        board.human_create(title="a", status="backlog")


def test_human_delete_soft(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    board.human_delete(c["id"], c["ifVersion"])
    assert board.get(c["id"])["deleted"] is True
    assert all(x["id"] != c["id"] for x in board.list())
    assert any(x["id"] == c["id"] for x in board.list(include_deleted=True))


def test_reassign_is_planner_only_and_returns_to_todo(repo, board):
    """裁决 34: only the planner re-routes a live card; reason lands in comments."""
    repo.create({"id": "r1"}, creator="human")
    repo.create({"id": "r2"}, creator="human")
    repo.create({"id": "planner", "canCreateCard": True, "canClaim": False}, creator="human")
    c = board.human_create(title="a", role="r1")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    blocked = board.move(Actor("r1", "s1"), c["id"], "blocked", claimed["ifVersion"])

    with pytest.raises(PotError, match="planner_only"):
        board.reassign(Actor("r1", "s1"), c["id"], "r2", "换人", blocked["ifVersion"])
    with pytest.raises(PotError, match="need_reason"):
        board.reassign(Actor("planner", "p1"), c["id"], "r2", "", blocked["ifVersion"])

    moved = board.reassign(
        Actor("planner", "p1"), c["id"], "r2", "r1 卡住，换 r2", blocked["ifVersion"]
    )
    assert moved["status"] == "todo"
    assert moved["holder"] is None and moved["role"] == "r2"
    assert any("换 r2" in cm["text"] for cm in moved["comments"])
    with pytest.raises(PotError, match="no_such_role"):
        board.reassign(Actor("planner", "p1"), c["id"], "ghost", "x", moved["ifVersion"])


def test_reassign_refuses_done(repo, board):
    """done 只能被重开（人），不能被改派搅动。"""
    repo.create({"id": "r1"}, creator="human")
    repo.create({"id": "planner", "canCreateCard": True, "canClaim": False}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    done = board.report(Actor("r1", "s1"), c["id"], "shipped", claimed["ifVersion"])
    with pytest.raises(PotError, match="bad_transition"):
        board.reassign(Actor("planner", "p1"), c["id"], None, "x", done["ifVersion"])


def test_release_needs_reason(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    with pytest.raises(PotError, match="need_reason"):
        board.release(Actor("r1", "s1"), c["id"], "", claimed["ifVersion"])
