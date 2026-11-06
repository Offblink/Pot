# -*- coding: utf-8 -*-
"""S3 修复卡的自检：量「板在画里四边留白」「校验条 × 卡行文字重叠」「收尾方块是否在画内」。

    python promo/scripts/check-s3.py

判据（来自卡面）：
  · 撞停帧（342/344/352）：整块板四边留白 ≥ 40 屏幕像素
  · 校验条与任何卡行文字的**重叠面积 = 0**
  · 收尾帧（444 之后）：认领的像素方块与租约环在画内（特写帧不要求，那时本来就看板）

不靠目测：板框/行框来自 layout.json（页面 CSS px），相机常数从 S3.tsx 读，
两者一乘就是屏幕矩形；元素两两求交得重叠面积。每帧都给数字。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080

layout = json.loads((ROOT / "src" / "layout.json").read_text(encoding="utf-8"))


def box(name: str):
    e = layout["elements"][name]
    return (e["x"], e["y"], e["width"], e["height"])


BOARD = box("board")                  # 876, 325.5, 440, 429
ROW_TODO = box("card-row-todo")       # 890, 534.5, 412, 36
ROW_DOING = box("card-row-doing")     # 890, 450.5, 412, 36
AGENT_EXEC1 = box("agent-exec-1")
BOX_BAY_TOP = box("bay-exec-1")

src = (ROOT / "src" / "shots" / "S3.tsx").read_text(encoding="utf-8")
CLOSE_ZOOM = float(re.search(r"CLOSE_ZOOM = ([\d.]+)", src).group(1))
FAR_ZOOM = float(re.search(r"FAR_ZOOM = ([\d.]+)", src).group(1))
PULL_CY = float(re.search(r"PULL_CY = ([\d.]+)", src).group(1))

# 校验条（源码：left=board.x, top=board.y-34, w=board.w, h=22）
STRIP = (BOARD[0], BOARD[1] - 34, BOARD[2], 22)
CX = BOARD[0] + BOARD[2] / 2          # BOARD_CENTER.x

ROWS = [("row-todo", ROW_TODO), ("row-doing", ROW_DOING)]


def screen(b, cx, cy, zoom):
    x, y, w, h = b
    return (960 + (x - cx) * zoom, 540 + (y - cy) * zoom, w * zoom, h * zoom)


def overlap(a, b):
    ox = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    oy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ox * oy


def report(label, cy, zoom, need_agent):
    bx, by, bw, bh = screen(BOARD, CX, cy, zoom)
    left, top = bx, by
    right, bottom = W - (bx + bw), H - (by + bh)
    ok_box = min(left, top, right, bottom) >= 40
    print("\n[%s]  zoom=%.2f  cy=%.0f" % (label, zoom, cy))
    print("  板屏幕矩形 : x %.1f..%.1f  y %.1f..%.1f  (%.0f×%.0f)" % (bx, bx + bw, by, by + bh, bw, bh))
    print("  四边留白   : 左 %.1f  上 %.1f  右 %.1f  下 %.1f  → %s (阈值 40)"
          % (left, top, right, bottom, "OK" if ok_box else "FAIL"))

    st = screen(STRIP, CX, cy, zoom)
    worst = 0.0
    for name, b in ROWS:
        a = overlap(st, screen(b, CX, cy, zoom))
        worst = max(worst, a)
        if a > 0:
            print("  重叠!  校验条 × %s : %.0f px²" % (name, a))
    print("  校验条     : y %.1f..%.1f，与卡行最大重叠 %.0f px² → %s"
          % (st[1], st[1] + st[3], worst, "OK" if worst == 0 else "FAIL"))

    ag = screen(AGENT_EXEC1, CX, cy, zoom)
    in_view = (ag[0] >= 0 and ag[0] + ag[2] <= W and ag[1] >= 0 and ag[1] + ag[3] <= H)
    flag = "" if (in_view or not need_agent) else "  FAIL"
    print("  执行者方块 : x %.0f..%.0f  y %.0f..%.0f  → %s%s"
          % (ag[0], ag[0] + ag[2], ag[1], ag[1] + ag[3],
             "在画内" if in_view else "在画外（本帧不要求）", flag))

    # 收尾帧还要看字幕带（S3 放顶部：top 126，高约 100）有没有压到工位或板
    cap_ok = True
    if need_agent:
        cap = (0.0, 126.0, float(W), 100.0)
        bay = screen((BOX_BAY_TOP[0], BOX_BAY_TOP[1], BOX_BAY_TOP[2], BOX_BAY_TOP[3]), CX, cy, zoom)
        a1 = overlap(cap, bay)
        a2 = overlap(cap, screen(BOARD, CX, cy, zoom))
        cap_ok = a1 == 0 and a2 == 0
        print("  S3 字幕带   : y 126..226，压工位 %.0f px²、压板 %.0f px² → %s"
              % (a1, a2, "OK" if cap_ok else "FAIL"))
    return ok_box and worst == 0 and (in_view or not need_agent) and cap_ok


ok = True
ok &= report("撞停 342 / 344 / 352（特写：板在框内 + 校验条不压字）", 540.0, CLOSE_ZOOM, need_agent=False)
ok &= report("收尾 480（认领：方块 + 租约环要在画内）", PULL_CY, FAR_ZOOM, need_agent=True)

print("\nALL OK" if ok else "\n有 FAIL —— 见上面逐项")
raise SystemExit(0 if ok else 1)
