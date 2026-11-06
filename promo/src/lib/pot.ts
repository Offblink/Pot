/**
 * Pot 自己的 design tokens —— 逐条抄自 web/style.css 的 :root（design-spec §4）。
 * 本片任何颜色/字体/圆角/阴影都必须从这里取，不许就地写死新值。
 */
export const C = {
  bg: '#f6f7f9',
  surface: '#ffffff',
  surface2: '#eceef2',
  text: '#1b1d22',
  text2: '#4b5563',
  dim: '#6b7280',
  border: '#e2e5ea',
  borderLight: '#eef0f4',
  accent: '#15803d',
  accentHover: '#166534',
  accentGlow: 'rgba(21,128,61,0.22)',
  accent2: '#2563eb',
  accent3: '#7c3aed',
  onAccent: '#ffffff',
  errorBg: '#fef2f2',
  errorBorder: '#fecaca',
  errorText: '#dc2626',
  warnBg: '#fffbeb',
  warnBorder: '#fde68a',
  okBg: '#f0fdf4',
  okBorder: '#bbf7d0',
  toolBg: '#eff6ff',
  toolBorder: '#d6e4fb',
} as const;

export const R = { card: 14, sm: 10, xs: 6, lg: 18 } as const;

export const SHADOW = {
  card: '0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04)',
  sidebar: '2px 0 16px rgba(0,0,0,0.04)',
  pop: '0 12px 48px rgba(10,12,30,0.18), 0 2px 8px rgba(10,12,30,0.08)',
  glow: '0 0 24px rgba(21,128,61,0.22)',
} as const;

/** web/style.css: --font / --mono */
export const FONT = {
  sans: "'Segoe UI Variable', 'Segoe UI', -apple-system, system-ui, sans-serif",
  mono: "'Cascadia Code', 'Cascadia Mono', Consolas, 'SF Mono', monospace",
} as const;

/** 影像阶字号（design-spec §4.3，按 Q11 的 1080p 阈值） */
export const FS = {
  caption: 60,
  sub: 40,
  cardTitle: 44,
  mono: 30,
  wordmark: 180,
} as const;

/** web/style.css:5-6 的三条缓动 */
export const EASE_CSS = {
  expo: 'cubic-bezier(0.16,1,0.3,1)',
  spring: 'cubic-bezier(0.34,1.56,0.64,1)',
  smooth: 'cubic-bezier(0.22,1,0.36,1)',
} as const;
