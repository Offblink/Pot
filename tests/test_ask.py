"""inquire (Inquire) tests: FakeLLM + threaded resolver, no network."""

import json
import threading
import time

import pytest

from pot.agents import build_planner, build_role
from pot.board import Board
from pot.config import Config
from pot.events import FnSink, NullSink
from pot.llm import LLMResult
from pot.roles import Role, RoleRepo
from pot.tools import ask as ask_mod
from pot.tools.ask import ASK_SCHEMA, make_ask_tool, resolve_ask

CFG = Config(api_key="k", endpoint="e", model="m")


@pytest.fixture
def board(tmp_path) -> Board:
    """A throwaway board: the ask tests never call a card tool, but the
    builders bind them, so an instance must exist."""
    return Board(tmp_path / "board.sqlite", RoleRepo(tmp_path / "roles"))


class ScriptedLLM:
    """Pops scripted LLMResults in order; records requested tool names."""

    def __init__(self, results: list[LLMResult]) -> None:
        self.results = list(results)
        self.requested: list[list[str]] = []

    def __call__(self, _messages: list[dict], tool_defs: list[dict]) -> LLMResult:
        self.requested.append([d["function"]["name"] for d in tool_defs])
        return self.results.pop(0)


def tool_call(name: str, args: dict, call_id: str = "t1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def first_ask(events: list, timeout: float = 5.0) -> dict:
    """Wait until an ask event appears and return its content."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        asks = [c for t, c in events if t == "ask"]
        if asks:
            return asks[0]
        time.sleep(0.01)
    pytest.fail("ask event never emitted")


def run_orchestrator(fake: ScriptedLLM, sink, board: Board) -> list[dict]:
    """Drive one Planner turn with the fake LLM; returns the mutated messages."""
    agent = build_planner(CFG, sink, board=board, llm=fake)
    messages = [{"role": "user", "content": "hi"}]
    agent.run(messages)
    return messages


def test_confirm_returns_answer(board):
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    fake = ScriptedLLM(
        [
            LLMResult(
                tool_calls=[
                    tool_call(
                        "inquire",
                        {
                            "question": "继续吗?",
                            "options": [{"label": "是"}, {"label": "否"}],
                        },
                    )
                ]
            ),
            LLMResult(content="好的"),
        ]
    )

    def resolver() -> None:
        content = first_ask(events)
        assert resolve_ask(content["id"], "是")

    thread = threading.Thread(target=resolver)
    thread.start()
    messages = run_orchestrator(fake, sink, board)
    thread.join(5)
    assert not thread.is_alive()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs[0]["content"] == "USER: 是"

    ask_content = next(c for t, c in events if t == "ask")
    assert set(ask_content) == {"id", "questions", "timeout_s"}
    assert ask_content["timeout_s"] == ask_mod.ASK_TIMEOUT_S  # card renders a countdown
    (q,) = ask_content["questions"]
    assert q["question"] == "继续吗?"
    assert q["options"] == [{"label": "是"}, {"label": "否"}]
    assert q["allow_custom"] is True
    # registry is drained after the ask completes
    assert not ask_mod._pending


def test_multi_question_numbered_answer(board):
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    fake = ScriptedLLM(
        [
            LLMResult(
                tool_calls=[
                    tool_call(
                        "inquire",
                        {
                            "questions": [
                                {"question": "项目名?", "options": [{"label": "YESIR"}]},
                                {"question": "端口?"},
                            ]
                        },
                    )
                ]
            ),
            LLMResult(content="done"),
        ]
    )

    def resolver() -> None:
        content = first_ask(events)
        assert resolve_ask(content["id"], ["YESIR", "8799"])

    thread = threading.Thread(target=resolver)
    thread.start()
    messages = run_orchestrator(fake, sink, board)
    thread.join(5)
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs[0]["content"] == "USER:\n1. YESIR\n2. 8799"

    (q1, q2) = next(c for t, c in events if t == "ask")["questions"]
    assert q1["options"] == [{"label": "YESIR"}]
    assert q2["options"] == [] and q2["allow_custom"] is True


def test_completed_ask_recorded_for_persistence():
    records: list = []
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    tool = make_ask_tool(sink, on_answer=records.append)
    thread = threading.Thread(target=lambda: tool.fn({"question": "q?", "options": ["a"]}))
    thread.start()
    content = first_ask(events)
    resolve_ask(content["id"], "a")
    thread.join(5)
    (rec,) = records
    assert rec["id"] == content["id"]
    assert rec["questions"] == [
        {"question": "q?", "options": [{"label": "a"}], "allow_custom": True}
    ]
    assert rec["answers"] == "a"
    assert rec["status"] == "answered"
    # placed by the friend view: the call that raised it + when it was answered
    assert rec["call_id"] is None  # called directly here, not through the agent
    assert isinstance(rec["ts"], float)


def test_ask_record_carries_its_tool_call_id():
    """The friend view anchors the answered card at the tool call that raised
    it. That only works if the record remembers the id — without it the
    renderer had to guess positionally and dumped the rest at the end."""
    records: list = []
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    tool = make_ask_tool(sink, on_answer=records.append)
    thread = threading.Thread(target=lambda: tool.fn({"question": "q?"}, "call-42"), daemon=True)
    thread.start()
    content = first_ask(events)
    resolve_ask(content["id"], "ok")
    thread.join(5)
    assert records[0]["call_id"] == "call-42"


def test_timeout_recorded_with_timeout_status(monkeypatch, board):
    monkeypatch.setattr(ask_mod, "ASK_TIMEOUT_S", 0.05)
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    fake = ScriptedLLM(
        [
            LLMResult(tool_calls=[tool_call("inquire", {"question": "在吗?"}, call_id="t9")]),
            LLMResult(content="算了"),
        ]
    )
    agent = build_planner(CFG, sink, board=board, llm=fake)
    messages = [{"role": "user", "content": "hi"}]
    agent.run(messages)
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs[0]["content"] == "ERROR: 用户未回答"
    assert ("ping", None) in events  # heartbeat kept the stream alive
    assert agent.asks and agent.asks[0]["status"] == "timeout" and agent.asks[0]["answers"] is None
    # timed-out ask cannot be resolved anymore
    ask_content = next(c for t, c in events if t == "ask")
    assert not resolve_ask(ask_content["id"], "太晚了")


def test_confirm_missing_question():
    tool = make_ask_tool(NullSink())
    assert tool.fn({}) == "ERROR: Missing required argument: question"
    assert tool.fn({"question": "   "}) == "ERROR: Missing required argument: question"
    assert tool.fn({"questions": [{"no_question": 1}]}) == (
        "ERROR: Missing required argument: question"
    )


def test_resolve_unknown_id():
    assert not resolve_ask("nope", "x")


def test_options_normalization():
    args = {
        "question": "q",
        "options": ["plain", {"label": "l1", "description": "d1"}, {"no_label": True}, 42],
        "allow_custom": False,
    }
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    tool = make_ask_tool(sink)
    thread = threading.Thread(target=lambda: tool.fn(dict(args)))
    thread.start()
    content = first_ask(events)
    assert content["questions"][0]["options"] == [
        {"label": "plain"},
        {"label": "l1", "description": "d1"},
    ]
    assert content["questions"][0]["allow_custom"] is False
    assert resolve_ask(content["id"], "ok")
    thread.join(5)
    assert not thread.is_alive()


def test_ask_schema_shape():
    fn = ASK_SCHEMA["function"]
    assert fn["name"] == "inquire"
    assert fn["parameters"]["required"] == ["question"]
    assert set(fn["parameters"]["properties"]) == {
        "question",
        "options",
        "allow_custom",
        "questions",
    }


def test_ask_wakes_on_abort():
    """A stopped turn wakes the blocked ask tool instead of holding the
    session lock for the full ASK_TIMEOUT_S."""
    events: list = []
    sink = FnSink(lambda t, c: events.append((t, c)))
    stop = threading.Event()
    tool = make_ask_tool(sink, should_abort=stop.is_set)
    out: list[str] = []

    def blocker() -> None:
        out.append(tool.fn({"question": "ok?"}))

    thread = threading.Thread(target=blocker, daemon=True)
    thread.start()
    first_ask(events)  # fails the test if no ask card was emitted
    time.sleep(0.05)  # let the tool enter its wait loop
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert out[0].startswith("ERROR")
    assert "停止" in out[0] or "aborted" in out[0].lower()
    assert not ask_mod._pending


def test_only_planner_has_inquire(board):
    """The Planner's table carries inquire + the board; a resident role gets
    the board but never inquire — a role reports through cards, not asks."""
    sink = FnSink(lambda _t, _c: None)
    planner = build_planner(CFG, sink, board=board, llm=None)
    planner_names = {d["function"]["name"] for d in planner.tool_defs}
    assert "inquire" in planner_names
    assert "pot_board_create" in planner_names
    assert not planner_names & {"spawn", "background"}

    role_agent = build_role(
        CFG,
        sink,
        role=Role(id="worker", name="W", mission="do things", tools=["shell"]),
        session_id="s1",
        board=board,
        llm=None,
    )
    role_names = {d["function"]["name"] for d in role_agent.tool_defs}
    assert "inquire" not in role_names
    assert "pot_board_claim" in role_names and "pot_board_report" in role_names
    assert not role_names & {"spawn", "background"}
