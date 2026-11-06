from PIL import Image
import os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
im = Image.open(r"public\textures\chat-full-zh-2x.png").convert("RGB")
W, H = im.size
print("texture", W, H)
px = im.load()
# page px = texture px / 2
def sample(x, y):
    return px[int(x*2), int(y*2)]

# classify a row: does x range 285..950 contain white-ish block (>=252 all channels) or bluish?
rows = []
for y in range(60, 1080, 1):
    white = 0
    blue = 0
    for x in range(285, 950, 5):
        r, g, b = sample(x, y)
        if r >= 252 and g >= 252 and b >= 252:
            white += 1
        elif b > r + 6 and b > 244:
            blue += 1
    rows.append((y, white, blue))

# group contiguous rows with white>=80 or blue>=60
def groups(pred):
    out = []
    for y, w, b in rows:
        if pred(w, b):
            if out and y == out[-1][1] + 1:
                out[-1][1] = y
            else:
                out.append([y, y])
    return out

g = groups(lambda w, b: w >= 80 or b >= 60)
for a, b in g:
    if b - a >= 8:
        print(f"block y {a}..{b}   h={b-a+1}  center={(a+b)/2:.0f}")
