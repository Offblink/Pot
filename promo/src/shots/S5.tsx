/**
 * S5 —— 报告交回，卡就完成了。
 * 卡：doc-park-left-pill-deal / doc-park-left-pill-deal
 * demo TSX：demos/ui-entrance/doc-park-left-pill-deal/DocParkLeftPillDeal.tsx
 * 命门照抄：驻留**不是淡出**而是 translateX −55% + scale 0.92（origin 0% 50%，只露约 35%）；
 * 发牌起点 T0 = [0.26, 0.48, 0.70]（间隔 0.22 ≈ 38f，是一句旁白的长度，不是 UI stagger）；
 * 药丸两条曲线并行：opacity 0.035 窗（快）+ translateY 14→0 / scale 0.94→1 的 outBack 0.062 窗（慢，约 11f）；
 * 字幕 cs = f+0.05（落定后约 3f 才起），逐词加深占 70%，下一张前清场；
 * 依据联动：文档里那一句被荧光笔自左划出，一条细线连到药丸。
 *
 * 适配改动（promo/notes.md）：
 *   · "文档"换成 Pot 的**那个会话**（chat-full 真截图），结论三块换成报告块（摘要 / 清单证据 / 风险），
 *     文案逐字取自 design-spec §6.1。
 *   · 完成拍（690–720）在本镜开头、板心特写上：卡上浮 6px + **顿帧 2f + 3px 全画面微震**（slam #2），
 *     划掉线 12f、压暗、绿勾 7f 描出、mono done —— 这是 Pot 最反直觉的一刻（report 直达 done、
 *     跳过已退役的"待验收"）。720 硬切到会话，报告块正是在这一刻落回去的。
 *   · 三块报告是 React 真文字（不是截图），因为它们要在镜里逐块落定。
 */
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { TEX } from '../assets';
import { C, FONT, R, SHADOW } from '../lib/pot';
import { ChatPane, ReportCard, ReportLink, PANE_W, PARK_SCALE } from '../lib/ChatPane';
import { E, ramp, rampD, segLinear, mix, clamp01, mulberry32, dampedSettle } from '../lib/helpers';
import { CHAT, PAGE, SCENE } from '../sceneLayout';
import { SHOT } from '../timeline';

export const S5_FROM = SHOT('S5').from; // 690
export const S5_DURATION = SHOT('S5').dur; // 225

const CUT = 720; // 完成拍 → 会话（本镜内部的一次硬切）
const PARK0 = 726;
const PARK_DUR = 43;

/** 报告三块（逐字取自 design-spec §6.1） */
export const REPORTS = [
  { head: '摘要', body: '7 处过期描述，3 处需改链接', cue: 767 },
  { head: '清单证据', body: '每条都附行号与原文', cue: 806 },
  { head: '风险', body: '旧版命令示例仍被引用', cue: 845 },
];

/**
 * 完成拍取景：按**整块板**取，不按行取。
 * 旧值 zoom 2.6 / cy = rowDoing.y+40 = 490.5 → 可见高 415 < 板高 429，上下必切（与 S3 同一个毛病）。
 * 现在 zoom 2.0 / cy 540（= BOARD_CENTER.y）：可见 960×540，板 880×429 全在框内，上下各余 55.5。
 */
const BOARD_CENTER_Y = SCENE.board.y + SCENE.board.h / 2; // 540
const BOARD_CENTER_X = SCENE.board.x + SCENE.board.w / 2; // 1096
const BOARD_CAM: CamKey[] = [
  { frame: 690, cx: BOARD_CENTER_X, cy: BOARD_CENTER_Y, zoom: 2.0, rotX: 0 },
  { frame: 720, cx: BOARD_CENTER_X, cy: BOARD_CENTER_Y, zoom: 2.0 * 1.015, rotX: 0 },
];

/**
 * 会话驻留：**按页面 1:1 裁到左侧 1080px**（不是缩到 0.8 再把整页塞进画）。
 *
 * 旧值 zoom 0.80 / cx 360：可见页宽 2400（比页面还宽）→ 页面只占画面 64%、左侧 840px 死区，
 * 而且 cx 偏左把右半截推出画外 → 会话切顶、主体跑到左上角。
 *
 * 现在：页面 x 0..1080 映射到屏幕 0..1080（占画宽 **56.3%**），page y 0..1080 映射到 0..1080
 * （**不切顶不切底**）；右侧 1080..1920 是留给报告卡片的留白区。
 * "park 不是淡出"落在**以左缘为锚的 1→0.985 微缩**上：右缘 1080 → 1063.8 ≈ 卡面写的"约 1060"。
 */

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/** 报告卡片几何（卡面给的字阶与尺寸；位置改成逐行对齐，见下） */
export const CARD_W = 320;
export const CARD_H = 76;
export const CARD_LEFT = 1080;

