import subprocess, sys, os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
# extract frames 905..945 and report mean luminance
out = r"out\qa\f_seam"
os.makedirs(out, exist_ok=True)
cmd = ["ffmpeg","-y","-v","error","-i","out/pot-promo.mp4",
       "-vf","select='between(n,905,945)'","-fps_mode","passthrough",
       os.path.join(out,"s_%03d.png")]
subprocess.run(cmd, check=True)
from PIL import Image
import glob
files = sorted(glob.glob(os.path.join(out,"s_*.png")))
print("frames:", len(files))
for i,f in enumerate(files):
    im = Image.open(f).convert("L").resize((192,108))
    px = list(im.getdata())
    mean = sum(px)/len(px)
    print(f"frame {905+i:4d}  mean={mean:6.2f}  {'<== BLACK' if mean < 20 else ''}")
