/**
 * S4 —— 配额满了，就多开一个。
 * 卡：quad-split-parallel-scenes / quad-split-parallel-scenes
 * demo TSX：demos/rhythm/quad-split-parallel-scenes/QuadSplitParallelScenes.tsx
 * 卡的配方 = **错拍表**（相邻重事件 3–6f，任一帧不得两格同时发生重事件），不是 2×2 的外形。
 * 本片按 5B 卡的要求把它落到 Pot 自己的空间里：**俯视场景里的多条轨道同时前进**，
 * 不并排三块 UI 截图；四路各自跑自己的微事件：
 *   TL 写手在轨道上推卡 / TR 审稿逐条勾清单 / BL exec#1 的耗时读数跳数 / BR wip 1/1 满 → 复印出 exec#2 → ×2
 * 错拍表（本镜自己的，逐条核过相邻 ≥3f）：
 *   546 TL  552 TR  556 BL  560 TL  566 TR  570 BL  574 TL  580 TR  584 BL
 *   588 BR wip 红  600 BR exec#2 亮  608 BR ×2  616 BR wip 2/2
 * 适配改动：2×2 硬切 → 同一块板上的四条轨道；末段 660–675 四轨收拢回一整块板（本片独有，
 * 把"并行"收束成"一块板"的主语，也是 S5 的接缝）。
 */
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { TEX } from '../assets';
import { C, FONT, R, SHADOW } from '../lib/pot';
import { E, ramp, rampD, segLinear, mix, clamp01, mulberry32, dampedSettle } from '../lib/helpers';
import { BOARD_CENTER, PAGE, SCENE } from '../sceneLayout';
import { SHOT } from '../timeline';

export const S4_FROM = SHOT('S4').from; // 540
export const S4_DURATION = SHOT('S4').dur; // 150

const ZOOM = 1.18;
const CAM: CamKey[] = [
  { frame: 540, cx: BOARD_CENTER.x, cy: 495, zoom: ZOOM, rotX: 0 },
  { frame: 660, cx: BOARD_CENTER.x, cy: 492, zoom: ZOOM + 0.02, rotX: 0 },
  { frame: 690, cx: BOARD_CENTER.x, cy: 490, zoom: ZOOM + 0.03, rotX: 0 },
];

/** 四个轨道端点（工位 → 板心），坐标全部来自 layout.json */
const LANES = [
  { id: 'writer', from: { x: SCENE.bayWriter.x + 88, y: SCENE.bayWriter.y }, label: '写手', color: C.accent2, events: [546, 560, 574] },
  { id: 'review', from: { x: SCENE.bayReview.x + 88, y: SCENE.bayReview.y }, label: '审稿', color: C.accent3, events: [552, 566, 580] },
  { id: 'exec1', from: { x: SCENE.bayExec.x, y: SCENE.bayExec.y + 66 }, label: '执行者#1', color: C.accent, events: [556, 570, 584] },
  { id: 'exec2', from: { x: SCENE.bayExec.x + 176, y: SCENE.bayExec.y + 66 }, label: '执行者#2', color: C.accent, events: [600, 608, 616] },
] as const;

const toBoard = (p: { x: number; y: number }) => {
  const dx = BOARD_CENTER.x - p.x;
  const dy = BOARD_CENTER.y - p.y;
  const len = Math.hypot(dx, dy) || 1;
  // 轨道只画到任务板的外缘（画进板面就成了涂鸦，而且会压住卡行）
  const halfW = SCENE.board.w / 2 + 10;
  const halfH = SCENE.board.h / 2 + 10;
  const reach = Math.min(
    Math.abs(dx) > 1e-6 ? halfW / Math.abs(dx / len) : Infinity,
    Math.abs(dy) > 1e-6 ? halfH / Math.abs(dy / len) : Infinity,
    len,
  );
  return { dx: dx / len, dy: dy / len, len: reach };
};

/** 一条轨道上第 k 个事件的推进进度（0..1），轨道收拢阶段整体退回 */
const laneProgress = (f: number, events: readonly number[], k: number) => {
  const cue = events[k];
  return clamp01((f - cue) / 10);
};

