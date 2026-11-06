# -*- coding: utf-8 -*-
"""修复被 PowerShell 脚本块替换写坏的 helpers import 行（上一步的副作用）。

坏行形如：`param($m) $inner=$m.Groups[1].Value; ...`（被当成源码写进去了）。
这里统一换成一行的完整 import（超集，未用到的名字无害）。
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "shots"
GOOD = (
    "import { E, ramp, rampD, segLinear, mix, clamp01, mulberry32, dampedSettle } from '../lib/helpers';"
)

for p in sorted(SRC.glob("*.tsx")):
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    hit = 0
    for ln in lines:
        if "param($m)" in ln:
            out.append(GOOD + "\n")
            hit += 1
        else:
            out.append(ln)
    if hit:
        p.write_text("".join(out), encoding="utf-8")
        print("%-10s fixed %d" % (p.name, hit))
