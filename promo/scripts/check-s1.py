# -*- coding: utf-8 -*-
"""S1 自检：输入条四边距、底部条带均匀性、顶部有无被切元素。

    python promo/scripts/check-s1.py
"""
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "out" / "qa"
BG = (246, 247, 249)


def consts():
    src = (ROOT / "src" / "shots" / "S1.tsx").read_text(encoding="utf-8")
    g = lambda k: float(re.search(k + r"\s*=\s*([\d.]+)", src).group(1))
    slot = re.search(r"const SLOT = \{ x: ([\d.]+), y: ([\d.]+), w: ([\d.]+), h: ([\d.]+) \}", src)
    return (g("CX"), g("CY"), g("ZOOM"), tuple(float(x) for x in slot.groups()))


CX, CY, ZOOM, (SX, SY, SW, SH) = consts()
left = 960 + (SX - CX) * ZOOM
right = left + SW * ZOOM
top = 540 + (SY - CY) * ZOOM
bottom = top + SH * ZOOM
print("由源码常数算出的输入条屏幕矩形：")
print("  x %.1f..%.1f  y %.1f..%.1f   (w %.1f, h %.1f)" % (left, right, top, bottom, right - left, bottom - top))
print("  边距：左 %.1f  右 %.1f  上 %.1f  下 %.1f" % (left, 1920 - right, top, 1080 - bottom))
ok_bar = (1920 - right) >= 120 and left > 0 and (1080 - bottom) >= 200 and top >= 200
print("  → %s（右≥120 / 下≥200 / 上≥200 / 左>0）" % ("OK" if ok_bar else "FAIL"))


def band_uniform(im, y0, y1):
    px = im.load()
    lo = [255, 255, 255]
    hi = [0, 0, 0]
    for y in range(y0, y1, 4):
        for x in range(0, 1920, 16):
            c = px[x, y]
            for i in range(3):
                lo[i] = min(lo[i], c[i])
                hi[i] = max(hi[i], c[i])
    return tuple(hi[i] - lo[i] for i in range(3)), tuple(lo), tuple(hi)


for name in ("fixS1b-30", "fixS1b-90", "fixS1b-110"):
    p = QA / (name + ".png")
    im = Image.open(p).convert("RGB")
    d, lo, hi = band_uniform(im, 1080 - 120, 1080)
    d2, lo2, hi2 = band_uniform(im, 0, 60)
    print("\n%s  底部 120px 条带：ΔRGB %s  (%s .. %s)" % (name, d, lo, hi))
    print("   顶部 60px 条带：ΔRGB %s  (%s .. %s)" % (d2, lo2, hi2))
    print("   → 底带 %s ／ 顶带 %s" % (
        "均匀" if max(d) <= 2 else "有接缝/色带",
        "无被切元素" if max(d2) <= 2 else "有内容/边缘",
    ))
