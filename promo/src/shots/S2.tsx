/**
 * S2 —— 一句话，一张卡（+ 俯视场景揭示）。
 * 两张卡：
 *   · 物件层 row-embed / row-embed
 *     demo TSX：demos/ui-entrance/row-embed/RowEmbed.tsx
 *     命门照抄：落点=真实槽位、底边 2px 强调色缝只闪一次、缝裁进圆角、
 *     下落走 bezier(.5,0,.8,.75)（末段仍带速度砸进槽位）+ press 回弹。
 *   · 相机层 crane-rise-reveal / crane-rise-reveal
 *     demo TSX：demos/opening/crane-rise-reveal/CraneRiseReveal.tsx
 *     命门照抄：scale 3.0→1.0 / 102f / 一条 bezier(0.2,0,0.25,1) 共用给
 *     对准点与 scale（零速起步、19% 处峰速、长尾临顶缓停）；视野上缘越过某行
 *     即触发该行洗光（逐帧解，不固定间隔）；满幅后不再补推、静止 ≥30f。
 *
 * 适配性改动（promo/notes.md）：
 *   · 空板 backplate 用 scene-full-empty，在本镜开头 120–132f 交叉淡入满板纹理 ——
 *     两张都是真截图；不这么做就只能给落点打补丁、假装那格是空的。
 *   · 主角卡是 React 真文字覆层（真实卡行只有 36px 高，放大 3.2 倍后仍是原文，
 *     但需要它在镜头里动，所以用覆层盖住原行）。
 */
import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { C, FONT, R, SHADOW } from '../lib/pot';
import { TEX } from '../assets';
import { E, ramp, rampD, segLinear, mix, clamp01, mulberry32, dampedSettle } from '../lib/helpers';
import { BOARD_CENTER, HERO, PAGE, ROW_Y, SCENE } from '../sceneLayout';
import { SHOT } from '../timeline';

export const S2_FROM = SHOT('S2').from; // 120
export const S2_DURATION = SHOT('S2').dur; // 180

const SLOT = SCENE.rowTodo; // 真实槽位（layout.json）
const HOLD_ZOOM = 3.2;
const CRANE_START = 144;
const CRANE_END = 246;
const FLY = 14; // row-embed：飞行 12f + 缓冲，压到 14f
const LAND = S2_FROM + FLY; // 134

/**
 * 取景按**内容包围盒**，不按整页（1920×1080 里大半是空底色）。
 * 内容 = 中央任务板 x876..1316 / y325.5..754.5 + 三个工位（writer 634,722.8 /
 * exec 1008,74.8 / review 1382,722.8，各 176×66.4）
 *   → 包围盒 x 634..1558（924 宽）、y 74.8..789.2（714 高），中心 (1096, 432)。
 * zoom 1.45：可见 1324×745，内容 924×714 装得下，左右各余 200、上下各余 15.5；
 * 内容占画面高度 714×1.45 = 1035 / 1080 = **95.8%**（旧值 zoom 1.0 只有 23% 宽，四周全是死白）。
 */
const REVEAL_ZOOM = 1.45;
const CONTENT_CY = 431; // (74.8 + 789.2) / 2 ≈ 432，取 431 让下沿多留 1px
const CONTENT_CX = BOARD_CENTER.x; // = 1096，与包围盒水平中心一致

const CAM: CamKey[] = [
  { frame: 120, cx: CONTENT_CX, cy: CONTENT_CY, zoom: HOLD_ZOOM, rotX: 0 },
  { frame: CRANE_START, cx: CONTENT_CX, cy: CONTENT_CY, zoom: HOLD_ZOOM, rotX: 0 },
  { frame: CRANE_END, cx: CONTENT_CX, cy: CONTENT_CY, zoom: REVEAL_ZOOM, rotX: 0 },
  { frame: 300, cx: CONTENT_CX, cy: CONTENT_CY, zoom: REVEAL_ZOOM * 1.018, rotX: 0 },
];

