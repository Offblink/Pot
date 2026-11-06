# BGM 授权（Pot 宣传片）

本片 BGM 取自 video-shotcraft 技能的 BGM 备选库
（`data/skills/video-shotcraft/assets/audio/`，授权见同目录 `ATTRIBUTION.md`）。

| 工程内文件 | 原曲 | 艺术家 | 风格 | BPM | 许可 | 处理 |
|---|---|---|---|---|---|---|
| `public/audio/bgm/pot-bgm-120bpm.mp3` | House Vibez | Lily J | House | 123 → **120** | Mixkit Stock Music Free License（免署名、可商用） | `atempo=0.975610` 归一到 120 BPM；`-ss 24.630` 对齐下拍；40.0s，头 0.30s / 尾 1.5s 淡入淡出；48kHz 立体声 192kbps MP3 |

上游清单：https://assets.mixkit.co/music/745/745.mp3

## 为什么选这首

- 备选里 5 首的实测 BPM：tech-house ~124、cat-walk ~129、g-eazy-nba-type ~86、
  house-vibez ~123、tonight-hiphop ~103。本片设计定案写的是 **120 BPM 网格**
  （六段边界 120/300/540/690/915f 正好落在第 8/20/36/46/61 拍）。
- house-vibez 与 120 只差 2.4%：`atempo` 一个几乎听不出的变速就能让整片对上网格；
  其余四首要变 3.3%–12%，其中 103 BPM 那首要提 16.5%，鼓点会明显赶。
- 气质是稳态 house 底，没有大起大落的 drop，正好垫在"无旁白 + 字幕叙事"之下。

## 交付注意

- Mixkit 许可免署名，但**发布前建议自行复核一次**该曲目页面（上游 ATTRIBUTION.md 也这么写）。
- 成片交付两版：带 BGM（`pot-promo.mp4`）与不带 BGM（`pot-promo-nobgm.mp4`，保留 SFX），
  后者方便用户后期自配音乐。
