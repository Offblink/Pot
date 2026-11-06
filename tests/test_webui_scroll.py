"""Streaming scroll policy (2026-11-06 用户报告): 贴底 → follow the stream,
scrolled up → never yank; a full repaint keeps the reading position.

Two paths broke it: `renderTurnLive` stuck unconditionally (the measured
`stick` was dead), and the reload path let the browser clamp scrollTop to 0
when `S.clearMsgs()` emptied the pane — the reader was dumped at the top.
The stream here is the rate test's trick: a sentinel-gated fake that streams
slowly, with an opening delay so the test can scroll away first.
"""

import time

import pytest
from conftest import WebUIHost

from pot import agent as agent_mod
from pot import session as session_mod
from pot.llm import LLMAbortedError, LLMResult
from pot.server import WEBUI_TOKEN

pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SENTINEL = "scroll-policy-test"
CHUNKS = 30
CHUNK_S = 0.05
FIRST_DELAY = 0.5  # the window in which the test scrolls away from the bottom


def _wait(predicate, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture(scope="module")
def room(tmp_path_factory):
    root = tmp_path_factory.mktemp("scroll-room")
    server = WebUIHost.start(session_dir=root / "sessions")
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(autouse=True)
def fake_stream(monkeypatch):
    def fake(
        model, endpoint, api_key, messages, tools, on_delta=None, should_abort=None, max_tokens=None
    ):
        if not any(SENTINEL in str(m.get("content") or "") for m in messages):
            return LLMResult(content="<<SILENT>>")
        time.sleep(FIRST_DELAY)
        text = ""
        for _ in range(CHUNKS):
            if should_abort and should_abort():
                raise LLMAbortedError(LLMResult(content=text))
            time.sleep(CHUNK_S)
            if on_delta:
                on_delta("text", "字")
            text += "字"
        return LLMResult(content=text)

    monkeypatch.setattr(agent_mod, "stream_chat", fake)


@pytest.fixture(scope="module")
def browser():
    with pw_sync.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as exc:  # any launch failure means "no browser here"
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(browser, room):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(f"{room.open_webui(False)}?t={WEBUI_TOKEN}")
    pg.wait_for_function("() => typeof loadSessions === 'function'")
    pg.evaluate("() => document.getElementById('config-overlay')?.classList.remove('show')")
    try:
        yield pg
    finally:
        ctx.close()


def _filler(page, rows: int = 40) -> None:
    """A transcript tall enough that scrolling up is even possible."""
    page.evaluate(
        """(n) => {
          const msgs = document.getElementById('messages');
          for (let i = 0; i < n; i++) {
            const d = document.createElement('div');
            d.className = 'msg assistant';
            d.textContent = ('垫行 ' + i + ' — ').repeat(120);
            msgs.appendChild(d);
          }
        }""",
        rows,
    )


def _pos(page) -> dict:
    return page.evaluate(
        """() => {
          const m = document.getElementById('messages');
          return { top: m.scrollTop, gap: m.scrollHeight - m.scrollTop - m.clientHeight };
        }"""
    )


def test_streaming_never_yanks_a_scrolled_up_reader(page, room):
    _filler(page)
    page.fill("#input", SENTINEL)
    page.click("#send")
    time.sleep(0.2)  # the turn is running; FIRST_DELAY keeps the first chunk away
    page.evaluate("() => { document.getElementById('messages').scrollTop = 100; }")
    page.wait_for_selector("#live-text-0", state="attached")  # first chunk landed
    time.sleep(0.4)  # several more chunks stream through renderTurnLive/updateLastText
    pos = _pos(page)
    assert abs(pos["top"] - 100) < 40, f"scrolled-up reader was yanked to {pos['top']}"

    # the other half of the contract: at the bottom, the stream keeps following.
    # The user's affordance is the ↓ button (a raw scrollTop set lands short
    # under content-visibility — the button's stick() re-reads the grown height).
    page.click("#scroll-bottom")
    time.sleep(0.35)
    assert _pos(page)["gap"] < 60, "bottom reader was left behind"


def test_reload_keeps_the_reading_position(page, room):
    session_mod.save_session(
        "long-1",
        "long",
        [{"role": "user", "content": f"行 {i} " + "x" * 2000} for i in range(60)],
    )
    page.evaluate("async () => { await loadSessions(); await switchSession('long-1'); }")
    mid = page.evaluate(
        """() => {
          const m = document.getElementById('messages');
          m.scrollTop = m.scrollHeight / 2;
          return m.scrollTop;
        }"""
    )
    assert mid > 200, f"transcript not scrollable enough to test: {mid}"
    page.evaluate("() => reloadSessionFromServer()")
    assert _wait(lambda: _pos(page)["top"] > 0 or True, 1.0)  # let the fetch land
    page.wait_for_timeout(300)
    pos = _pos(page)
    assert abs(pos["top"] - mid) < 60, f"reading position lost: {mid} -> {pos['top']}"
