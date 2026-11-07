# Pot — Positive Bots · Spec v1.0（定稿，2026-11-05）

状态：**定稿**。裁决 1–23 全部闭合（见 §9），M0–M4 已实现并在本机验收；M5 只剩打包一项，明确不在 v1 范围内（见 §8）。

命名：Pot（花盆）——Positive Bots 缩写；角色是种子，看板是土壤。

---

## 0. 一句话定位

Fungi 砍成**纯单机**本机 Agent（保留桌面控制、MCP、技能与日记），
把「临时分层的 subagent」换成「**常驻角色 + 主动认领的任务看板**」，
启动器用 Compose Multiplatform 重写（看板 UI 只在启动器），聊天留在浏览器 WebUI、换 TRead 皮。
**移动端整体移除。**

## 1. 范围

### 1.1 保留（Fungi → Pot 平移）

- 本机 Agent 工具面：`screen`（click/type/key/scroll/drag、候选编号制、逐字输入、两条规则、开关即许可）、
  会话式 bash、`shell`/`web`/`inquire`/`files`/`search`
- **MCP 支持**（tools/mcp.py）
- **技能与日记系统**（skills.py + diary.py）
- 会话存储（`sessions/`）、ask 汇聚卡、模型配置、runlog（`logs/` 14 天）
- WebUI 聊天（浏览器访问，见 §6）
- 文件的**本地**打开/浏览（`openfile.py`；跨机传输随房间砍掉，见 §1.2）

### 1.2 移除（裁决：只保留 MCP 和技能日记；信使连带全砍；纯单机）

| 块 | 连带移除 |
|---|---|
| GhostWorld 角色控制 | spec §43/§44 整块 |
| VidSense 视频理解 | `video` 工具、vidsense/ 快照、设置页对应区块 |
| 信使全链 | courier 记忆/四周日历/双通道/反馈框、信使 `todo` 工具与 GUI 日历页、`data/todos.json` 不再读写（新增的计划 `todo` 是不同物，见裁决 17） |
| 房间与多机 | hub 多机协议（join/leave/heartbeat/peers/mail）、发起房/加入房页、好友视图、同意流、会话旁观、**文件传输全链路**（xfer.py、`/api/transfer*`、裸字节 upload） |
| **移动端全部** | `web/m.html`+`m.js`(63K)+`m.css`(34K)、GUI 手机端页、**扫码功能**、segno 依赖、防火墙手机放行（spec §32）、端口扫描/探测、`gui/mobile.py`、`gui/firewall.py`、CMP Android target、Mobile-Design 参考 |
| trilayer | `spawn`/`background` 工具、L1/L2/L3 addendum（**删净**，见 §3.4） |
| 自动更新 | 不恢复（Fungi §34 维持） |

连带推论（直接定）：
- hub 退化为 **loopback-only 本机 HTTP 服务**（只喂 WebUI + 看板 API + 会话 API）；防火墙代码成死代码，随房间删
- 托盘语义：「有房间才有托盘」→「**启动器进程活着托盘就在**」（裁决 24：关窗收进托盘）；「点托盘图标」保留
- 防火墙一键放行、端口扫描、单例 QSharedMemory 中与房间相关的语义随房间死

### 1.3 新增

- 任务看板引擎（Python host 内）+ 角色表 + `pot_board_*` agent 工具
- 计划 `todo` 工具（裁决 17）：agent 列计划，聊天内可更新卡片、完成项划掉动画（动画随 M3）；与已砍的信使 todo 不同物
- 会话置顶（裁决 18）：WebUI 会话列表置顶，标记随会话持久化（随 M3）
- 后台执行继承（裁决 20）：长时命令作业无损接管 + 空闲自动续跑，细则见 §3.4
- CMP 桌面启动器：**看板页 + 设置页 + 托盘 + host 生命周期 + 「打开聊天」**
- WebUI 换 TRead 皮（§6）

### 1.4 非目标（v1 不做）

- 不做移动端（Android/iOS 都不做；WebView 壳方案随移动端一起废弃）
- 不做多机房间/文件传输/好友社交
- 不做 DSH 插件、不做云同步、不做 Super-agent 外部事件源（纯本地任务）
- 不做 git worktree 隔离（先靠 WIP+租约）
- 不做自动更新（手动发版）

## 2. 现状事实（脑暴依据）

- Fungi subagent：`fungi/trilayer.py`，spawn 异步（报告走 `[background report]` 回注）+ background 命令式；
  状态只活在 `self.subagents: dict`——**没有账本**、没有身份延续、没有"谁做了一半"的可查询状态
