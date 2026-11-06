# -*- coding: utf-8 -*-
"""在**已渲染帧**上量：左侧三块消息的中心 vs 三张报告卡的中心（屏幕 px）。

同时验证左窗格的 park 缩放：page_y → screen_y = 540 + (page_y - 540) * 0.985

    python promo/scripts/measure-s5-align.py out/qa/fixS5c-900.png
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
name = sys.argv[1] if len(sys.argv) > 1 else "out/qa/fixS5c-900.png"
p = Path(name)
if not p.is_absolute():
    p = (ROOT / p).resolve()
im = Image.open(p).convert("RGB")
PX = im.load()
BG = (246, 247, 249)


def is_bg(c, tol=3):
    return all(abs(c[i] - BG[i]) <= tol for i in range(3))


# ── 左窗格：x 250..1000 内的内容块 ──
def blocks(x0, x1, y0=90, y1=700, step=1):
    out, cur = [], None
    for y in range(y0, y1):
        on = any(not is_bg(PX[x, y]) for x in range(x0, x1, 4))
        if on and cur is None:
            cur = [y, y]
        elif on and cur is not None:
            cur[1] = y
        elif cur is not None:
            if cur[1] - cur[0] > 8:
                out.append(tuple(cur))
            cur = None
    if cur is not None and cur[1] - cur[0] > 8:
        out.append(tuple(cur))
    return out


left = blocks(300, 1040)
print("左窗格内容块（屏幕 px）：")
for i, (a, b) in enumerate(left, 1):
    mid = (a + b) // 2
    xs = [x for x in range(300, 1040) if not is_bg(PX[x, mid])]
    print("  块%d  y %3d..%3d  中心 %6.1f   x右缘 %s" % (i, a, b, (a + b) / 2, xs[-1] if xs else None))

# ── 右列：三张近白卡片（#fff，带描边），x 1060..1450 ──
cards = blocks(1062, 1440, 90, 760)
print("\n右列报告卡（屏幕 px）：")
centers = []
for i, (a, b) in enumerate(cards, 1):
    centers.append((a + b) / 2)
    xs = [x for x in range(1062, 1440) if not is_bg(PX[x, (a + b) // 2])]
    print("  卡%d  y %3d..%3d  中心 %6.1f   x %s..%s" % (i, a, b, (a + b) / 2, xs[0] if xs else None, xs[-1] if xs else None))

if len(left) >= 3 and len(cards) >= 1:
    # 左三块（跳过任何 y<100 的残片）
    ls = [((a + b) / 2) for a, b in left][-3:]
    print("\n对齐误差（卡中心 - 左行中心）：")
    for i, c in enumerate(centers):
        if i < len(ls):
            print("  对%d  卡 %6.1f  左 %6.1f  Δ %+5.1f  %s"
                  % (i + 1, c, ls[i], c - ls[i], "OK" if abs(c - ls[i]) <= 2 else "FAIL"))
