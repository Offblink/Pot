# -*- coding: utf-8 -*-
"""S6 984 帧纯度：满幅 #06060a，四角与四条 60px 边带逐像素检查。

    python promo/scripts/check-s6-984.py out/qa/s6b-984.png
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DARK = (6, 6, 10)
W, H = 1920, 1080
BAND = 60

p = Path(sys.argv[1] if len(sys.argv) > 1 else "out/qa/s6b-984.png")
if not p.is_absolute():
    p = (ROOT / p).resolve()
im = Image.open(p).convert("RGB")
PX = im.load()

dark = 0
non = []
for y in range(H):
    for x in range(0, W):  # 全像素（本帧应当是全暗）
        c = PX[x, y]
        if c == DARK:
            dark += 1
        else:
            non.append((x, y))

band_bad = 0
for y in range(H):
    for x in list(range(BAND)) + list(range(W - BAND, W)):
        if PX[x, y] != DARK:
            band_bad += 1
for y in list(range(BAND)) + list(range(H - BAND, H)):
    for x in range(W):
        if PX[x, y] != DARK:
            band_bad += 1

print("文件      :", p.name)
print("#06060a 占比: %.4f%%  (%d/%d)" % (100.0 * dark / (W * H), dark, W * H))
print("边带非暗像素:", band_bad)
print("四角      :", [PX[xy] for xy in ((2, 2), (W - 3, 2), (2, H - 3), (W - 3, H - 3))])
if non:
    xs = [a for a, _ in non]
    ys = [b for _, b in non]
    print("非暗区域  : x %d..%d  y %d..%d  (共 %d 像素)" % (min(xs), max(xs), min(ys), max(ys), len(non)))
ok = band_bad == 0 and (dark / (W * H)) > 0.97
print("\n→ %s" % ("OK：满幅暗场、四边无边带" if ok else "FAIL"))
raise SystemExit(0 if ok else 1)
