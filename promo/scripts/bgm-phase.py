# -*- coding: utf-8 -*-
"""找 BGM 的第一拍相位：把候选段落解成 8kHz 单声道，算能量包络的差分，
取最陡的上升沿作为下拍位置（不再依赖 librosa，本机没装）。

    python promo/scripts/bgm-phase.py <in.mp3> <搜索起点秒> <搜索窗秒>
→ 打印最陡上升沿相对 <搜索起点> 的秒数（这个值用来 -ss 微调，让第一拍落在 t=0）
"""
import struct
import subprocess
import sys
import wave
from pathlib import Path

src = sys.argv[1]
start = float(sys.argv[2]) if len(sys.argv) > 2 else 24.0
win = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

tmp = Path(__file__).resolve().parent / "_phase.wav"
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(win), "-i", src,
     "-ac", "1", "-ar", "8000", str(tmp)],
    check=True,
)
with wave.open(str(tmp), "rb") as w:
    n = w.getnframes()
    raw = w.readframes(n)
samples = struct.unpack("<%dh" % n, raw)

hop = 80  # 10 ms
env = []
for i in range(0, n - hop, hop):
    seg = samples[i:i + hop]
    env.append(sum(abs(x) for x in seg) / hop)

# onset strength = 正向差分，再取最大值（带 30ms 的最小平滑）
best, best_i = 0.0, 0
for i in range(3, len(env) - 1):
    d = env[i] - env[i - 3]
    if d > best:
        best, best_i = d, i
print("phase_offset=%.3f" % (best_i * hop / 8000.0))
tmp.unlink(missing_ok=True)
