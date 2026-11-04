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
角色定义（mission/tools/model/wip/canClaim/canCreateCard）
  → data/roles/<id>.json      ← 磁盘，跨会话有效；七道闸在 host 侧引擎校验，必须落盘
角色的对话记忆
  → sessions/ 长期会话         ← 与定义分开；WebUI 会话列表可见、带角色徽章、可旁观
```

```jsonc
// data/roles/<id>.json（草案）
{
  "id": "executor",
  "name": "执行者",
  "mission": "…进 system prompt…",
  "tools": ["screen", "shell", "files", "…"],   // 代码级生效，不靠提示词自觉
  "model": "…",              // 空 = 跟随全局
  "wip": 2,                  // 同时最多持有的卡
  "canClaim": ["coding"],    // 可认领的卡标签；空 = 全部
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

五列 + 受阻：`待规划 / 待办 / 进行中 / 待验收 / 已完成`（+ 软删）。
**卡片粗粒度**（裁决 Q9）：一个目标一张卡，卡内自己拆步骤；看板给人看，太细会刷屏。

```jsonc
// 卡片（草案；实际存 sqlite，见 §7）
{
  "id": "p-xxxxx",
  "title": "…", "desc": "…",          // desc 含 goal + reply_format（原 spawn 参数搬家）+ constraints
  "labels": ["coding"],                // 与角色 canClaim 匹配
  "priority": "urgent|normal|low",
  "status": "backlog|todo|doing|review|done",
  "role": "executor",                  // 期望角色；空 = 任何角色
  "holder": "<role-id>:<session-id>",  // 认领者；null = 无人
  "ifVersion": 7,                      // 乐观并发
  "leaseUntil": …,                     // 租约 → 到期自动回 todo
  "checklist": [{text, done, evidence}],
  "report": {summary, files, selfTest, risks},
  "comments": [{by, text, at}],
  "createdBy": …, "createdAt": …, "updatedAt": …
}
```

**七道闸（全部代码级）**：

| 闸 | 规则 | 违反返回 |
|---|---|---|
| 角色匹配 | `labels ⊆ role.canClaim` 且 `card.role` 匹配 | `role_mismatch` |
| WIP | holder 数 < role.wip | `wip_full` |
| 持有保护 | holder 非空不可被第三方抢 | `already_held` |
| 乐观锁 | ifVersion 不匹配拒绝写 | `stale_version` |
| **done 闸** | **agent 永远到不了 done**，只能 → review；done 仅人工 ✓ | `human_only` |
| 退回 | 人 ✗ 退回 todo，原因进卡（角色开工前必读） | — |
| 租约 | 超时 → 自动回 todo、清 holder、评论留痕 | — |

### 3.3 Planner（主控角色，原 L1）

- 唯一与用户对话的角色；分工 = 建卡（role + labels + desc）+ 建角色（受 §3.1 约束）
- 默认 `canClaim=false`（只派活不抢活；可配）
- 看板空时可直接干活（小任务不开卡——沿"Trivial one-step 直接做"）
- 收到卡片进 review 的通知，报告以**卡片块**进对话

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
- 定稿结果落作业卡 + 会话通知（红点）。

### 3.5 agent 工具面（草案）

```
pot_board_list      查板（按列/角色/标签过滤）
pot_board_get       读单卡全文（desc/评论/清单/报告）
pot_board_create    建卡（Planner 或 canCreateCard 角色）
pot_board_claim     认领（七道闸全在这）
pot_board_move      流转（→review 由 holder；→done 不暴露给 agent）
pot_board_comment   追加评论
pot_board_checklist DoD 勾选（必须附 evidence）
pot_board_report    提交结构化报告 → 自动进 review
pot_board_release   主动放手（回 todo，带原因）
```

人侧动作（**只在启动器看板页**）：建卡、改派、✓ 完成、✗ 退回、续租约、角色表与模板管理。

计划工具（裁决 17）：`todo(items)` —— 全量替换本会话计划清单（`[{text, done}]`），返回翻转项供前端做划掉动画；
显示为聊天内可更新卡片。

## 4. 启动器（CMP 桌面）

### 4.1 技术基线

- Kotlin 2.3.21 + CMP 1.12.2 + Material3；JDK 17；阿里云 maven 镜像
- 目标：Windows v1（macOS/Linux 结构预留）；打包 `packageMsi`；**不自动更新**（只提示有新版）
- 通信：**方案 A——HTTP 子进程**。CMP 拉起 Python host 为子进程，经 loopback HTTP 读写
  （hub 既有 `/api/*` + 新增 `/api/board/*`、`/api/roles/*`、`/api/host/status`）；
  Python 侧零重构、崩溃隔离（host 挂了启动器能显示状态并重启）

### 4.2 页面（五页砍剩两页 + 托盘）

| 页 | 内容 |
|---|---|
| **看板（新，主页面）** | 五列看板、卡片详情、改派/验收、角色表与模板管理、租约状态 |
| 设置 | 模型配置、（信使/VidSense/更新区块已随功能砍除）、host 路径 |
| 托盘（迁 CMP，裁决 Q5/24） | 进程活着托盘就在；**关窗=收进托盘**（宿主继续跑）；左键显示窗口，菜单：显示窗口 / 打开聊天 / 停止·启动宿主 / 退出；菜单用 **Swing 弹层**（裁决 21） |
| 顶栏 | 恒定：状态徽章 / 看板·设置·关于 / **打开聊天**（裁决 22）/ 语言开关（裁决 21）/ 主题开关 |

二维码生成（zxing）**随移动端作废**，不实现。

## 5. 聊天：浏览器 WebUI（裁决：chat-home = 浏览器）

- 沿 Fungi 现状：托盘/启动器「打开聊天」→ 浏览器；**webUI 聊天逻辑零重写**
- 区块调整：砍好友栏/同意滑条/旁观/传输弹窗/手机 auth-banner；保留会话列表、聊天、ask 卡、
  模型切换、token 速率、深浅主题、子代理卡 → **改为角色会话卡（带角色徽章）**
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
| M4 | CMP 启动器（看板页/设置/托盘/起停 host/打开聊天，方案 A） | 真机截图：看板操作闭环、host 崩溃恢复 |
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
| 15 | 看板 UI 落点 | **只在启动器**（浏览器聊天页不重复做看板） |
| 16 | 看板存储 | **sqlite**（H2 否决：Java 库配不上 Python host；JSON 并发弱） |
| 17 | 计划 todo 工具（2026-11-04 追加） | **新增**：`todo(items)` 全量替换计划清单、聊天内可更新卡片、完成项划掉动画（动画随 M3）；与已砍的信使 todo 不同物，`data/todos.json` 维持不读写 |
| 18 | 会话置顶（2026-11-04 追加） | **做**：WebUI 会话列表置顶，标记随会话持久化（随 M3） |
| 19 | btw 输入框（2026-11-04 追加） | **否决**（“这么麻烦”）——不做 |
| 20 | 后台执行继承（2026-11-04 追加） | **无损接管**原进程（不杀不重跑，作业表 + 临时文件）+ **空闲自动续跑**（完成时无回合在跑则唤醒，忙则挂起补投）；细则见 §3.4 |
| 21 | i18n（2026-11-04 追加） | **一处开关控两边**：顶栏语言下拉改启动器即时重绘，并把代码经 `POST /api/host/lang` 写进 `config.json` 的 `ui_lang`（host 是唯一写者，持配置锁），WebUI 的 `/lang.js` 下次加载即生效；`/api/host/status` 回带 `ui_lang`，一致时不写盘。托盘菜单改用 **Swing 弹层**——win32 菜单用系统菜单字体且 `MenuItem.setFont` 无效，英文系统上中文必豆腐 |
| 22 | 「打开聊天」落点（2026-11-04 追加） | **恒定在顶栏**（语言开关左侧），不放设置页 |
| 23 | v1 交付形态（2026-11-05 追加） | **源码交付**（pip + gradle run，前置 Python 3.13/JDK 17）；安装包与宿主部署形态推迟到 M5+，不阻塞 v1 |
| 24 | 关窗行为（2026-11-05 追加） | **关窗=收进托盘**，宿主继续跑；托盘在启动器进程寿命内常驻（推翻「host 运行才有托盘」），左键显示窗口，退出只走托盘菜单的「退出」 |

## 10. 风险

1. **M2a/M2b 是最大的坑**：砍单面广（房间+信使+移动三大块），635 个测试里钉旧语义的**大面积删除属预期**，
   不是漏测；spawn 提示词重写（L1/L2/L3 + clone 分支）与看板映射同批完成
2. **CMP↔Python 双进程生命周期**：单例、端口占用、host 崩溃重启、「关窗进托盘、托盘=进程活着」新语义要在启动器重做
   ——Fungi 的关窗进托盘教训要带过来
3. **loopback 化的隐性依赖**：原 hub 路由里混着房间与本机两族，拆的时候别把 WebUI 会话/保存路由误删
   （`/api/sessions`、`/api/save`、`/api/poll` 必须活着）
4. **GFW 构建**：CMP 走阿里云镜像已验；msi 打包链路未验（首次 `packageMsi` 单独试）
5. **sqlite 并发**：多角色会话并发 claim → WAL 模式 + 单写事务；M1 里压测定参
