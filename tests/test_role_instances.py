"""Role instances (裁决 33): per-instance WIP, maxInstances as a privilege."""

import pytest

from pot.errors import PotError
from pot.roles import Actor, RoleRepo


def test_wip_counts_per_instance(repo, board):
    """一个实例满 wip 不挡另一个实例（裁决 33：wip 按实例计）。"""
    repo.create({"id": "exec", "wip": 1, "canClaim": ["coding"]}, creator="human")
    c1 = board.human_create(title="a", labels=["coding"])
    c2 = board.human_create(title="b", labels=["coding"])
    a = Actor("exec", "s1")
    b = Actor("exec", "s2")

    board.claim(a, c1["id"], c1["ifVersion"])
    with pytest.raises(PotError, match="wip_full"):
        board.claim(a, c2["id"], c2["ifVersion"])  # same instance: full
    ok = board.claim(b, c2["id"], c2["ifVersion"])  # second instance: own slot
    assert ok["holder"] == "exec:s2"


def test_max_instances_is_human_only(tmp_path):
    """maxInstances 进 _PRIVILEGED：Planner 不能自选，只能从模板继承。"""
    repo = RoleRepo(tmp_path / "roles")
    repo.create({"id": "tpl", "isTemplate": True, "wip": 1, "maxInstances": 2}, "human")

    with pytest.raises(PotError, match="planner_no_privilege"):
        repo.create({"id": "greedy", "template": "tpl", "maxInstances": 9}, "planner")
    derived = repo.create({"id": "derived", "template": "tpl"}, "planner")
    assert derived.maxInstances == 2

    with pytest.raises(PotError, match="bad_value"):
        repo.create({"id": "zero", "maxInstances": 0}, "human")


def test_default_max_instances_is_three(tmp_path):
    repo = RoleRepo(tmp_path / "roles")
    role = repo.create({"id": "plain"}, "human")
    assert role.maxInstances == 3
    assert role.to_dict()["maxInstances"] == 3
