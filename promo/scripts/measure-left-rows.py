# -*- coding: utf-8 -*-
"""量 chat-full 纹理里左侧三块消息的 y 范围与 x 右缘（页面 CSS px）。

判据：非底色（--bg #f6f7f9）像素。逐行统计 → 得到三块的 y 区间；
再在每块的纵向中点扫一行 → 得到该块的 x 左/右缘。
"""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
im = Image.open(ROOT / "public" / "textures" / "chat-full-zh-2x.png").convert("RGB")
W, H = im.size
PX = im.load()
BG = (246, 247, 249)


def is_bg(c, tol=3):
    return all(abs(c[i] - BG[i]) <= tol for i in range(3))


# 只看消息列（页面 x 280..1060），避开侧栏与输入区
X0, X1 = 280 * 2, 1060 * 2
rows = []
for y in range(40 * 2, 990 * 2):
    n = 0
    for x in range(X0, X1, 4):
        if not is_bg(PX[x, y]):
            n += 1
            if n >= 3:
                break
    rows.append((y // 2, n >= 3))

# 聚成块
blocks, cur = [], None
for y, on in rows:
    if on and cur is None:
        cur = [y, y]
    elif on:
        cur[1] = y
    elif cur is not None:
        if cur[1] - cur[0] > 8:
            blocks.append(tuple(cur))
        cur = None
if cur is not None and cur[1] - cur[0] > 8:
    blocks.append(tuple(cur))

print("左侧内容块（页面 CSS px）：")
out = []
for i, (a, b) in enumerate(blocks, 1):
    mid = (a + b) // 2
    xs = [x // 2 for x in range(X0, X1) if not is_bg(PX[x, mid * 2])]
    left, right = (xs[0], xs[-1]) if xs else (None, None)
    print("  块%d  y %4d..%4d  高 %3d  中心 %6.1f   x %s..%s"
          % (i, a, b, b - a + 1, (a + b) / 2, left, right))
    out.append({"i": i, "y0": a, "y1": b, "h": b - a + 1, "center": (a + b) / 2, "xRight": right})

(ROOT / "out" / "qa" / "left-rows.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n写出 out/qa/left-rows.json")
