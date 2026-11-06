# -*- coding: utf-8 -*-
"""终检抽帧：每镜 ≥3 帧，落成 review-<shot>-<n>.png（一条 ffmpeg 解一次，再改名）。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "out" / "qa"
MP4 = ROOT / "out" / "pot-promo.mp4"

FRAMES = [
    ("S1", 30), ("S1", 60), ("S1", 110),
    ("S2", 135), ("S2", 200), ("S2", 280),
    ("S3", 320), ("S3", 344), ("S3", 500),
    ("S4", 560), ("S4", 620), ("S4", 680),
    ("S5", 700), ("S5", 780), ("S5", 880),
    ("S6", 950), ("S6", 1000), ("S6", 1100), ("S6", 1199),
]

sel = "+".join("eq(n\\,%d)" % f for _, f in FRAMES)
tmp = QA / "_review-seq-%03d.png"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(MP4),
                "-vf", "select='%s'" % sel, "-fps_mode", "passthrough", str(tmp)], check=True)

made = 0
for i, (shot, frame) in enumerate(FRAMES, start=1):
    src = QA / ("_review-seq-%03d.png" % i)
    dst = QA / ("review-%s-%d.png" % (shot, frame))
    if src.exists():
        src.replace(dst)
        made += 1
    else:
        print("MISSING", shot, frame)
print("wrote", made, "review frames")
