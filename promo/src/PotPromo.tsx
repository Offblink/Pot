import React from 'react';
import { AbsoluteFill, Audio, Sequence } from 'remotion';
import { BGM, SFX } from './audio';
import { Caption } from './lib/Caption';
import { C } from './lib/pot';
import { S1 } from './shots/S1';
import { S2 } from './shots/S2';
import { S3 } from './shots/S3';
import { S4 } from './shots/S4';
import { S5 } from './shots/S5';
import { S6 } from './shots/S6';
import { SHOT, SUBTITLES } from './timeline';

/** 合成级 props：`bgm` 供阶段 6 从同一条时间线渲出无 BGM 版（--props=props-nobgm.json） */
export type PotPromoProps = {
  bgm: boolean;
};

export const POT_PROMO_DEFAULTS: PotPromoProps = { bgm: true };

/**
 * 字幕层：从 SUBTITLES 派生，绝对帧 → Sequence 窗口。
 * 位置不是随手给的，是跟每镜的取景算过的（三镜都是「内容铺满画框」，字幕必须落在
 * 内容之间的空地带，否则就是叠字）：
 *   S1 输入条在中下 → 字幕在顶部 96；
 *   S2 揭晓后工位顶 23.6、板顶 387.0（屏幕 px）→ 两者之间的空地板 120–387，字幕放 150；
 *   S3 工位 15–114、板 391–1034 → 空地板 114–391，字幕放 126；
 *   其余（S4 四轨、S5 会话+报告、S6 字标）底部有空处，仍走默认 bottom 96。
 */
const CAPTION_LAYOUT: Record<string, { placement: 'top' | 'bottom'; bottom: number }> = {
  S1: { placement: 'top', bottom: 300 },
  S2: { placement: 'top', bottom: 150 },
  S3: { placement: 'top', bottom: 126 },
};
const DEFAULT_CAPTION = { placement: 'bottom' as const, bottom: 96 };

/** 绝对帧 → 它属于哪一镜（区间左闭右开，末镜兜底） */
const shotAt = (frame: number) => {
  const ids = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'] as const;
  for (const id of ids) {
    const s = SHOT(id);
    if (frame >= s.from && frame < s.from + s.dur) return id;
  }
  return 'S6' as const;
};

const Captions: React.FC = () => (
  <>
    {SUBTITLES.map((c) => {
      // S6 的 tail 由 shots/S6.tsx 自己排版（TAIL_IN），这里必须跳过——
      // 否则「一台机器。一块板。」会在同一帧出现两次（画面正中 + 底部字幕框）。
      // timeline.ts 里的 caption 字符串是事实源，不动；只在渲染层排除。
      if (c.from >= SHOT('S6').from) return null;
      const layout = CAPTION_LAYOUT[shotAt(c.from)] ?? DEFAULT_CAPTION;
      return (
        <Sequence key={`${c.text}-${c.from}`} from={c.from} durationInFrames={c.dur}>
          <Caption text={c.text} duration={c.dur} placement={layout.placement} bottom={layout.bottom} />
        </Sequence>
      );
    })}
  </>
);

const SHOT_COMPONENTS: Record<string, React.FC> = { S1, S2, S3, S4, S5, S6 };

export const PotPromo: React.FC<PotPromoProps> = ({ bgm }) => {
  // bgm 在阶段 6 接到 <Audio>；这里先把它作为合成级开关预留（不影响画面，保证两版同源）
  const bgmEnabled = bgm !== false;
  return (
    <AbsoluteFill style={{ background: C.bg }} data-bgm={bgmEnabled ? 'on' : 'off'}>
      {(['S1', 'S2', 'S3', 'S4', 'S5', 'S6'] as const).map((id) => {
        const s = SHOT(id);
        const Comp = SHOT_COMPONENTS[id];
        return (
          <Sequence key={id} from={s.from} durationInFrames={s.dur} name={`${id} ${s.card}`}>
            <Comp />
          </Sequence>
        );
      })}
      <Captions />
      {/* 声音：BGM 受 bgm 开关控制（无 BGM 版靠 --props 从同一条时间线渲出），SFX 常驻 */}
      {bgmEnabled ? <Audio src={BGM.src} volume={BGM.volume} /> : null}
      {SFX.map((s, i) => (
        <Sequence key={`sfx-${i}-${s.from}`} from={s.from} durationInFrames={s.durationInFrames} name={`SFX ${i} ${s.note.slice(0, 18)}`}>
          <Audio src={s.src} startFrom={s.startFrom} volume={s.volume} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

/** 供未使用的 import 静默（useCurrentFrame 由各镜头组件自己读） */
export const _unused = 0;
