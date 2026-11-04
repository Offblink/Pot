"""Agent builders (pot.agents): Planner vs resident role — prompt, whitelist, wiring.

Replaces the retired trilayer tests: spawn/background/L1-L3 machinery is gone
(spec §3.4), so what matters now is that each builder hands the model exactly
the surface its role defines — no more, no less.
"""

import pytest

from pot import agents
from pot.agent import SYSTEM_PROMPT
from pot.board import Board
from pot.config import Config
from pot.events import FnSink
from pot.roles import Role, RoleRepo

CFG = Config(api_key="k", endpoint="e", model="m")


@pytest.fixture
def board(tmp_path) -> Board:
    return Board(tmp_path / "board.sqlite", RoleRepo(tmp_path / "roles"))


def _names(agent) -> set[str]:
    return {d["function"]["name"] for d in agent.tool_defs}


# ---- resolve_tool_names: a role's `tools` field is the privilege ground ----


def test_tool_groups_expand():
    role = Role(id="r", tools=["shell", "files"])
    assert agents.resolve_tool_names(role) == frozenset(
        {"bash", "bash_start", "bash_send", "bash_kill", "read", "write", "edit"}
    )


def test_raw_base_names_pass_and_screen_is_deferred():
    # `screen` never lands in the whitelist: it is bound separately and only
    # when the host allows desktop control (spec §35.3).
    role = Role(id="r", tools=["grep", "screen", "web_search"])
    assert agents.resolve_tool_names(role) == frozenset({"grep", "web_search"})


def test_unknown_tool_group_is_ignored_not_fatal():
    assert agents.resolve_tool_names(Role(id="r", tools=["nonsense"])) == frozenset()


# ---- build_role: mission prompt + declared surface only ----


def test_role_prompt_carries_mission_and_board_discipline(board):
    sink = FnSink(lambda _t, _c: None)
    role = Role(id="exec", name="执行者", mission="Ship the code.", tools=["shell"])
    agent = agents.build_role(CFG, sink, role=role, session_id="s1", board=board)
    assert "Ship the code." in agent.system_prompt
    assert agents.ROLE_SECTION in agent.system_prompt
    assert agent.system_prompt.startswith(SYSTEM_PROMPT)
    assert "## Skills" in agent.system_prompt  # roles read skills


def test_role_tool_surface_is_the_declared_whitelist(board):
    sink = FnSink(lambda _t, _c: None)
    shell_role = Role(id="r1", tools=["shell"])
    agent = agents.build_role(CFG, sink, role=shell_role, session_id="s1", board=board)
    names = _names(agent)
    assert "bash" in names
    assert "web" not in names and "web_search" not in names  # not declared
    # board tools and readonly skills are granted, never the user-facing ask
    assert {"pot_board_claim", "pot_board_report", "skills"} <= names
    assert "inquire" not in names
    assert "diary" not in names
    assert "todo" not in names  # the host attaches todo, not the builder


def test_role_model_override_follows_the_definition(board):
    sink = FnSink(lambda _t, _c: None)
    agent = agents.build_role(
        CFG,
        sink,
        role=Role(id="r", model="other-model", tools=[]),
        session_id="s1",
        board=board,
    )
    assert agent.model == "other-model"
    fallback = agents.build_role(
        CFG, sink, role=Role(id="r", tools=[]), session_id="s1", board=board
    )
    assert fallback.model is None  # None → cfg.model at completion time


def test_role_gets_screen_only_when_declared(board, monkeypatch):
    monkeypatch.setattr(CFG, "pc_control", True, raising=False)
    sink = FnSink(lambda _t, _c: None)
    with_screen = agents.build_role(
        CFG, sink, role=Role(id="a", tools=["screen"]), session_id="s", board=board
    )
    without = agents.build_role(
        CFG, sink, role=Role(id="b", tools=["shell"]), session_id="s", board=board
    )
    assert "screen" in _names(with_screen)
    assert "screen" not in _names(without)


