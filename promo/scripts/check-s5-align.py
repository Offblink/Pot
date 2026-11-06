# -*- coding: utf-8 -*-
"""S5 对齐自检（权威版）。

思路：**左侧三行用纹理量**（2x 原图、没有被 park 缩放与视频编码扰动），
卡片用**渲染帧**量，然后把卡片中心换算回页面坐标再比：
    page_y = 540 + (screen_y − 540) / 0.985      （左窗格 scale 0.985、绕 y=540 缩放）

为什么不在渲染帧上量左侧：助手气泡的填充色 ≈ (249,252,250)，与底色 (246,247,249)
只差 1–3/255，视频编码后有几行落进容差里 → 会把块1 的上缘误判低 6px（实测偏 +2px）。
纹理是原始 2x，没有这个噪声。

    python promo/scripts/check-s5-align.py out/qa/fixS5c-900.png
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BG = (246, 247, 249)
PARK_SCALE = 0.985
EXPECT = [181.5, 276.0, 412.5]


def near(c, ref, tol):
    return all(abs(c[i] - ref[i]) <= tol for i in range(3))


def texture_rows():
    im = Image.open(ROOT / "public" / "textures" / "chat-full-zh-2x.png").convert("RGB")
    PX = im.load()
    out, cur = [], None
    for y in range(40 * 2, 990 * 2):
        on = False
        for x in range(280 * 2, 1060 * 2, 4):
            if not near(PX[x, y], BG, 3):
                on = True
                break
        yy = y // 2
        if on and cur is None:
            cur = [yy, yy]
        elif on and cur is not None:
            cur[1] = yy
        elif cur is not None:
            if cur[1] - cur[0] > 8:
                out.append(tuple(cur))
            cur = None
    if cur is not None and cur[1] - cur[0] > 8:
        out.append(tuple(cur))
    return [(a, b, (a + b) / 2) for a, b in out]


def card_bands(p):
    im = Image.open(p).convert("RGB")
    PX = im.load()
    out, cur = [], None
    for y in range(80, 780):
        on = near(PX[1390, y], (255, 255, 255), 6) and near(PX[1090, y], (255, 255, 255), 6)
        if on and cur is None:
            cur = [y, y]
        elif on and cur is not None:
            cur[1] = y
        elif cur is not None:
            if cur[1] - cur[0] >= 20:
                out.append(tuple(cur))
            cur = None
    if cur is not None and cur[1] - cur[0] >= 20:
        out.append(tuple(cur))
    return out


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "out/qa/fixS5c-900.png"
    p = Path(name)
    if not p.is_absolute():
        p = (ROOT / p).resolve()

    rows = texture_rows()
    print("左侧三行（纹理实测，页面 px）：")
    rows_sel = [r for r in rows if r[1] > 100]
    for i, (a, b, c) in enumerate(rows_sel, 1):
        print("  行%d  y %4d..%4d  中心 %6.1f" % (i, a, b, c))

    bands = card_bands(p)
    print("\n三张报告卡（%s，屏幕 px）：" % p.name)
    centers_page = []
    for i, (a, b) in enumerate(bands, 1):
        sc = (a + b) / 2
        pg = 540 + (sc - 540) / PARK_SCALE
        centers_page.append(pg)
        print("  卡%d  y %3d..%3d  屏幕中心 %6.1f  → 页面 %6.1f" % (i, a, b, sc, pg))

    ok = True
    print("\n对齐（卡中心页面坐标 − 左行中心）：")
    for i in range(min(len(rows_sel), len(centers_page))):
        d = centers_page[i] - rows_sel[i][2]
        good = abs(d) <= 2
        ok = ok and good
        print("  对%d  卡 %6.1f  左 %6.1f  Δ %+5.1f  %s" % (i + 1, centers_page[i], rows_sel[i][2], d, "OK" if good else "FAIL"))
    if len(rows_sel) != len(centers_page):
        # 780 / 820 帧卡片还在陆续发牌（cue 767/806/845），少几张是预期的
        print("  提示：本帧有 %d 张卡（全片三张在 845 帧之后齐），逐对误差见上" % len(centers_page))
        print("  已出现卡片是否都对齐：" + ("是" if ok else "否"))

    # 与设计卡给的期望值对一下（顺便记录）
    print("\n左行中心 vs 卡面给的 181.5 / 276 / 412.5：")
    for i, r in enumerate(rows_sel[:3]):
        print("  行%d %.1f  (卡面 %.1f, Δ %+0.1f)" % (i + 1, r[2], EXPECT[i], r[2] - EXPECT[i]))

    print("\n%s" % ("ALL OK" if ok else "有 FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
