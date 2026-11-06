/**
 * S1 —— 一句话。
 * 卡：glass-pill-dictation-typing / glass-pill-dictation-typing
 * demo TSX：demos/interaction/glass-pill-dictation-typing/GlassPillDictationTyping.tsx
 *
 * 保留的命门（卡《参数表》+《已知坑》）：
 *   · 胶囊**定宽**，不随打字伸缩（伸缩会读作 chip 而不是输入条）
 *   · 出场 scale 1.25→1，snappy 20f；opacity 前 2f 就满（先"在了"再落位）
 *   · 落位前 14f 带 6px→0 景深虚化
 *   · 光标先行（f2），文字匀速 3f/字（真人速度，R3）
 *   · 光随打字退去：g = 1 − smooth(f26→f80)，与打字同窗
 * 适配性改动（写进 promo/notes.md）：
 *   · 材质从"玻璃 + 暖光 + 声波按钮"换成 Pot 的 --surface/--border/--shadow-card +
 *     --accent-glow 绿（design-spec §12 第 10 条）
 *   · 胶囊尺寸取真实输入槽位（1000×57 页面 px），不再用 1240×132：
 *     覆层必须与真实槽位同尺寸同位置，否则读作贴片（Q1/Q9）
 *   · 打字窗口改成 26–80f（18 字 × 3f），落位 6–26f —— 与 plan.json 的 beats 一致
 */
