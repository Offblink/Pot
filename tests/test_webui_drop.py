"""Drag-and-drop upload (2026-11-06): the whole page is the drop zone.

A dropped File goes up raw to /upload — same origin, so no CORS exists in the
design (the worry this feature was asked about) — and its path lands in the
input exactly like the browse button's /pickfile. The name is basenamed
server-side, so ?name=../evil can never escape data/uploads.
"""

import threading

import pytest

from pot import server as webui_server
from pot.server import WEBUI_TOKEN

pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

_DROP_FILE = """([name, body]) => {
  const dt = new DataTransfer();
  dt.items.add(new File([body], name, { type: 'text/plain' }));
  window.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
}"""

_DROP_NO_FILES = """(uri) => {
  const dt = new DataTransfer();
  dt.setData('text/uri-list', uri);
  window.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
}"""


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
    """A WebUI server whose sessions AND uploads land in tmp, never data/."""
    from pot import session as session_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(webui_server, "UPLOADS_DIR", tmp_path / "uploads")
    runtime = webui_server.WebUIRuntime()
    server = webui_server.make_webui_server(0, runtime)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def page(browser, room):
    base, _ = room
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(f"{base}?t={WEBUI_TOKEN}")
    pg.wait_for_selector("#input")
    pg.evaluate("() => document.getElementById('config-overlay')?.classList.remove('show')")
    try:
        yield pg
    finally:
        ctx.close()


def test_drag_shows_the_overlay_and_drop_saves_the_file(page, room):
    _, tmp = room
    page.evaluate(
        """() => {
          const dt = new DataTransfer();
          dt.items.add(new File(['x'], 'probe.txt'));
          window.dispatchEvent(new DragEvent('dragenter', { bubbles: true, dataTransfer: dt }));
        }"""
    )
    page.wait_for_selector("#drop-overlay:not(.hidden)")  # the whole page advertised itself

    page.evaluate(_DROP_FILE, ["dropped-note.txt", "hello drop"])
    page.wait_for_selector("#drop-overlay.hidden", state="attached")
    page.wait_for_function(
        "() => document.getElementById('input').value.includes('dropped-note.txt')"
    )
    saved = tmp / "uploads" / "dropped-note.txt"
    assert saved.read_text(encoding="utf-8") == "hello drop"  # bytes really landed
    assert str(saved) in page.locator("#input").input_value()  # and the path is what the model gets


def test_upload_basenames_a_traversal_name(page, room):
    _, tmp = room
    result = page.evaluate(
        """async () => {
          const r = await fetch('/upload?name=' + encodeURIComponent('../evil.txt'),
                                { method: 'POST', body: 'nope' });
          return await r.json();
        }"""
    )
    assert result["path"] == str(tmp / "uploads" / "evil.txt")
    assert (tmp / "uploads" / "evil.txt").read_text(encoding="utf-8") == "nope"
    assert not (tmp / "evil.txt").exists()  # the traversal never left the directory


def test_a_dropped_link_lands_as_text_without_any_fetch(page, room):
    page.evaluate(_DROP_NO_FILES, "https://example.com/doc")
    page.wait_for_function(
        "() => document.getElementById('input').value.includes('example.com/doc')"
    )
