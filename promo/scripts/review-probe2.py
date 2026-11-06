# -*- coding: utf-8 -*-
"""终检取证②：S3 撞停帧文字锐度裁切 + 各镜 overlay 文字的实际屏幕像素高。"""
from pathlib import Path

from PIL import Image

QA = Path(__file__).resolve().parents[1] / "out" / "qa"

# ① S3 344：板标题行放大 3 倍看锐度
im = Image.open(QA / "review-S3-2.png").convert("RGB")
im.crop((500, 90, 900, 190)).resize((1200, 300), Image.NEAREST).save(QA / "review-S3-text-zoom.png")
print("S3-344 crop saved")

# ② 把各镜 overlay 文字的字号与相机 zoom 换算成屏幕像素高（Q11 判定）
rows = [
    ("S1 打字（PageCam 内 38px）", 38, 1.15),
    ("S1 字幕（屏幕空间 60px）", 60, 1.0),
    ("S2 卡标题（PageCam 内 14.5px @ 落定）", 14.5, 1.45),
    ("S2 字幕 60px", 60, 1.0),
    ("S3 卡标题 14.5px @ 撞停", 14.5, 2.15),
    ("S3 校验条 chip 13px @ 撞停", 13, 2.15),
    ("S3 校验条 mono 12.5px @ 撞停", 12.5, 2.15),
    ("S5 报告卡标题 14.5px（屏幕空间）", 14.5, 1.0),
    ("S5 报告卡正文 13px（屏幕空间）", 13, 1.0),
    ("S4 轨道标签 11.5px @ zoom 1.18", 11.5, 1.18),
    ("S6 字标 180px", 180, 1.0),
    ("S6 tail 44px", 44, 1.0),
]
print("\n%-38s %7s %6s %7s %7s" % ("元素", "源码px", "zoom", "屏幕px", "占帧高"))
for name, fs, z in rows:
    px = fs * z
    print("%-38s %7.1f %6.2f %7.1f %6.1f%%%s" % (name, fs, z, px, 100 * px / 1080,
                                                 "" if px >= 32 else "   <<Q11"))
