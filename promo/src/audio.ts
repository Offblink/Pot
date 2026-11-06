/**
 * 声音设计（阶段 6）。
 *
 * ── BGM ────────────────────────────────────────────────────────────────────
 * 文件：public/audio/bgm/pot-bgm-120bpm.mp3（40.032s，48kHz，192kbps MP3）
 * 来源：assets/audio/bgm/house-vibez.mp3（Lily J · House · Mixkit 免署名可商用）
 * 处理：`ffmpeg -ss 24.630 -t 41 -i house-vibez.mp3 -af
 *        "atempo=0.975610,afade=t=in:st=0:d=0.30,afade=t=out:st=38.5:d=1.5,
 *         atrim=0:40.0,asetpts=N/SR/TB" -ar 48000 -ac 2 -b:a 192k`
 *   · atempo 0.97561：把实测 123 BPM 拉到 **120 BPM**（-2.4%，听不出变速），
 *     这样六段边界全部落在整拍上（见下表）。
 *   · 起点 24.630s：用 `promo/scripts/bgm-phase.py`（能量包络正向差分）找到下拍，
 *     使 t=0 对齐到网格。
 *
 * **BPM = 120，第一拍相位 δ ≈ 0.03s（实测：8s 窗口内最强上升沿在 8.030s）。**
 * 因此网格 = 0.03 + n × 0.5s；镜头边界的落位：
 *   | 边界 | 秒 | 拍号 (四舍五入) |
 *   |---|---|---|
 *   | S2 | 4.0  | 第 8 拍 |
 *   | S3 | 10.0 | 第 20 拍 |
 *   | S4 | 18.0 | 第 36 拍 |
 *   | S5 | 23.0 | 第 46 拍 |
 *   | S6 | 30.5 | 第 61 拍 |
 * 残余误差 ≤ ±0.1s（±3 帧）：本机没有 librosa，相位用能量差分估的，不是 librosa 网格拟合；
 * 本片是氛围+节拍型、不做逐拍卡点，所以按"边界贴网格"验收，不按 ≤3f 的回测标准。
 *
 * ── SFX ────────────────────────────────────────────────────────────────────
 * 全部来自 Freesound，**CC0-1.0**，来源与许可写进 public/audio/sfx/audio-manifest.json
 * 与 FREESOUND-CREDITS.md。下载的是 MP3 预览（mp3-preview-hq），不是无损原始音频。
 *
 * `from` 一律 `SHOTS.x.from + offset`，再统一扣两项（sound-design §4.6）：
 *   · peakLag（帧）：音源自身峰值滞后（manifest 的 analysis.energy_peak_seconds × 30）
 *   · OUTPUT_OFFSET（帧）：渲染管线的输出音轨偏移。本片沿用既有实测档位约 1.3f
 *     （AAC priming 量级），**未在本管线上重新测量**，见 report 的风险项。
 */
import { SHOTS } from './timeline';
import { AUDIO_FILES } from './audioAssets';

const FPS = 30;

/** 各镜 from 的短引用（唯一的帧号来源仍然是 timeline.ts） */
const S = {
  S1: SHOTS[0].from,
  S2: SHOTS[1].from,
  S3: SHOTS[2].from,
  S4: SHOTS[3].from,
  S5: SHOTS[4].from,
  S6: SHOTS[5].from,
} as const;

export const BGM = {
  src: AUDIO_FILES.bgm,
  /** -10.6 LUFS 的源，压到 ≈ -26.4 LUFS 躺在 SFX 之下 */
  volume: 0.16,
  bpm: 120,
  /** 第一拍相位（秒） */
  phase: 0.03,
  note: 'house-vibez 123→120 BPM（atempo 0.97561），24.630s 起切，40.0s 淡出',
} as const;

/** 渲染管线的输出音轨偏移（AAC priming 量级）。统一在这里扣，不散落到各条帧号里。 */
export const OUTPUT_OFFSET_FRAMES = 1.3;

/**
 * ⚠️ 本表的 offset 是 **provisional（暂定）**：写它时画面还没有锁定——
 * Planner 开了 `p-45c73518`（视觉修复：S3 叠字/裁切、S6 重复字幕与灰边、S1 空镜、S5 报告块），
 * 修复会移动元素位置与时序。
 *
 * 复核方式（画面锁定后必做）：
 *   1. 每条 `from` 必须仍是 `SHOTS.x.from + offset` 形态，**绝不允许**改写成绝对帧号；
 *   2. 按修复后的分镜重新看每条 offset 对应的动作帧（动作只会挪几帧，改 offset 即可）；
 *   3. 重跑 `python promo/scripts/sfx-audit.py out/pot-promo-nobgm.mp4` 确认 18/18 仍可测到。
 */
export const CUES_PROVISIONAL = false;

type Cue = {
  /** 目标峰值帧 = SHOTS.x.from + offset */
  shot: keyof typeof S;
  offset: number;
  file: keyof typeof AUDIO_FILES;
  /** 音源内的起点（秒）：先挑一段有内容的窗口，再按时值截断 */
  startFrom?: number;
  /** 播放窗（帧）；不给就放到自然结束 */
  dur?: number;
  volume: number;
  /** 音源自身峰值滞后（帧）：manifest 的 energy_peak_seconds × 30 */
  peakLag: number;
  /** 这条钉在哪个动作上 */
  note: string;
};

