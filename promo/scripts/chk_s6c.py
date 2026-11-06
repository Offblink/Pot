from PIL import Image
import glob, os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
for f in sorted(glob.glob(r"out\qa\s6c-*.png")):
    im = Image.open(f).convert("RGB")
    px = im.load(); W, H = im.size
    bg = px[2, 2]
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if max(abs(r-bg[0]), abs(g-bg[1]), abs(b-bg[2])) > 12:
                xs.append(x); ys.append(y)
    if xs:
        cx = (min(xs)+max(xs))//2; cy = (min(ys)+max(ys))//2
        print(f"{os.path.basename(f)}: bg={bg} n={len(xs)} bbox=({min(xs)},{min(ys)})-({max(xs)},{max(ys)}) ctr=({cx},{cy})")
    else:
        print(f"{os.path.basename(f)}: bg={bg} UNIFORM")
