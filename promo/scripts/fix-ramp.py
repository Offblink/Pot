# -*- coding: utf-8 -*-
"""把 `ramp(f, start, duration)` 形态的调用改成显式的 `rampD(f, start, duration)`。

背景：helpers 里的 `ramp(frame, a, b, easing)` 第三参是**绝对结束帧**，
但我在几个镜头里顺手当成了"时长"。两者在 (a,b) 都很大时看不出差别，
在小帧号上就完全错窗口（S6 的 bgDark 直接恒等于 1，整帧变黑）。

规则：`ramp(f, X, Y[, E])` 里 Y 不含 '+' 且 Y < 60 而 X >= 60 → 视为时长。
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
pat = re.compile(r"ramp\(\s*f\s*,\s*([^,()]+?)\s*,\s*([^,()]+?)\s*(,\s*[^()]+?)?\)")

total = 0
for p in sorted(SRC.rglob("*.tsx")):
    text = p.read_text(encoding="utf-8")
    out = []
    last = 0
    n = 0
    for m in pat.finditer(text):
        a, b = m.group(1).strip(), m.group(2).strip()
        try:
            av, bv = int(a), int(b)
        except ValueError:
            continue
        if bv < 60 and av >= 60:
            out.append(text[last:m.start()])
            out.append("rampD(f, %s, %s%s)" % (a, b, m.group(3) or ""))
            last = m.end()
            n += 1
    if n:
        out.append(text[last:])
        p.write_text("".join(out), encoding="utf-8")
        print("%-12s %d" % (p.name, n))
        total += n
print("total", total)