- 子代理不继承 `screen`（spec §949：动手的是本机 Agent 本人）——Pot 沿用
- 可复用的看板机制（本会话调研）：`cloader/dsh-taskboard`（五列、claim 协议闸、agent 到不了 done、
  `ifVersion` 乐观并发、持有不可抢、DoD 清单、结构化报告）；DSH `TeamTaskBoard`（CAS+DAG）；
  Super-agent 的纪律（按影响刹车、只在人必须行动时说话、授权范围）
- CMP 配方已验证：Kotlin 2.3.21 + CMP 1.12.2 + JDK 17 + 阿里云镜像（compose 插件必须与 Kotlin 同版本）
- webUI 体量 ~354 KB（app.js 64K / common.js 103K / style.css 49K）——聊天逻辑全留

## 3. 核心机制：Taskboard + 角色

### 3.1 角色（Role）

角色 = **常驻 agent 身份**，两层分开存：

```
角色定义（mission/tools/model/wip/canClaim/canCreateCard/maxInstances）
  → data/roles/<id>.json      ← 磁盘，跨会话有效；七道闸在 host 侧引擎校验，必须落盘
角色的对话记忆
  → sessions/ 长期会话         ← 与定义分开；**一实例一会话**（裁决 33：同角色可多实例、
                                 各自 wip 与编号 #n），不进用户会话列表（裁决 29），可按 id 打开
```

```jsonc
// data/roles/<id>.json（草案）
{
  "id": "executor",
  "name": "执行者",
  "mission": "…进 system prompt…",
  "tools": ["screen", "shell", "files", "…"],   // 代码级生效，不靠提示词自觉
  "model": "…",              // 空 = 跟随全局
  "wip": 2,                  // 每个实例同时最多持有的卡（裁决 33）
  "maxInstances": 3,         // 同角色实例上限；自动增殖到此为止（裁决 33，仅人可改）
  "canClaim": ["coding"],    // 可认领的卡标签（子集比较）；空 = 不限（任何标签都行）
  "canCreateCard": false,
  "template": null,          // 派生自哪个模板（Planner 建的角色必填）
  "createdBy": "human"       // 或 "planner"（见下）
}
```

**谁建角色（裁决 Q2）**：人和 Planner 都能建，但**权限不等价**：

| | 人 | Planner |
|---|---|---|
| `mission`/`name`/`canClaim` 标签 | ✅ | ✅ |
| `tools`/`model`/`wip`/权限 | ✅ 随意配 | ❌ **只能从人预设的模板派生**（`template` 必填），不能自选 |
| 删除 / 改权限 | ✅ | ❌ 永远只有人 |
| 留痕 | `createdBy: "human"` | `createdBy: "planner"` + 建卡上下文 |

原则：**Planner 能造角色，造不出有特权的角色**——工具面与权限是人的专属领地。

硬边界（沿 Fungi）：`screen` 只挂"本机执行者"一个角色；权限只有人能改。

### 3.2 看板（Board）

四列：`待办 / 进行中 / 受阻 / 已完成`（+ 软删）。**`待规划`（backlog）与 `待验收`（review）
随裁决 32 退役**：报告即完成，规划直接进待办。**卡片粗粒度**（裁决 Q9）：一个目标一张卡，
卡内自己拆步骤；看板给人看，太细会刷屏。

```jsonc
// 卡片（草案；实际存 sqlite，见 §7）
{
  "id": "p-xxxxx",
  "title": "…", "desc": "…",          // desc 含 goal + reply_format（原 spawn 参数搬家）+ constraints
  "labels": ["coding"],                // 与角色 canClaim 匹配
  "priority": "urgent|normal|low",
  "status": "todo|doing|blocked|done", // backlog/review 已退役（裁决 32）
  "role": "executor",                  // 期望角色；空 = 任何角色
  "holder": "<role-id>:<session-id>",  // 认领者（= 角色实例）；null = 无人
  "ifVersion": 7,                      // 乐观并发
  "leaseUntil": …,                     // 租约 → 到期自动回 todo
  "checklist": [{text, done, evidence}],
  "report": {summary, files, selfTest, risks},
  "comments": [{by, text, at}],
  "source": "session-id",              // 派它的会话（裁决 31 的通知闸）
  "createdBy": …, "createdAt": …, "updatedAt": …
}
```

**闸（全部代码级）**：

