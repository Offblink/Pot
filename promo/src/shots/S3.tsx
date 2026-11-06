/**
 * S3 —— 谁认领，由标签决定。
 * 卡：crash-zoom-punch / crash-zoom-punch（撞停款）
 * demo TSX：demos/camera/crash-zoom-punch/CrashImpactReal.tsx
 * 命门照抄：急推 6f ease-in(cubic) 1→2.0；撞停**不回弹**、机位高频抖
 * 14px·e^(−t/1.8) 6f 收干；前 hold ≥30f 建立全景、后 hold ≥45f 读特写；
 * 运动模糊只包急推段、震屏段保持清晰。（全片 slam 配额 3 处，这里是第 1 处。）
 *
 * 适配性改动（promo/notes.md）：
 *   · 撞停时的"整幅负片/集中线"不做 —— 与 Pot 的亮场工程嗓音冲突，代价是把 slam
 *     的重音全部押在顿帧 + 震屏 + 一次红 chip 翻转上（卡里 3f 负片本就是可选款）。
 *   · 收尾不回 1.0，停在 1.45 并把取景中心上抬到 436：回 1.0 时板只占画宽 23%，
 *     "卡滑向进行中""方块亮起"都会退化成几个像素；而上抬是为了让执行者工位的
 *     像素方块与租约环（页面 y≈75–133）真的进画。
 *   · 被拒的角色是**审稿**不是写手：采集数据里 写手.canClaim = [docs] 而卡标签也是
 *     docs（相交，不该被拒）；让 审稿（canClaim [review]）去撞 docs 才是画面与数据
 *     自洽的那次 role_mismatch。文案（role_mismatch / 执行 / 执行者#1）一个字没改。
 */
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { C, FONT, R, SHADOW } from '../lib/pot';
import { TEX } from '../assets';
import { E, ramp, rampD, segLinear, mix, clamp01, mulberry32, dampedSettle } from '../lib/helpers';
import { BOARD_CENTER, HERO, PAGE, SCENE } from '../sceneLayout';
import { RHYTHM, SHOT } from '../timeline';
import { S2_EXIT_CAM } from './S2';

export const S3_FROM = SHOT('S3').from; // 300
export const S3_DURATION = SHOT('S3').dur; // 240

const SLOT = SCENE.rowTodo; // 890, 534.5, 412, 36
const DEST = SCENE.rowDoing; // 890, 450.5, 412, 36
const PUNCH = RHYTHM.hitStop ? 336 : 336; // 急推起
const HIT = PUNCH + 6; // 342 撞停
const FREEZE = RHYTHM.hitStop; // 2f 顿帧
const REJECT = 352;
const FIX = 390;
const PULL = 420;
const CLAIM = 444;

const CLOSE_ZOOM = 2.15; // 上限（卡给的区间 2.0–2.15 里选了上限：起手 1.4756 时这是 1.457 倍急推，2.0 只有 1.355 倍，偏软）。2.15 下可见高 502 vs 板 429 → 上下各余 36.7 页面 px = **78.9 屏幕 px**，减震屏 14px 仍安全
const FAR_ZOOM = 1.5; // 收尾：可见高度 720；板底 754.5 与执行者工位顶 75 同时进画

/**
 * 收尾的取景中心**向上抬**（540 → 425）：执行者工位在页面 y≈74.8–141.2，
 * cy=540 时可见上缘 180，方块与租约环整块在画外——那样"方块亮起 + 租约环"就白做了。
 * cy=425 / 1.5x 时：工位 15–114、板 391–1034（四边留白 630/15/630/46），
 * 两者之间的空地板 114–391 正好留给字幕（PotPromo 把 S3 这句放到顶部 126–226）。
 */
const PULL_CY = 425;

/**
 * 起手机位 = **S2 最后一帧的机位**（卡 p-864cf327）。
 * 帧 299 → 300 逐像素连续，读作"同一个机位硬切"，不再有"整页缩小 + 左上冒侧栏"的跳变。
 * 常量从 S2 导出（`S2_EXIT_CAM`），不是在这里抄一份数值——以后 S2 改收尾，S3 自动跟随。
 *
 * 撞停段（336→342）只把 cy 从 431 抬到 540（板心），zoom 推到 CLOSE_ZOOM：
 * cy 必须回 540，否则 2.15x 下可见带是 288.8..791.2 vs 板 325.5..754.5 之外——
 * 板底 754.5 会贴在 791.2 之内但上面 325.5 已越过 288.8 的余量不足，实算会切。
 */
