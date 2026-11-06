/**
 * 时间线单一事实源。
 *
 * SHOTS 是唯一的一份帧号表：字幕窗口、SFX 钉帧、转场点全部从它派生。
 * 数据逐字取自 promo/design-spec.md §9/§10 与 promo/plan.json（六段 1200f）。
 * 节奏命门（缓动值、关键留白帧）是同文件里的常量，不进镜头 props。
 */

export type ShotId = 'S1' | 'S2' | 'S3' | 'S4' | 'S5' | 'S6';

export type CaptionCue = {
  text: string;
  /** 绝对帧（30fps），字幕开始入场的那一帧 */
  from: number;
  /** 显示时长（帧）。入场 8f、出场 5f 由 Caption 组件内部处理 */
  dur: number;
};

export type Shot = {
  id: ShotId;
  from: number;
  dur: number;
  card: string;
  styleKey: string;
  /** 主字幕（无旁白：字幕是唯一语言通道） */
  caption: string;
  captionFrom: number;
  /** 同一镜里额外的字句（S2 的第二句） */
  extraCaptions?: { text: string; from: number }[];
};

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const DURATION_IN_FRAMES = 1200;

export const SHOTS: Shot[] = [
  {
    id: 'S1',
    from: 0,
    dur: 120,
    card: 'glass-pill-dictation-typing',
    styleKey: 'glass-pill-dictation-typing',
    caption: '你只给它一句话',
    captionFrom: 92,
  },
  {
    id: 'S2',
    from: 120,
    dur: 180,
    card: 'row-embed',
    styleKey: 'row-embed',
    caption: '它没有留在对话里，',
    captionFrom: 144,
    extraCaptions: [{ text: '它落在板上。', from: 246 }],
  },
  {
    id: 'S3',
    from: 300,
    dur: 240,
    card: 'crash-zoom-punch',
    styleKey: 'crash-zoom-punch',
    caption: '谁认领，由标签决定',
    captionFrom: 444,
  },
  {
    id: 'S4',
    from: 540,
    dur: 150,
    card: 'quad-split-parallel-scenes',
    styleKey: 'quad-split-parallel-scenes',
    caption: '配额满了，就多开一个',
    captionFrom: 546,
  },
  {
    id: 'S5',
    from: 690,
    dur: 225,
    card: 'doc-park-left-pill-deal',
    styleKey: 'doc-park-left-pill-deal',
    caption: '报告交回，卡就完成了',
    captionFrom: 720,
  },
  {
    id: 'S6',
    from: 915,
    dur: 285,
    card: 'ui-strip-away-outro',
    styleKey: 'ui-strip-away-outro',
    caption: '一台机器。一块板。',
    captionFrom: 1135,
  },
];

export const SHOT = (id: ShotId): Shot => {
  const s = SHOTS.find((x) => x.id === id);
  if (!s) throw new Error(`unknown shot ${id}`);
  return s;
};

/** 字幕表：从 SHOTS 派生，别处不许再写一份帧号。
 *
 * `CAPTION_CLEAR`：每句字幕在本镜结束前 16f 就清场。这一条是为了**接缝**——
 * 否则上一镜的最后一帧还挂着字幕、下一镜首帧没有，两帧就不逐像素一致了
 * （S5→S6 的 914/915 就是这种情况，卡 p-6267acd2 要求 Δ=0）。
 */
export const CAPTION_CLEAR = 16;

export const SUBTITLES: CaptionCue[] = SHOTS.flatMap((s) => {
  const extras = (s.extraCaptions ?? []).map((c) => ({ text: c.text, from: c.from }));
  const cues = [{ text: s.caption, from: s.captionFrom }, ...extras];
  const shotEnd = s.from + s.dur - CAPTION_CLEAR;
  return cues.map((c, i) => ({
    text: c.text,
    from: c.from,
    // 一句字幕挂到下一句（或本镜结束前 16f），不重叠
    dur: Math.max(CAPTION_CLEAR + 8, (cues[i + 1]?.from ?? shotEnd) - c.from),
  }));
});

/** 转场点：全部硬切（design-spec §9），故转场帧 === 各镜 from，去掉首帧。 */
export const TRANSITIONS = SHOTS.slice(1).map((s) => s.from);

/** SFX 钉帧（阶段 6 会补音源；这里先由 SHOTS 派生相对偏移） */
export const SFX_CUES = [
  { shot: 'S1' as ShotId, offset: 26, action: 'keyboard-typing-start' },
  { shot: 'S1' as ShotId, offset: 86, action: 'enter-key' },
  { shot: 'S2' as ShotId, offset: 0, action: 'whoosh-mid' },
  { shot: 'S2' as ShotId, offset: 14, action: 'card-impact' },
  { shot: 'S2' as ShotId, offset: 102, action: 'crane-rise-whoosh' },
  { shot: 'S3' as ShotId, offset: 36, action: 'crash-zoom' },
  { shot: 'S3' as ShotId, offset: 42, action: 'reject-thud' },
  { shot: 'S3' as ShotId, offset: 144, action: 'claim-click' },
].map((c) => ({ ...c, frame: SHOT(c.shot).from + c.offset }));

// ─── 节奏命门（常量，不进 props）──────────────────────────────────────────────
export const RHYTHM = {
  /** 字幕：入场 8f、出场 5f（design-spec §5） */
  captionIn: 8,
  captionOut: 5,
  /** 卡片落位：飞行 12f + press 4f（row-embed 命门） */
  cardFly: 14,
  /** S2 卡片入场的 rotateX 起始角与高度（row-embed 命门） */
  cardRotX: 16,
  cardDropPx: 120,
  /** S3 整画面 slam：撞停起 2f 顿帧 + 14px 震屏衰减（crash-zoom-punch 命门） */
  hitStop: 2,
  shakeAmp: 14,
  shakeTau: 1.8,
  /** 批量动效收尾静止（R2） */
  restFrames: 15,
};
