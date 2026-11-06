# -*- coding: utf-8 -*-
"""精确量真实输入框的几何（页面 CSS px）。

输入框填充色与外部底色同为 --bg，所以只能靠**描边**定位：
  · 列扫描（x 固定）→ 上下缘；
  · 行扫描取**没有文字的两行**（框内上部/下部）→ 左右缘。
"""
from pathlib import Path

from PIL import Image

TEX = Path(__file__).resolve().parents[1] / "public" / "textures" / "chat-full-zh-2x.png"
im = Image.open(TEX).convert("RGB")


def darker(c, base, d=4):
    return sum(base) - sum(c) >= d


def runs(vals, gap=3):
    out, cur = [], []
    for v in vals:
        if cur and v - cur[-1] <= gap:
            cur.append(v)
        else:
            if cur:
                out.append(cur)
            cur = [v]
    if cur:
        out.append(cur)
    return [(g[0], g[-1]) for g in out]


for ROW in (1004, 1010, 1050, 1055):
    y = ROW * 2
    base = im.getpixel((560, y))
    hits = [x // 2 for x in range(280 * 2, 1919 * 2) if darker(im.getpixel((x, y)), base)]
    print("行 y=%d:" % ROW, runs(hits)[:8])

for COL in (300, 1200):
    x = COL * 2
    base = im.getpixel((x, 1975))
    hits = [yy // 2 for yy in range(993 * 2, 1080 * 2) if darker(im.getpixel((x, yy)), base)]
    print("列 x=%d:" % COL, runs(hits)[:8])
