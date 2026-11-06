/**
 * 采集纹理的几何真相（promo/public/textures/layout.json 的副本，页面 CSS px）。
 * 所有覆层元素的落点都从这里取 —— 落进真实槽位，不许凭手感写坐标（Q9）。
 *
 * 拍照时的一次性事实，写死在这里并在 notes.md 记下来源：
 *   - 中央任务板 #scene-center   x 876  y 325.5  w 440  h 429
 *   - 板内列表     #scene-list    x 890  y 366.5  w 412  h 374（行高 36、行距 36）
 *   - 聊天输入区   #input-area    x 272  y 998.4  w 1648 h 81.6
 *   - 真实 textarea 内槽           x 293  y 1009   w 1456 h 57
 */
import layout from './layout.json';

type Box = { x: number; y: number; w: number; h: number };

const el = (name: string): Box => {
  const raw = (layout.elements as Record<string, { x: number; y: number; width: number; height: number }>)[name];
  if (!raw) throw new Error(`layout.json 里没有 ${name}`);
  return { x: raw.x, y: raw.y, w: raw.width, h: raw.height };
};

export const PAGE = { w: 1920, h: 1080 } as const;

/** 场景页（俯视看板） */
export const SCENE = {
  board: el('board'),
  boardList: el('board-list'),
  boardHead: el('board-head'),
  bayWriter: el('bay-writer-1'),
  bayExec: el('bay-exec-1'),
  /**
   * 审稿的工位没被单独采（布局只导出了 bay-writer-1 / bay-exec-1）。
   * 用它的像素方块反推：同一个 176×66.39 的隔间，方块距左缘 +13、距顶 +37.4
   * （由 bay-writer-1 与 agent-writer-1 的差值算出）。
   */
  bayReview: { x: el('agent-review-1').x - 13, y: el('agent-review-1').y - 37.4, w: 176, h: 66.39 },
  agentWriter: el('agent-writer-1'),
  agentExec1: el('agent-exec-1'),
  agentExec2: el('agent-exec-2'),
  agentReview: el('agent-review-1'),
  rowTodo: el('card-row-todo'),
  rowDoing: el('card-row-doing'),
  rowBlocked: el('card-row-blocked'),
  rowDone: el('card-row-done'),
} as const;

/** 板心 = 正多边形的原点；S2/S3 的相机都以它为轴 */
export const BOARD_CENTER = {
  x: SCENE.board.x + SCENE.board.w / 2,
  y: SCENE.board.y + SCENE.board.h / 2,
} as const;

/** 聊天页 */
export const CHAT = {
  sidebar: el('sidebar'),
  messages: el('messages'),
  input: el('input-area'),
  toolCard: el('tool-card'),
  reportBlock: el('report-block'),
} as const;

/**
 * 真实输入框内槽（上表「textarea 内槽」一条）：覆层胶囊与它同尺寸同位置，
 * 只是把占位符那行盖掉、换成真实 React 文字。
 */
export const CHAT_INPUT_SLOT = { x: 293, y: 1009, w: 1000, h: 57 } as const;

/** 板内行的 y 序列（行高 36、行距 36，从第一行 top 起） */
export const ROW_Y = [366.5, 450.5, 486.5, 534.5, 570.5, 606.5, 660.5, 694.5] as const;

/** 本片虚构数据里那条主角卡 —— 标题逐字取自 design-spec §6.1 */
export const HERO = {
  title: '把 README 里过期的地方找出来',
  label: 'docs',
  holder: '执行者#1',
  priority: 'normal' as 'normal' | 'urgent' | 'low',
} as const;
