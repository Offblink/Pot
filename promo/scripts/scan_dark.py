import subprocess, os, glob
from PIL import Image
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
out = r"out\qa\allframes"
os.makedirs(out, exist_ok=True)
for f in glob.glob(os.path.join(out, "*.png")):
    os.remove(f)
# 8 fps decimation-free: we need every frame, so extract all at 1/4 scale
subprocess.run(["ffmpeg","-y","-v","error","-i","out/pot-promo.mp4",
                "-vf","scale=480:270","-fps_mode","passthrough",
                os.path.join(out,"a_%04d.png")], check=True)
files = sorted(glob.glob(os.path.join(out,"a_*.png")))
print("total frames:", len(files))
dark = []
for i, f in enumerate(files):
    im = Image.open(f).convert("L")
    px = list(im.getdata())
    mean = sum(px) / len(px)
    if mean < 20:
        dark.append((i, round(mean, 1)))
print("dark frames (<20):", len(dark))
# group consecutive
groups = []
for idx, m in dark:
    if groups and idx == groups[-1][1] + 1:
        groups[-1][1] = idx
    else:
        groups.append([idx, idx])
for a, b in groups:
    print(f"  frames {a}..{b}  ({b-a+1} frames, {a/30:.2f}s..{b/30:.2f}s)")