| 闸 | 规则 | 违反返回 |
|---|---|---|
| 角色匹配 | `labels ⊆ role.canClaim` 且 `card.role` 匹配；**建卡即验**（裁决 42：labels 无任何角色可领 → 创建当场拒，错误带现词表） | `role_mismatch` |
| WIP | **同一实例**的 holder 数 < role.wip（一实例一会话——裁决 33） | `wip_full` |
| 持有保护 | holder 非空不可被第三方抢 | `already_held` |
| 乐观锁 | ifVersion 不匹配拒绝写 | `stale_version` |
| **报告即完成** | `pot_board_report` 提交 → **直达 done**（清租约；holder 留作署名——裁决 36 已完成行要显示身份#编号）——裁决 32，原 done 闸翻转 | — |
| 重开 | 人把 done 重开回 todo、清 holder，原因进卡 | — |
| 租约 | 超时 → 自动回 todo、清 holder、评论留痕 | — |

### 3.3 Planner（主控角色，原 L1）

- 唯一与用户对话的角色；分工 = 建卡（role + labels + desc）+ 建角色（受 §3.1 约束）
- 默认 `canClaim=false`（只派活不抢活；可配）
- 看板空时可直接干活（小任务不开卡——沿"Trivial one-step 直接做"）
- 卡片**完成**（report 直达 done，裁决 32）→ **host 直写卡片块**进「派它的那个会话」
  （裁决 30/31）：把结构化 report 渲染成卡片消息直接落盘 + 打「card」红点——**不叫模型、
  不产生 `[card review]` 这类内部通知消息、不新开会话**；只有 `source`=派它的会话、且该
  会话无 `role` 才投递，人工卡/种子卡聊天零打扰（完成状态看板上自己会显示）
- **Planner 自主改派（裁决 34）**：卡进 `blocked` → host 用**内部 note**（渲染层永不显示）
  唤醒 `source` 会话的 Planner，由它用 `pot_board_reassign`（仅 planner 可用）换角色退回
  todo 或解阻；租约到期仍走规则闸自动回 todo 重新派发
- 带 role 的会话（执行者等）**不出现在会话列表**（裁决 29）：它是角色的记忆载体，
  文件照常在 `data/sessions`、可按 id 打开排查；用户列表里只有自己的对话

### 3.4 旧机制退役（裁决 Q1：删净）

| 旧 | 新 |
|---|---|
| `spawn(goal, reply_format, context, constraints)` | `pot_board_create`（参数原样进 desc） |
| `background` | 看板卡 + 异步认领；后台命令仍归会话式 bash |
| `[background report]` 回注 | 卡片流转 + 报告块 + 会话通知 |
| `MAX_SPAWNS_PER_TURN=8` | 角色 `wip`（持久、可查、UI 可见） |
| `self.subagents: dict` | 看板（可查询、启动器可视） |
| L1/L2/L3 固定三层 | 任意角色任意深度；**默认仍三层**：Planner → 协作者 → 执行者 |

`spawn`/`background` 工具、L1/L2/L3 addendum、clone 分支相关 prompt **整块删净**，不留 deprecated；
旧会话 `subagents` 字段只读展示、不迁移。

**后台执行继承（裁决 20，2026-11-04）**：按钮与窄 abort（`tool_abort_event`，agent 循环层）原样保留；
被砍的只有重派目标与 `[background report]` 回注两处机制。长时命令走**作业**：

- 「后台执行」**不杀进程、不重跑**——pid 与临时输出文件（stdout/err 本就落临时文件）挂进作业表，立即返回作业 id；
- 作业**跨回合存活**（Fungi「回合结束即收割」的政策不适用于作业），边界 = 退出即定稿 / 空闲超时 / 手动 kill；
- **空闲自动续跑**：完成时无回合在跑 → 输出作为新输入唤醒 agent 接着干；回合在跑 → 挂起，回合结束补投；
  唤醒输入一律带 `internal` 标记，**渲染层永不显示**（裁决 35），模型结论没变就 `<<SILENT>>`；
- 定稿结果落作业卡 + 会话通知（红点）。

### 3.5 agent 工具面（草案）

```
pot_board_list      查板（按列/角色/标签过滤）
pot_board_get       读单卡全文（desc/评论/清单/报告）
pot_board_create    建卡（Planner 或 canCreateCard 角色）
pot_board_claim     认领（闸全在这，wip 按实例计）
pot_board_move      流转（→blocked 由 holder；→done 不暴露给 agent——done 只由 report 抵达）
pot_board_comment   追加评论
pot_board_checklist DoD 勾选（必须附 evidence）
pot_board_report    提交结构化报告 → **直达 done**（裁决 32）
pot_board_release   主动放手（回 todo，带原因）
pot_board_reassign  换角色退回 todo / 解阻（**仅 planner**，裁决 34）
```

