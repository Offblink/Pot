"""Scene e2e (裁决 36, 同日修订): the top-down board is the center task board —
the original todo-card list of undone AND done — with one bay per busy agent
type on a regular polygon's vertices; no Planner, no status panel.

Skips (never fails) where playwright is missing, so CI without a browser stays
green.
"""

import time

import pytest
from conftest import WebUIHost

from pot import dispatch as dispatch_mod
from pot import session as session_mod
from pot.board import Board
from pot.llm import LLMResult
from pot.roles import Actor, RoleRepo
from pot.server import WEBUI_TOKEN

pw_sync = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


class SilentLLM:
    def __call__(self, _messages, _tool_defs):
        return LLMResult(content="<<SILENT>>")


def _wait(predicate, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture(scope="module")
def room(tmp_path_factory):
    root = tmp_path_factory.mktemp("scene-room")
    roles = RoleRepo(root / "roles")
    roles.create({"id": "exec", "name": "执行者", "canClaim": ["coding"], "wip": 2}, "human")
    board = Board(root / "board.sqlite", roles)
    dispatch_mod.reset_for_tests(roles=roles, board_obj=board)
    server = WebUIHost.start(session_dir=root / "sessions", llm=SilentLLM())
    try:
        session_mod.save_session(
            "exec-1",
            "执行者",
            [
                {"role": "system", "content": ""},
                # a hidden host note in the agent's transcript (裁决 35)
                {"role": "user", "content": "[job report] SECRET-INTERNAL", "internal": True},
            ],
            role="exec",
        )
        session_mod.set_key("exec-1", "instance", 1)
        actor = Actor("exec", "exec-1")
        doing = board.human_create("进行中的卡", labels=["coding"])
        board.claim(actor, doing["id"], doing["ifVersion"])
        done = board.human_create("已完工的卡", labels=["coding"])
        held = board.claim(actor, done["id"], done["ifVersion"])
        board.report(actor, done["id"], "shipped", held["ifVersion"])
        board.human_create("待办的卡", labels=["coding"])
        session_mod.save_session("chat-1", "我的会话", [{"role": "user", "content": "hi"}])
        yield server, roles, board
    finally:
        server.stop()
        dispatch_mod.reset_for_tests()


@pytest.fixture(scope="module")
def browser():
    with pw_sync.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(browser, room):
    url = f"{room[0].open_webui(False)}?t={WEBUI_TOKEN}"
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    pg.goto(url)
    pg.wait_for_function("() => typeof sceneIsOpen === 'function'")
    pg.evaluate("() => document.getElementById('config-overlay')?.classList.remove('show')")
    try:
        yield pg
    finally:
        ctx.close()


def test_scene_center_board_lists_undone_and_done(page, room):
    page.click("#btn-scene")
    page.wait_for_selector("#scene-overlay:not(.hidden)")

    # the revision: no Planner element, no status panel — the board IS the center
    assert page.locator("#scene-planner").count() == 0
    assert page.locator("#scene-panel").count() == 0

    # one bay for the one busy agent type, on the polygon's vertex
    page.wait_for_selector(".scene-bay .scene-agent")
    assert page.locator(".scene-bay").count() == 1
    assert page.locator(".scene-bay-label").text_content().strip() == "执行者"

    # the center board is the original todo-card list: undone AND done
    assert page.locator("#scene-center-count").text_content().strip() == "2"  # doing + todo
    assert page.locator("#scene-list .scene-card").count() == 3
    list_text = page.locator("#scene-list").text_content()
    assert "进行中的卡" in list_text and "待办的卡" in list_text and "已完工的卡" in list_text
    done_row = page.locator(".scene-card.done")
    assert done_row.count() == 1
    assert "exec#1" in done_row.text_content()  # holder signature (裁决 36)


def test_scene_detail_offers_reopen_for_done_cards(page, room):
    page.click("#btn-scene")
    page.locator(".scene-card.done").click()
    page.wait_for_selector("#scene-detail-modal:not(.hidden)")
    assert "已完工的卡" in page.locator("#sd-title").text_content()
    # done card → 重开 + 删除; no acceptance step exists anymore (裁决 32)
    assert page.locator('[data-act="reopen"]').count() == 1
    page.locator('[data-act="reopen"]').click()
    assert page.locator("#sd-reason").count()  # reason input appears (原因进卡)
    page.keyboard.press("Escape")
    page.wait_for_selector("#scene-detail-modal.hidden", state="attached")


def test_scene_agent_click_opens_temp_transcript_without_internal_notes(page, room):
    page.click("#btn-scene")
    page.locator(".scene-agent").first.click()
    page.wait_for_selector("#scene-agent-modal:not(.hidden)")
    assert "exec#1" in page.locator("#sa-title").text_content()
    transcript = page.locator("#sa-transcript").text_content()
    assert "SECRET-INTERNAL" not in transcript  # 裁决 35: internal never renders
    page.keyboard.press("Escape")


def test_picking_a_session_leaves_the_scene(page, room):
    page.click("#btn-scene")
    page.wait_for_selector("#scene-overlay:not(.hidden)")
    page.locator('.session-row[data-sid="chat-1"]').click()
    page.wait_for_selector("#scene-overlay.hidden", state="attached")


def test_picking_the_open_session_leaves_the_scene_too(page, room):
    """2026-11-06: the OPEN session's own card used to hit the hide/show toggle
    behind the overlay — the click looked dead and the board never closed."""
    page.locator('.session-row[data-sid="chat-1"]').click()
    page.wait_for_selector("#messages .msg")  # chat-1 is the open session now
    page.click("#btn-scene")
    page.wait_for_selector("#scene-overlay:not(.hidden)")
    page.locator('.session-row[data-sid="chat-1"]').click()  # same card, again
    page.wait_for_selector("#scene-overlay.hidden", state="attached")
    assert page.locator("#messages .msg").count() > 0  # records actually on screen
