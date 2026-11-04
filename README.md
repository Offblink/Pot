# Pot

**单机常驻角色 + 任务看板的本机 Agent 宿主。** 你给一句话目标，Planner 把它变成看板上的一张卡，
常驻角色自己认领、执行、写回报，你只负责在「待验收」那一列点 ✓。

![board](docs/images/board-zh.png)

（英文界面：`board-en.png`；同一套皮、同一份数据，语言在顶栏切换。）

## 它是什么

一台机器、一个宿主进程、几个常驻角色、一块看板。没有房间、没有多机、没有云。

- **角色（Role）**：`planner` 是系统种下的主控，能把目标拆成卡片；`executor` 是干活的手。
  角色表在盘上（人掌权），可新建/编辑/删除；模板派生保证 agent 建的角色拿不到额外权限。
- **看板（Board）**：六列——待规划 / 待办 / 进行中 / 待验收 / 已完成 / 受阻。
  进「进行中」要拿租约，租约到期自动被规则收走；只有人能在「待验收」点 ✓ 或 ✗（退回必须写原因）。
- **计划（Plan）**：agent 用 `todo` 工具列计划，WebUI 右侧抽屉实时显示，完成的项逐行划掉。
- **聊天**：浏览器里的 WebUI（启动器「打开聊天」带 token 拉起），流式输出、工具卡、耗时读数、子代理卡。

三个部件：

| 部件 | 技术 | 位置 |
|---|---|---|
| 宿主 | Python 3.13 | `pot/` —— 看板引擎、角色、工具面、HTTP（hub + WebUI 同进程） |
| 启动器 | Kotlin + Compose Multiplatform 1.12.2 | `launcher/` —— 看板页 / 设置 / 关于 / 托盘 / 宿主生命周期 |
| 聊天界面 | 原生 JS（无构建） | `web/` —— 由宿主的 loopback 服务器直接发出 |

## 快速开始

前置：Windows（v1 目标）、Python **3.13**、JDK **17**。

```powershell
# 1. 依赖
git clone <this repo> pot; cd pot
pip install -e .

# 2. 起宿主（人肉用它就够了：WebUI + hub 一起起来）
python -m pot --web
#    Pot WebUI: http://localhost:<port>
#    Pot Hub:   http://127.0.0.1:<port>

# 3. 或者起启动器（推荐：看板 + 托盘 + 一键拉起宿主）
cd launcher
gradle --no-daemon run          # 首次会拉 Compose 依赖；本机已有 9.5.0 缓存
```

第一次打开 WebUI 会弹配置框：填 **endpoint / API Key / 模型名**（存在仓库根目录的
`config.json`，已 gitignore）。启动器「设置」页也能改，并会读 `/model` 回显当前模型。

启动器默认 **自动拉起宿主**（设置页可关）；「打开聊天」在顶栏，host 跑着才可用。

## 看板怎么跑

1. 顶栏「打开聊天」→ WebUI 里说一句话，例如「把 README 里过期的地方找出来」。
2. Planner 建卡（可带标签/优先级/角色），卡片落「待办」。
3. 角色按标签认领 → 「进行中」，拿租约（可续租）。
4. 角色干完 → 写回报 → 「待验收」。
5. 你在启动器里点 **✓ 完成**（或 **✗ 退回** 并写原因）；退回的原因进卡片评论，角色下次开工必读。

卡片必须自足：角色只看得到这张卡，看不到你的聊天上下文。

## 语言与托盘

- **语言**：顶栏 `中文 / English` 一处开关，同时管启动器与 WebUI——启动器立刻重绘，WebUI 下次
  刷新生效（写进 `config.json` 的 `ui_lang`，由 `/lang.js` 提供）。
- **托盘**：只在宿主运行时存在（宿主挂了托盘就没了，这是设计）。右键出菜单：打开聊天 / 停止宿主 / 退出；
  左键直接开聊天。菜单向上弹（不盖任务栏），点别处即关。
- **图标**：🪴 —— 托盘、标题栏/任务栏、关于页同一张。

![tray](docs/images/tray-zh.png)

## 目录

```
pot/            宿主：board.py(看板引擎) roles.py tools/ server.py hub/ session.py …
launcher/       CMP 启动器（Kotlin；Standalone Gradle build）
web/            浏览器 WebUI（index.html + app.js/common.js/i18n.js/motion.js/style.css）
tests/          pytest（含 Playwright 真浏览器用例）
docs/           spec.md（v1.0 定稿，唯一权威）+ images/
scripts/        launcher-click-complete.ps1（UI 验收点击）、dump_prompts.py、check.ps1
```

## 开发与门禁

```powershell
python -m ruff check . && python -m ruff format --check .
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests -q     # 486 passed
cd launcher; gradle --no-daemon compileKotlin                # 启动器编译
```

UI 验收脚本（需启动器已跑、且「待验收」列里有卡）：

```powershell
powershell -File scripts/launcher-click-complete.ps1 -DryRun   # 只报坐标
powershell -File scripts/launcher-click-complete.ps1           # 真点
```

它不写死像素：按调色板主色（浅色 `#15803D` / 深色 `#4ADE80`）在页头下方找药丸大小的实心块，
窗口移动或缩放都不影响。

## 现状与边界（v0.1）

- 单机单人：没有多机房间、文件传输、好友、移动端（都在 M2a 从 Fungi 平移时砍掉了）。
- Windows 优先；macOS/Linux 结构预留但没验过。
- 不做自动更新。
- **安装包还没做**（M5 未完成的最后一块）：目前是源码跑 `gradle run`。打包时要把 Python 宿主的
  部署形态一起定下来（自备 Python 还是要塞进安装包）。
- 版本号只在 `pyproject.toml` 一处，启动器构建时读它生成常量，安装包也用同一个值。