export const S4: React.FC = () => {
  const local = useCurrentFrame();
  const f = local + S4_FROM;

  // 收拢：660–675 四轨退回、缝消失，回到一整块板
  const collapse = ramp(f, 660, 675, E.inOutCubic);
  const laneAlpha = 1 - collapse;
  const spawn = rampD(f, 604, 6, E.linear); // exec#2 方块亮起（明度跳变，不缩放）
  const wipFull = f >= 588 && f < 616;
  const counterOn = rampD(f, 608, 6, E.outCubic);

  // 计数器 ×2 的滚动格：确定性伪随机只用于极轻的姿态抖动
  const jitter = (i: number) => {
    const r = mulberry32(0x9e + i);
    return (r() - 0.5) * 2;
  };

  return (
    <AbsoluteFill style={{ background: C.bg, overflow: 'hidden' }}>
      <PageCam src={TEX.sceneFull} pageH={PAGE.h} keys={CAM} bg={C.bg} frame={f} ease={(t) => E.smooth(t)}>
        {/* 四条轨道：一条强调色细轨从工位连向板心，事件沿轨道推进 */}
        {LANES.map((lane, li) => {
          const { dx, dy, len } = toBoard(lane.from);
          const grow = rampD(f, 542 + li * 2, 12, E.outCubic) * laneAlpha;
          if (grow <= 0.01) return null;
          return (
            <svg key={lane.id} width={1920} height={1080} style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity: grow }}>
              <line
                x1={lane.from.x}
                y1={lane.from.y}
                x2={lane.from.x + dx * len}
                y2={lane.from.y + dy * len}
                stroke={lane.color}
                strokeWidth={2}
                strokeDasharray="6 8"
                opacity={0.5}
                strokeDashoffset={(1 - grow) * 200}
              />
              {lane.events.map((cue, k) => {
                const p = laneProgress(f, lane.events, k);
                if (p <= 0 || p >= 1) return null;
                const px = lane.from.x + dx * len * p;
                const py = lane.from.y + dy * len * p;
                return (
                  <g key={k}>
                    <circle cx={px} cy={py} r={5} fill={lane.color} opacity={1 - p * 0.6} />
                    <circle cx={px} cy={py} r={11} fill="none" stroke={lane.color} strokeWidth={1.5} opacity={(1 - p) * 0.6} />
                  </g>
                );
              })}
            </svg>
          );
        })}

        {/* TL：写手推上去的那张卡（沿轨道滑到板边），三次脉冲式微调标题 */}
        {f >= 546 && f < 660 ? (
          <div
            style={{
              position: 'absolute',
              left: SCENE.board.x - 116,
              top: SCENE.rowTodo.y - 8,
              width: 108,
              height: 30,
              borderRadius: R.xs,
              background: C.surface,
              border: `1px solid ${C.border}`,
              boxShadow: SHADOW.card,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '0 8px',
              opacity: laneAlpha * rampD(f, 546, 8, E.outCubic),
              transform: `translateX(${(1 - rampD(f, 546, 30, E.expo)) * -46}px)`,
              zIndex: 8,
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: 2, background: C.accent2, flex: 'none' }} />
            <span style={{ fontFamily: FONT.sans, fontSize: 11.5, color: C.text2, whiteSpace: 'nowrap', overflow: 'hidden' }}>
              补中文注释
            </span>
          </div>
        ) : null}

        {/* TR：审稿的清单勾选（三次，错开 566/580） */}
        {f >= 552 && f < 660 ? (
          <div
            style={{
              position: 'absolute',
              left: SCENE.board.x + SCENE.board.w + 24,
              top: SCENE.rowDoing.y - 4,
              width: 132,
              padding: '8px 10px',
              borderRadius: R.sm,
              background: C.surface,
              border: `1px solid ${C.border}`,
              boxShadow: SHADOW.card,
              display: 'flex',
              flexDirection: 'column',
              gap: 5,
              opacity: laneAlpha * rampD(f, 552, 8, E.outCubic),
              zIndex: 8,
            }}
          >
            <span style={{ fontFamily: FONT.sans, fontSize: 10.5, color: C.dim, letterSpacing: '0.04em' }}>审稿 · 清单</span>
            {[552, 566, 580].map((cue, i) => {
              const on = rampD(f, cue, 5, E.outCubic);
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      width: 11,
                      height: 11,
                      borderRadius: 3,
                      border: `1.5px solid ${on > 0.4 ? C.accent : C.border}`,
                      background: on > 0.4 ? C.accent : 'transparent',
                      flex: 'none',
                    }}
                  />
                  <span
                    style={{
                      fontFamily: FONT.sans,
                      fontSize: 11,
                      color: on > 0.4 ? C.text : C.dim,
                      textDecoration: on > 0.4 ? 'line-through' : 'none',
                    }}
                  >
                    {['核对小节标题', '复核旧链接', '通读一遍'][i]}
                  </span>
                </div>
              );
            })}
          </div>
        ) : null}

        {/* BL：exec#1 的工具卡耗时读数跳数（三次） */}
        {f >= 556 && f < 660 ? (
          <div
            style={{
              position: 'absolute',
              left: SCENE.bayExec.x - 30,
              top: SCENE.bayExec.y + 78,
              padding: '7px 11px',
              borderRadius: R.sm,
              background: C.toolBg,
              border: `1px solid ${C.toolBorder}`,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              opacity: laneAlpha * rampD(f, 556, 8, E.outCubic),
              zIndex: 8,
            }}
          >
            <span style={{ fontFamily: FONT.sans, fontSize: 11, color: C.accent2 }}>检索 README</span>
            <span style={{ fontFamily: FONT.mono, fontSize: 11.5, color: C.text, fontVariantNumeric: 'tabular-nums' }}>
              {(Math.round(3 + ramp(f, 556, 60, E.linear) * 9)).toString()}s
            </span>
          </div>
        ) : null}

        {/* BR：WIP 配额 + 实例增殖（本镜的"满了就多开一个"） */}
        <div
          style={{
            position: 'absolute',
            left: SCENE.bayExec.x + 96,
            top: SCENE.bayExec.y - 34,
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            alignItems: 'flex-start',
            opacity: rampD(f, 544, 10, E.smooth),
            zIndex: 9,
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              height: 20,
              padding: '0 9px',
              borderRadius: 999,
              border: `1px solid ${wipFull ? C.warnBorder : C.okBorder}`,
              background: wipFull ? C.warnBg : C.okBg,
              color: wipFull ? '#b45309' : C.accent,
              fontFamily: FONT.mono,
              fontSize: 11.5,
              fontWeight: 600,
              transform: `scale(${wipFull ? 1.04 : 1})`,
            }}
          >
            {wipFull ? 'wip 1/1' : 'wip 2/2'}
          </div>
          {/* ×2 计数：滚一格 */}
          <div style={{ height: 16, overflow: 'hidden', opacity: counterOn }}>
            <div style={{ transform: `translateY(${(1 - counterOn) * 16}px)`, fontFamily: FONT.mono, fontSize: 12, color: C.accent, fontWeight: 700 }}>
              ×2
            </div>
          </div>
        </div>

        {/* exec#2 的像素方块：同尺寸、明度跳变亮起（不做缩放弹跳） */}
        <div
          style={{
            position: 'absolute',
            left: SCENE.agentExec1.x + 26,
            top: SCENE.agentExec1.y,
            width: SCENE.agentExec1.w,
            height: SCENE.agentExec1.h,
            borderRadius: 2,
            border: `2px solid ${spawn > 0.5 ? C.text : 'transparent'}`,
            background: spawn > 0.5 ? C.accent : 'transparent',
            boxShadow: spawn > 0.5 ? `0 0 10px ${C.accentGlow}` : 'none',
            opacity: spawn,
            zIndex: 7,
          }}
        />

        {/* 租约倒计时环：套在板心那张 doing 卡上，全程匀速回转 */}
        {f >= 548 && f < 660 ? (
          <>
            <div
              style={{
                position: 'absolute',
                left: SCENE.rowDoing.x + SCENE.rowDoing.w - 18,
                top: SCENE.rowDoing.y + 6,
                width: 24,
                height: 24,
                borderRadius: 999,
                border: `2px solid ${C.border}`,
                opacity: laneAlpha * 0.9,
                zIndex: 8,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: SCENE.rowDoing.x + SCENE.rowDoing.w - 18,
                top: SCENE.rowDoing.y + 6,
                width: 24,
                height: 24,
                borderRadius: 999,
                border: `2px solid ${C.accent}`,
                borderTopColor: 'transparent',
                opacity: laneAlpha * 0.9,
                transform: `rotate(${((f - 548) / 30) * 360 + jitter(0) * 0}deg)`,
                zIndex: 8,
              }}
            />
          </>
        ) : null}
      </PageCam>

      {/* 收拢后的一记极淡压实：整块板回到静止（0.5s rest 的开头） */}
      <AbsoluteFill
        style={{
          pointerEvents: 'none',
          background: C.bg,
          opacity: Math.max(0, (f - 675) / 15) * 0,
        }}
      />
    </AbsoluteFill>
  );
};
