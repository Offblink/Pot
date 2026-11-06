/**
 * 本片的公共小工具。
 *  - mulberry32 / velocityAt / lagged / dampedSettle 直接来自
 *    data/skills/video-shotcraft/assets/lib/helpers（原样 copy，见 rand.ts / motion.ts）
 *  - ramp / mix / clamp / 三条缓动 是本片自用的一层薄封装
 *
 * 确定性铁律：本文件不出现 Date.now() / Math.random()。
 */
import { Easing } from 'remotion';

export { mulberry32 } from './rand';
export { velocityAt, lagged, dampedSettle } from './motion';

export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
export const mix = (a: number, b: number, t: number) => a + (b - a) * t;
export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** 线性进度：frame 在 [a, b] 内的 0..1（两端 clamp），再走一条 easing */
export const segLinear = (frame: number, a: number, b: number) => (b <= a ? (frame >= b ? 1 : 0) : clamp01((frame - a) / (b - a)));

export const ramp = (frame: number, a: number, b: number, easing: (t: number) => number = (t) => t) =>
  easing(segLinear(frame, a, b));

export const rampD = (frame: number, start: number, dur: number, easing: (t: number) => number = (t) => t) =>
  ramp(frame, start, start + dur, easing);


/** web/style.css 的三条缓动，写成 Remotion 可用的函数 */
export const E = {
  linear: (t: number) => t,
  /** --ease-out-expo / 工程默认 */
  expo: Easing.bezier(0.16, 1, 0.3, 1),
  /** --ease-spring：只给卡片落地 / chip 落位的 1.02 微过冲 */
  spring: Easing.bezier(0.34, 1.56, 0.64, 1),
  /** --ease-smooth：交叉淡化、字幕、相机拉回 */
  smooth: Easing.bezier(0.22, 1, 0.36, 1),
  /** 专业信赖基线（pipeline 品牌→动效参数表） */
  trust: Easing.bezier(0, 0, 0.2, 1),
  /** crane 升降臂（crane-rise-reveal 命门） */
  crane: Easing.bezier(0.2, 0, 0.25, 1),
  /** row-embed 下落：末段仍带速度砸进槽位 */
  drop: Easing.bezier(0.5, 0, 0.8, 0.75),
  inCubic: Easing.in(Easing.cubic),
  outCubic: Easing.out(Easing.cubic),
  outQuad: Easing.out(Easing.quad),
  inOutCubic: Easing.inOut(Easing.cubic),
};

/** 2px 强调色缝 / 绿勾这类一次性小事件的光晕（必须裁进圆角，Q4） */
export const glowRing = (color: string, px: number) => `0 0 ${px}px ${color}`;
