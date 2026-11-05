"""Sidebar toggle under a huge transcript (G, 2026-11-06).

The margin transition reflows the main area every frame; at 800 message rows
the probe measured 9fps (avg 106ms/frame) until `.msg` gained
content-visibility:auto (49 frames, avg 25ms — parity with a small DOM).
Timing itself is machine-dependent, so this pins the behavior the CSS must
not break instead: the toggle still flips both ways and every row survives
the two layout passes readable.
"""

import threading

import pytest

from pot import server as webui_server
from pot.server import WEBUI_TOKEN

pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

_ROWS = 300


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
def room(tmp_path, monkeypatch):
    from pot import session as session_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path / "sessions")
    runtime = webui_server.WebUIRuntime()
    server = webui_server.make_webui_server(0, runtime)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def page(browser, room):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(f"{room}?t={WEBUI_TOKEN}")
    pg.wait_for_selector("#input")
    pg.evaluate("() => document.getElementById('config-overlay')?.classList.remove('show')")
    try:
        yield pg
    finally:
        ctx.close()


def test_toggle_keeps_a_huge_transcript_intact(page, room):
    page.evaluate(
        """(n) => {
          const msgs = document.getElementById('messages');
          for (let i = 0; i < n; i++) {
            const d = document.createElement('div');
            d.className = 'msg assistant';
            d.textContent = 'row ' + i;
            msgs.appendChild(d);
          }
        }""",
        _ROWS,
    )
    burger = page.locator("#hamburger-sidebar")
    burger.click()
    page.wait_for_function(
        "() => document.getElementById('sidebar').classList.contains('collapsed')"
    )
    burger.click()
    page.wait_for_function(
        "() => !document.getElementById('sidebar').classList.contains('collapsed')"
    )
    # both layout passes later: every row is still there and the last one reads
    assert page.locator("#messages .msg").count() == _ROWS
    assert page.locator("#messages .msg").nth(_ROWS - 1).text_content() == f"row {_ROWS - 1}"
