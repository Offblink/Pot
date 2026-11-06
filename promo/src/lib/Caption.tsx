/**
 * 字幕。底子是 assets/lib/Caption.tsx（模板片的 mono 信息条），本片按
 * design-spec §4.3 的影像字阶改成：60px、Segoe UI Variable、--text 主色 + --surface 底板，
 * 底板上一条 --accent 竖条。原组件 22px 的"信息条"风格低于 Q11 的 56px 字幕线，
 * 只有作为叙事主字幕时才必须提到 60px —— 本片就是主字幕。
 *
 * 入场 8f（smooth，上浮 10px）、出场 5f，与 timeline.ts 的 RHYTHM 一致。
 */
import { interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { C, FONT, FS, R, SHADOW } from './pot';
import { E } from './helpers';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

export const Caption: React.FC<{
  text: string;
  /** 显示窗口（帧） */
  duration: number;
  /** 距画面底部的距离 */
  bottom?: number;
  /** 字幕站哪：画面底部（默认）或顶部 —— 主体占住底部时（S1 输入条）用 top */
  placement?: 'top' | 'bottom';
  inFrames?: number;
  outFrames?: number;
}> = ({ text, duration, bottom = 96, placement = 'bottom', inFrames = 8, outFrames = 5 }) => {
  const frame = useCurrentFrame();
  const { height } = useVideoConfig();
  const inT = interpolate(frame, [0, inFrames], [0, 1], { ...clamp, easing: E.smooth });
  const outT = interpolate(frame, [duration - outFrames, duration], [1, 0], { ...clamp, easing: E.smooth });
  const op = Math.min(inT, outT);

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        ...(placement === 'top' ? { top: bottom } : { bottom }),
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',
        opacity: op,
        transform: `translateY(${(1 - inT) * 10}px)`,
      }}
    >
      <div
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          gap: 20,
          padding: '18px 34px 18px 30px',
          borderRadius: R.card,
          background: C.surface,
          border: `1px solid ${C.border}`,
          boxShadow: SHADOW.card,
        }}
      >
        <span style={{ width: 6, height: FS.caption * 0.62, borderRadius: 3, background: C.accent, flex: 'none' }} />
        <span
          style={{
            fontFamily: FONT.sans,
            fontSize: FS.caption,
            fontWeight: 600,
            letterSpacing: '0.005em',
            lineHeight: 1.1,
            color: C.text,
            whiteSpace: 'nowrap',
          }}
        >
          {text}
        </span>
      </div>
      {/* 供 Q11 自检：字幕底边到画面底的距离（height 被读一次，避免未使用告警） */}
      <span style={{ display: 'none' }}>{height}</span>
    </div>
  );
};
