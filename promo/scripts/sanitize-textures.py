# -*- coding: utf-8 -*-
"""把 textures 里带 `@` 的文件名复制成 ASCII 安全名（`-2x`）。

Remotion 的 staticFile() 对 `@` 会做两次 URL 编码（`@` → `%40` → `%2540`），
随后报 "already prefixed with the static base /public" 而拒绝加载。
阶段 4 的采集产物文件名保持原样（design-spec / 采集 README 都按 `@2x` 引用），
这里只是给 Remotion 生成一份同名不同字的副本；改图后重跑一次即可。
"""
import shutil
from pathlib import Path

TEX = Path(__file__).resolve().parents[1] / "public" / "textures"

n = 0
for p in sorted(TEX.glob("*@2x.png")):
    dst = p.with_name(p.name.replace("@2x.png", "-2x.png"))
    shutil.copy2(p, dst)
    n += 1
print("copied", n, "textures ->", TEX)
