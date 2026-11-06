# -*- coding: utf-8 -*-
"""S1 返工取证：输入区上下白场的范围、页面底部颜色、上一版接缝的位置与色差。"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
im = Image.open(ROOT / "public" / "textures" / "chat-full-zh-2x.png").convert("RGB")

print("== 列 x=1200（消息区内）页面 y 960..1079 ==")
prev = None
for y in range(960, 1080):
    c = im.getpixel((1200 * 2, y * 2))
    if c != prev:
        print("   y=%4d → %s" % (y, c))
        prev = c

print("\n== 列 x=340（输入框内左侧空白）页面 y 985..1079 ==")
prev = None
for y in range(985, 1080):
    c = im.getpixel((340 * 2, y * 2))
    if c != prev:
        print("   y=%4d → %s" % (y, c))
        prev = c

print("\n== 行 y=1030 页面 x 272..300 / 1740..1780 ==")
for x in list(range(272, 300, 4)) + list(range(1740, 1782, 4)):
    print("   x=%4d → %s" % (x, im.getpixel((x * 2, 1030 * 2))))

print("\n== chat-report 切片（会话里那条消息）==")
rep = Image.open(ROOT / "public" / "textures" / "chat-report-2x.png").convert("RGB")
print("   尺寸", rep.size, " 左上角像素", rep.getpixel((2, 2)), " 中心", rep.getpixel((rep.size[0] // 2, rep.size[1] // 2)))
