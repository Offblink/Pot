# -*- coding: utf-8 -*-
"""打印左右边缘若干像素的颜色，判断有没有残余的 1px 边线 / 露底。"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
im = Image.open(ROOT / "out" / "qa" / "fixS1b-90.png").convert("RGB")
print("left :", [(x, im.getpixel((x, 785))) for x in (0, 1, 2, 3, 5, 8, 12, 20, 26, 30)])
print("right:", [(x, im.getpixel((x, 785))) for x in (1690, 1700, 1705, 1710, 1720, 1740, 1880, 1895, 1900, 1903, 1910, 1919)])
print("top  :", [(y, im.getpixel((900, y))) for y in (0, 120, 168, 200, 240, 300)])
