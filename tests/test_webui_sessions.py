"""The sidebar session list: renaming a session has to stick in the list itself.

Rows are reused keyed by id, so a row's ✎ handler can hold the session object of
an older /sessions fetch; the rename then lands on the file (and on that stale
object) while `renderSessionList`'s guard compares the painted title against the
*live* list entry and puts the old name back. 2026-09-11 user report:
「会话列表的重命名回车后不更新命名（虽然已经改了，但是刷新才显示）」。

Skips (never fails) where playwright is missing, so CI without a browser stays
green.
"""

import time

import pytest
from conftest import WebUIHost

from pot import session as session_mod
from pot.config import Config
from pot.llm import LLMResult
from pot.server import WEBUI_TOKEN


def _wait(predicate, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CFG = Config(api_key="k", endpoint="e", model="m")


class SilentLLM:
    """No courier chatter: this module drives the sidebar, it does not converse."""

    def __call__(self, _messages, _tool_defs):
        return LLMResult(content="<<SILENT>>")


@pytest.fixture(scope="module")
def room(tmp_path_factory):
    root = tmp_path_factory.mktemp("sessions-room")
    server = WebUIHost.start(session_dir=root / "sessions", llm=SilentLLM())
    try:
        yield server
    finally:
        server.stop()


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
    url = f"{room.open_webui(False)}?t={WEBUI_TOKEN}"
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(url)
    pg.wait_for_function("() => typeof loadSessions === 'function'")
    pg.evaluate("() => document.getElementById('config-overlay')?.classList.remove('show')")
    try:
        yield pg
    finally:
        ctx.close()


def _titles(page) -> list:
    return page.evaluate("() => allSessions.map(s => s.title)")


def test_renaming_a_session_updates_the_list_not_only_the_file(page):
    """The name must change on screen, in the live list, and on the server — all
    three, and without an uncaught error from the rename's own teardown."""
    errors: list = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    # the sidebar lives collapsed at some viewports; open it so the rows are clickable
    page.evaluate(
        """() => {
             const sb = document.getElementById('sidebar');
             if (sb && sb.classList.contains('collapsed')) {
               document.getElementById('hamburger-sidebar').click();
             }
           }"""
    )
    page.click("#btn-new-session")
    # Wait for THIS session, not for "a row": the pinned transfer session (§53)
    # is always there, so a row count says nothing about the new one.
    page.wait_for_function("() => allSessions.some(s => s.title === '(new session)')")
    # Rows are painted in list order and the transfer session is first, so
    # address this test's own row by index rather than "the first one".
    index = page.evaluate("() => allSessions.findIndex(s => s.title === '(new session)')")
    assert index >= 0, page.evaluate("() => allSessions.map(s => s.title)")
    row = page.locator(".session-row").nth(index)
    assert row.locator(".session-row-title").text_content() == "(new session)"

    # A second /sessions fetch — what the 3 s resume poll does — replaces the list
    # objects while the row (and its ✎ handler) is reused: the stale-closure setup.
    page.evaluate("async () => { await loadSessions(); }")
    row.locator(".session-row-act:not(.del)").click()
    page.fill(".rename-input", "改名要立刻生效")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)

    assert row.locator(".session-row-title").text_content() == "改名要立刻生效"
    assert "改名要立刻生效" in _titles(page)
    served = page.evaluate(
        "async () => (await (await fetch('/sessions')).json()).sessions.map(s => s.title)"
    )
    assert "改名要立刻生效" in served, "the save must have reached the server too"
    assert errors == [], "the rename must not throw on its way out (Enter then blur)"


def test_a_403_is_not_mistaken_for_an_unconfigured_shell(page):
    """BUG-08: a browser without the WebUI token gets 403 from /config-status.
    The shell used to read that as "not configured" and opened the config
    card — a wizard that cannot fix a missing token. The card stays shut and
    the banner says what is actually wrong."""
    page.route(
        "**/config-status",
        lambda route: route.fulfill(
            status=403,
            content_type="application/json",
            body='{"error": "forbidden"}',
        ),
    )
    page.reload()
    page.wait_for_function("() => typeof loadSessions === 'function'")
    page.wait_for_timeout(500)  # the gate is async: give it its turn
    assert (
        page.evaluate("() => document.getElementById('config-overlay').classList.contains('show')")
        is False
    ), "403 opened the configure card"
    # The banner element died with the room cut; the 403 now speaks on the status line.
    shown = page.evaluate(
        """() => {
          const s = document.getElementById('status');
          return !!(s && s.textContent.trim().length > 0);
        }"""
    )
    assert shown is True, "no status line told the reader the page is unauthorized"
    page.unroute("**/config-status")


def test_role_sessions_never_reach_the_sidebar(page):
    """裁决 29: the sidebar is the user's conversations; an agent's memory
    session (a `role` key) gets no row — its file stays on disk regardless."""
    session_mod.save_session("role-e2e", "执行者", [{"role": "user", "content": "hi"}], role="exec")
    page.evaluate("async () => { await loadSessions(); }")

    ids = page.evaluate("() => allSessions.map(s => s.id)")
    assert "role-e2e" not in ids, ids
    served = page.evaluate(
        "async () => (await (await fetch('/sessions')).json()).sessions.map(s => s.id)"
    )
    assert "role-e2e" not in served, served
    assert session_mod.load_session("role-e2e")["role"] == "exec"  # the file survives