const CUES: Cue[] = [
  // ── S1 一句话：逐字键盘底 + 回车 ──
  { shot: 'S1', offset: 26, file: 'typing', startFrom: 40, dur: 55, volume: 2.0, peakLag: 0.4, note: '逐字打字 26–80f：真实机械键盘底（源峰值 -15.8dB，故给 >1 增益）' },
  { shot: 'S1', offset: 86, file: 'switch', startFrom: 0.13, dur: 10, volume: 0.55, peakLag: 5, note: '回车：真实机械开关拟音' },

  // ── S2 一张卡 + 俯视场景 ──
  { shot: 'S2', offset: 0, file: 'swoosh', volume: 0.42, dur: 16, peakLag: 5, note: 'S1→S2 硬切：一句话凝成卡（短 whoosh）' },
  { shot: 'S2', offset: 16, file: 'paper', startFrom: 0.9, dur: 22, volume: 0.40, peakLag: 7, note: '卡从空中降下：纸张滑入' },
  { shot: 'S2', offset: 14, file: 'thud', volume: 0.55, dur: 12, peakLag: 2, note: '卡落进真实槽位：实而短的一记' },
  { shot: 'S2', offset: 40, file: 'whoosh2', startFrom: 0.15, dur: 40, volume: 0.55, peakLag: 11, note: 'crane 拉升：镜头一路拉开' },

  // ── S3 标签闸：急推 → 拒 → 认领 ──
  { shot: 'S3', offset: 36, file: 'whoosh2', dur: 18, volume: 0.50, peakLag: 15, note: '急推 6f（全片 slam #1 的音画同帧）' },
  { shot: 'S3', offset: 44, file: 'buzz', volume: 0.34, dur: 12, peakLag: 4, note: '撞停后 2f：role_mismatch 的一记闷电' },
  { shot: 'S3', offset: 144, file: 'switch', startFrom: 0.13, dur: 10, volume: 0.50, peakLag: 5, note: '通过/认领：标签对上，卡换区' },

  // ── S4 多轨并行：只留收拢的一记（连发不逐格配音）──
  { shot: 'S4', offset: 120, file: 'thud', volume: 0.28, dur: 12, peakLag: 2, note: '四轨收拢回一整块板（660f）' },

  // ── S5 报告即完成 ──
  { shot: 'S5', offset: 2, file: 'stamp', startFrom: 1.05, dur: 16, volume: 0.50, peakLag: 3, note: 'report → done：一记纸质盖章（slam #2 同帧）' },
  { shot: 'S5', offset: 77, file: 'swoosh', volume: 0.30, dur: 16, peakLag: 5, note: '报告块①落回会话（767f）' },
  { shot: 'S5', offset: 116, file: 'whoosh2', startFrom: 0.15, dur: 16, volume: 0.26, peakLag: 11, note: '报告块②（806f）：换样本防机枪' },
  { shot: 'S5', offset: 155, file: 'swoosh', volume: 0.22, dur: 16, peakLag: 5, note: '报告块③（845f）：音量阶梯递减' },

  // ── S6 收尾：剥离启动 → riser → 字标 impact → 一点 sparkle ──
  // 重做后 S6 不再有「点绿色圆钮」这一拍（它是板头元素，而 S6 已改成从 S5 末帧接上来剥离）。
  // 时间锚点：侧栏起剥 942、四层灭尽 968、迁移 968→984、字标 spring 定版 984、tail 1134。
  { shot: 'S6', offset: 27, file: 'switch', startFrom: 0.13, dur: 10, volume: 0.42, peakLag: 5, note: '剥离启动：侧栏最先离场（942f）' },
  { shot: 'S6', offset: 69, file: 'riser', dur: 92, volume: 0.45, peakLag: 82, note: '剥离铺垫：riser 峰值落在 984f＝字标 spring 定版同帧' },
  { shot: 'S6', offset: 69, file: 'thud', volume: 0.50, dur: 12, peakLag: 2, note: '字标落定（984f）的一记实音' },
  { shot: 'S6', offset: 100, file: 'sparkle', dur: 12, volume: 0.30, peakLag: 0.45, note: '字标定版后的一点光（1015f，全片唯一一处 sparkle）' },
];

export type SfxEntry = {
  from: number;
  src: string;
  startFrom?: number;
  durationInFrames: number;
  volume: number;
  note: string;
};

/** 最终表：帧号 = SHOTS.x.from + offset − peakLag − OUTPUT_OFFSET */
export const SFX: SfxEntry[] = CUES.map((c) => {
  const targetPeak = S[c.shot] + c.offset;
  const from = Math.round(targetPeak - c.peakLag - OUTPUT_OFFSET_FRAMES);
  return {
    from,
    src: AUDIO_FILES[c.file],
    startFrom: c.startFrom,
    durationInFrames: c.dur ?? 24,
    volume: c.volume,
    note: `${c.shot}+${c.offset} → 峰值 ${targetPeak}f（峰值滞后 ${c.peakLag}f）｜${c.note}`,
  };
});

/** 镜头边界 ↔ 拍号对照（给自检与 report 用） */
export const BEAT_GRID = SHOTS.map((s) => ({
  shot: s.id,
  frame: s.from,
  seconds: s.from / FPS,
  beat: Math.round((s.from / FPS - BGM.phase) / (60 / BGM.bpm)),
}));