/**
 * S2 **最后一帧的取景**，供 S3 起手对齐用（卡 p-864cf327）。
 *
 * 为什么不能直接用 `REVEAL_ZOOM`：S2 在自己的 Sequence 里只渲染到 local 179 = 绝对帧 299，
 * 而 CAM 的末键是帧 300 —— 所以 299 帧并不是 1.45，而是 246→300 这段线性推近上的 53/54 处
 * （≈1.4756）。S3 若从 1.45 起手，板上会跳 1.8%（约 11px），正好超出卡里给的 1px 容差。
 *
 * 这里**不新增任何数值**：只用 CAM 里已有的两个键按同一条线性插值取 299 帧，
 * 所以以后谁改了 S2 的收尾推近，S3 的起手会自动跟着走。
 */
const S2_EXIT_FRAME = SHOT('S2').from + SHOT('S2').dur - 1; // 299
const CAM_PENULT = CAM[CAM.length - 2]; // frame 246, zoom REVEAL_ZOOM
const CAM_LAST = CAM[CAM.length - 1]; // frame 300, zoom REVEAL_ZOOM * 1.018
const EXIT_T = (S2_EXIT_FRAME - CAM_PENULT.frame) / (CAM_LAST.frame - CAM_PENULT.frame);
export const S2_EXIT_CAM = {
  frame: S2_EXIT_FRAME,
  cx: CONTENT_CX,
  cy: CONTENT_CY,
  zoom: CAM_PENULT.zoom + (CAM_LAST.zoom - CAM_PENULT.zoom) * EXIT_T,
} as const;

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/**
 * 相机在绝对帧 f 的取景（只用来解洗光触发帧）。
 * ⚠ 这里的 cy/zoom 插值必须与上面 CAM 的三个关键帧同步改：
 * 洗光按「视野上缘首次越过某行顶边」触发，cy 一偏，每行的触发帧就全错位。
 * 现在整条运镜是纯 zoom（cx/cy 恒定），所以没有漂移项。
 */
const camAt = (frame: number) => {
  const p = frame <= CRANE_START ? 0 : frame >= CRANE_END ? 1 : E.crane(clamp01((frame - CRANE_START) / (CRANE_END - CRANE_START)));
  const zoom = HOLD_ZOOM + (REVEAL_ZOOM - HOLD_ZOOM) * p;
  const cy = CONTENT_CY; // 起手与落定同一个 cy → 纯 zoom，无漂移
  return { zoom, cy, visTop: cy - 540 / zoom };
};

/** 每行洗光的触发帧：视野上缘首次越过该行顶边（开场已在画内的不触发） */
const ROW_TRIG = ROW_Y.map((y) => {
  if (camAt(CRANE_START).visTop <= y) return -1;
  for (let f = CRANE_START; f <= CRANE_END; f++) if (camAt(f).visTop <= y + 2) return f;
  return CRANE_END;
});

/** 相机 ease：拉升段走 crane，其余段（最后的 1→1.018 极缓推近）走 linear */
const easeFor = (frame: number) => (t: number) => (frame >= CRANE_START && frame < CRANE_END ? E.crane(t) : t);

