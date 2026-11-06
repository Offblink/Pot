# -*- coding: utf-8 -*-
"""终检用的取证脚本：裁图、量色、扫敏感串。

    python promo/scripts/review-probe.py
"""
import re
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "out" / "qa"
MP4 = ROOT / "out" / "pot-promo.mp4"


def grab(frame: int, name: str):
    p = QA / name
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(MP4),
                    "-vf", "select=eq(n\\,%d)" % frame, "-frames:v", "1", str(p)], check=True)
    return p


# ① S5 报告卡片区放大（看正文可读性）
p = grab(780, "review-S5-3.png")
im = Image.open(p).convert("RGB")
print("S5-780", im.size)
im.crop((1060, 280, 1460, 570)).resize((800, 580), Image.LANCZOS).save(QA / "review-S5-cards-zoom.png")

# ② S6 950 暗场纯度
p = grab(950, "review-S6-1.png")
im = Image.open(p).convert("RGB")
print("S6-950 corners", im.getpixel((5, 5)), im.getpixel((1915, 1075)), "center", im.getpixel((960, 540)))

# ③ 数据安全：扫源码里的可疑串
pats = [r"C:\\Users", r"sk-[A-Za-z0-9]{8,}", r"api[_-]?key", r"deepseek", r"gpt-", r"claude",
        r"用户名", r"@[a-z0-9]+\.com"]
print("\n源码敏感串扫描（src/ + public 纹理名）：")
hits = 0
for f in sorted(list((ROOT / "src").rglob("*.ts*")) + list((ROOT / "src").rglob("*.json"))):
    t = f.read_text(encoding="utf-8", errors="ignore")
    for pat in pats:
        for m in re.finditer(pat, t):
            print("  %s: %s ... %s" % (f.name, pat, t[max(0, m.start() - 20):m.start() + 40].replace("\n", " ")))
            hits += 1
print("  命中数：", hits)
