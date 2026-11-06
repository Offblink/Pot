/**
 * 动效工作台清单（references/workbench.md §2–3）。
 *
 * 原则：时间表与文案只写一份 —— 这里**只 import** timeline.ts / 镜头组件，
 * 给每个单元补 component / props / schema。节奏命门（缓动、顿帧、抖动幅度、
 * 相机关键帧）全部留在组件里当常量，不进 props。
 *
 * 可调 = 文案、颜色、字号、位置、开关；
 * 不可调 = 缓动曲线、时值配比、相机路径、slam 的顿帧帧数。
 */
import { SHOTS, SUBTITLES, SFX_CUES, TRANSITIONS } from './timeline';
import { PotPromo } from './PotPromo';
import { S1 } from './shots/S1';
import { S2 } from './shots/S2';
import { S3 } from './shots/S3';
import { S4 } from './shots/S4';
import { S5 } from './shots/S5';
import { S6 } from './shots/S6';
import { C, FS } from './lib/pot';

type Schema = Array<Record<string, unknown>>;

const COMPONENTS: Record<string, React.FC> = { S1, S2, S3, S4, S5, S6 };

/** 每个镜头单元：语境级 props + 它的可编辑 schema */
const UNITS = SHOTS.map((s) => {
  const base = {
    id: s.id,
    label: `${s.id} · ${s.card}`,
    from: s.from,
    duration: s.dur,
    component: COMPONENTS[s.id],
    caption: s.caption,
    card: s.card,
    styleKey: s.styleKey,
  };
  const textSchema: Schema = [{ type: 'textarea', key: 'caption', label: '字幕文案', default: s.caption }];

  switch (s.id) {
    case 'S1':
      return {
        ...base,
        props: { caption: s.caption, accent: C.accent, fontSize: FS.caption },
        schema: [
          ...textSchema,
          { type: 'color', key: 'accent', label: '输入条强调色', default: C.accent },
          { type: 'number', key: 'fontSize', label: '字幕字号', default: FS.caption, min: 40, max: 80, step: 2, unit: 'px' },
        ],
      };
    case 'S2':
      return {
        ...base,
        props: { caption: s.caption, extraCaption: s.extraCaptions?.[0]?.text ?? '' },
        schema: [
          ...textSchema,
          { type: 'textarea', key: 'extraCaption', label: '第二句字幕', default: s.extraCaptions?.[0]?.text ?? '' },
        ],
      };
    case 'S3':
      return {
        ...base,
        props: { caption: s.caption, rejectLabel: 'role_mismatch', passLabel: '已具备 · 可认领' },
        schema: [
          ...textSchema,
          { type: 'text', key: 'rejectLabel', label: '拒绝码（mono）', default: 'role_mismatch' },
          { type: 'text', key: 'passLabel', label: '通过文案', default: '已具备 · 可认领' },
        ],
      };
    case 'S4':
      return {
        ...base,
        props: { caption: s.caption, wipFull: 'wip 1/1', wipOk: 'wip 2/2', counter: '×2' },
        schema: [
          ...textSchema,
          { type: 'text', key: 'wipFull', label: '满配额读数', default: 'wip 1/1' },
          { type: 'text', key: 'wipOk', label: '增殖后读数', default: 'wip 2/2' },
          { type: 'text', key: 'counter', label: '实例计数', default: '×2' },
        ],
      };
    case 'S5':
      return {
        ...base,
        props: {
          caption: s.caption,
          heads: ['摘要', '清单证据', '风险'],
          bodies: ['7 处过期描述，3 处需改链接', '每条都附行号与原文', '旧版命令示例仍被引用'],
        },
        schema: [
          ...textSchema,
          { type: 'textarea', key: 'bodies', label: '三块报告正文（每行一块）', default: '7 处过期描述，3 处需改链接\n每条都附行号与原文\n旧版命令示例仍被引用' },
        ],
      };
    default:
      // S6
      return {
        ...base,
        props: { caption: s.caption, wordmark: 'Pot', icon: '🪴' },
        schema: [
          ...textSchema,
          { type: 'text', key: 'wordmark', label: '品牌字标', default: 'Pot' },
          { type: 'text', key: 'icon', label: '图标', default: '🪴' },
        ],
      };
  }
});

export const WORKBENCH = {
  name: 'Pot 宣传片 · 一台机器。一块板。',
  fps: 30,
  width: 1920,
  height: 1080,
  total: SHOTS.reduce((a, s) => a + s.dur, 0),
  background: C.bg,
  shots: UNITS,
  /** 字幕层：直接从 SUBTITLES 派生（唯一事实源） */
  captions: SUBTITLES.map((c) => ({ from: c.from, duration: c.dur, text: c.text })),
  /** 转场点（本片全部硬切，故为空；保留字段给工作台读） */
  transitions: TRANSITIONS.map((from) => ({ from, duration: 1, kind: 'hard-cut' })),
  /** SFX 钉帧（阶段 6 填 src；这里只有帧号与动作名） */
  sfx: SFX_CUES.map((c) => ({ from: c.frame, duration: 24, src: '', volume: 0.6, note: c.action })),
  bgm: [{ from: 0, duration: SHOTS.reduce((a, s) => a + s.dur, 0), src: '', volume: 0.3 }],
  order: ['transitions', 'captions', 'overlays'],
  /** 原合成，供 parity 对照 */
  original: PotPromo,
} as const;
