# -*- coding: utf-8 -*-
"""第二遍：`ramp(f, X, SMALL)` 里 X 是常量表达式（如 CLAIM + 12）的情况，
上一遍的正则因含 '+' 跳过了。这里按"第三参 < 60 且第二参不是小常量"统一改成 rampD。
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
pat = re.compile(r"ramp\(\s*(f|frame)\s*,\s*([^,]+?)\s*,\s*(-?\d+)\s*(,\s*[^()]+?)?\)")

total = 0
for p in sorted(SRC.rglob("*.tsx")):
    text = p.read_text(encoding="utf-8")
    out, last, n = [], 0, 0
    for m in pat.finditer(text):
        dur = int(m.group(3))
        head = m.group(2).strip()
        # 只处理"时长"形态：第三参是 1..59 的整数，且第二参不是 0/小字面量
        if not (1 <= dur < 60):
            continue
        try:
            if int(head) < 60:
                continue
        except ValueError:
            pass
        out.append(text[last:m.start()])
        out.append("rampD(%s, %s, %s%s)" % (m.group(1), head, m.group(3), m.group(4) or ""))
        last = m.end()
        n += 1
    if n:
        out.append(text[last:])
        p.write_text("".join(out), encoding="utf-8")
        print("%-12s %d" % (p.name, n))
        total += n
print("total", total)
