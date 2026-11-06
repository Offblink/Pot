# Pot 宣传片 · 阶段 4 素材采集

一条命令重跑全部素材：

```powershell
python promo/capture/capture.py
```

## 它做什么

用 `tests/conftest.py` 的 `WebUIHost`（真宿主 + 假 LLM）在 loopback 上起一个**临时** WebUI，
播种一份虚构看板，用 Playwright(Chromium) 以 `1920×1080 @ deviceScaleFactor 2` 截三层产物：

| 层 | 产物 | 说明 |
|---|---|---|
| 整页图 | `scene-full-zh@2x.png`、`scene-full-empty@2x.png`、`chat-full-zh@2x.png`、`chat-report-full@2x.png` | 3840×2160（= CSS 1920×1080 × 2） |
| 元素切片 | `scene-board@2x.png`、`scene-bay-*.png`、`scene-agent-*.png`、`ui-card-row-*.png`、`ui-chip-*.png`、`chat-messages@2x.png`、`chat-report@2x.png` | 按选择器裁切，PNG |
| 坐标表 | `promo/public/textures/layout.json` | 每个元素在整页坐标系下的 bbox，单位 **页面 CSS px**（截图尺寸 ÷ 2） |

输出目录：`promo/public/textures/`。脚本每次运行前清空 `promo/capture/_runtime/`（角色库、
board.sqlite、会话目录、临时 config.json 都在里面）。

## 依赖

```powershell
python -m pip install playwright   # 已装可跳过
python -m playwright install chromium
```

其余依赖就是仓库自己的（`pot` 包可 import）、以及跑 `tests/conftest.py` 需要的 `pytest`。

## 端口与 token 从哪来

脚本里**没有硬编码端口**：

* 端口：`WebUIHost.start()` 用 `make_webui_server(0, runtime)` 绑 0 号端口，URL 取自
  `server.open_webui(False)` → `http://127.0.0.1:<随机端口>`。
* token：`from pot.server import WEBUI_TOKEN`，URL 上带 `?t=<token>`（和各 WebUI 测试同一路径）。
* 语言：临时 `config.json` 写 `{"api_key":"k","ui_lang":"zh","model":"演示模型"}` 并通过
  `pytest.MonkeyPatch` 把 `pot.config.CONFIG_PATH` 指过去，所以界面是中文、且不会弹 API-key 弹层。
  仓库根的 `config.json` 全程未被读写。

## 播种数据（`seed.json`，可重放）

* 角色 3 个：`写手`（canClaim `docs`，wip 1）、`审稿`（canClaim `review`，wip 1）、`执行者`（canClaim 空=不限，wip 2）。
* 实例 4 个：`writer-1`、`review-1`、`exec-1`、`exec-2`（执行者 2 个实例，走 `set_key(sid,'instance',n)`）。
* 卡 9 张：3 doing（写手/exec#1/exec#2 各持一张）、1 blocked（审稿，方块转红）、3 todo、2 done（划掉压暗）。
* 会话 5 个：4 个角色会话 + `我的会话`（user 一句 + assistant 一段 + 一个 tool 卡 + 一条报告卡片块）。
* 全部虚构：无真实用户名、真实路径、api key、真实模型名。

## 哪张图是"手工构造"的

* `scene-full-empty@2x.png`：**同一机位**、同一 DOM，只是清空了 `#scene-list` 的内容并把
  `#scene-center-count` 置 0（面板本体、边框、位置都没动），作为 S2 飞入镜头的空 backplate。
* 报告卡片块：不是手写 HTML，用的是宿主真实渲染函数 `pot.dispatch.done_block([card], 'zh')`，
  把结果作为一条 assistant 消息存进会话——所以 `chat-report@2x.png` 是产品自己画出来的样子。
* `ui-chip-*.png`：chip 由场景详情弹层里宿主自己的 `#sd-body .scene-chip` 渲染，
  个别截取时**详情弹层是打开的**，因此 `layout.json` 里 `chip-*` 的 bbox 属于弹层坐标系，
  不要拿去做场景内定位（只作切片尺寸参考）。

## 采集时踩到的坑（已写进脚本）

1. **先起宿主再播种会话**：`session.save_session` 用的是被 `WebUIHost` 打补丁的 `SESSIONS_DIR`，
   顺序反了会把 5 个会话写进用户真实的 `data/sessions/`。脚本现在先 `WebUIHost.start()`，
   并断言 `SESSIONS_DIR` 在 `_runtime/` 之下，否则直接中止。
2. **wip 配额会挡住播种**：writer/exec 的 wip 分别是 1/2，先建 doing 卡再想 claim 出去做 done 卡会
   `wip_full`。现在先跑完 done（report 即完成、holder 只留署名），再建 doing。
3. **场景每 2s 轮询重绘**：截图期间 `scenePoll` 会把 DOM 换掉（偶发空白/半渲染）。脚本在进场景后
   `clearInterval(sceneTimer)` 停掉轮询，并等 `document.fonts.ready` + 700ms。
4. 关场景不能用 `page.click('#btn-scene')`——`#scene-overlay` 盖住了按钮，Playwright 会一直等
   指针事件。改用页面自己的 `sceneClose()`。
