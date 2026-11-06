from PIL import Image, ImageChops
import subprocess, os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
os.makedirs(r"out\qa\seam2", exist_ok=True)
for n in (914, 915):
    subprocess.run(["ffmpeg","-y","-v","error","-i","out/pot-promo.mp4",
                    "-vf", f"select='eq(n\\,{n})'", "-fps_mode","passthrough",
                    rf"out\qa\seam2\f{n}.png"], check=True)
a = Image.open(r"out\qa\seam2\f914.png").convert("RGB")
b = Image.open(r"out\qa\seam2\f915.png").convert("RGB")
d = ImageChops.difference(a, b)
bbox = d.getbbox()
hist = d.convert("L").histogram()
nonzero = sum(hist[1:])
maxdiff = max(i for i, v in enumerate(hist) if v > 0)
print(f"914 vs 915 -> max channel diff = {maxdiff}, nonzero px = {nonzero} / {a.size[0]*a.size[1]}, bbox = {bbox}")
