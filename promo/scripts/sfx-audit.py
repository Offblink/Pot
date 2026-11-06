# -*- coding: utf-8 -*-
"""逐条 SFX 对帧测量（不是试听，是测量）：证明每条钉帧在成片音轨里真的响了。

    python promo/scripts/sfx-audit.py out/pot-promo-nobgm.mp4
    python promo/scripts/sfx-audit.py out/pot-promo.mp4     # 带 BGM 版：看会不会被盖

关键：**不复制第二份帧号表**。这里直接解析 `src/timeline.ts`（SHOTS 的 from）与
`src/audio.ts`（CUES 的 shot/offset/dur/peakLag + OUTPUT_OFFSET_FRAMES），
再按 audio.ts 里同一个公式 `from = SHOTS.x.from + offset − peakLag − OUTPUT_OFFSET` 重算。

方法：音轨解成 8kHz 单声道，10ms 一格算 RMS；每条 cue 的窗口峰值 RMS 与
「全片 RMS 中位数」比，Δ ≥ 6dB 记为"听得见"。
"""
import math
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SR, HOP = 8000, 80  # 10ms


def parse():
    tl = (ROOT / "src" / "timeline.ts").read_text(encoding="utf-8")
    shots = {m.group(1): int(m.group(2)) for m in re.finditer(r"id: '(\w+)',\s*\n\s*from: (\d+)", tl)}
    au = (ROOT / "src" / "audio.ts").read_text(encoding="utf-8")
    off_m = re.search(r"OUTPUT_OFFSET_FRAMES = ([\d.]+)", au)
    out_off = float(off_m.group(1)) if off_m else 0.0
    cues = []
    for m in re.finditer(
        r"\{ shot: '(\w+)', offset: (\d+), file: '(\w+)',(.*?)note: '([^']*)' \}",
        au,
    ):
        shot, offset, fkey, mid, note = m.groups()
        dur = re.search(r"dur: (\d+)", mid)
        lag = re.search(r"peakLag: ([\d.]+)", mid)
        vol = re.search(r"volume: ([\d.]+)", mid)
        cues.append({
            "shot": shot, "offset": int(offset), "file": fkey, "note": note,
            "dur": int(dur.group(1)) if dur else 24,
            "peakLag": float(lag.group(1)) if lag else 0.0,
            "volume": float(vol.group(1)) if vol else 0.0,
        })
    for c in cues:
        c["from"] = round(shots[c["shot"]] + c["offset"] - c["peakLag"] - out_off)
    return cues, out_off


def rms_frames(path: Path):
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
    s = struct.unpack("<%dh" % n, raw)
    out = []
    for i in range(0, n - HOP, HOP):
        seg = s[i:i + HOP]
        out.append(10 * math.log10(max(sum(x * x for x in seg) / HOP, 1.0) / (32768.0 ** 2)))
    return out


def main() -> int:
    video = Path(sys.argv[1] if len(sys.argv) > 1 else "out/pot-promo-nobgm.mp4")
    if not video.is_absolute():
        video = (ROOT / video).resolve()
    if not video.exists():
        print("missing", video)
        return 2
    wav = ROOT / "out" / "_audit.wav"
    # 只看左声道：`-ac 1` 会把立体声相加，反相内容会互相抵消（本项目实测：whoosh /
    # buzz / stamp / riser 在 mono 下被抵消到静音，看着像"没渲染"）。
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video),
                    "-af", "pan=mono|c0=c0", "-ar", str(SR), str(wav)], check=True)
    rms = rms_frames(wav)
    cues, out_off = parse()
    srt = sorted(rms)
    median = srt[len(srt) // 2]

    print("video      :", video.name)
    print("cues       : %d（解析自 src/audio.ts；OUTPUT_OFFSET_FRAMES=%s）" % (len(cues), out_off))
    print("length     : %.2fs   median RMS %.1f dBFS" % (len(rms) / 100.0, median))
    print()
    print("%-5s %-4s %-6s %-5s %-7s %-7s %s" % ("shot", "off", "from", "dur", "peak", "Δ", "动作"))
    weak = 0
    for c in cues:
        a, b = int(c["from"] * 100 / 30), int((c["from"] + c["dur"]) * 100 / 30)
        seg = [x for x in rms[max(0, a):b] if x > -90]
        if not seg:
            print("%-5s %-4d %-6d %-5d %-7s %-7s %s  << 没响" % (c["shot"], c["offset"], c["from"], c["dur"], "-", "-", c["note"][:34]))
            weak += 1
            continue
        peak = max(seg)
        delta = peak - median
        flag = "" if delta >= 6 else "  << 太轻"
        if delta < 6:
            weak += 1
        print("%-5s %-4d %-6d %-5d %6.1f %+7.1f %s%s" % (
            c["shot"], c["offset"], c["from"], c["dur"], peak, delta, c["note"][:34], flag))
    wav.unlink(missing_ok=True)
    print("\nweak/none: %d / %d" % (weak, len(cues)))
    return 0 if weak == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
