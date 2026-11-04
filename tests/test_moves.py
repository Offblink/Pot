"""Transition rules beyond the seven gates: who may move what (spec §3.2/§3.5)."""

import pytest

from pot.errors import PotError
from pot.roles import Actor


def test_unheld_move_needs_claim_first(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    with pytest.raises(PotError, match="not_holder"):
        board.move(Actor("r1", "s1"), c["id"], "review", c["ifVersion"])


def test_third_party_move_blocked(repo, board):
    repo.create({"id": "r1"}, creator="human")
    repo.create({"id": "r2"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    with pytest.raises(PotError, match="already_held"):
        board.move(Actor("r2", "s1"), c["id"], "review", claimed["ifVersion"])


def test_backlog_promotion_needs_planning_privilege(repo, board):
    """推进待规划 → 待办是规划特权（canCreateCard）。"""
    repo.create({"id": "worker"}, creator="human")
    repo.create({"id": "planner", "canCreateCard": True}, creator="human")
    c = board.human_create(title="idea", status="backlog")

    with pytest.raises(PotError, match="cant_create"):
        board.move(Actor("worker", "s1"), c["id"], "todo", c["ifVersion"])
    ok = board.move(Actor("planner", "s1"), c["id"], "todo", c["ifVersion"])
    assert ok["status"] == "todo"


def test_blocked_roundtrip_by_holder(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    blocked = board.move(Actor("r1", "s1"), c["id"], "blocked", claimed["ifVersion"])
    resumed = board.move(Actor("r1", "s1"), c["id"], "doing", blocked["ifVersion"])
    assert resumed["status"] == "doing"
    assert resumed["leaseUntil"] is not None  # 回 doing 重新起租


def test_claim_only_from_todo(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a", status="backlog")
    with pytest.raises(PotError, match="bad_status"):
        board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])


def test_human_assign_unheld_only(repo, board):
    repo.create({"id": "r1"}, creator="human")
    repo.create({"id": "r2"}, creator="human")
    c = board.human_create(title="a", role="r1")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])

    with pytest.raises(PotError, match="already_held"):
        board.human_assign(c["id"], "r2", claimed["ifVersion"])

    back = board.human_reject(c["id"], "改派", claimed["ifVersion"])
    assigned = board.human_assign(c["id"], "r2", back["ifVersion"])
    assert assigned["role"] == "r2"
    with pytest.raises(PotError, match="no_such_role"):
        board.human_assign(c["id"], "ghost", assigned["ifVersion"])


def test_human_delete_soft(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    board.human_delete(c["id"], c["ifVersion"])
    assert board.get(c["id"])["deleted"] is True
    assert all(x["id"] != c["id"] for x in board.list())
    assert any(x["id"] == c["id"] for x in board.list(include_deleted=True))


def test_human_renew_lease(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    renewed = board.human_renew_lease(c["id"], claimed["ifVersion"])
    assert renewed["leaseUntil"] >= claimed["leaseUntil"]

    free = board.human_create(title="b")
    with pytest.raises(PotError, match="no_holder"):
        board.human_renew_lease(free["id"], free["ifVersion"])


def test_release_needs_reason(repo, board):
    repo.create({"id": "r1"}, creator="human")
    c = board.human_create(title="a")
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    with pytest.raises(PotError, match="need_reason"):
        board.release(Actor("r1", "s1"), c["id"], "", claimed["ifVersion"])
