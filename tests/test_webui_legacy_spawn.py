"""Old session files still carry `subagents` records (M2b retired spawn, so new
turns never write them). Clicking a spawn card reopens that record in a modal —
and the mapping used to drop the two fields the modal is made of: `status` came
out "unknown" and the body was empty, because trilage stores the tail as
`status` + `events` while registerArchived only copied layer/tool/goal/format
(user-visible as a blank modal, 2026-11-04).

Skips (never fails) where Playwright/Chromium is missing, like the other WebUI
modules.
"""

import pytest
from conftest import WebUIHost

from pot import session as session_mod
from pot.config import Config
from pot.llm import LLMResult
from pot.server import WEBUI_TOKEN

pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CFG = Config(api_key="k", endpoint="e", model="m")

MESSAGES = [
    {"role": "user", "content": "delegate this"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "spawn",
                    "arguments": '{"goal":"read the docs","reply_format":"yes/no"}',
                },
            }
        ],
    },
]

SUBAGENTS = [
    {
        "id": "a1",
        "call_id": "call-1",
        "layer": 2,
        "tool": "spawn",
        "goal": "read the docs",
        "reply_format": "yes/no",
        "status": "done",
        "events": [{"type": "text", "content": "subagent said hello"}],
    }
]


class SilentLLM:
    def __call__(self, _messages, _tool_defs):
        return LLMResult(content="<<SILENT>>")


@pytest.fixture(scope="module")
def room(tmp_path_factory):
    root = tmp_path_factory.mktemp("legacy-spawn")
    server = WebUIHost.start(session_dir=root / "sessions", llm=SilentLLM())
    session_mod.save_session("legacy-1", "legacy", MESSAGES, subagents=SUBAGENTS)
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(scope="module")
def browser():
    with pw_sync.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


def test_legacy_spawn_card_reopens_its_status_and_events(browser, room):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(f"{room.open_webui(False)}?t={WEBUI_TOKEN}")
        page.wait_for_function("() => typeof loadSessions === 'function'")
        # open the seeded session
        page.wait_for_selector(".session-row", timeout=10000)
        page.click(".session-row")
        page.wait_for_selector(".spawn-block", timeout=10000)
        page.click(".spawn-block")
        page.wait_for_selector("#agent-modal-overlay.show", timeout=5000)
        modal = page.inner_text("#agent-modal")
        assert "done" in modal, modal  # status mapping
        assert "subagent said hello" in modal, modal  # events mapping
    finally:
        ctx.close()
