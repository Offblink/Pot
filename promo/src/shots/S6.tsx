/**
 * S6 —— 一台机器。一块板。
 *
 * **重做（卡 p-6267acd2）**：不再重放整块俯视看板。S5 已经把「会话 + 三张报告卡」交代完，
 * 所以 S6 从 **S5 的末帧接着剥离**——第 1 帧（915）与 S5 的最后一帧（914）逐像素一致。
 * 共用 `lib/ChatPane` 里的同一份窗格/卡片/连线实现，不另写坐标。
 *
 * 卡：ui-strip-away-outro / ui-strip-away-outro
 * demo TSX：demos/outro/ui-strip-away-outro/UiStripAwayOutro.tsx
 * 命门照抄：层间 4f、每层 14f、`E.inCubic` 加速离场、0→7px 蒸发模糊、
 * 各层朝画外方向位移；唯一幸存者**先迁移后熄灭**；字标 spring 定版后 hold ≥1s。
 *
 * 四层（由外到内）：③ 侧栏 → ① 三张报告卡 → ② 会话窗格 → ④ 地板，各差 4f。
 */
import React from 'react';
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { ChatPane, ReportCard, ReportLink, PANE_W, PARK_SCALE } from '../lib/ChatPane';
import { C, FONT, FS } from '../lib/pot';
import { E, rampD, ramp, mix } from '../lib/helpers';
import { CARD_H, CARD_LEFT, CARD_W, REPORTS, cardTop, linkX1, linkY, S5_ROW_CENTER } from './S5';
import { SHOT } from '../timeline';

export const S6_FROM = SHOT('S6').from; // 915
export const S6_DURATION = SHOT('S6').dur; // 285

/** Pot 的暗色主题（web/style.css:9） */
const DARK = {
  bg: '#06060a',
  text: '#e0e0e0',
  text2: '#8a8a99',
  glow: 'rgba(74,222,128,0.25)',
} as const;

// ── 时间表（285f：915..1199）────────────────────────────────────────────────
const HOLD_END = 925; // 承接 S5 末帧，静止 10f
const T_SIDEBAR = 942; // ③ 侧栏先走
const T_CARDS = 946; // ① 三张报告卡
const T_PANE = 950; // ② 会话窗格
const T_FLOOR = 954; // ④ 地板
const STRIP_DUR = 14; // 每层 14f（命门）
const DARK_FROM = 964;
const DARK_END = 978; // 四层离场（968）之后再压到 #06060a：剥离全程看得见，黑场交给字标
const MIG_FROM = 978; // 幸存者迁移起（此时底已是纯黑、四层已灭尽）
const MIG_TO = 996;
const LOGO_IN = MIG_TO; // 迁移落位后 spring 定版
const TAIL_IN = 1130;
const HOLD_FROM = 1026; // 字标 hold 起（到 1130 = 104f = 3.47s ≥1.2s）

type StripStyle = { opacity: number; transform: string; filter?: string };

/** 某层的蒸发：ease-in 加速 + 方向性位移 + 渐增模糊（卡里的 strip() 原样） */
const strip = (f: number, start: number, dx: number, dy: number): StripStyle => {
  const p = rampD(f, start, STRIP_DUR, E.inCubic);
  return {
    opacity: 1 - p,
    transform: `translate(${(dx * p).toFixed(2)}px, ${(dy * p).toFixed(2)}px)`,
    filter: p > 0.001 ? `blur(${(p * 7).toFixed(2)}px)` : undefined,
  };
};

/** 幸存者迁移：从会话顶栏的「Pot」到屏心 */
const MIG = {
  fromX: 358 * PARK_SCALE + 20, // 页面 (358,37) → 屏幕；+20 是「Pot」二字大致半宽
  fromY: 540 + (37 - 540) * PARK_SCALE,
  toX: 960,
  toY: 500,
  fromScale: 22 / FS.wordmark, // 顶栏那行字号 22px → 相对字标的比例
  toScale: 0.86, // 交给 spring 从 86% 收到 100%
};

