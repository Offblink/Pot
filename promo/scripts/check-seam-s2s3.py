# -*- coding: utf-8 -*-
"""S2→S3 接缝自检：把 299 与 300 两帧叠起来，量「板」的屏幕矩形差多少像素。

判据（卡 p-864cf327）：板的位置与大小一致，允许 1px 误差。
做法：两帧里板的描边是 2px 近黑（--text #1b1d22）圆角矩形，先按"暗像素行/列"找出它，
再比较 x/y/w/h —— 不用看像素 diff（相机之外还有逐行洗光等差异，diff 会很吵）。
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "out" / "qa"


def board_rect(name: str):
    im = Image.open(QA / ("%s.png" % name)).convert("RGB")
    w, h = im.size
    px = im.load()

    def dark(x, y):
        r, g, b = px[x, y]
        return r + g + b < 200  # 近黑描边（#1b1d22 ≈ 90）

    # 逐行找"该行暗像素 ≥ 200 个"的区间（板的上/下边框是长横线）
    rows = [y for y in range(h) if sum(1 for x in range(0, w, 2) if dark(x, y)) > 100]
    cols = [x for x in range(w) if sum(1 for y in range(0, h, 2) if dark(x, y)) > 100]
    if not rows or not cols:
        return None
    return {"x": cols[0], "y": rows[0], "w": cols[-1] - cols[0], "h": rows[-1] - rows[0]}


a = board_rect("fixS3b-299")
b = board_rect("fixS3b-300")
print("帧 299 板框:", a)
print("帧 300 板框:", b)
if a and b:
    d = {k: b[k] - a[k] for k in ("x", "y", "w", "h")}
    print("差值 (300-299):", d)
    ok = all(abs(v) <= 1 for v in d.values())
    print("→ %s（判据：每项 |Δ| ≤ 1px）" % ("一致" if ok else "不一致"))
    raise SystemExit(0 if ok else 1)
print("→ 没找到板框，检查阈值")
raise SystemExit(2)
