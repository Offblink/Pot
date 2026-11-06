/**
 * 静态资源路径。
 *
 * 本机实测（remotion 4.0.484）：`window.remotion_staticBase` 是 `/public`，
 * 而 `<Img>` 自己会把静态基准拼到相对路径前面。于是：
 *   · `staticFile('textures/x.png')` → 内部先拼成 `/public/textures/x.png`，
 *     再被「已经带 staticBase 前缀」的检查判为非法而抛错（模板工程首帧同样报这个）；
 *   · 手工拼 `/public/...` 给 `<Img>` → 会被再拼一次，变成 `/public/public/...` 404。
 * 正确做法就是**给相对路径**，让 Remotion 自己拼基准。这个函数只做一件事：
 * 去掉前导斜杠、保留相对路径。
 */
export const staticUrl = (path: string): string => path.replace(/^\/+/, '');
