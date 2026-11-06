/**
 * S5 末帧那个画面的**唯一一份实现**：左侧会话窗格 + 右侧三张报告卡 + 依据连线。
 *
 * 为什么抽出来（卡 p-6267acd2）：S6 的第一帧必须与 S5 的最后一帧**逐像素一致**，
 * 而"复制粘贴一份坐标"迟早会漂。所以 S5 和 S6 都渲染这里的同一组组件，
 * 只有"剥离进度"不同 —— S5 传恒等值，S6 逐层加位移/透明度。
 *
 * 纹理用 Remotion 的 `<Img>`（它会 delayRender）而不是 CSS `background-image`：
 * 后者不会等图片解码，渲染时可能截到"只有底色"的帧 —— 这就是 915..919 / 926..927
 * 那 7 帧纯黑的根因。
 */
import React from 'react';
import { Img } from 'remotion';
import { TEX } from '../assets';
import { C, FONT, R, SHADOW } from './pot';

/** 会话窗格被裁到左侧多宽（页面 px = 屏幕 px，1:1） */
export const PANE_W = 1080;
/** park 的终值缩放：以左缘为锚 1→0.985（"驻留不是淡出"） */
export const PARK_SCALE = 0.985;

/** 会话窗格：x 0..PANE_W，内部整页纹理按 `scale` 以左缘为锚缩放 */
export const ChatPane: React.FC<{
  scale: number;
  /** 会话里那块报告卡上的荧光笔进度 0..1 */
  hl: number;
  /** 右缘渐隐：只有整窗格需要；单独裁侧栏时必须关掉，否则会在 272 处多画一条渐变 */
  fade?: boolean;
  style?: React.CSSProperties;
}> = ({ scale, hl, fade = true, style }) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      top: 0,
      width: PANE_W,
      height: 1080,
      overflow: 'hidden',
      ...style,
    }}
  >
    <Img
      src={TEX.chatFull}
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        width: 1920,
        height: 1080,
        transformOrigin: '0% 50%',
        transform: `scale(${scale})`,
      }}
    />
    {/* 会话里那张报告块的荧光笔：结论从这一块里长出来 */}
    {hl > 0 ? (
      <div
        style={{
          position: 'absolute',
          left: 289,
          top: 348,
          width: 232 * hl,
          height: 26,
          borderRadius: 2,
          background: 'rgba(21,128,61,0.18)',
        }}
      />
    ) : null}
    {/* 右缘一条渐隐，读作"这块窗格被裁到左边、后面还有" */}
    {fade ? (
      <div
        style={{
          position: 'absolute',
          right: 0,
          top: 0,
          width: 48,
          height: 1080,
          background: `linear-gradient(90deg, rgba(246,247,249,0) 0%, ${C.bg} 100%)`,
        }}
      />
    ) : null}
  </div>
);

/** 一张报告卡（外观固定；位置与入场由调用方给） */
export const ReportCard: React.FC<{
  head: string;
  body: string;
  left: number;
  top: number;
  width: number;
  minHeight: number;
  opacity: number;
  /** 入场用：translateY 与 scale（落定态是 0 / 1） */
  liftY: number;
  pop: number;
  style?: React.CSSProperties;
}> = ({ head, body, left, top, width, minHeight, opacity, liftY, pop, style }) => (
  <div
    style={{
      position: 'absolute',
      left,
      top,
      width,
      minHeight,
      boxSizing: 'border-box',
      borderRadius: R.card,
      background: C.surface,
      border: `1px solid ${C.border}`,
      boxShadow: SHADOW.card,
      opacity,
      transform: `translateY(${liftY.toFixed(2)}px) scale(${pop.toFixed(4)})`,
      transformOrigin: '0% 50%',
      padding: '14px 16px 14px 17px',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      overflow: 'hidden',
      zIndex: 8,
      ...style,
    }}
  >
    {/* 左缘 3px accent 竖条：层级靠它，不靠圆形勾图标 */}
    <span
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 3,
        background: C.accent,
        borderRadius: `${R.card}px 0 0 ${R.card}px`,
      }}
    />
    <span style={{ fontFamily: FONT.sans, fontSize: 14.5, fontWeight: 600, color: C.text, lineHeight: 1.2 }}>{head}</span>
    <span style={{ fontFamily: FONT.sans, fontSize: 13, fontWeight: 400, color: C.text2, lineHeight: 1.6 }}>{body}</span>
  </div>
);

/** 依据连线：从该行消息右缘水平指出，到卡片左缘；draw 0..1 控制画到哪 */
export const ReportLink: React.FC<{ x1: number; x2: number; y: number; draw: number; style?: React.CSSProperties }> = ({
  x1,
  x2,
  y,
  draw,
  style,
}) => {
  if (draw <= 0) return null;
  const w = (x2 - x1) * draw;
  return (
    <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, pointerEvents: 'none', ...style }}>
      <line x1={x1} y1={y} x2={x1 + w} y2={y} stroke={C.accent} strokeWidth={1.5} strokeLinecap="round" opacity={0.9} />
      <circle cx={x1} cy={y} r={3} fill={C.accent} opacity={Math.min(1, draw * 3)} />
    </svg>
  );
};