export const S6: React.FC = () => {
  const local = useCurrentFrame();
  const f = local + S6_FROM;
  const { fps } = useVideoConfig();

  const sidebar = strip(f, T_SIDEBAR, -140, 0); // ③ 向左 140
  const cards = strip(f, T_CARDS, 140, -40); // ① 向右 140、上移 40
  const pane = strip(f, T_PANE, -120, 0); // ② 向左 120
  const floor = strip(f, T_FLOOR, 0, 60); // ④ 向下 60

  // 压暗：满幅一层，952→972 均匀走到 1（不随层走，所以不会出现矩形色差）
  // 用 outCubic 让底「先黑下来」：迁移开始（966）时已达 ~97%，字标全程白字黑底、不会经过低对比灰。
  const darkOn = rampD(f, DARK_FROM, DARK_END - DARK_FROM, E.outCubic);

  // 幸存者：先迁移（966→984），再 spring 定版（984→1014）
  const mig = rampD(f, MIG_FROM, MIG_TO - MIG_FROM, E.inOutCubic);
  const springP = spring({ frame: f - LOGO_IN, fps, config: { damping: 14, stiffness: 90 } });
  const logoScale = mix(MIG.fromScale, MIG.toScale, mig) * (MIG.toScale + (1 - MIG.toScale) * springP);
  const logoX = mix(MIG.fromX, MIG.toX, mig);
  const logoY = mix(MIG.fromY, MIG.toY, mig);
  const tailP = spring({ frame: f - TAIL_IN, fps, config: { damping: 14, stiffness: 90 } });

  return (
    <AbsoluteFill style={{ background: C.bg, overflow: 'hidden' }}>
      {/* ① 纸底（安全层）：任何纹理没解码时看到的是 --bg，绝不再是纯黑 */}
      <AbsoluteFill style={{ background: C.bg }} />

      {/* ④ 地板：满幅纸面，最后走（向下 60） */}
      {f >= T_FLOOR ? <AbsoluteFill style={{ background: C.bg, ...floor }} /> : null}

      {/* ③ 侧栏 / ② 会话窗格
          剥离开始前（f < T_SIDEBAR）只画一份整窗格 —— 与 S5 末帧的层结构完全一致，
          这样 915 帧才能与 914 帧逐像素相等。剥离开始后才拆成两片（侧栏先走、窗格后走）。 */}
      {f < T_SIDEBAR ? (
        <ChatPane scale={PARK_SCALE} hl={1} />
      ) : (
        <>
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              width: 272,
              height: 1080,
              overflow: 'hidden',
              ...sidebar,
            }}
          >
            <ChatPane scale={PARK_SCALE} hl={1} fade={false} />
          </div>
          <ChatPane
            scale={PARK_SCALE}
            hl={1}
            style={{ ...pane, clipPath: 'inset(0 0 0 272px)' }}
          />
        </>
      )}

      {/* ① 三张报告卡 + 依据连线，作为整组一起飞走 */}
      <AbsoluteFill style={{ ...cards }}>
        {REPORTS.map((r, k) => (
          <ReportLink key={`lnk-${r.head}`} x1={linkX1(k)} x2={CARD_LEFT} y={linkY(k)} draw={1} />
        ))}
        {REPORTS.map((r, k) => (
          <ReportCard
            key={r.head}
            head={r.head}
            body={r.body}
            left={CARD_LEFT}
            top={cardTop(k)}
            width={CARD_W}
            minHeight={CARD_H}
            opacity={1}
            liftY={0}
            pop={1}
          />
        ))}
      </AbsoluteFill>

      {/* 压暗：满幅、均匀，984 精确到 1 */}
      {darkOn > 0 ? <AbsoluteFill style={{ background: DARK.bg, opacity: darkOn }} /> : null}

      {/* 幸存者 + 字标：同一个「Pot」，先迁移后定版 */}
      <div
        style={{
          position: 'absolute',
          left: logoX,
          top: logoY,
          transform: `translate(-50%, -50%) scale(${logoScale})`,
          fontFamily: FONT.sans,
          fontWeight: 700,
          fontSize: FS.wordmark,
          lineHeight: 1,
          letterSpacing: '-0.02em',
          color: DARK.text,
          whiteSpace: 'nowrap',
          opacity: f >= MIG_FROM ? 1 : 0,
        }}
      >
        Pot
      </div>

      {/* 🪴 在字标左侧淡入（字标定版之后才出现） */}
      {f >= LOGO_IN ? (
        <div
          style={{
            position: 'absolute',
            left: logoX - 190,
            top: logoY,
            transform: 'translate(-50%, -50%)',
            fontSize: FS.wordmark * 0.5,
            lineHeight: 1,
            opacity: Math.min(1, springP * 1.4),
          }}
        >
          🪴
        </div>
      ) : null}

      {/* tail：一台机器。一块板。 */}
      {f >= TAIL_IN ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 720,
            display: 'flex',
            justifyContent: 'center',
            opacity: Math.min(1, tailP * 1.4),
            transform: `translateY(${((1 - tailP) * 12).toFixed(2)}px)`,
          }}
        >
          <span
            style={{
              fontFamily: FONT.sans,
              fontSize: FS.sub,
              fontWeight: 500,
              letterSpacing: '0.08em',
              color: DARK.text2,
            }}
          >
            一台机器。一块板。
          </span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
