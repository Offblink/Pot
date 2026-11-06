# -*- coding: utf-8 -*-
"""Pot 宣传片 · 阶段 4 素材采集：2x 全页纹理 + 元素切片 + layout.json。

一条命令重跑全部采集：
    python promo/capture/capture.py

设计要点
--------
* 用 tests/conftest.py 的 `WebUIHost`（真宿主、假 LLM）起一个 loopback WebUI，
  会话/角色/看板全落在 `promo/capture/_runtime/` 的临时目录里 —— 不碰仓库根的
  `config.json`，不碰用户正在用的 `data/board.sqlite`，不写 `data/sessions/`。
* 端口与 token 全部来自 `WebUIHost.open_webui()` 与 `pot.server.WEBUI_TOKEN`，
  脚本里没有硬编码端口。
* 三层产出：整页图（视口 1920×1080 @ dpr 2 → 3840×2160）、按选择器裁的元素切片、
  `layout.json`（每个元素在整页坐标系下的 bbox，单位是页面 CSS px = 截图尺寸 ÷ 2）。
* 所有卡片标题/角色名/消息都是虚构演示数据（`seed.json` 可重放），不含真实
  用户名、真实文件路径、api key 或真实模型名。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]          # 仓库根（Pot/）
HERE = Path(__file__).resolve().parent              # promo/capture/
OUT_DIR = ROOT / "promo" / "public" / "textures"
RUNTIME_DIR = HERE / "_runtime"
SEED_JSON = HERE / "seed.json"

VIEWPORT = {"width": 1920, "height": 1080}
DPR = 2
SETTLE_MS = 700            # 字体就绪后再等这么久，让入场动效落定
LANG = "zh"

SELECTORS = {
    # 场景
    "scene_overlay": "#scene-overlay",
    "scene_floor": "#scene-floor",
    "board": "#scene-center",
    "board_list": "#scene-list",
    "board_empty": "#scene-none",
    "bay": ".scene-bay",
    "bay_label": ".scene-bay-label",
    "agent": ".scene-agent",
    "card_row": ".scene-card",
    "card_title": ".scene-card-title",
    "chip": ".scene-chip",
    # 聊天
    "sidebar": "#sidebar",
    "messages": "#messages",
    "input": "#input-area",
    "session_row": ".session-row",
    "tool_card": ".msg.tool",
    # 弹层
    "detail_body": "#sd-body",
}
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from conftest import WebUIHost  # noqa: E402

from pot import dispatch as dispatch_mod  # noqa: E402
from pot import session as session_mod  # noqa: E402
from pot.board import Board  # noqa: E402
from pot.dispatch import done_block  # noqa: E402
from pot.llm import LLMResult  # noqa: E402
from pot.roles import Actor, RoleRepo  # noqa: E402
from pot.server import WEBUI_TOKEN  # noqa: E402


class SilentLLM:
    """没有模型调用：本脚本只采集页面，不跑任何一轮对话。"""

    def __call__(self, _messages, _tool_defs):
        return LLMResult(content="<<SILENT>>")


# ── 播种（全部虚构；与 seed.json 一一对应） ──────────────────────────────────

def seed(roles: RoleRepo, board: Board) -> dict:
    roles.create({"id": "writer", "name": "写手", "canClaim": ["docs"], "wip": 1}, "human")
    roles.create({"id": "review", "name": "审稿", "canClaim": ["review"], "wip": 1}, "human")
    roles.create({"id": "exec", "name": "执行者", "canClaim": [], "wip": 2}, "human")

    w1 = Actor("writer", "writer-1")
    r1 = Actor("review", "review-1")
    e1 = Actor("exec", "exec-1")
    e2 = Actor("exec", "exec-2")

    def todo(title, labels, priority="normal"):
        return board.human_create(title, labels=labels, priority=priority)

    def doing(title, labels, actor, priority="normal"):
        c = todo(title, labels, priority)
        return board.claim(actor, c["id"], c["ifVersion"])

    def blocked(title, labels, actor, reason):
        c = doing(title, labels, actor)
        return board.move(actor, c["id"], "blocked", c["ifVersion"])

    def done(title, labels, actor, summary):
        c = doing(title, labels, actor)
        return board.report(actor, c["id"], summary, c["ifVersion"])

    cards = {
        # done（2）——先把这两张 claim+report 走完（报告即完成，holder 只留作署名），
        # 否则 writer/exec 的 wip 配额会被 doing 卡占满，新一轮 claim 直接 wip_full
        "done_one": done("给续传章节补边界说明", ["docs"], w1, "补了 3 处边界，链接改指新版"),
        "done_two": done("清掉无用的调试日志", ["coding"], e1, "删了 12 行打印，跑过一遍用例"),
        # doing（3）——三个实例各持一张，场景里长出任一工位的绿方块
        "doing_write": doing("给续传章节补中文注释", ["docs"], w1),
        "doing_exec1": doing("把上传卡在 99% 的问题钉住", ["coding"], e1, "urgent"),
        "doing_exec2": doing("给看板加导出 CSV", ["coding"], e2),
        # blocked（1）——审稿卡住，方块转红
        "blocked": blocked("核对发布页的旧截图", ["review"], r1, "缺新版截图，等设计导出"),
        # todo（3）
        "todo_pub": todo("整理发布清单", ["docs"]),
        "todo_tray": todo("修托盘菜单字体", ["coding"], "low"),
        "todo_readme": todo("把 README 里过期的地方找出来", ["docs"]),
    }
    return cards


def seed_sessions(cards: dict) -> None:
    """4 个角色会话（3 角色 / 执行者 2 实例）+ 1 个「我的会话」。"""
    role_msgs = [
        {"role": "system", "content": ""},
        {"role": "user", "content": "把这件事做完，做完写回报。"},
    ]
    for sid, title, role, inst in [
        ("writer-1", "写手", "writer", 1),
        ("review-1", "审稿", "review", 1),
        ("exec-1", "执行者", "exec", 1),
        ("exec-2", "执行者", "exec", 2),
    ]:
        session_mod.save_session(sid, title, list(role_msgs), role=role)
        session_mod.set_key(sid, "instance", inst)

    chat = [
        {"role": "system", "content": ""},
        {"role": "user", "content": "把 README 里过期的地方找出来"},
        {
            "role": "assistant",
            "content": "已经拆成三张卡放进看板：续传章节、托盘字体、发布清单。"
                       "角色是按标签认领的，不用我排队。",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_01",
                    "function": {
                        "name": "pot_board_create",
                        "arguments": json.dumps({"title": "整理发布清单", "labels": ["docs"]},
                                                ensure_ascii=False),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_01",
         "content": "created p-3f21ac · 整理发布清单 · todo · labels=docs"},
        # 报告回到会话：宿主真实渲染的卡片块（pot.dispatch.done_block）
        {"role": "assistant", "content": done_block([cards["done_one"]], LANG)},
    ]
    session_mod.save_session("chat-1", "我的会话", chat)


# ── 采集 ─────────────────────────────────────────────────────────────────────

def shot(page, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path))
    return {"file": path.name}


def shot_el(page, selector: str, path: Path, *, nth: int | None = None) -> dict:
    page.wait_for_selector(selector)
    loc = page.locator(selector)
    el = loc.nth(nth) if nth is not None else loc.first
    path.parent.mkdir(parents=True, exist_ok=True)
    el.screenshot(path=str(path))
    return {"file": path.name}


def bbox(page, selector: str, *, nth: int | None = None) -> dict | None:
    loc = page.locator(selector)
    el = loc.nth(nth) if nth is not None else loc.first
    if el.count() == 0:
        return None
    box = el.bounding_box()
    if not box:
        return None
    return {k: round(v, 2) for k, v in box.items()}


def settle(page, wait_sel: str | None = None) -> None:
    if wait_sel:
        page.wait_for_selector(wait_sel)
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(SETTLE_MS)


def open_scene(page) -> None:
    page.click("#btn-scene")
    page.wait_for_selector("#scene-overlay:not(.hidden)")
    # 场景每 2s 轮询重绘一次；停掉计时器，避免截图期间 DOM 被换掉
    page.evaluate("() => { try { clearInterval(sceneTimer); } catch (e) {} }")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(SETTLE_MS)


def main() -> int:
    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    roles = RoleRepo(RUNTIME_DIR / "roles")
    board = Board(RUNTIME_DIR / "board.sqlite", roles)
    dispatch_mod.reset_for_tests(roles=roles, board_obj=board)
    cards = seed(roles, board)

    # 配置也走临时文件：既保证 /config-status 认为"已配置"（否则 API-key 弹层会盖住页面），
    # 又保证界面语言是中文（/lang.js 读 config.json 的 ui_lang）。
    cfg = RUNTIME_DIR / "config.json"
    cfg.write_text(json.dumps({"api_key": "k", "ui_lang": "zh", "model": "演示模型"},
                              ensure_ascii=False),
                   encoding="utf-8")
    from pot import config as config_mod

    mp_cfg = pytest.MonkeyPatch()
    mp_cfg.setattr(config_mod, "CONFIG_PATH", cfg)

    # 会话目录必须已被 WebUIHost 指到临时区，否则会写进用户的 data/sessions
    # （2026-11-05 实测踩过：先 save_session 再 start 会漏 5 个文件到真实目录）。
    server = WebUIHost.start(session_dir=RUNTIME_DIR / "sessions", llm=SilentLLM())
    sessions_dir = Path(session_mod.SESSIONS_DIR).resolve()
    if RUNTIME_DIR.resolve() not in sessions_dir.parents:
        server.stop()
        raise SystemExit(f"安全中止：SESSIONS_DIR 未被重定向到临时区（{sessions_dir}）")
    seed_sessions(cards)

    url = f"{server.open_webui(False)}?t={WEBUI_TOKEN}&lang={LANG}"
    manifest: dict = {"pages": {}, "elements": {}, "notes": []}
    detail_ids = {
        "doing": cards["doing_exec1"]["id"],
        "blocked": cards["blocked"]["id"],
        "done": cards["done_one"]["id"],
        "todo": cards["todo_readme"]["id"],
    }

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(
                viewport=VIEWPORT,
                device_scale_factor=DPR,
                locale="zh-CN",
                reduced_motion="reduce",
            )
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_function("() => typeof sceneIsOpen === 'function'")
            page.evaluate(
                "() => document.getElementById('config-overlay')?.classList.remove('show')"
            )

            # 1) 场景全景
            open_scene(page)
            page.wait_for_selector(".scene-bay .scene-agent")
            shot(page, OUT_DIR / "scene-full-zh@2x.png")

            # 2) 空 backplate：同一机位，任务板无卡（清空列表 + 计数归零）
            page.evaluate(
                """() => {
                    const list = document.getElementById('scene-list');
                    if (list) list.innerHTML = '';
                    const n = document.getElementById('scene-center-count');
                    if (n) n.textContent = '0';
                }"""
            )
            page.wait_for_timeout(120)
            shot(page, OUT_DIR / "scene-full-empty@2x.png")
            manifest["notes"].append(
                "scene-full-empty@2x.png：与全景同一机位，仅清空 #scene-list 的内容并"
                "把 #scene-center-count 置 0（面板本体与几何位置未改），作为飞入镜头的空 backplate。"
            )

            # 刷新回真数据，再采切片
            page.reload()
            page.wait_for_function("() => typeof sceneIsOpen === 'function'")
            page.evaluate(
                "() => document.getElementById('config-overlay')?.classList.remove('show')"
            )
            open_scene(page)
            page.wait_for_selector(".scene-card")

            manifest["pages"]["scene"] = {
                "file": "scene-full-zh@2x.png",
                "emptyFile": "scene-full-empty@2x.png",
                "pageW": VIEWPORT["width"],
                "pageH": VIEWPORT["height"],
                "dpr": DPR,
            }
            # 3) 元素切片：中央任务板 / 两个工位 / 卡行
            shot_el(page, SELECTORS["board"], OUT_DIR / "scene-board@2x.png")
            for role_id, sid_alias, name in [
                ("writer", "writer-1", "writer"),
                ("exec", "exec-1", "exec"),
            ]:
                bay = page.locator(".scene-bay").filter(has_text=name_cn(role_id))
                if bay.count():
                    bay.first.screenshot(path=str(OUT_DIR / f"scene-bay-{sid_alias}@2x.png"))
                    bay.first.locator(".scene-agent").first.screenshot(
                        path=str(OUT_DIR / f"scene-agent-{sid_alias}@2x.png")
                    )
            for key, alias in [("todo_readme", "todo"), ("done_one", "done")]:
                sel = f'.scene-card[data-card="{cards[key]["id"]}"]'
                if page.locator(sel).count():
                    page.locator(sel).screenshot(path=str(OUT_DIR / f"ui-card-row-{alias}@2x.png"))

            # 4) layout（场景）
            def add_el(name, selector, page_id="scene", nth=None):
                box = bbox(page, selector, nth=nth)
                if box:
                    manifest["elements"][name] = {"page": page_id, **box}
                return box

            add_el("board", SELECTORS["board"])
            add_el("board-list", SELECTORS["board_list"])
            add_el("board-head", "#scene-center-head")
            for role_id, sid_alias in [("writer", "writer-1"), ("exec", "exec-1")]:
                bay = page.locator(".scene-bay").filter(has_text=name_cn(role_id))
                if bay.count():
                    b = bay.first.bounding_box()
                    if b:
                        manifest["elements"][f"bay-{sid_alias}"] = {
                            "page": "scene", **{k: round(v, 2) for k, v in b.items()}
                        }
            # 每个像素方块
            for i in range(page.locator(".scene-agent").count()):
                box = bbox(page, ".scene-agent", nth=i)
                sid = page.locator(".scene-agent").nth(i).get_attribute("data-sid") or f"i{i}"
                if box:
                    manifest["elements"][f"agent-{sid}"] = {"page": "scene", **box}
            for key, alias in [("todo_readme", "todo"), ("done_one", "done"),
                               ("doing_exec1", "doing"), ("blocked", "blocked")]:
                sel = f'.scene-card[data-card="{cards[key]["id"]}"]'
                add_el(f"card-row-{alias}", sel)

            # 5) chip 切片 + bbox：借详情弹层里宿主自己渲染的 .scene-chip
            chip_map = [
                ("doing", cards["doing_exec1"]["id"], "st-doing", "ui-chip-doing@2x.png"),
                ("blocked", cards["blocked"]["id"], "st-blocked", "ui-chip-blocked@2x.png"),
                ("done", cards["done_one"]["id"], "st-done", "ui-chip-done@2x.png"),
            ]
            for alias, cid, cls, fname in chip_map:
                page.locator(f'.scene-card[data-card="{cid}"]').click()
                page.wait_for_selector("#scene-detail-modal:not(.hidden)")
                page.wait_for_timeout(150)
                sel = f'#sd-body .scene-chip.{cls}'
                if page.locator(sel).count():
                    page.locator(sel).first.screenshot(path=str(OUT_DIR / fname))
                    box = bbox(page, sel)
                    if box:
                        manifest["elements"][f"chip-{alias}"] = {"page": "scene", **box}
                page.keyboard.press("Escape")
                page.wait_for_timeout(150)
            # 标签 chip（复用 done 卡的详情，取 .scene-chip.lab）
            page.locator(f'.scene-card[data-card="{cards["done_one"]["id"]}"]').click()
            page.wait_for_selector("#scene-detail-modal:not(.hidden)")
            page.wait_for_timeout(150)
            if page.locator("#sd-body .scene-chip.lab").count():
                page.locator("#sd-body .scene-chip.lab").first.screenshot(
                    path=str(OUT_DIR / "ui-chip-label@2x.png")
                )
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)

            # 6) 聊天页（侧栏 + 消息 + tool 卡 + 报告块）
            page.evaluate("sceneClose()")     # 场景overlay 盖住了按钮，直接调住主自己的关闭函数
            page.wait_for_selector("#scene-overlay.hidden", state="attached")
            page.locator('.session-row[data-sid="chat-1"]').click()
            page.wait_for_selector(f'{SELECTORS["messages"]} .msg')
            settle(page, f'{SELECTORS["messages"]} .msg')
            shot(page, OUT_DIR / "chat-full-zh@2x.png")
            page.locator(SELECTORS["messages"]).screenshot(
                path=str(OUT_DIR / "chat-messages@2x.png")
            )
            manifest["pages"]["chat"] = {
                "file": "chat-full-zh@2x.png",
                "pageW": VIEWPORT["width"],
                "pageH": VIEWPORT["height"],
                "dpr": DPR,
            }
            for name, sel in [
                ("sidebar", SELECTORS["sidebar"]),
                ("messages", SELECTORS["messages"]),
                ("input-area", SELECTORS["input"]),
            ]:
                box = bbox(page, sel)
                if box:
                    manifest["elements"][name] = {"page": "chat", **box}
            if page.locator(SELECTORS["tool_card"]).count():
                manifest["elements"]["tool-card"] = {
                    "page": "chat", **(bbox(page, SELECTORS["tool_card"]) or {})
                }
            # 最后一条 assistant 消息就是报告卡片块
            last_assistant = page.locator(".msg.assistant").last
            box = last_assistant.bounding_box()
            if box:
                manifest["elements"]["report-block"] = {
                    "page": "chat", **{k: round(v, 2) for k, v in box.items()}
                }
                last_assistant.screenshot(path=str(OUT_DIR / "chat-report@2x.png"))
                last_assistant.scroll_into_view_if_needed()
                page.wait_for_timeout(200)
                shot(page, OUT_DIR / "chat-report-full@2x.png")

            ctx.close()
            browser.close()
    finally:
        server.stop()
        dispatch_mod.reset_for_tests()

    manifest["notes"].append(
        "chat-report@2x.png / chat-report-full@2x.png：报告块由宿主的真实渲染函数 "
        "pot.dispatch.done_block(cards, 'zh') 生成后存进会话消息，不是手写 HTML。"
    )
    manifest["notes"].append(
        "所有数据来自 promo/capture/seed.json 的虚构播种：角色 写手/审稿/执行者，"
        "卡 9 张，会话 5 个；执行者有 2 个实例（exec#1/exec#2）。"
    )
    (OUT_DIR / "layout.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_seed_json()

    files = sorted(p.name for p in OUT_DIR.glob("*.png"))
    print(f"output dir : {OUT_DIR}")
    print(f"files      : {len(files)} png + layout.json")
    for name in files:
        print("  -", name)
    print(f"elements   : {len(manifest['elements'])}")
    print("OK")
    return 0


def name_cn(role_id: str) -> str:
    return {"writer": "写手", "review": "审稿", "exec": "执行者"}[role_id]


def write_seed_json() -> None:
    data = {
        "note": "本片采集用的虚构播种数据（可重放）：角色 / 卡 / 会话。无真实用户名、路径、key、模型名。",
        "roles": [
            {"id": "writer", "name": "写手", "canClaim": ["docs"], "wip": 1},
            {"id": "review", "name": "审稿", "canClaim": ["review"], "wip": 1},
            {"id": "exec", "name": "执行者", "canClaim": [], "wip": 2},
        ],
        "instances": [
            {"role": "writer", "session": "writer-1", "number": 1},
            {"role": "review", "session": "review-1", "number": 1},
            {"role": "exec", "session": "exec-1", "number": 1},
            {"role": "exec", "session": "exec-2", "number": 2},
        ],
        "cards": [
            {"title": "给续传章节补中文注释", "labels": ["docs"], "status": "doing", "holder": "writer:writer-1"},
            {"title": "把上传卡在 99% 的问题钉住", "labels": ["coding"], "priority": "urgent", "status": "doing", "holder": "exec:exec-1"},
            {"title": "给看板加导出 CSV", "labels": ["coding"], "status": "doing", "holder": "exec:exec-2"},
            {"title": "核对发布页的旧截图", "labels": ["review"], "status": "blocked", "holder": "review:review-1"},
            {"title": "整理发布清单", "labels": ["docs"], "status": "todo"},
            {"title": "修托盘菜单字体", "labels": ["coding"], "priority": "low", "status": "todo"},
            {"title": "把 README 里过期的地方找出来", "labels": ["docs"], "status": "todo"},
            {"title": "给续传章节补边界说明", "labels": ["docs"], "status": "done", "holder": "writer:writer-1"},
            {"title": "清掉无用的调试日志", "labels": ["coding"], "status": "done", "holder": "exec:exec-1"},
        ],
        "sessions": [
            {"id": "writer-1", "title": "写手", "role": "writer", "instance": 1},
            {"id": "review-1", "title": "审稿", "role": "review", "instance": 1},
            {"id": "exec-1", "title": "执行者", "role": "exec", "instance": 1},
            {"id": "exec-2", "title": "执行者", "role": "exec", "instance": 2},
            {"id": "chat-1", "title": "我的会话", "role": None,
             "messages": ["user: 把 README 里过期的地方找出来",
                          "assistant: 已经拆成三张卡放进看板…",
                          "assistant(tool_call): pot_board_create",
                          "tool(result): created p-3f21ac · 整理发布清单 · todo",
                          "assistant: 📋 卡片已完成（pot.dispatch.done_block 真实渲染）"]},
        ],
    }
    SEED_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