export const S2: React.FC = () => {
  const local = useCurrentFrame();
  const f = local + S2_FROM;

  // 空板 → 满板（真截图之间的交叉淡化，压在开头，卡还没落地）
  const fullOn = rampD(f, S2_FROM + 2, 12, E.smooth);

  // row-embed 飞行
  const p = segLinear(f, S2_FROM, LAND, E.drop); // 0→1，末段仍带速度
  const air = 1 - p;
  const landed = f >= LAND;
  const press = landed ? ramp(f, LAND, LAND + 4, E.outQuad) : 0;
  const scale = landed ? 0.995 + 0.005 * press : 1.06 - 0.065 * p;
  const appear = ramp(f, S2_FROM, S2_FROM + 3, E.linear);
  // 纵向速度 → 运动模糊（落地为 0）
  const vy = 120 * (1 - segLinear(f + 0.5, S2_FROM, LAND, E.drop) - (1 - segLinear(f - 0.5, S2_FROM, LAND, E.drop)));
  const mb = landed ? 0 : Math.min(3.2, Math.abs(vy) * 0.22);

  // 底边 2px 强调色缝
  const seamSpread = landed ? ramp(f, LAND, LAND + 5, E.outCubic) : 0;
  const seamOp = landed ? interpolate(f, [LAND, LAND + 2, LAND + 8], [1, 1, 0], clamp) : 0;

  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {/* 空板 backplate（真截图，任务板无卡） */}
      <AbsoluteFill style={{ opacity: 1 }}>
        <PageCam src={TEX.sceneFullEmpty} pageH={PAGE.h} keys={CAM} bg={C.bg} ease={easeFor(f)} frame={f} />
      </AbsoluteFill>
      {/* 满板（真截图） */}
      <AbsoluteFill style={{ opacity: fullOn }}>
        <PageCam src={TEX.sceneFull} pageH={PAGE.h} keys={CAM} bg={C.bg} ease={easeFor(f)} frame={f}>
          {/* 逐行洗光：视野上缘越过一行，该行一道强调色从左掠过（crane 的可读性来源） */}
          {ROW_TRIG.map((t, i) => {
            if (t < 0) return null;
            const prog = rampD(f, t, 20, E.outCubic);
            const op = Math.min(1, rampD(f, t, 3, E.linear)) * (1 - rampD(f, t + 6, 18, E.smooth));
            if (op <= 0.002) return null;
            const head = -0.2 + 1.3 * prog;
            return (
              <div
                key={`sweep-${i}`}
                style={{
                  position: 'absolute',
                  left: SCENE.boardList.x - 6,
                  top: ROW_Y[i] - 2,
                  width: SCENE.boardList.w + 12,
                  height: 32,
                  borderRadius: R.xs + 2,
                  opacity: op,
                  background: `linear-gradient(90deg, rgba(21,128,61,0.02) 0%, rgba(21,128,61,0.16) ${(head * 100).toFixed(1)}%, rgba(21,128,61,0) ${((head + 0.24) * 100).toFixed(1)}%)`,
                  boxShadow: `inset 0 0 0 1px rgba(21,128,61,0.16)`,
                }}
              />
            );
          })}

          {/* 落点补丁：把真实纹理里的那一行压成板面，等主角卡自己落进去（Q9：不悬空） */}
          <div
            style={{
              position: 'absolute',
              left: SLOT.x - 2,
              top: SLOT.y - 1,
              width: SLOT.w + 4,
              height: SLOT.h + 2,
              background: C.surface,
              borderRadius: R.xs,
              opacity: ramp(f, S2_FROM, S2_FROM + 4, E.linear),
            }}
          />

          {/* 主角卡：真实文字覆层，从空中砸进真实槽位 */}
          {f >= S2_FROM && f < 300 ? (
            <div
              style={{
                position: 'absolute',
                left: SLOT.x,
                top: SLOT.y,
                width: SLOT.w,
                height: SLOT.h,
                opacity: appear,
                zIndex: 6,
                transform: `perspective(900px) translateY(${(-120 * air).toFixed(2)}px) rotateX(${(16 * air).toFixed(3)}deg) scale(${scale.toFixed(4)})`,
                filter: mb > 0.25 ? `blur(0px)` : undefined,
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  borderRadius: R.xs,
                  background: C.bg,
                  border: `1px solid ${C.border}`,
                  boxSizing: 'border-box',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '0 9px',
                  overflow: 'hidden',
                  // 两层影：离地时大而虚 + 近地小而实；落地后收敛成卡片影
                  boxShadow: `0 ${(34 * air).toFixed(1)}px ${(64 * air).toFixed(1)}px -10px rgba(0,0,0,${(0.18 * air).toFixed(3)}), ${SHADOW.card}`,
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: C.accent2, flex: 'none' }} />
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontFamily: FONT.sans,
                    fontSize: 14.5,
                    color: C.text,
                  }}
                >
                  {HERO.title}
                </span>
                <span style={{ fontFamily: FONT.mono, fontSize: 11.5, color: C.dim, flex: 'none' }} />
              </div>
              {/* 嵌入瞬间的 2px 强调色缝：只闪一次、两端羽化、裁在圆角里 */}
              {seamOp > 0 ? (
                <div
                  style={{
                    position: 'absolute',
                    left: (SLOT.w - SLOT.w * seamSpread) / 2,
                    top: SLOT.h - 2,
                    width: SLOT.w * seamSpread,
                    height: 2,
                    borderRadius: 1,
                    opacity: seamOp,
                    background: `linear-gradient(90deg, rgba(21,128,61,0) 0%, ${C.accent} 18%, ${C.accent} 82%, rgba(21,128,61,0) 100%)`,
                    boxShadow: `0 0 7px rgba(21,128,61,0.38)`,
                  }}
                />
              ) : null}
            </div>
          ) : null}
        </PageCam>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
