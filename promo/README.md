# Pot 宣传片（promo）

40 秒 / 1920×1080 / 30fps / 1200 帧。用 Remotion 渲染，画面全部来自 **Pot 真实页面截图**
（`promo/public/textures/`，由 `promo/capture/capture.py` 采集），数据全部虚构。

## 一条命令重渲

```powershell
cd promo
npx remotion render src/index.ts PotPromo out/pot-promo.mp4 --browser-executable="C:\Program Files\Google\Chrome\Application\chrome.exe"
npx remotion render src/index.ts PotPromo out/pot-promo-nobgm.mp4 --props=props-nobgm.json --browser-executable="C:\Program Files\Google\Chrome\Application\chrome.exe"
```

- 第二版（无 BGM、保留 SFX）靠 `props-nobgm.json`（内容 `{"bgm":false}`）从**同一条时间线**渲出。
  Windows 必须走文件，不能内联 JSON。
- `--browser-executable` 在本机是**必需**的：`node_modules/.remotion/` 里缓存的 headless shell 起不来，
  用系统 Chrome 才能渲染。
- 单版约 4–5 分钟（`remotion.config.ts` 里 jpeg92 + concurrency 8）。

## 目录

```
promo/
  src/
    index.tsx        Composition 注册（PotPromo / 1200f / 30fps / 1920×1080）
    timeline.ts      ★ 唯一时间源：SHOTS / SUBTITLES / TRANSITIONS / SFX_CUES / RHYTHM
    PotPromo.tsx     按 SHOTS 排 Sequence；字幕层在这里（含 CAPTION_LAYOUT）
    audio.ts         BGM + 18 条 SFX 钉帧（from 一律 SHOTS.x.from + offset − peakLag − 1.3f）
    assets.ts        纹理 import 入口（webpack import，不走 staticFile，见下）
    audioAssets.ts   音频 import 入口
    sceneLayout.ts   layout.json 的几何常量（板/行/工位/输入槽）
    layout.json      采集阶段的 bbox 原始表（CSS px）
    lib/             PageCam / Caption / helpers / pot(tokens) / rand / motion
    shots/S1..S6.tsx 六个镜头
    workbench.ts     动效工作台清单（每镜 component/props/schema）
  public/
    textures/        真实页面截图（3840×2160 的 @2x + 元素切片）
    audio/bgm/       pot-bgm-120bpm.mp3（House Vibez，123→120 BPM）
    audio/sfx/       10 个 CC0 素材 + audio-manifest.json + FREESOUND-CREDITS.md
    audio/BGM-ATTRIBUTION.md
  capture/           采集脚本 + seed.json + README（阶段 4 的产物）
  scripts/           自检/取证脚本（见下表）
  out/               成片与 out/qa 静帧档案
```

## 怎么改文案

**只改 `src/timeline.ts` 的 `SHOTS[].caption` / `extraCaptions`** —— 它是唯一事实源，
字幕层由 `SUBTITLES` 派生，别处不要再写一份。

字幕位置在 `src/PotPromo.tsx` 的 `CAPTION_LAYOUT`（按镜头给 `placement` 与 `bottom`），
改之前先看那几行注释：每个位置都是跟该镜的取景算过的（避开板/工位/输入条）。

## 怎么改画面

按镜头改 `src/shots/S?.tsx`。每个文件顶部都写了「保留了哪张卡/变体的哪几条命门」与
「为 Pot 做了哪些适配」，改之前先读。

节奏命门（缓动、顿帧、震屏、相机关键帧）都是文件内常量，**不进 props**。

## 声音

- BGM：`src/audio.ts` 的 `BGM`（`volume 0.16`、120 BPM、相位 0.03s），授权见
  `public/audio/BGM-ATTRIBUTION.md`。
- SFX：`src/audio.ts` 的 `CUES`（18 条），全部 CC0，来源与许可见
  `public/audio/sfx/audio-manifest.json` 与 `FREESOUND-CREDITS.md`。
- 换音：用技能库的 `assets/scripts/sfx-source.py search/get`，下载到 `public/audio/sfx/`，
  再在 `src/audioAssets.ts` 里加一条 import。

## 动效工作台

```powershell
cd ..\data\skills\video-shotcraft
node workbench/scripts/open.mjs "C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo"
```

打开 http://localhost:5198 ，成片会被拆成 镜头 / 字幕 / 转场 / 音效 多轨，可逐项微调后导出。
清单在 `src/workbench.ts`。

## 自检脚本

| 脚本 | 用途 |
|---|---|
| `scripts/qa-stills.py` | 逐镜出验收静帧（`python scripts/qa-stills.py S4 600` 单张） |
| `scripts/check-plan.py` | 时间轴六段求和 = 1200 |
| `scripts/verify-shots.py` | 镜头卡名/style-key 在 `library.json` 里校验 |
| `scripts/check-s3.py` / `check-s3b.py` | S3 板四边留白、校验条与卡行重叠、侧栏特征像素 |
| `scripts/check-seam-s2s3.py` | S2 末帧与 S3 首帧的板框是否一致（Δ≤1px） |
| `scripts/check-s1.py` | S1 输入条四边距、底/顶条带色差 |
| `scripts/check-s6-dark.py` / `check-s6-uniform.py` | S6 暗场纯度、蒸发过程区域亮度差 |
| `scripts/sfx-audit.py <mp4>` | 逐条 SFX 在成片里是否真的测到 |
| `scripts/measure-input-row.py` / `probe-s1.py` | 从纹理里量真实输入框几何 |

## 两个已踩过的坑（改代码前先知道）

1. **`staticFile()` 在本机不可用**：`window.remotion_staticBase` 是 `/public`，
   `staticFile('textures/x.png')` 会被判「already prefixed」直接抛错；手工拼又会变
   `/public/public/...` 404。所以纹理与音频**全部走 webpack import**（`src/assets.ts`、
   `src/audioAssets.ts`）。加新素材要在这两个文件里加 import。
2. **纹理文件名不能带 `@`**：`@2x` 在 URL 里会被二次编码成 `%2540`。
   `scripts/sanitize-textures.py` 生成 `-2x` 副本（原文件保留），代码里用 `-2x` 那份。
