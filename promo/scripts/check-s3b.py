# -*- coding: utf-8 -*-
"""S3 修复后的四项量化自检。

    python promo/scripts/check-s3b.py

1. 板框（近黑描边）与四边留白 —— 344 帧要 ≥40 屏幕 px
2. 左侧 0..270px 是否还有侧栏（侧栏里有「新建会话」渐变按钮，蓝色饱和度很高）
3. 299 vs 300 接缝（板框差 ≤1px）
"""
from pathlib import Path

from PIL import Image

QA = Path(__file__).resolve().parents[1] / "out" / "qa"


def rect(name):
    im = Image.open(QA / ("%s.png" % name)).convert("RGB")
    w, h = im.size
    px = im.load()
    dark = lambda x, y: sum(px[x, y]) < 200
    rows = [y for y in range(h) if sum(1 for x in range(0, w, 2) if dark(x, y)) > 100]
    cols = [x for x in range(w) if sum(1 for y in range(0, h, 2) if dark(x, y)) > 100]
    return (im, cols[0], rows[0], cols[-1] - cols[0], rows[-1] - rows[0]) if rows and cols else (im, None, None, None, None)


def sidebar_blue(name):
    im = Image.open(QA / ("%s.png" % name)).convert("RGB")
    px = im.load()
    n = 0
    for y in range(0, 1080, 4):
        for x in range(0, 270, 4):
            r, g, b = px[x, y]
            if b > 120 and b - r > 60 and b - g > 40:  # 蓝紫渐变（--accent2 / --accent-3）
                n += 1
    return n


print("=== 板框与四边留白 ===")
for name in ("fixS3b-300", "fixS3b-310", "fixS3b-330", "fixS3b-336", "fixS3b-344"):
    im, x, y, w, h = rect(name)
    if x is None:
        print("%-14s 找不到板框" % name)
        continue
    W, H = im.size
    m = (x, y, W - 1 - x - w, H - 1 - y - h)
    print("%-14s 板 %4d,%4d %4dx%4d   留白 左%3d 上%3d 右%3d 下%3d" % (name, x, y, w, h, *m))

print("\n=== 左侧 270px 内蓝色像素数（侧栏按钮的特征；0 = 无侧栏）===")
for name in ("fixS3b-300", "fixS3b-310", "fixS3b-330", "fixS3b-336"):
    print("%-14s %d" % (name, sidebar_blue(name)))
print("（对照：修复前的 f330 应为大数）", sidebar_blue("f330"))

print("\n=== 接缝 299 vs 300 ===")
a = rect("fixS3b-299")[1:]
b = rect("fixS3b-300")[1:]
d = tuple(bi - ai for ai, bi in zip(a, b))
print("299:", a)
print("300:", b)
print("差:", d, "→", "一致" if all(abs(v) <= 1 for v in d) else "不一致")