人侧动作（**WebUI 中心板/详情 + 启动器角色页**）：建卡、重开、删除、角色表与模板管理（裁决 37）。

计划工具（裁决 17）：`todo(items)` —— 全量替换本会话计划清单（`[{text, done}]`），返回翻转项供前端做划掉动画；
显示为聊天内可更新卡片。

## 4. 启动器（CMP 桌面）

### 4.1 技术基线

- Kotlin 2.3.21 + CMP 1.12.2 + Material3；JDK 17；阿里云 maven 镜像
- 目标：Windows v1（macOS/Linux 结构预留）；打包 `packageMsi`；**不自动更新**（只提示有新版）
- 通信：**方案 A——HTTP 子进程**。CMP 拉起 Python host 为子进程，经 loopback HTTP 读写
  （hub 既有 `/api/*` + 新增 `/api/board/*`、`/api/roles/*`、`/api/host/status`）；
  Python 侧零重构、崩溃隔离（host 挂了启动器能显示状态并重启）
- 单例（裁决 27）：`%APPDATA%\Pot\launcher.lock` 文件锁、按用户；拿不到锁记
  `refused: another instance holds the lock` 后退出——第二份启动器不抢 `board.sqlite`/`config.json`、不双托盘

### 4.2 页面（看板已随裁决 37 移到 WebUI）

| 页 | 内容 |
|---|---|
| **角色（主页面）** | 角色表与模板管理；原「看板」tab 及其列、归档、详情弹层**整体删除**（裁决 37：建卡/重开/详情迁到 WebUI 场景） |
| 设置 | 模型配置、（信使/VidSense/更新区块已随功能砍除）、host 路径 |
| 托盘（迁 CMP，裁决 Q5/24） | 进程活着托盘就在；**关窗=收进托盘**（宿主继续跑）；左键显示窗口，菜单：显示窗口（窗口已开时置灰——裁决 28） / 打开日志（裁决 25） / 打开聊天 / 停止·启动宿主 / 退出；菜单用 **Swing 弹层**（裁决 21） |
| 顶栏 | 恒定：状态徽章 / 角色·设置·关于 / **打开聊天**（裁决 22）/ 语言开关（裁决 21）/ 主题开关 |

二维码生成（zxing）**随移动端作废**，不实现。

## 5. 聊天：浏览器 WebUI（裁决：chat-home = 浏览器）

- 沿 Fungi 现状：托盘/启动器「打开聊天」→ 浏览器；**webUI 聊天逻辑零重写**
- 区块调整：砍好友栏/同意滑条/旁观/传输弹窗/手机 auth-banner；保留会话列表、聊天、ask 卡、
  模型切换、token 速率、深浅主题；子代理卡随 spawn 退役删除，角色会话**不进列表**（裁决 29）
- **俯视看板场景**（裁决 36，同日修订）：正中任务板（原版 todo 卡片样式的完成/未完成清单）+ 正 N 边形顶点上的 agent 隔间；无 Planner、无状态板，点方块进临时会话视图
- 语言与结构不动（i18n 保留）；语言由启动器顶栏一处开关统一控制（裁决 21）

## 6. WebUI 主题：TRead（Gasp-Design）皮

CSS 变量层整体移植（`web/style.css` + 新 `web/board.css` 不需要——看板在启动器原生）：

```css
:root{
  --bg:#06060a; --surface:#0a0a14; --surface2:#0d0d18; --border:#1a1a2e;
  --fg:#e0e0e0; --muted:#666; --dim:#8a8a99;
  --c1:#4ade80; --c2:#60a5fa; --c3:#a78bfa; --c4:#f472b6;
  --warn:#fbbf24; --err:#f87171;
  --topbar-bg:rgba(6,6,10,.85);
}
:root[data-theme="light"]{ /* TRead 浅色：中性灰白，无粉色系 */ }
```

- 卡片 = surface + 1px border，hover 上浮 + 绿光晕；主按钮 135° 三色渐变 + 深色字；mono 标签
- 深浅主题一键切换、随数据持久化（沿 theme-switch，换值即可）
- 动效沿 `motion.js`（已有 stagger）；角色会话卡/ask 卡同款转场
- **启动器看板的配色与 TRead 同源**（Kotlin 侧实现同一套 hex）：待办=蓝 c2、进行中=橙 warn、
  待验收=紫 c3、完成=绿 c1、受阻=err——两端一皮

