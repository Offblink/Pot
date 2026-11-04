"""Role table + templates + the Planner privilege matrix (spec §3.1, 裁决 6)."""

import pytest

from pot.errors import PotError


def test_human_create_full_freedoms(repo):
    r = repo.create(
        {"id": "exec", "name": "执行者", "tools": ["screen"], "wip": 3, "canClaim": ["coding"]},
        creator="human",
    )
    assert r.createdBy == "human"
    assert repo.get("exec").name == "执行者"  # 中文往返


def test_planner_needs_template(repo):
    with pytest.raises(PotError, match="need_template"):
        repo.create({"id": "helper"}, creator="planner")


def test_planner_derives_privileges_from_template(repo):
    repo.create(
        {
            "id": "tpl-worker",
            "isTemplate": True,
            "tools": ["shell", "files"],
            "wip": 3,
            "model": "m1",
        },
        creator="human",
    )
    with pytest.raises(PotError, match="planner_no_privilege"):
        repo.create({"id": "h1", "template": "tpl-worker", "tools": ["screen"]}, creator="planner")

    r = repo.create(
        {"id": "h2", "name": "帮手", "canClaim": ["coding"], "template": "tpl-worker"},
        creator="planner",
    )
    assert r.tools == ["shell", "files"]  # 特权从模板派生，不是 Planner 说的
    assert r.wip == 3
    assert r.model == "m1"
    assert r.canCreateCard is False
    assert r.createdBy == "planner"
    assert r.name == "帮手"  # mission/name/canClaim 是 Planner 自己的领地
    assert r.canClaim == ["coding"]


def test_template_target_must_exist_and_be_template(repo):
    with pytest.raises(PotError, match="template_missing"):
        repo.create({"id": "x", "template": "ghost"}, creator="planner")
    repo.create({"id": "plain"}, creator="human")
    with pytest.raises(PotError, match="not_template"):
        repo.create({"id": "y", "template": "plain"}, creator="planner")
    with pytest.raises(PotError, match="planner_no_privilege"):
        repo.create({"id": "z", "isTemplate": True, "template": "plain"}, creator="planner")


def test_only_human_updates_or_deletes(repo):
    repo.create({"id": "exec"}, creator="human")
    with pytest.raises(PotError, match="human_only"):
        repo.update("exec", {"wip": 5}, creator="planner")
    with pytest.raises(PotError, match="human_only"):
        repo.delete("exec", creator="planner")
    assert repo.update("exec", {"wip": 5}, creator="human").wip == 5
    repo.delete("exec", creator="human")
    with pytest.raises(PotError, match="no_such_role"):
        repo.get("exec")


def test_id_and_value_validation(repo):
    with pytest.raises(PotError, match="bad_id"):
        repo.create({"id": "Bad Id!"}, creator="human")
    repo.create({"id": "dup"}, creator="human")
    with pytest.raises(PotError, match="id_exists"):
        repo.create({"id": "dup"}, creator="human")
    with pytest.raises(PotError, match="bad_value"):
        repo.create({"id": "w0", "wip": 0}, creator="human")
    with pytest.raises(PotError, match="bad_value"):
        repo.create({"id": "cc", "canClaim": True}, creator="human")