const CAM: CamKey[] = [
  { frame: 300, cx: S2_EXIT_CAM.cx, cy: S2_EXIT_CAM.cy, zoom: S2_EXIT_CAM.zoom, rotX: 0 },
  { frame: PUNCH, cx: S2_EXIT_CAM.cx, cy: S2_EXIT_CAM.cy, zoom: S2_EXIT_CAM.zoom, rotX: 0 },
  { frame: HIT, cx: BOARD_CENTER.x, cy: BOARD_CENTER.y, zoom: CLOSE_ZOOM, rotX: 0 },
  { frame: PULL, cx: BOARD_CENTER.x, cy: BOARD_CENTER.y, zoom: CLOSE_ZOOM, rotX: 0 },
  { frame: CLAIM, cx: BOARD_CENTER.x, cy: PULL_CY, zoom: FAR_ZOOM, rotX: 0 },
  { frame: 540, cx: BOARD_CENTER.x, cy: PULL_CY, zoom: FAR_ZOOM + 0.02, rotX: 0 },
];

/** 急推走 ease-in(cubic)（卡：>10f 就成普通推近），其余段 smooth */
const easeFor = (frame: number) => (t: number) => (frame >= PUNCH && frame <= HIT ? E.inCubic(t) : E.smooth(t));

/** 顿帧：撞停后 2f 把动画时间按住（整画面 slam 的"咬住"手感） */
const holdFrame = (f: number) => (f >= HIT ? f - FREEZE : f);

/** 震屏：14px · e^(−t/1.8)，6f 收干。确定性——用 mulberry32 固定种子，不用 Math.random */
const SHAKE = Array.from({ length: 12 }, (_, i) => {
  const rnd = mulberry32(0x50 + i);
  return { x: rnd() * 2 - 1, y: rnd() * 2 - 1 };
});
const shakeAt = (f: number) => {
  const t = f - HIT;
  if (t < 0 || t > 10) return { x: 0, y: 0 };
  const amp = RHYTHM.shakeAmp * Math.exp(-t / RHYTHM.shakeTau);
  const s = SHAKE[Math.min(SHAKE.length - 1, Math.max(0, Math.round(t)))];
  return { x: s.x * amp, y: s.y * amp };
};

/**
 * chip 样式。**原来的签名 `chip(text, ...)` 把 text 当参数收下却从不渲染**，
 * 于是校验条上只剩两个空药丸（S3-a.png 里那个"淡红圆圈"就是它）——
 * 现在只返回样式，文字由调用处的 children 提供。
 */
const chipStyle = (fg: string, bg: string, border: string, mono = false): React.CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  height: 20,
  padding: '0 9px',
  borderRadius: 999,
  border: `1px solid ${border}`,
  background: bg,
  color: fg,
  fontFamily: mono ? FONT.mono : FONT.sans,
  fontSize: 13,
  fontWeight: 600,
  lineHeight: 1,
  whiteSpace: 'nowrap',
  flex: 'none',
});

