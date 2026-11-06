from PIL import Image
import glob, os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
for f in sorted(glob.glob(r"out\qa\mig\f*.png")):
    im = Image.open(f).convert("RGB")
    W, H = im.size
    px = im.load()
    # background = mode color of corners
    bg = px[2, 2]
    # logo = pixels far from bg
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if max(abs(r-bg[0]), abs(g-bg[1]), abs(b-bg[2])) > 12:
                xs.append(x); ys.append(y)
    name = os.path.basename(f)
    if xs:
        print(f"{name}: bg={bg} bbox=({min(xs)},{min(ys)})-({max(xs)},{max(ys)}) "
              f"center=({(min(xs)+max(xs))//2},{(min(ys)+max(ys))//2}) n={len(xs)}")
    else:
        print(f"{name}: bg={bg} NO CONTENT (uniform)")
