# -*- coding: utf-8 -*-
"""像素 diff：两张 PNG 的逐通道最大差、不同像素数、平均差。

    python promo/scripts/pixel-diff.py out/qa/s6b-914.png out/qa/s6b-915.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    p = Path(name)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return Image.open(p).convert("RGB")


a = load(sys.argv[1] if len(sys.argv) > 1 else "out/qa/s6b-914.png")
b = load(sys.argv[2] if len(sys.argv) > 2 else "out/qa/s6b-915.png")
if a.size != b.size:
    print("尺寸不同：", a.size, b.size)
    raise SystemExit(1)

diff = ImageChops.difference(a, b)
bbox = diff.getbbox()
data = list(diff.getdata())
mx = max(max(px) for px in data)
nz = sum(1 for px in data if px != (0, 0, 0))
tot = sum(sum(px) for px in data)
print("尺寸        :", a.size)
print("最大通道差  :", mx)
print("非零像素数  : %d / %d  (%.4f%%)" % (nz, len(data), 100.0 * nz / len(data)))
print("平均通道差  : %.6f" % (tot / (len(data) * 3.0)))
print("差异包围盒  :", bbox)
if bbox:
    diff.crop(bbox).save(ROOT / "out" / "qa" / "diff-seam.png")
    print("差异图已存  : out/qa/diff-seam.png")
print("\n→ %s" % ("逐像素一致 Δ=0" if mx == 0 else "存在差异"))
raise SystemExit(0 if mx == 0 else 1)