export const S3: React.FC = () => {
  const local = useCurrentFrame();
  const f = local + S3_FROM;

  const camFrame = holdFrame(f);
  const shake = shakeAt(f);

  // 被拒：卡退 4px（一次 recoil，不弹跳）+ 红色 chip
  const recoil = f >= REJECT ? 4 * (1 - ramp(f, REJECT, REJECT + 8, E.outCubic)) : 0;
  // 通过：夹住后的绿 chip
  const fixed = f >= FIX;

  // 444：从待办行滑到进行中行（30f），随后身份落位
  const slide = ramp(f, CLAIM, CLAIM + 30, E.expo);
  const cardY = mix(SLOT.y, DEST.y, slide);
  const metaOn = rampD(f, CLAIM + 12, 12, E.smooth);

  // 方块亮起：一次明度跳变（不缩放，硬规则）
  const lit = rampD(f, CLAIM + 6, 6, E.linear);
  // 租约环：起转
  const ringOn = rampD(f, CLAIM + 18, 12, E.smooth);
  const ringSpin = ((camFrame - (CLAIM + 18)) / 30) % 1;

  const stripOp = Math.min(rampD(f, REJECT - 6, 8, E.smooth), 1 - rampD(f, CLAIM - 10, 10, E.smooth));
  const vacated = rampD(f, CLAIM + 8, 10, E.smooth); // 原位空出：把纹理里那张卡盖成板面

  return (
    <AbsoluteFill style={{ background: C.bg, overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `translate(${shake.x.toFixed(2)}px, ${shake.y.toFixed(2)}px)` }}>
        <PageCam src={TEX.sceneFull} pageH={PAGE.h} keys={CAM} bg={C.bg} ease={easeFor(camFrame)} frame={camFrame}>
          {/* 主角卡：真实文字覆层，盖住纹理里的那一行，好让它自己动 */}
          <div
            style={{
              position: 'absolute',
              left: SLOT.x - recoil,
              top: cardY,
              width: SLOT.w,
              height: SLOT.h,
              zIndex: 6,
              borderRadius: R.xs,
              background: C.bg,
              border: `1px solid ${C.border}`,
              boxSizing: 'border-box',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '0 9px',
              overflow: 'hidden',
              boxShadow: SHADOW.card,
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
            <span
              style={{
                fontFamily: FONT.mono,
                fontSize: 11.5,
                color: f >= CLAIM ? C.accent : C.dim,
                flex: 'none',
                opacity: metaOn,
              }}
            >
              {HERO.holder}
            </span>
          </div>

          {/* 原位空出：卡滑走以后，待办那一格回到板面（Q9：不留悬空的旧行） */}
          {vacated > 0 ? (
            <div
              style={{
                position: 'absolute',
                left: SLOT.x - 2,
                top: SLOT.y - 1,
                width: SLOT.w + 4,
                height: SLOT.h + 2,
                background: C.surface,
                borderRadius: R.xs,
                opacity: vacated,
              }}
            />
          ) : null}

          {/* 标签闸：校验条挪到**面板上方**（板外注释），横向 space-between。
              放在行间会压在「整理发布清单」上（580.5 落在 568.5–604.5 的行里）；
              放到板下方会撞字幕带。这里 top = board.y − 34 = 291.5，2.0x 下落在屏幕 y≈43。 */}
          {stripOp > 0.01 ? (
            <div
              style={{
                position: 'absolute',
                left: SCENE.board.x,
                top: SCENE.board.y - 34,
                width: SCENE.board.w,
                height: 22,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                opacity: stripOp,
                zIndex: 7,
              }}
            >
              <span style={chipStyle(C.text2, C.surface2, C.border)}>标签 {HERO.label}</span>
              <span
                style={{
                  fontFamily: FONT.mono,
                  fontSize: 12.5,
                  color: C.dim,
                  whiteSpace: 'nowrap',
                  flex: 'none',
                }}
              >
                {fixed ? '执行者 · canClaim = 不限' : '审稿 · canClaim = [review]'}
              </span>
              <span
                style={
                  fixed
                    ? chipStyle(C.accent, C.okBg, C.okBorder, true)
                    : chipStyle(C.errorText, C.errorBg, C.errorBorder, true)
                }
              >
                {fixed ? '已具备 · 可认领' : 'role_mismatch'}
              </span>
            </div>
          ) : null}

          {/* 对应的像素方块亮起：一次明度跳变 + 一圈租约环（不做缩放弹跳） */}
          <div
            style={{
              position: 'absolute',
              left: SCENE.agentExec1.x - 2,
              top: SCENE.agentExec1.y - 2,
              width: SCENE.agentExec1.w + 4,
              height: SCENE.agentExec1.h + 4,
              borderRadius: 3,
              border: `2px solid ${C.text}`,
              background: lit > 0.5 ? C.accent : 'transparent',
              boxShadow: lit > 0.5 ? `0 0 12px ${C.accentGlow}` : 'none',
              opacity: lit > 0 ? 1 : 0,
              zIndex: 5,
            }}
          />
          {ringOn > 0.01 ? (
            <div
              style={{
                position: 'absolute',
                left: SCENE.agentExec1.x + SCENE.agentExec1.w / 2 - 16,
                top: SCENE.agentExec1.y + SCENE.agentExec1.h / 2 - 16,
                width: 32,
                height: 32,
                borderRadius: 999,
                border: `2px dashed ${C.accent}`,
                opacity: 0.85 * ringOn,
                transform: `rotate(${ringSpin * 360}deg)`,
                zIndex: 5,
              }}
            />
          ) : null}
        </PageCam>
      </AbsoluteFill>

      {/* 撞停时的一次曝光：不是负片，只是一层极短的亮压（Δ 亮度 ≤6%），
          把重音交给顿帧与震屏，颜色仍然只有 Pot 的 token */}
      {f >= HIT && f < HIT + 3 ? (
        <AbsoluteFill
          style={{
            pointerEvents: 'none',
            background: C.surface,
            opacity: 0.06 * (1 - dampedSettle(f - HIT, 0.2, 0.9)),
          }}
        />
      ) : null}
      <span style={{ display: 'none' }}>
        {segLinear(f, 0, 1).toFixed(2)}
        {clamp01(slide).toFixed(2)}
      </span>
    </AbsoluteFill>
  );
};
