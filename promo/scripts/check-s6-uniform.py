# -*- coding: utf-8 -*-
"""S6 蒸发过程均匀性自检：同一帧里，几个不同归属区域（侧栏 / 空地板 / 板面外）
的平均亮度应当一致 —— 只要出现"某块明显偏亮或偏暗"，就是卡面说的灰块/灰边带。

    python promo/scripts/check-s6-uniform.py 966 956 950
"""
import sys
from pathlib import Path

from PIL import Image

QA = Path(__file__).resolve().parents[1] / "out" / "qa"

# 取样的"空场"点：都不落在任何 UI 元素上，只代表该区域的底色
PROBES = {
    "sidebar 0-272": (120, 500),
    "地板 272-1920": (1500, 500),
    "板外左": (700, 500),
    "板外右": (1250, 700),
    "顶部": (960, 40),
    "底部": (960, 1040),
}


def main() -> int:
    frames = [int(a) for a in sys.argv[1:]] or [950, 956, 966]
    for fr in frames:
        p = QA / ("fixS6-%d.png" % fr)
        if not p.exists():
            print("fixS6-%d 缺文件" % fr)
            return 2
        im = Image.open(p).convert("RGB")
        vals = {k: sum(im.getpixel(xy)) / 3.0 for k, xy in PROBES.items()}
        lo, hi = min(vals.values()), max(vals.values())
        print("frame %d  spread %.1f  %s" % (fr, hi - lo, {k: round(v, 1) for k, v in vals.items()}))
        if hi - lo > 14:
            print("   → FAIL：区域间亮度差 > 14（可见灰块/灰边带）")
            return 1
        print("   → OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
