# -*- coding: utf-8 -*-
"""为 Pot 宣传片挑 SFX：按动作语义搜索 Freesound（CC0），挑一条，下载并生成 manifest。

    python promo/scripts/pick-sfx.py            # 搜索 + 选 + 下载
    python promo/scripts/pick-sfx.py --dry      # 只搜索并打印候选，不下载

选择规则（写死在这里，可复核）：
  · 只要 CC0（search 端已按 cc0 过滤）
  · 单发动作：时长 0.2–6s 最优，>10s 扣分（那是环境音，要自己裁）
  · 打字底：反而要长样本（≥20s），一记一记从里面裁，比逐字拼同一个 click 自然
  · 同分看评分人数（popularity 只作辅助证据）
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "data" / "skills" / "video-shotcraft" / "assets" / "scripts" / "sfx-source.py"
OUT = ROOT / "promo" / "public" / "audio" / "sfx"

# (slot, 查询, 期望时长区间, 备注)
SLOTS = [
    ("typing", "mechanical keyboard typing", (18.0, 240.0), "逐字键盘底：长样本，按帧裁"),
    ("card-whoosh", "paper slide whoosh", (0.2, 4.0), "一句话凝成卡：纸/短 whoosh"),
    ("deal-whoosh", "whoosh transition", (0.2, 3.0), "卡片飞入"),
    ("land-thud", "thud impact wood", (0.15, 3.0), "落进槽位：实而短"),
    ("reject-buzz", "buzz electric short", (0.15, 2.5), "校验红拒：闷、不刺耳"),
    ("claim-click", "mechanical switch click", (0.05, 2.0), "认领：真实开关拟音"),
    ("stamp", "rubber stamp paper", (0.1, 3.0), "完成：盖章"),
    ("return-swoosh", "swoosh", (0.3, 2.0), "报告落回会话"),
    ("riser", "riser", (0.8, 5.0), "收尾铺垫"),
    ("sparkle", "glass ping", (0.2, 3.0), "字标落定的一点光（真玻璃声，不要卡通音）"),
]


def search(q: str, limit: int = 12):
    r = subprocess.run(
        [sys.executable, str(TOOL), "search", q, "--limit", str(limit)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if r.returncode != 0:
        print("  ! search failed:", (r.stdout + r.stderr).strip()[:200])
        return []
    try:
        return json.loads(r.stdout).get("results", [])
    except json.JSONDecodeError:
        print("  ! bad json")
        return []


def pick(results, lo, hi):
    # 硬排除：离期望区间太远的不进候选（508s 的整段音乐被当 buzz 就是这样漏进来的）
    results = [x for x in results if lo * 0.4 <= float(x.get('duration_seconds') or 0) <= hi * 5]
    def score(x):
        d = float(x.get("duration_seconds") or 0)
        s = 0.0
        if lo <= d <= hi:
            s += 100
        else:
            dist = (lo - d) if d < lo else (d - hi)
            s -= min(80.0, dist * 18)
        s += min(20.0, (x.get("rating_count") or 0) ** 0.5)
        s += (x.get("rating") or 0) * 2
        return s

    return max(results, key=score) if results else None


def main() -> int:
    dry = "--dry" in sys.argv
    chosen = []
    for slot, q, rng, note in SLOTS:
        res = search(q)
        best = pick(res, *rng)
        if not best:
            print("%-14s NONE" % slot)
            continue
        print("%-14s %-44s %6.2fs  %s  (%s)" % (slot, best["title"][:44], best["duration_seconds"],
                                                best["id"], best.get("license_label")))
        chosen.append((slot, best["id"], note))

    if dry:
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    ids = [c[1] for c in chosen]
    print("\ndownloading %d files -> %s" % (len(ids), OUT))
    r = subprocess.run(
        [sys.executable, str(TOOL), "get", *ids, "--out-dir", str(OUT), "--license", "cc0", "--workers", "3"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    print((r.stdout or "")[-1500:])
    if r.returncode != 0:
        print("!! get failed:", (r.stderr or "")[-800:])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