/**
 * 三张报告卡与左侧三块消息**逐行对齐**（卡 p-bc0fae38）。
 *
 * 左侧三块的行中心是**页面坐标**（`scripts/measure-left-rows.py` 从纹理逐行扫出来的）：
 *   ① 助手气泡 151–212 → 181.5   ② tool 卡 222–330 → 276.0   ③ 报告块 342–486 → 412.5
 *
 * ⚠ 但不能直接拿这三个数当屏幕 y：左侧窗格 park 后是 `scale 0.985`，且
 * `transformOrigin: '0% 50%'` → 绕 y=540 缩放，所以
 *   screen_y = 540 + (page_y − 540) × 0.985  ⇒  187.0 / 280.0 / 414.4
 * 直接在 181.5 放卡会让最上面那张差 5.5px（超出卡要求的 ≤2px）。
 * 帧 880 实测三块中心 188.0 / 280.0 / 414.5，与本式一致。
 */
export const S5_ROW_CENTER_PAGE = [181.5, 276.0, 412.5] as const;
export const S5_ROW_CENTER = S5_ROW_CENTER_PAGE.map((y) => 540 + (y - 540) * PARK_SCALE);

/** 三块左侧消息的**右缘**（页面 px，`measure-left-rows.py` 实测 959 / 768 / 686）→ 屏幕 px */
export const S5_ROW_RIGHT = [959, 768, 686].map((x) => x * PARK_SCALE); // 944.6 / 756.5 / 675.7

/** 连线从「该行右缘 + 8px」出发，到卡片左缘 —— 不再从窗格右缘（1063.8）凭空起 */
const LINK_PAD = 8;
export const linkX1 = (k: number) => S5_ROW_RIGHT[k] + LINK_PAD;
export const linkY = (k: number) => S5_ROW_CENTER[k];

/** 卡片顶 = 行中心 − 卡高/2 → 149 / 242 / 376.4；卡组下缘 452.4（字幕带在 720，不冲突） */
export const cardTop = (k: number) => S5_ROW_CENTER[k] - CARD_H / 2;

/** 逐词加深字幕（卡里的 Caption 语法，字阶按 Q11 提到 40px） */
const WordCaption: React.FC<{ text: string; showV: number; innP: number; outP: number }> = ({ text, showV, innP, outP }) => {
  const words = text.split(' ');
  const n = words.length || 1;
  const st = 0.78 / n;
  const win = st * 1.5;
  const rowOp = outP > 0 ? clamp01(1 - (outP - 0.7) / 0.3) : showV;
  const mixC = (q: number) => {
    const a = [0xc4, 0xc6, 0xcc];
    const b = [0x1b, 0x1d, 0x22];
    const qq = clamp01(q);
    return `rgb(${Math.round(a[0] + (b[0] - a[0]) * qq)},${Math.round(a[1] + (b[1] - a[1]) * qq)},${Math.round(a[2] + (b[2] - a[2]) * qq)})`;
  };
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', opacity: rowOp, whiteSpace: 'nowrap' }}>
      {words.map((w, i) => {
        const q = clamp01((innP - i * st) / win);
        let color = mixC(q);
        if (outP > 0) color = mixC(1 - clamp01((outP - i * (0.55 / n)) / (0.55 / n * 1.4)));
        return (
          <span key={i} style={{ fontFamily: FONT.sans, fontSize: 30, fontWeight: 600, color, marginRight: i === n - 1 ? 0 : 6 }}>
            {w}
          </span>
        );
      })}
    </div>
  );
};

