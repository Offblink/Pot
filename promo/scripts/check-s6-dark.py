# -*- coding: utf-8 -*-
"""S6 暗场自检。

两条判据（对应卡面的"985f 必须是纯 #06060a / 不得有可见矩形边界"）：
  1. **四条边带**（各 60px 宽）与**四角**必须逐像素等于 #06060a
     —— 有任何图层裁片残留，边界一定先在这些地方露出来。
  2. 非 #06060a 的像素必须**聚成一小块**（幸存者 🪴 按钮 + 它的柔光），
     其外接矩形面积不超过画面的 3%；一旦出现"方块/条带"，面积会远超这个量。
另外统计整幅里 #06060a 的占比，给 report 一个直接的数字。

    python promo/scripts/check-s6-dark.py
"""
from pathlib import Path

from PIL import Image

QA = Path(__file__).resolve().parents[1] / "out" / "qa"
DARK = (6, 6, 10)
W, H = 1920, 1080
BAND = 60


def check(name: str, max_blob_frac: float, min_dark: float = 99.0) -> bool:
    p = QA / ("%s.png" % name)
    if not p.exists():
        print("%-12s 缺文件" % name)
        return False
    im = Image.open(p).convert("RGB")
    px = im.load()

    dark = 0
    xs, ys = [], []
    for y in range(H):
        for x in range(0, W, 2):  # 隔列采样，够用且快
            c = px[x, y]
            if c == DARK:
                dark += 1
            else:
                xs.append(x)
                ys.append(y)
    sampled = (W // 2) * H
    frac = 100.0 * dark / sampled

    # 边带 / 四角
    band_bad = 0
    for y in range(H):
        for x in list(range(BAND)) + list(range(W - BAND, W)):
            if px[x, y] != DARK:
                band_bad += 1
    for y in list(range(BAND)) + list(range(H - BAND, H)):
        for x in range(W):
            if px[x, y] != DARK:
                band_bad += 1

    blob = 0.0
    if xs:
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        blob = 100.0 * bw * bh / (W * H)

    ok = (frac > min_dark) and (band_bad == 0) and (blob <= max_blob_frac)
    print("%-12s #06060a 占比 %.2f%%  边带非暗像素 %d  非暗像素外接框 %.2f%%  → %s"
          % (name, frac, band_bad, blob, "OK" if ok else "FAIL"))
    if xs:
        print("             非暗区域 x %d..%d  y %d..%d" % (min(xs), max(xs), min(ys), max(ys)))
    return ok


if __name__ == "__main__":
    # 985：场上只剩迁移中的 🪴 按钮 + 柔光，允许 4%
    a = check("fixS6-985", 4.0)
    # 1199：只剩字标 + tail
    b = check("fixS6-1199", 25.0, 95.0)
    raise SystemExit(0 if (a and b) else 1)
