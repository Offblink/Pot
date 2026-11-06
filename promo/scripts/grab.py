import subprocess, os
os.chdir(r"C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo")
os.makedirs(r"out\qa\mig", exist_ok=True)
for n in (960, 968, 975, 984, 1015, 1134, 1199):
    out = rf"out\qa\mig\f{n}.png"
    subprocess.run(["ffmpeg","-y","-v","error","-i","out/pot-promo.mp4",
                    "-vf", f"select='eq(n\\,{n})'", "-fps_mode","passthrough", out], check=True)
    print("wrote", out)