import React from 'react';
import { AbsoluteFill, Img, interpolate, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { C, FONT, R, SHADOW } from '../lib/pot';
import { TEX } from '../assets';
import { E, ramp, rampD, segLinear, clamp01 } from '../lib/helpers';
import { PAGE } from '../sceneLayout';

export const S1_DURATION = 120;

const TEXT = '把 README 里过期的地方找出来';
const TYPE0 = 26;
const CPF = 3; // 帧/字：18 字 × 3 = 54f（26→80）
const LAND0 = 6;
const LAND_DUR = 20;
const GLOW_OFF = [26, 80] as const;

/**
 * 相机：**整条输入框必须完整在画内**，这是本卡的硬约束。
 *
 * 上一版 CY 800 / zoom 1.50：可见页宽 = 1920/1.5 = 1280 < 输入框宽 1459 →
 * 右端圆角被切出画面（读作"截屏没对齐"）；且可见下缘 1160 > 页高 1080 →
 * 露出容器底，与页面底部（白色）形成一条水平色带。
 *
 * 现在（选方案 A 的前半条：**把可见页宽做到 ≥1600px**）：
 *   zoom 1.15 → 可见 1670×939；输入框 1459×63 在屏幕占 **1678×72.5**
 *   cx 1106.78 → 画面左缘正好落在页面 x=272（侧栏右缘），**侧栏整块不进画**
 *   cy 815.4  → 输入框屏幕 **y 750..822.5**：上留 750、下留 257.5（≥200 ✓）
 *   输入框屏幕 x **25.3..1703.2**：右留 216.8（≥120 ✓），左 25.3（画面左缘即会话列起点）
 *   打字文字 38 页面 px × 1.15 = **43.7 屏幕 px**（≥34 ✓）
 */
const CX = 1106.78;
const CY = 815.4;
const ZOOM = 1.15;
const CAM: CamKey[] = [
  { frame: 0, cx: CX, cy: CY, zoom: ZOOM, rotX: 0 },
  { frame: 120, cx: CX + 6, cy: CY + 5, zoom: ZOOM + 0.02, rotX: 0 },
];

/** 页面坐标 → 屏幕 y（相机无旋转，纯 translate+zoom） */
const screenY = (pageY: number) => 540 + (pageY - CY) * ZOOM;

/**
 * 顶部遮罩：0..240px。**不透明段到 70%（=168px）**，
 * 这样页面 y 342..478 那条报告块（屏幕 −4..154）被完全吃掉，
 * 不会留"半张卡"在顶边。
 */
const TOP_MASK = 240;

/**
 * 底部遮罩：从页面 y=1062（输入区那条白色页脚起点）一直盖到画面底。
 * 盖掉它 → 画面下缘与页面其余部分同色（--bg），既没有白色页脚色带，
 * 也没有"页面结束 → 容器底"的接缝。
 */
const BOTTOM_MASK_FROM = screenY(1062); // ≈ 823.6

/** 会话里最后一条消息（真实切片 chat-report，392×137 页面 px），放在输入框上方 ~120px */
const SLICE = { x: 293, y: 754.5, w: 392, h: 137 } as const;

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const mixHex = (a: string, b: string, t: number) => {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ch = (sh: number) => Math.round(((pa >> sh) & 255) + ((((pb >> sh) & 255) - ((pa >> sh) & 255)) * t));
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
};

export const S1: React.FC = () => {
  const f = useCurrentFrame();

  // 落位（卡的命门：opacity 前 2f 满，scale 1.25→1 snappy 20f，前半段景深虚化）
  const appear = ramp(f, 0, 2, E.linear);
  const landT = ramp(f, LAND0, LAND0 + LAND_DUR, E.expo);
  const scale = 1.25 + (1 - 1.25) * landT;
  const defocus = 6 * (1 - ramp(f, LAND0, LAND0 + 14, E.outCubic));

  // 打字：floor(p·len + 1e-6) —— 那个 epsilon 防末字符在整点因浮点误差不出现（卡的已知坑）
  const typed = Math.floor(clamp01((f - TYPE0) / (TEXT.length * CPF)) * TEXT.length + 1e-6);
  const caretOn = f >= 2 && f < 88 && (f < TYPE0 || typed < TEXT.length ? true : Math.floor(f / 8) % 2 === 0);

  // 光随输入退去
  const g = 1 - ramp(f, GLOW_OFF[0], GLOW_OFF[1], E.smooth);

  // 回车：键压 + ripple
  const press = ramp(f, 86, 88, E.outQuad) * (1 - ramp(f, 88, 92, E.smooth));
  const ripple = f >= 86 ? ramp(f, 86, 96, E.outCubic) : 0;


/**
 * 覆层几何 = **实测的真实输入框**（`scripts/measure-input-row.py`）：
 *   x 294..1753（宽 1459）、y 998..1059（高 61）
 * `sceneLayout.ts` 里的 CHAT_INPUT_SLOT（293/1009/1000×57）是采集阶段手填的近似值，
 * 比真实框低 11px、高 4px —— 直接用会在屏幕 837（真框上沿）与 939（覆层下沿）
 * 各留一条横线，看起来像"双边框"。
 * 宽度按"覆盖到画面外"取 1460：zoom 1.50 的可见右缘是页面 1433，
 * 真实框右缘 1753 本来就在画外，覆层必须盖过去，否则会露出一道竖直接缝。
 */
const SLOT = { x: 294, y: 998, w: 1460, h: 61 } as const;

  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <PageCam src={TEX.chatFull} pageH={PAGE.h} keys={CAM} bg={C.bg}>
        {/* 覆层：真实输入槽位上的胶囊（定宽，不伸缩） */}
        <div
          style={{
            position: 'absolute',
            left: SLOT.x,
            top: SLOT.y,
            width: SLOT.w,
            height: SLOT.h,
            opacity: appear,
            transform: `scale(${scale}) translateY(${press * 4}px)`,
            transformOrigin: '0% 50%',
            filter: defocus > 0.05 ? `blur(${defocus.toFixed(2)}px)` : undefined,
            borderRadius: R.sm,
            overflow: 'hidden',
            boxSizing: 'border-box',
            background: C.surface,
            border: `1px solid ${g > 0.5 ? mixHex(C.accent, C.border, (1 - g) * 2 > 1 ? 1 : (1 - g) * 2) : C.border}`,
            boxShadow: `${SHADOW.card}${g > 0.02 ? `, 0 0 ${Math.round(24 * g)}px ${C.accentGlow}` : ''}`,
          }}
        >
          {/* 内嵌强调光：左淡右浓，随打字退去（光在输入条里面，不是外部光晕） */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              opacity: g,
              background: `linear-gradient(90deg, rgba(21,128,61,0) 0%, rgba(21,128,61,0.10) 38%, rgba(21,128,61,0.28) 78%, rgba(21,128,61,0.42) 100%)`,
            }}
          />
          {/* 顶沿高光线：两端渐隐，裁在圆角里（Q4） */}
          <div
            style={{
              position: 'absolute',
              left: 16,
              right: 16,
              top: 1,
              height: 1,
              opacity: 0.9,
              background: `linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.9) 18%, rgba(255,255,255,0.5) 78%, rgba(255,255,255,0))`,
            }}
          />
          {/* 打字文字 + 光标 */}
          <div
            style={{
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              height: '100%',
              paddingLeft: 34,
              fontFamily: FONT.sans,
              fontSize: 38,
              fontWeight: 500,
              letterSpacing: '-0.005em',
              color: C.text,
              whiteSpace: 'pre',
            }}
          >
            <span>{TEXT.slice(0, typed)}</span>
            <span
              style={{
                display: 'inline-block',
                width: 3,
                height: 40,
                marginLeft: 2,
                borderRadius: 2,
                background: mixHex(C.text, C.accent, 0.85 * g),
                opacity: caretOn ? 1 : 0,
              }}
            />
          </div>
          {/* 回车 ripple：从输入条右端向外扩一圈 accent 光环，裁在圆角里 */}
          {ripple > 0 && ripple < 1 ? (
            <div
              style={{
                position: 'absolute',
                right: -10,
                top: SLOT.h / 2 - 10,
                width: 20 + 240 * ripple,
                height: 20 + 240 * ripple,
                marginTop: -(10 + 120 * ripple),
                borderRadius: 999,
                border: `2px solid ${C.accent}`,
                opacity: 0.45 * (1 - ripple),
              }}
            />
          ) : null}
        </div>

        {/* 会话里最后一条消息：**真实切片**（chat-report，392×137 页面 px），
            放在输入框上方 ~120px，给画面一个"这是真实会话底部"的语义锚点。
            它是页面坐标系里的元素，跟着相机一起动（不会与底图错位）。 */}
        <Img
          src={TEX.chatReport}
          style={{
            position: 'absolute',
            left: SLICE.x,
            top: SLICE.y,
            width: SLICE.w,
            height: SLICE.h,
            opacity: rampD(f, 8, 14, E.smooth),
          }}
        />
      </PageCam>

      {/* 顶部遮罩：0..240，**不透明到 70%（168px）** —— 页面 y342..478 那条报告块
          （屏幕 −4..154）被整块吃掉，画面顶边不会出现"半张卡"。
          渐隐段 168..240 把页面的输入框投影也一起化掉。 */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 0,
          height: TOP_MASK,
          pointerEvents: 'none',
          background: `linear-gradient(to bottom, ${C.bg} 0%, ${C.bg} 70%, rgba(246,247,249,0) 100%)`,
        }}
      />

      {/* 底部遮罩：从页面 y=1062（输入区那条白色页脚起点，屏幕 ≈823.6）盖到画面底。
          盖掉它以后，画面下缘与页面其余部分**同色**：既没有白色页脚色带，
          也没有"页面结束（1080）→ 容器底"的接缝（上一版那条 y≈967 的带子就是这么来的）。 */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: BOTTOM_MASK_FROM,
          bottom: 0,
          pointerEvents: 'none',
          background: C.bg,
        }}
      />
      <span style={{ display: 'none' }}>{interpolate(f, [0, 1], [0, 0], clamp)}</span>
    </AbsoluteFill>
  );
};

/** 打字进度（供自检与工作台读） */
export const s1TypedChars = (frame: number) =>
  Math.floor(clamp01((frame - TYPE0) / (TEXT.length * CPF)) * TEXT.length + 1e-6);
export const s1TypingWindow = { from: TYPE0, to: TYPE0 + TEXT.length * CPF, cpf: CPF };
export const s1LandWindow = { from: LAND0, dur: LAND_DUR };
export const s1Seg = segLinear;