## 7. 数据与存储

```
data/
├── board.sqlite        # 看板卡片账本（裁决：sqlite——Python 标准库零依赖、行级 CAS、打包零成本）
├── roles/<id>.json     # 角色定义 + 模板（人可读可改）
├── sessions/           # 保留（含角色会话）
└── （todos.json / courier_memory 随信使砍除，不再读写）
config.json             # 新增 board/roles/launcher 键；砍除键清理；旧模型配置保留
```

- **新仓 Pot**（裁决 Q7）：从 Fungi 平移所需模块，Fungi 冻结为 v0.8.x 参考；
  `sessions/` 可拷贝续用，`todos.json`/信使数据不迁
- sqlite 与 Fungi 全 JSON 风格不一致是已知取舍：claim CAS 行级正确性 > 风格统一

## 8. 里程碑（可砍）

| # | 内容 | 验收 |
|---|---|---|
| M1 | 看板引擎（sqlite）+ 角色表/模板 + `pot_board_*` + 计划 `todo` 工具（纯 Python；划掉动画随 M3） | 单测：七道闸逐条红绿；并发 claim 压测 |
| M2a | **砍单落地**：房间/信使/移动/GhostWorld/VidSense 从 Fungi 树移除，hub 退 loopback | 门禁绿（测试大量删除属预期，见风险 2） |
| M2b | trilayer → 看板：spawn 删净、Planner 提示词重写、角色会话挂载 | 真机：一句话 → 建卡 → 认领 → 执行 → review → 人验收 |
| M3 | WebUI 换 TRead 皮 + 区块清理（好友/传输等）+ 会话置顶 + todo 卡划掉动画 | 真机截图：深浅主题、角色徽章、置顶与划掉动画 |
| M4 | CMP 启动器（角色页/设置/托盘/起停 host/打开聊天，方案 A；看板页已随裁决 37 移除） | 真机截图：角色管理、host 崩溃恢复 |
| M5 | 文档（README 故事版 + 本 spec 定稿） | 已完成 2026-11-05 |
| M5+ | 打包（msi）**不在 v1 范围**（裁决 23） | 未做：需先定 Python 宿主的部署形态 |

依赖：M1 → M2b；M2a 可与 M1 并行；M3/M4 依赖 M2a。

**交付形态（裁决 23）**：v1 以源码运行交付——`pip install -e .` + `python -m pot --web`，启动器
`gradle --no-daemon run`；前置是 Python 3.13 与 JDK 17。安装包（msi）连同「宿主怎么随包走」留到
M5+，届时单独裁决（自备 Python 还是要塞进安装包）。

## 9. 裁决日志（全部已闭合）

