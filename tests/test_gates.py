"""Seven code-level gates, one test each (spec §3.2). M1 acceptance: red → green."""

import pytest

from pot.board import Board
from pot.errors import PotError
from pot.roles import Actor


def _card(board, **kw):
    kw.setdefault("title", "任务")
    kw.setdefault("labels", ["coding"])
    return board.human_create(**kw)


def test_gate_role_match(repo, board):
    """闸 1 角色匹配：labels ⊆ canClaim、card.role 钉住、canClaim=false 全拒。"""
    repo.create({"id": "exec", "canClaim": ["coding"]}, creator="human")
    repo.create({"id": "coder", "canClaim": ["coding"]}, creator="human")
    repo.create({"id": "planner", "canClaim": False, "canCreateCard": True}, creator="human")

    # (a) labels 不在 canClaim 里
    a = _card(board, title="a", labels=["ui"])
    with pytest.raises(PotError, match="role_mismatch"):
        board.claim(Actor("exec", "s1"), a["id"], a["ifVersion"])

    # (b) card.role 钉了别的角色
    b = _card(board, title="b", role="exec")
    with pytest.raises(PotError, match="role_mismatch"):
        board.claim(Actor("coder", "s1"), b["id"], b["ifVersion"])

    # (c) canClaim=false 永远不能认领
    c = _card(board, title="c")
    with pytest.raises(PotError, match="role_mismatch"):
        board.claim(Actor("planner", "s1"), c["id"], c["ifVersion"])

    # (d) 匹配的认领通过；失败的认领不改版本
    ok = board.claim(Actor("exec", "s1"), c["id"], c["ifVersion"])
    assert ok["holder"] == "exec:s1"
    assert ok["ifVersion"] == c["ifVersion"] + 1


def test_gate_wip(repo, board):
    """闸 2 WIP：持有数 < wip 才能再抢。"""
    repo.create({"id": "worker", "wip": 1}, creator="human")
    a = _card(board, title="a")
    b = _card(board, title="b")
    board.claim(Actor("worker", "s1"), a["id"], a["ifVersion"])
    with pytest.raises(PotError, match="wip_full"):
        board.claim(Actor("worker", "s1"), b["id"], b["ifVersion"])


def test_gate_holder_protected(repo, board):
    """闸 3 持有保护：第三方不可抢；持有者自己续认领 = 续租。"""
    repo.create({"id": "r1"}, creator="human")
    repo.create({"id": "r2"}, creator="human")
    c = _card(board)
    board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    fresh = board.get(c["id"])

    with pytest.raises(PotError, match="already_held"):
        board.claim(Actor("r2", "s1"), c["id"], fresh["ifVersion"])

    renewed = board.claim(Actor("r1", "s1"), c["id"], fresh["ifVersion"])
    assert renewed["holder"] == "r1:s1"
    assert renewed["ifVersion"] == fresh["ifVersion"] + 1


def test_gate_stale_version(repo, board):
    """闸 4 乐观锁：ifVersion 不匹配拒绝一切写。"""
    repo.create({"id": "r1"}, creator="human")
    c = _card(board)
    with pytest.raises(PotError, match="stale_version"):
        board.claim(Actor("r1", "s1"), c["id"], 42)
    with pytest.raises(PotError, match="stale_version"):
        board.comment(Actor("r1", "s1"), c["id"], "ping", 42)
    with pytest.raises(PotError, match="stale_version"):
        board.human_complete(c["id"], 42)


def test_gate_done_human_only(repo, board):
    """闸 5 done 闸：agent 永远到不了 done，只能 → review；✓ 是人的。"""
    repo.create({"id": "r1"}, creator="human")
    c = _card(board)
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    with pytest.raises(PotError, match="human_only"):
        board.move(Actor("r1", "s1"), c["id"], "done", claimed["ifVersion"])

    review = board.move(Actor("r1", "s1"), c["id"], "review", claimed["ifVersion"])
    done = board.human_complete(c["id"], review["ifVersion"])
    assert done["status"] == "done"
    assert done["holder"] is None
    assert done["leaseUntil"] is None


def test_gate_reject(repo, board):
    """闸 6 退回：人 ✗ 回 todo、清 holder、原因进卡。"""
    repo.create({"id": "r1"}, creator="human")
    c = _card(board)
    claimed = board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])
    review = board.move(Actor("r1", "s1"), c["id"], "review", claimed["ifVersion"])

    with pytest.raises(PotError, match="need_reason"):
        board.human_reject(c["id"], "", review["ifVersion"])

    back = board.human_reject(c["id"], "验收不过，重做", review["ifVersion"])
    assert back["status"] == "todo"
    assert back["holder"] is None
    assert any("验收不过" in cm["text"] for cm in back["comments"])


def test_gate_lease(repo, tmp_path):
    """闸 7 租约：超时自动回 todo、清 holder、评论留痕。"""
    board = Board(tmp_path / "board.sqlite", repo, lease_seconds=0)
    repo.create({"id": "r1"}, creator="human")
    c = _card(board)
    board.claim(Actor("r1", "s1"), c["id"], c["ifVersion"])

    after = board.get(c["id"])  # lease_seconds=0 → 下一次操作即扫到过期
    assert after["status"] == "todo"
    assert after["holder"] is None
    assert any("租约" in cm["text"] for cm in after["comments"])
    assert after["ifVersion"] > c["ifVersion"]
