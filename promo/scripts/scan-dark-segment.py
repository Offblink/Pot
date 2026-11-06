# -*- coding: utf-8 -*-
"""扫一段/整片成片的逐帧平均亮度，找"黑闪"。

    python promo/scripts/scan-dark-segment.py out/seam.mp4 900 1000
    python promo/scripts/scan-dark-segment.py out/pot-promo.mp4 0 1200

判据（卡 p-6267acd2）：`900..975` 内 mean<200 的帧数必须为 0；
只有预期的暗场（976 之后）允许暗。逐帧解 1/4 尺寸灰度、打印每一帧的 mean 与区间。
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
mp4 = Path(sys.argv[1] if len(sys.argv) > 1 else "out/seam.mp4")
if not mp4.is_absolute():
    mp4 = (ROOT / mp4).resolve()
start = int(sys.argv[2]) if len(sys.argv) > 2 else 900
end = int(sys.argv[3]) if len(sys.argv) > 3 else 1000

with tempfile.TemporaryDirectory() as td:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4),
                    "-vf", "scale=480:270", "-fps_mode", "passthrough",
                    str(Path(td) / "f_%04d.png")], check=True)
    files = sorted(Path(td).glob("f_*.png"))
    print("段：%s  帧 %d..%d（解出 %d 帧）" % (mp4.name, start, end, len(files)))
    means, dark, dark_early = [], [], []
    for i, f in enumerate(files):
        im = Image.open(f).convert("L")
        px = list(im.getdata())
        m = sum(px) / len(px)
        absf = start + i
        means.append((absf, m))
        if m < 20:
            dark.append((absf, round(m, 1)))
        if absf < 976 and m < 200:
            dark_early.append((absf, round(m, 1)))

    print("首 6 帧 mean :", [(a, round(b, 1)) for a, b in means[:6]])
    print("末 6 帧 mean :", [(a, round(b, 1)) for a, b in means[-6:]])
    print("mean 最低 3 帧:", sorted([(round(m, 1), a) for a, m in means])[:3])
    print("")
    print("纯黑帧 (<20)        : %d  %s" % (len(dark), dark[:12]))
    print("900..975 内 mean<200 : %d  %s" % (len(dark_early), dark_early[:12]))
    print("")
    print("→ %s" % ("OK：无黑闪" if not dark_early else "FAIL：早期区间存在暗帧"))
    raise SystemExit(0 if not dark_early else 1)
