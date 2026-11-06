from PIL import Image
import os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
im = Image.open(r"public\textures\chat-full-zh-2x.png").convert("RGB")
px = im.load()
BG = (246, 247, 249)
def diff(c):
    return max(abs(c[0]-BG[0]), abs(c[1]-BG[1]), abs(c[2]-BG[2]))

rows = []
for y in range(60, 1080):
    n = 0
    for x in range(285, 980, 3):
        if diff(px[x*2, y*2]) > 3:
            n += 1
    rows.append((y, n))

# contiguous rows where n >= 60 (a filled block across most of the column)
out = []
for y, n in rows:
    if n >= 60:
        if out and y == out[-1][1] + 1:
            out[-1][1] = y
        else:
            out.append([y, y])
print("=== filled bands (n>=60) ===")
for a, b in out:
    if b - a >= 6:
        print(f"y {a:4d}..{b:4d}  h={b-a+1:3d}  center={(a+b)/2:6.1f}")

# also print n per row coarsely for the interesting range
print("\n=== row profile 130..520 (every 6px) ===")
for y, n in rows:
    if 130 <= y <= 520 and y % 6 == 0:
        print(f"{y:4d} {n:4d} {'#'*min(n//4, 60)}")
