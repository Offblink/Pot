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


def test_scene_draws_feed_lines_from_bays_to_the_board(page, room):
    """宣传片同款（2026-11-06 用户点名）：每个 agent 方块一条虚线插进任务板，
    干活的方块上有源源不断流向任务板的圆点；左右工位与板之间要留出可见缝。"""
    page.click("#btn-scene")
    # attached, not visible: a vertical line has a zero-width box, which
    # Playwright counts as hidden even though the geometry is correct
    page.wait_for_selector("#scene-links line", state="attached")
    # one line per AGENT (square), not per bay — 用户定的形态
    assert page.locator("#scene-links line").count() == page.locator(".scene-agent").count()

    floor = page.locator("#scene-floor").bounding_box()
    agent = page.locator(".scene-agent").first.bounding_box()
    line = page.locator("#scene-links line").first
    x1, y1 = float(line.get_attribute("x1")), float(line.get_attribute("y1"))
    x2, y2 = float(line.get_attribute("x2")), float(line.get_attribute("y2"))
    # starts at the agent square's centre ...
    assert abs(x1 - (agent["x"] - floor["x"] + agent["width"] / 2)) < 3
    assert abs(y1 - (agent["y"] - floor["y"] + agent["height"] / 2)) < 3
    # ... and runs to the floor centre, where the opaque board card covers the tail
    assert abs(x2 - floor["width"] / 2) < 3 and abs(y2 - floor["height"] / 2) < 3

    # the working exec keeps feeding the board: dots ride the line (SMIL motion)
    assert page.locator("#scene-links .scene-flow").count() >= 1
    assert page.locator("#scene-links animateMotion").count() >= 1


def test_bulk_delete_removes_only_the_selected_cards(page, room):
    """批量删除（2026-11-06 用户点名）：☑ 进选择态 → 点行勾选 → 确认 → 只删所选。"""
    board = room[2]
    extra = [board.human_create(f"bulk-{i}", labels=["coding"]) for i in range(3)]

    page.click("#btn-scene")
    page.wait_for_selector(".scene-card")
    page.click("#scene-select")
    assert not page.locator("#bulk-del").is_enabled()  # nothing picked yet

    page.locator(".scene-card", has_text="bulk-0").click()
    page.locator(".scene-card", has_text="bulk-1").click()
    assert page.locator("#scene-bulk").is_visible()
    assert "(2)" in page.locator("#bulk-del").text_content()
    assert page.locator(".scene-card.sel").count() == 2

    page.click("#bulk-del")
    page.click("#confirm-ok")
    assert _wait(lambda: all(board.get(c["id"])["deleted"] for c in extra[:2]), 10)
    assert not board.get(extra[2]["id"])["deleted"]  # unselected survivor
    page.wait_for_selector("#scene-bulk.hidden", state="attached")  # mode exits on success


def test_empty_hint_never_sits_under_a_full_board(page, room):
    """空态提示（没有正在工作的 agent）不能被任务板遮挡——任务多、板顶到 56vh 上限时
    提示必须仍在板上方（2026-11-06 用户报；回归：旧 top:24% 落在板带 22%–78% 里）。"""
    board = room[2]
    for i in range(40):
        board.human_create(f"堆叠任务-{i:02d}", labels=["coding"])
    page.click("#btn-scene")
    page.wait_for_selector(".scene-card")

    geo = page.evaluate("""() => {
      sceneData.instances = [];   // no busy agents → the empty hint renders
      sceneRender();
      const e = document.querySelector('.scene-empty').getBoundingClientRect();
      const c = document.getElementById('scene-center').getBoundingClientRect();
      return { emptyBottom: e.bottom, emptyWidth: e.width, centerTop: c.top, centerHeight: c.height };
    }""")
    assert geo["emptyWidth"] > 0  # the hint actually rendered
    assert geo["centerHeight"] > 400  # the board really grew tall (many cards)
    assert geo["emptyBottom"] <= geo["centerTop"]  # …and still cannot cover the hint
