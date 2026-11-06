# -*- coding: utf-8 -*-
"""打印 audio-manifest.json 的关键测量值（钉帧要用：峰值时刻 / 有效窗 / 峰值电平）。"""
import json
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "public" / "audio" / "sfx" / "audio-manifest.json"
m = json.loads(p.read_text(encoding="utf-8"))
assets = m.get("assets") or []
print("%-18s %-9s %6s %7s %6s %6s %s" % ("file", "id", "dur", "peakdB", "pk_t", "end", "title"))
for a in assets:
    meas = a.get("analysis") or {}
    print("%-18s %-9s %6.2f %7.2f %6.3f %6.2f %s" % (
        a.get("file"), str(a.get("id", "")).replace("fs:", ""),
        meas.get("duration_seconds") or 0, meas.get("sample_peak_dbfs") or 0,
        meas.get("energy_peak_seconds") or 0, meas.get("active_end_seconds") or 0,
        (a.get("title") or "")[:44],
    ))
print("\nlicenses:", sorted({(a.get("license_label") or a.get("license") or "?") for a in assets}))