| # | 议题 | 裁决 |
|---|---|---|
| 1 | 功能砍单 | **只保留 MCP + 技能日记**；GhostWorld、VidSense、信使、好友/旁观/传输全砍 |
| 2 | 信使深度 | 连带全砍（记忆+日历+todo+反馈，todos.json 不再读写） |
| 3 | 单机深度 | **纯单机**：房间/传输/社交全砍，hub 退 loopback |
| 4 | 移动端 | **整体移除**；m.html/m.js/m.css、扫码、segno、防火墙手机放行全删 |
| 5 | spawn 退役 | **删净**，不留 deprecated |
| 6 | 角色创建 | **Planner 也可建**，但权限/工具面只能从人预设模板派生；删除/改权只有人 |
| 7 | 仓库 | **新仓 Pot**，Fungi 冻结 |
| 8 | 启动器通信 | **HTTP 子进程（方案 A）** |
| 9 | worktree | v1 不要 |
| 10 | 移动壳设计语言 | 作废（移动端没了） |
| 11 | 托盘 | 迁 CMP（保 PULL_UP、「点图标进 WebUI」） |
| 12 | 卡片粒度 | 粗粒度（一目标一卡） |
| 13 | 自动更新 | 不恢复 |
| 14 | 聊天落点 | 浏览器 WebUI（启动器不内嵌） |
| 15 | 看板 UI 落点 | **只在启动器**（浏览器聊天页不重复做看板）——**裁决 36 反转：搬 WebUI 俯视场景** |
| 16 | 看板存储 | **sqlite**（H2 否决：Java 库配不上 Python host；JSON 并发弱） |
| 17 | 计划 todo 工具（2026-11-04 追加） | **新增**：`todo(items)` 全量替换计划清单、聊天内可更新卡片、完成项划掉动画（动画随 M3）；与已砍的信使 todo 不同物，`data/todos.json` 维持不读写 |
| 18 | 会话置顶（2026-11-04 追加） | **做**：WebUI 会话列表置顶，标记随会话持久化（随 M3） |
| 19 | btw 输入框（2026-11-04 追加） | **否决**（“这么麻烦”）——不做 |
| 20 | 后台执行继承（2026-11-04 追加） | **无损接管**原进程（不杀不重跑，作业表 + 临时文件）+ **空闲自动续跑**（完成时无回合在跑则唤醒，忙则挂起补投）；细则见 §3.4 |
| 21 | i18n（2026-11-04 追加） | **一处开关控两边**：顶栏语言下拉改启动器即时重绘，并把代码经 `POST /api/host/lang` 写进 `config.json` 的 `ui_lang`（host 是唯一写者，持配置锁），WebUI 的 `/lang.js` 下次加载即生效；`/api/host/status` 回带 `ui_lang`，一致时不写盘。托盘菜单改用 **Swing 弹层**——win32 菜单用系统菜单字体且 `MenuItem.setFont` 无效，英文系统上中文必豆腐 |
| 22 | 「打开聊天」落点（2026-11-04 追加） | **恒定在顶栏**（语言开关左侧），不放设置页 |
| 23 | v1 交付形态（2026-11-05 追加） | **源码交付**（pip + gradle run，前置 Python 3.13/JDK 17）；安装包与宿主部署形态推迟到 M5+，不阻塞 v1 |
| 24 | 关窗行为（2026-11-05 追加） | **关窗=收进托盘**，宿主继续跑；托盘在启动器进程寿命内常驻（推翻「host 运行才有托盘」），左键显示窗口，退出只走托盘菜单的「退出」 |
| 25 | 日志入口（2026-11-05 追加） | **只在托盘**：设置页删掉日志行，托盘菜单「显示窗口 / 打开聊天」之间加「打开日志」（`Log.openFolder()`）；日志本体不动（一天一个文件、14 天保留） |
| 26 | 看板列收口（2026-11-05 追加） | **视图层收口，数据层不动**：列内倒序（`updatedAt` 降序）、每列只显示最近 12 张、列底「更早的 N 张 · 查看归档」进归档（今天/昨天/本周、更早，按标签/角色筛，只读）；紧凑卡只留标题+优先级点+角色/持有者小字，描述/清单/报告/评论与全部操作进详情弹层；**不自动删卡**（`deleted` 仍是唯一软删路径）——**裁决 36/37 后随看板页移除作废** |
| 27 | 单例（2026-11-05 追加） | **文件锁**：`%APPDATA%\Pot\launcher.lock` 按用户，拿不到锁记日志后退出；唤窗 IPC（第二次启动把已有窗口叫到前面）暂不做 |
| 28 | 顶栏/托盘微调（2026-11-05 追加，用户点名） | **语言两点切换**：两选一的选项不要下拉，点一下直接切（zh↔en）；**托盘「显示窗口」仅在窗口隐藏时可用**（已开则置灰）；**裸 TextButton 加发丝描边成按钮**——编辑/删这类「差点看不出是按钮」的都要有边 |
| 29 | 角色会话可见性（2026-11-05 追加，用户点名） | **列表里完全隐藏**：带 `role` 的会话不进 WebUI `/sessions` 与 hub `/api/sessions`——用户会话列表只剩自己的对话；文件保留（`data/sessions`），可按 id 打开排查 |
| 30 | 卡片报告投递（2026-11-05 追加，判据：*Take as little human attention as possible, and give as much value as possible*） | **host 直写卡片块**：review 到达时由 host 把结构化 report 渲染成卡片消息**直接写进来源会话**并打「card」红点——不叫模型、不产生内部通知消息；WebUI 靠既有的每会话 3s 轮询发现转录变长并刷新。原 `[card review]` 注入 + 模型转述两段全删（`latest_user_session`/`review_note` 退役） |
| 31 | 通知闸（2026-11-05 追加） | **只有本会话派出的卡才回本会话**：`pot_board_create` 给卡盖 `source`=创建它的会话；投递要求 source 存在且是无 `role` 的会话。人工卡/种子卡聊天零打扰（看板照常显示 review）——「you dispatched」从此为真 |
| 32 | 报告即完成（2026-11-05 追加，用户点名「验收去掉」） | **`pot_board_report` 直达 done**：报告提交即完成、清租约（**holder 留作署名**，场景已完成行显示身份#编号——裁决 36），人零介入；`backlog`（待规划）与 `review`（待验收）两状态**退役**，存量迁移 `backlog→todo`、`review→done`；人工动作只剩**重开**（`done→todo`、清 holder、原因进评论）。闸5 翻转，「不给自己判卷」由看板统计与重开仍在人手来兜底 |
| 33 | 同角色多实例（2026-11-05 追加，用户点名「加编号」） | 角色可多实例：**一实例一会话、独立 wip、独立编号 `#n`**（会话落 `instance` 字段）；dispatch 自动增殖——有可认领卡而全实例满 wip → 开新实例，上限 `maxInstances`（角色字段，默认 3，仅人可改、进 `_PRIVILEGED`）；`holder=role:session` 天然区分实例 |
| 34 | Planner 自主改派（2026-11-05 追加，用户选「自主」而非规则级） | 卡进 **blocked** → host 用**内部 note** 唤醒 `source` 会话的 Planner（note 渲染层永不显示），由它用新工具 `pot_board_reassign`（**仅 planner 角色可用**）换角色退回 todo 或解阻；无 source/无会话则退回租约闸等规则兜底 |
| 35 | 作业报告内部化（2026-11-05 追加，用户困惑点） | `[job report]` 等 host 唤醒输入一律带 `internal` 标记：**渲染层（转录/标题/直播事件）永不显示**，模型照常读到；提示词要求「后台续跑结论没变就 `<<SILENT>>`」——说不说是模型的事，显示不显示是渲染的事 |
| 36 | 看板搬到 WebUI（2026-11-05 追加，用户构想；**反转裁决 15**；同日修订：去 Planner、去状态板） | **俯视场景，只有两样东西**：正中的**任务板** + 环绕它的 agent 隔间。有几种角色就画正几边形，隔间落在顶点上（工位），agent=像素方块+编号，卡住=红、无任务=消失，点方块进临时会话视图。任务板 = **原版 todo 卡片样式的完成/未完成清单**（优先级点+标题+身份#编号，已完成划掉压暗），点行开详情（重开/删除），＋ 建卡；**没有 Planner 元素、没有右移状态板**。数据零新后端：`/board` 轮询聚合**全部并发会话**的卡（全会话统计）。裁决 26 的 12 张收口/归档随看板页移除而作废 |
| 37 | 启动器去掉看板页（2026-11-05 追加，用户点名） | 启动器只剩 **角色**（+设置/关于/托盘/顶栏）；看板列、归档、详情弹层等死代码删除；人建卡入口移到 WebUI 中心板 |
| 38 | 卡完成后唤醒 Planner（2026-11-06 追加，用户「那你加吧」） | 卡进 **done** → `deliver_card_block` 之后，对同一 `notify_route` 目标再发一条**内部 note**（裁决 35 口径：渲染层不显示，模型默认 `<<SILENT>>`）：复盘报告、有后续就 `pot_board_create` 续拆/`pot_board_reassign` 调整。与裁决 34 的 blocked 唤醒同范式；人卡/种子卡照旧零打扰（裁决 31 闸不变） |
| 39 | 并行派工（2026-11-06 追加，用户「多 agent → 多像素」） | `dispatch_pending` 改**先收集、再并发**：一个周期先为每张可认领卡分配**不同实例**（本周期已分配的实例计满 → 触发裁决 33 增殖），再用有界线程池（`_MAX_PARALLEL=4`，限的是同时在飞的模型 API 调用）并行跑 `run_turn`；`_CYCLE` 持到全部回合汇合——嵌套唤醒拿不到锁、非阻塞直接返回。并发前提实测成立：`jobs` 的当前会话是 thread-local（不是全局态）、看板每操作独立连接 + BEGIN IMMEDIATE + WAL、告警与会话锁各自有锁 |
| 40 | 卡片退役通道（2026-11-06 追加，E；用户选「planner 可 retire 自己 source 的卡」） | 新工具 **`pot_board_retire`**（`Board.retire`）：**planner_only 闸 + reason 必填 + ifVersion**，把**自己 source 的活卡**（todo/doing/blocked）软删（`deleted=1`、`retired: <reason>` 进评论）——死卡不再永远堵 todo。**done 不可退役**（历史归场景，人经详情重开/删除）；无 source 的人卡只归人（WebUI 详情删除不变）；别会话的卡报 `not_your_card`；重退 `no_such_card`。Planner 提示词加一条自有卡退役说明 |
| 41 | 内置分工（2026-11-06 追加，用户「设计几个合理的分工内置到项目里」） | **五个内置角色随 `roles_repo()` 播种**（seed-if-missing，与 Planner 同语义：人可改可删、删除下次启动补回）：`executor` 执行者（`canClaim:["coding"]`，shell/files/search，通用+编码；无标签卡是任何列表的子集、按文件名序归它）、`writer` 写手（`docs`，files/search）、`tester` 测试员（`test`，shell/files，只报不修）、`researcher` 研究员（`research`，web/search/files，只查不改）、`reviewer` 审稿人（`review`，files/search，只审不改）。全部 `wip:5`（2026-11-06 用户定：1太少、30 太多）、`canCreateCard:false`。**分工判据 = 卡片标签 ⊆ 角色 canClaim**；无标签卡按角色文件名序归执行者（executor 排最前） |
| 42 | 建卡标签预检（2026-11-06 追加，Planner 死卡事故：Spore 宣传片两张卡 labels `video/design/capture` 无角色可领——建卡 `ok:true`、派工 `eligible()` 静默跳过、todo 永远进不了 `blocked` 所以 `stuck_note`（裁决34）永不触发，全链路零信号，用户「到现在无人认领」才发现） | **`_insert`（create/human_create 唯一入口）镜像角色匹配闸**：labels 非空且**没有任何角色**的 canClaim 覆盖它（钉了 `role` 就只算被钉角色）→ 创建即 `role_mismatch`，错误携带**现词表**与「留空=无标签卡任何角色可领」——死卡不再上板，发卡方一次改对。claim 侧同名闸保留：建卡后人改 canClaim 造成的**存量漂移**仍由它与派工跳过兜住 |
| 43 | 角色跨唤醒上下文（2026-11-06 追加，executor 会话撑爆：`20261105-212758.json` 10.47MB ≈105万 token 越过 DeepSeek 100 万上限，HTTP 400 全灭） | **角色唤醒不再重放转录**（`_execute_turn` 双视图：存储照旧全量，发给模型的列表每次重建）＝ 系统提示 + **记忆索引**（`data/mem/<role>/*.md` 每篇只塞**一行标题**，全文 `pot_memory_read` 按需取——列表无大小预算，用户裁）+ **上次收尾**（上一唤醒最终回复，硬截 4000 字）+ 本次 brief，**零历史行**——因此不需要遗忘/预算机制；`pot_memory_write` 可选（做完卡把耐久知识存成一篇）。进行中状态在**卡面**（checklist/评论）不在转录。人会话（Planner 聊天）不改，全量照旧。**「上次收尾」半条已被裁决 44 废止** |
| 44 | 角色唤醒只留总结（2026-11-07 追加，用户「删除给 agent 注入之前会话的机制，就连'遗忘'都不够，只保留总结就够了」） | **连裁决 43 的「上次收尾」也删**：`recap_section`/`_last_final_text`/`RECAP_CHARS`/`_USELESS_RECAPS` 整套退役，唤醒视图 = 系统提示 + **记忆索引**（总结标题）+ 本次 brief，**上一唤醒的收尾话也不再注入**——过去会话对模型零注入，唯一的跨唤醒载体就是总结（`pot_memory_write`/`pot_memory_read`）。存储全量与人会话全量重放均不变；裁决 43 里「不需要遗忘/预算机制」的判断维持，现在连收尾这条尾巴也不留 |

## 10. 风险

1. **M2a/M2b 是最大的坑**：砍单面广（房间+信使+移动三大块），635 个测试里钉旧语义的**大面积删除属预期**，
   不是漏测；spawn 提示词重写（L1/L2/L3 + clone 分支）与看板映射同批完成
2. **CMP↔Python 双进程生命周期**：单例（裁决 27）、关窗进托盘（裁决 24）、崩溃自动重启已在启动器落地；
   剩端口占用的边界情况 ——Fungi 的关窗进托盘教训要带过来
3. **loopback 化的隐性依赖**：原 hub 路由里混着房间与本机两族，拆的时候别把 WebUI 会话/保存路由误删
   （`/api/sessions`、`/api/save`、`/api/poll` 必须活着）
4. **GFW 构建**：CMP 走阿里云镜像已验；msi 打包链路未验（首次 `packageMsi` 单独试）
5. **sqlite 并发**：多角色会话并发 claim → WAL 模式 + 单写事务；M1 里压测定参
