"""Capture the WebUI scene (裁决 36) for docs/images/board-{zh,en}.png.

Runs against a throwaway board in a temp dir — never the repo's data/.
Usage:  python scripts/scene-shot.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import WebUIHost  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from pot import config as config_mod  # noqa: E402
from pot import dispatch as dispatch_mod  # noqa: E402
from pot import session as session_mod  # noqa: E402
from pot.board import Board  # noqa: E402
from pot.llm import LLMResult  # noqa: E402
from pot.roles import Actor, RoleRepo  # noqa: E402
from pot.server import WEBUI_TOKEN  # noqa: E402


class SilentLLM:
    def __call__(self, _messages, _tool_defs):
        return LLMResult(content="<<SILENT>>")


def seed(root: Path) -> None:
    roles = RoleRepo(root / "roles")
    roles.create({"id": "exec", "name": "执行者", "canClaim": ["coding"], "wip": 2}, "human")
    roles.create({"id": "docs", "name": "写手", "canClaim": ["doc"], "wip": 1}, "human")
    board = Board(root / "board.sqlite", roles)
    dispatch_mod.reset_for_tests(roles=roles, board_obj=board)

    def mount(role: str, n: int) -> str:
        sid = f"{role}-{n}"
        session_mod.save_session(sid, role, [{"role": "system", "content": ""}], role=role)
        session_mod.set_key(sid, "instance", n)
        return sid

    a1 = mount("exec", 1)
    a2 = mount("exec", 2)
    b1 = mount("docs", 1)

    doing = board.human_create("实现断点续传的分片校验", labels=["coding"], priority="urgent")
    held = board.claim(Actor("exec", a1), doing["id"], doing["ifVersion"])

    stuck = board.human_create("排查上传卡在 99% 的问题", labels=["coding"])
    held2 = board.claim(Actor("exec", a2), stuck["id"], stuck["ifVersion"])
    board.move(Actor("exec", a2), stuck["id"], "blocked", held2["ifVersion"])

    doc = board.human_create("给续传章节补中文注释", labels=["doc"])
    board.claim(Actor("docs", b1), doc["id"], doc["ifVersion"])

    done1 = board.human_create("修好托盘菜单字体", labels=["coding"])
    h = board.claim(Actor("exec", a1), done1["id"], done1["ifVersion"])
    board.report(
        Actor("exec", a1), done1["id"], "菜单改用 Swing 弹层，中英文都不豆腐。", h["ifVersion"]
    )

    board.human_create("整理发布清单", labels=["doc"], priority="low")
    board.human_create("给看板加导出 CSV", labels=["coding"], priority="normal")
    assert held["status"] == "doing"


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pot-scene-shot-"))
    cfg = tmp / "config.json"
    cfg.write_text('{"api_key": "k", "ui_lang": "zh"}', encoding="utf-8")
    config_mod.CONFIG_PATH = cfg
    session_mod.SESSIONS_DIR = tmp / "sessions"
    (tmp / "sessions").mkdir(parents=True, exist_ok=True)
    seed(tmp)

    server = WebUIHost.start(session_dir=tmp / "sessions", llm=SilentLLM())
    try:
        base = server.open_webui(False)
        out_dir = ROOT / "docs" / "images"
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for lang in ("zh", "en"):
                cfg.write_text(f'{{"api_key": "k", "ui_lang": "{lang}"}}', encoding="utf-8")
                # a fresh context per language: one load, one dict — a mid-flight
                # reload can re-fetch lang.js against a stale config and mix languages
                ctx = browser.new_context(viewport={"width": 1360, "height": 900})
                page = ctx.new_page()
                page.goto(f"{base}?t={WEBUI_TOKEN}")
                page.wait_for_function("() => typeof sceneIsOpen === 'function'")
                page.evaluate(
                    "() => document.getElementById('config-overlay')?.classList.remove('show')"
                )
                page.click("#btn-scene")
                page.wait_for_selector("#scene-overlay:not(.hidden)")
                page.wait_for_selector(".scene-bay .scene-agent")
                page.wait_for_timeout(400)  # let the polygon settle
                page.screenshot(path=str(out_dir / f"board-{lang}.png"))
                print(f"wrote docs/images/board-{lang}.png")
                ctx.close()
            browser.close()
    finally:
        server.stop()
        dispatch_mod.reset_for_tests()


if __name__ == "__main__":
    main()
