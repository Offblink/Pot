# -*- coding: utf-8 -*-
"""逐镜静帧验收（一条命令出全部验收帧）。

    python scripts/qa-stills.py            # 出 S1–S6 的全部验收帧
    python scripts/qa-stills.py S4 600     # 只出一张

本机必须带 --browser-executable（缓存的 headless shell 在这台机器上起不来），
见 promo/notes.md。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

FRAMES = [
    ("S1-a", 60), ("S1-b", 100),
    ("S2-a", 138), ("S2-b", 200), ("S2-c", 292),
    ("S3-a", 348), ("S3-b", 500), ("S3-c", 524),
    ("S4-a", 600), ("S4-b", 668),
    ("S5-a", 712), ("S5-b", 880),
    ("S6-a", 980), ("S6-b", 1100), ("S6-c", 1160),
]


def still(name: str, frame: int) -> bool:
    (ROOT / "out" / "qa").mkdir(parents=True, exist_ok=True)
    cmd = [
        "npx", "remotion", "still", "src/index.tsx", "PotPromo",
        f"out/qa/{name}.png", f"--frame={frame}",
        f"--browser-executable={BROWSER}", "--log=error",
    ]
    print(f"=== {name} @ {frame}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
        print("  FAILED:\n   " + "\n   ".join(tail), flush=True)
        return False
    return True


def main() -> int:
    if len(sys.argv) >= 3:
        ok = still(sys.argv[1], int(sys.argv[2]))
        return 0 if ok else 1
    bad = [n for n, f in FRAMES if not still(n, f)]
    print("FAILED:", bad if bad else "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