export const S5: React.FC = () => {
  const local = useCurrentFrame();
  const f = local + S5_FROM;

  // ── 完成拍（690–720）：卡上浮 + 顿帧 + 划掉 + 压暗 + 绿勾 ──
  const HIT = 694;
  const shakeT = f - (HIT + 2);
  const shake = shakeT >= 0 && shakeT <= 8 ? 3 * Math.exp(-shakeT / 1.6) : 0;
  const lift = f >= HIT ? 6 * (1 - rampD(f, HIT, 14, E.outCubic)) : 0;
  const strike = rampD(f, 696, 12, E.outCubic);
  const dim = rampD(f, 700, 14, E.smooth);
  const check = rampD(f, 704, 7, E.outCubic);
  const doneOn = rampD(f, 708, 8, E.smooth);

  // ── 会话 park（726–769）：不淡出，以左缘为锚微缩 1→0.985（右缘 1080 → 1063.8）──
  const park = segLinear(f, PARK0, PARK0 + PARK_DUR, E.inOutCubic);
  const paneScale = 1 + (PARK_SCALE - 1) * park;

  // 会话里的原指令位置（荧光笔划它）
  const HL_Y = 700;
  const hl = rampD(f, 851, 19, E.outCubic);

  const onBoard = f < CUT;
  /** 会话窗格的当前右缘（给连线用；按 1:1 裁切 + 左锚微缩算） */
  const paneRight = PANE_W * paneScale;

  return (
    <AbsoluteFill style={{ background: C.bg, overflow: 'hidden' }}>
      {onBoard ? (
        // ───── 完成拍：板心特写 ─────
        <AbsoluteFill style={{ transform: `translate(${shake * 0.6}px, ${shake}px)` }}>
          <PageCam src={TEX.sceneFull} pageH={PAGE.h} keys={BOARD_CAM} bg={C.bg} frame={f} ease={(t) => E.smooth(t)}>
            {/* 盖住纹理里那一行，换成会动的覆层 */}
            <div
              style={{
                position: 'absolute',
                left: SCENE.rowDoing.x - 2,
                top: SCENE.rowDoing.y - 1,
                width: SCENE.rowDoing.w + 4,
                height: SCENE.rowDoing.h + 2,
                background: C.surface,
                borderRadius: R.xs,
              }}
            />
            {/* 原位（S3 之前那张待办卡的位置）也一并盖成板面，避免同一个标题出现两次 */}
            <div
              style={{
                position: 'absolute',
                left: SCENE.rowTodo.x - 2,
                top: SCENE.rowTodo.y - 1,
                width: SCENE.rowTodo.w + 4,
                height: SCENE.rowTodo.h + 2,
                background: C.surface,
                borderRadius: R.xs,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: SCENE.rowDoing.x,
                top: SCENE.rowDoing.y - lift,
                width: SCENE.rowDoing.w,
                height: SCENE.rowDoing.h,
                borderRadius: R.xs,
                background: C.bg,
                border: `1px solid ${check > 0.5 ? C.okBorder : C.border}`,
                boxSizing: 'border-box',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '0 9px',
                opacity: 1 - 0.45 * dim,
                boxShadow: `${SHADOW.card}${lift > 0.5 ? ', 0 8px 18px rgba(0,0,0,0.10)' : ''}`,
                zIndex: 6,
                overflow: 'hidden',
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: 2, background: C.accent2, flex: 'none', opacity: 1 - dim * 0.6 }} />
              <span style={{ position: 'relative', flex: 1, minWidth: 0, fontFamily: FONT.sans, fontSize: 14.5, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {/* 划掉线只压住文字本身（12f 从左到右） */}
                <span style={{ position: 'relative', display: 'inline-block' }}>
                  把 README 里过期的地方找出来
                  <span
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: '52%',
                      height: 1.6,
                      width: `${strike * 100}%`,
                      background: C.dim,
                      borderRadius: 1,
                    }}
                  />
                </span>
              </span>
              {/* 绿勾 7f 描出 */}
              {check > 0 ? (
                <svg width={18} height={18} viewBox="0 0 18 18" style={{ flex: 'none' }}>
                  <path
                    d="M3.6 9.4 L7.2 13 L14.6 5"
                    fill="none"
                    stroke={C.accent}
                    strokeWidth={2.4}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    pathLength={1}
                    strokeDasharray={1}
                    strokeDashoffset={1 - check}
                  />
                </svg>
              ) : null}
              <span
                style={{
                  fontFamily: FONT.mono,
                  fontSize: 11.5,
                  color: C.accent,
                  flex: 'none',
                  opacity: doneOn,
                }}
              >
                done
              </span>
            </div>
          </PageCam>
        </AbsoluteFill>
      ) : (
        // ───── 报告交回会话 ─────
        <AbsoluteFill>
          {/* 会话驻留：左侧窗格（与 S6 共用 lib/ChatPane 的那一份实现，保证接缝逐像素一致） */}
          <ChatPane scale={paneScale} hl={hl} />

          {/* 依据连线：从**该行消息的右缘 +8px** 水平指出，到卡片左缘 */}
          {REPORTS.map((r, k) => (
            <ReportLink key={`lnk-${r.head}`} x1={linkX1(k)} x2={CARD_LEFT} y={linkY(k)} draw={rampD(f, r.cue + 5, 10, E.outCubic)} />
          ))}

          {/* 三张报告卡：外观与位置来自 lib/ChatPane + 本文件的逐行对齐常量 */}
          {REPORTS.map((r, k) => {
            const o = segLinear(f, r.cue, r.cue + 6, E.outQuad);
            const b2 = segLinear(f, r.cue, r.cue + 11, E.spring);
            if (o <= 0) return null;
            return (
              <ReportCard
                key={r.head}
                head={r.head}
                body={r.body}
                left={CARD_LEFT}
                top={cardTop(k)}
                width={CARD_W}
                minHeight={CARD_H}
                opacity={o}
                liftY={mix(14, 0, b2)}
                pop={mix(0.94, 1, b2)}
              />
            );
          })}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