# ---- build_planner: user-facing surface ----


def test_planner_prompt_carries_board_dispatch(board):
    sink = FnSink(lambda _t, _c: None)
    agent = agents.build_planner(CFG, sink, session_id="s1", board=board)
    assert agents.PLANNER_ADDENDUM in agent.system_prompt
    assert "pot_board_create" in _names(agent)
    assert "inquire" in _names(agent)


def test_planner_has_every_base_tool(board):
    from pot.tools import BASE_TOOL_NAMES

    sink = FnSink(lambda _t, _c: None)
    agent = agents.build_planner(CFG, sink, session_id="s1", board=board)
    assert set(BASE_TOOL_NAMES) <= _names(agent)


def test_diary_only_when_configured(board):
    sink = FnSink(lambda _t, _c: None)
    on = Config(api_key="k", diary=True)
    off = Config(api_key="k", diary=False)
    assert "diary" in _names(agents.build_planner(on, sink, session_id="s", board=board))
    assert "diary" not in _names(agents.build_planner(off, sink, session_id="s", board=board))


def test_should_abort_propagates(board):
    flag = {"on": False}
    sink = FnSink(lambda _t, _c: None)
    agent = agents.build_planner(
        CFG, sink, session_id="s", board=board, should_abort=lambda: flag["on"]
    )
    assert callable(agent.should_abort) and agent.should_abort() is False
    flag["on"] = True
    assert agent.should_abort() is True


def test_every_tool_description_is_a_plain_string(board):
    """A tuple description (trailing comma inside parens) serializes to a JSON
    array, which strict providers (GLM 1210) reject as an invalid parameter -
    the whole turn 400s. Assert the type at the source for every schema."""
    sink = FnSink(lambda _t, _c: None)
    planner = agents.build_planner(CFG, sink, session_id="s", board=board)
    role_agent = agents.build_role(
        CFG, sink, role=Role(id="r", tools=["shell"]), session_id="s", board=board
    )
    for agent in (planner, role_agent):
        for s in agent.tool_defs:
            assert isinstance(s["function"]["description"], str), s["function"]["name"]


# ---- the host wires it: role session → role agent + todo; plain → Planner ----


def test_runtime_build_agent_branches_on_the_session_role(tmp_path, monkeypatch):
    """交接 M2b: a session carrying `role` builds that resident role (mission +
    board + the plan todo tool, no inquire); every other session builds the
    Planner (board + inquire, NO todo — the plan lives with the work)."""
    from pot import session as session_mod
    from pot.server import WebUIRuntime

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path / "sessions")
    roles = RoleRepo(tmp_path / "roles")
    roles.create(
        {"id": "exec", "name": "执行者", "mission": "Ship the code.", "tools": ["shell"]},
        "human",
    )
    rt = WebUIRuntime(board=Board(tmp_path / "board.sqlite", roles), roles=roles)

    session_mod.save_session("r1", "执行者", [{"role": "system", "content": ""}], role="exec")
    role_sink = FnSink(lambda _t, _c: None)
    role_sink.session_id = "r1"
    role_agent = rt.build_agent(role_sink, lambda: False)
    assert "Ship the code." in role_agent.system_prompt
    assert "todo" in role_agent.extra_tools  # 计划工具挂角色会话
    assert "inquire" not in role_agent.extra_tools
    assert role_agent.tool_abort_event is not None

    session_mod.save_session("p1", "plain", [{"role": "system", "content": ""}])
    plan_sink = FnSink(lambda _t, _c: None)
    plan_sink.session_id = "p1"
    planner = rt.build_agent(plan_sink, lambda: False)
    assert agents.PLANNER_ADDENDUM in planner.system_prompt
    assert "todo" not in planner.extra_tools
    assert "inquire" in planner.extra_tools
    assert planner.tool_abort_event is not None
