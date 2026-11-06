/**
 * 纹理入口。阶段 4 的采集产物在 public/textures/，这里按模块**导入**而不是走
 * staticFile()/静态 URL：
 *   · 本机 remotion 4.0.484 的 staticBase 是 `/public`，`staticFile()` 会把自己拼好的
 *     `/public/...` 再判一次「已带前缀」而抛错；手工拼又会被拼第二次成 `/public/public/...`；
 *     相对路径则直接 404（见 src/lib/staticUrl.ts 的注释）。
 *   · 导入走 webpack 的资源处理，预览与渲染都拿得到稳定 URL。
 * 文件名保留采集时的 `@2x` 语义（sanitize-textures.py 生成 `-2x` 副本，因为 `@` 在
 * URL 里会被二次编码）。
 */
import chatFull from '../public/textures/chat-full-zh-2x.png';
import sceneFull from '../public/textures/scene-full-zh-2x.png';
import sceneFullEmpty from '../public/textures/scene-full-empty-2x.png';
import sceneBoard from '../public/textures/scene-board-2x.png';
import chatReport from '../public/textures/chat-report-2x.png';

export const TEX = {
  /** 聊天 WebUI 整页（3840×2160，CSS 1920×1080） */
  chatFull,
  /** 俯视场景整页（有 9 张卡） */
  sceneFull,
  /** 俯视场景整页（任务板无卡，飞入镜头的空 backplate） */
  sceneFullEmpty,
  /** 中央任务板元素切片 */
  sceneBoard,
  /** 报告卡片块切片 */
  chatReport,
} as const;
