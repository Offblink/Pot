# -*- coding: utf-8 -*-
"""扫一条水平线，打印颜色变化的转折点，用来定位输入条内部的竖直接缝。"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
name = sys.argv[1] if len(sys.argv) > 1 else "fixS1b-90"
y = int(sys.argv[2]) if len(sys.argv) > 2 else 785
im = Image.open(ROOT / "out" / "qa" / ("%s.png" % name)).convert("RGB")
prev = None
runs = []
start = 0
for x in range(0, 1920):
    c = im.getpixel((x, y))
    if prev is None:
        prev, start = c, 0
    elif c != prev and max(abs(c[i] - prev[i]) for i in range(3)) >= 2:
        if x - start >= 3:
            runs.append((start, x - 1, prev))
        prev, start = c, x
runs.append((start, 1919, prev))
print("y=%d 的颜色段（长度≥3）：" % y)
for a, b, c in runs:
    print("  x %4d..%4d  w=%4d  %s" % (a, b, b - a + 1, c))
