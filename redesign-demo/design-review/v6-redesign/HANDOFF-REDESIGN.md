# 交接文档 · 职引学生端全站整改

> 生成时间：2026-10-14
> 适用范围：`redesign-demo`（学生端前端）的全站设计整改
> 读者：接手这个工作的人（或下一个 agent）。**假设你没有任何上下文**。

---

## 0. 三十秒版

| | |
|---|---|
| **在哪** | `C:\Users\y'm'y\Desktop\zhiyin-flash`，分支 `新前端4` |
| **状态** | 4 个提交，工作区干净。**方向已选定但从未铺到真实页面** |
| **最重要的一句话** | 需求方批准的视觉方向是 **c2-hbu**，`redesign-demo/design-review/v6-redesign/directions/c2-hbu/index.html`。**真实页面目前与它差得远**——这件事是本轮最大的欠账，见 §5 |
| **最该先读的三份** | [`PLAN.md`](redesign-demo/design-review/v6-redesign/PLAN.md)（施工契约）、[`DESIGN-LANGUAGE.md`](redesign-demo/design-review/v6-redesign/DESIGN-LANGUAGE.md)（"活"的判定口径）、[`DESIGN-REVIEW-V7.md`](redesign-demo/design-review/v6-redesign/DESIGN-REVIEW-V7.md)（评审判决：丑的根因是"结构量低于感知阈值"） |
| **别做的事** | 别再"凭判断改视觉"。本轮的教训是：**没有可对照的靶子时，改多少轮都到不了位**（§9） |

---

## 1. 需求方要什么

### 1.1 原始意图（第一轮）
对 `redesign-demo` 做一次**能明显看出变化的全站设计整改**：结构、视觉表达、操作体验。
- 要：大气、美观、现代、有质感 + 克制、协调、实用
- 不要：**"不能把整改做成换颜色、圆角、阴影，再添加几个图标"**

### 1.2 范围（20 个区块 × 8 个维度）
**区块**：门户 / 导航与应用外壳 / 咨询对话 / 个人画像 / 诊断报告 / 方向方案 / 行动计划 / 日历与课表 / 学籍与资料 / 待办与目标 / 复盘与记录 / 岗位资讯 / 通用组件与状态 / 工具页 / 使用指南 / 设计规范 / 登录 / 账号设置 / 提醒 / 异常页

**每个区块检查 8 个维度**：①导航结构·功能分组·页面衔接 ②布局·区域比例·对齐·阅读顺序·空间分配 ③信息层级·主次·内容密度·留白·渐进展开 ④字体·字号·字重·行距·长文本阅读 ⑤组件形态·组合方式·视觉与交互一致性 ⑥图标·图表·图形的实际作用 ⑦动效·操作反馈·加载/空白/错误/成功状态 ⑧桌面与移动端

> 需求方原话："**不能只把对话、画像、计划等几个页面做好，就代表全站完成。**"

### 1.3 硬约束
- **允许全部重构**，但**门户页最好不变**，且**从门户进入必须直达对话页**
- **后端有的功能前端也要有**（字段以后端为准）
- **未提交的没用**（必须提交）
- **只做前端，不用真实数据**（演示数据即可）
- 配色：**河北大学官网红 + 校徽蓝 + 灰色系列 + 白色系列**，红蓝可切换
- 动效：**要"活"**，但**不是微过渡**；需求方明确否掉过"给静态界面加过渡"

### 1.4 需求方后来的关键纠正（都很重要）
| 原话 | 含义 |
|---|---|
| "说的动态感不是这种" | 否掉了"淡入 180ms + 位移 5px"这类做法 |
| "如果没有信息的变化呢，已经有的信息该如何更好的呈现？" | 追问不动时怎么"活" |
| "**你应该并没有按照我的需求检查与改造的范围，你只是改了我说的内容**" | 要求按 20 区块 × 8 维度**全量**检查，不是只改点名的 |
| "有没有检查两个界面的全部，比如顶端信息还有按钮，底端输入框" | 要求**逐元素**盘点 |
| "**还是丑**"/"太劣质了，像十几年前的造物" | 效果验收未通过（需求方也不知病因） |
| "**不是给你发过工具还有网站吗**" | 指出了没用他给的设计资源 |
| "**C:\...\c2-hbu\index.html 这是你之前给的，你自己看看一样吗**" | 指出了"批准的靶子从没铺到真实页" |

---

## 2. "活"的判定口径（已定型）

写在 [`DESIGN-LANGUAGE.md`](redesign-demo/design-review/v6-redesign/DESIGN-LANGUAGE.md)。核心是**截屏测试**：

> **一张静图不丢信息的界面 = 死的。**

- **对话页的活 = 过程可见**（谁在说、在想、在交接）
- **数据页的活 = 组织可见**（同一批信息可按来源/主题/可信度重组；结构显形；粒度与溯源；状态与不确定性显形）
- 数据不动时，**观看方式**可以动——这是"已有的信息如何更好呈现"的答案
- 反例表（明确禁止）：fade、数字滚动、持续背景运动、粒子、发光边框、指示线滑动、自动轮播

色值来源与可靠性分级见 [`COLORS.md`](redesign-demo/design-review/v6-redesign/COLORS.md)：
- **校徽蓝 `#0058A7`** —— 从官方校徽 PNG 实测（两份官方资产非背景像素 100% 是该值）。项目里曾写成 `#154494`，**是错的**
- **官网红 `#96000E`** —— 来自 `www.hbu.edu.cn/css/layout.css`
- 导航**不用大面积深蓝**；红只用于"需要你注意"，success 用灰（"完成不给颜色奖励"）

---

## 3. 视觉方向怎么定的

三轮直接在对话页上盲改失败后，改为**先做方向样张**。四套**真实可点页面**（不是静态图）：

| 方向 | 路径 | 立场 | 自认风险 |
|---|---|---|---|
| A 工作台 | [`directions/a-workbench/index.html`](redesign-demo/design-review/v6-redesign/directions/a-workbench/index.html) | 密度 + 刻度 + 数字纪律 | 变成没人味的控制台 |
| B 编辑物 | [`directions/b-editorial/index.html`](redesign-demo/design-review/v6-redesign/directions/b-editorial/index.html) | 排印（46→11px 跨度、41 字版心、零阴影） | 变成挂在网页上的 PDF |
| C 陪伴感（暖沙版） | [`directions/c-companion/index.html`](redesign-demo/design-review/v6-redesign/directions/c-companion/index.html) | 材质 + 温度 | 滑向通用 AI 应用模板 |
| **C2 河大配色版（选定）** | **[`directions/c2-hbu/index.html`](redesign-demo/design-review/v6-redesign/directions/c2-hbu/index.html)** | C 的结构 + 需求的配色 | 同上 |

**需求方选定 C2**，并要求按既定配色重做（暖沙版违反配色要求，留作对照）。

### C2 的定案（写在 [`PLAN.md`](redesign-demo/design-review/v6-redesign/PLAN.md) §4.5）
- 白灰为底与结构色；默认校徽蓝，可切官网红；三轴可切（主色 / 主题 / 密度）
- 蓝红两套对比度实测最低 **4.95:1**
- **"温度"的迁移**：暖沙版的温度来自色相；色相被锁死后搬到四处——材质（真半透明分层 + 内高光/内描边）、光影（统一照明模型，大模糊 + 大负扩散）、头像在场感（腮红 → 下巴背光/顶部镜面高光，**色相温度 → 明度温度**）、动效与排印节奏
- 头像为**卡通风格**，守住"不低龄化"（不正圆、无腮红/符号、幅度 ≤1.12 倍）
- 用户气泡**纯色**（`background-image: none`），四组实测最低 4.74:1
- 生成方式：`directions/c2-hbu/index.html` 由 `directions/c2-hbu/_tools/build.mjs` 从 c-companion + `_tools/c2.css` 生成，**重跑逐字节可复现**
- **两处已知限制**：深色主题下红蓝两套气泡填充相同（`#1b1b1d`），色相只在 1px 边上；40px 下头像识别件退成淡线

---

## 4. 做过什么（按阶段）

### 4.1 环境（已配好，无需重做）
- **MCP**：shadcn + stitch 已装进 DSH。配置在 `~/.dsh/profiles/desktop/cordis.patch.yml`，**新插件条目必须写在 `- insert:` 下**（不带 `insert:` 的 patch 只会覆盖已有条目，会报 `patch: entry "mcp-shadcn" not found`）
- **代理**：`C:\Users\y'm'y\.dsh\.env` 里 `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:7897`；仓库级 `git config http.proxy` 也已设
- **Playwright**：`PW_PATH=%LOCALAPPDATA%\npm-cache\_npx\9833c18b2d85bc59\node_modules\playwright`
- **dev server**：`http://127.0.0.1:5180`（hash 路由。`/#/report` 这类；`/report` 直接开会落到门户）
- **门禁**：`npm.cmd run typecheck`（vue-tsc）、`npm.cmd run build`、`node scripts/check-contrast.mjs`、`node scripts/check-classes.mjs`
  - ⚠️ `check-contrast.mjs` **在动工前就是红的**（6 处，全在 `src/components/`）
  - ⚠️ `check-classes.mjs` 对 BEM 修饰符式撞车抓不到（`.ws-sheet` 全局 ↔ `InfoSheet.vue` 的 `.ws-sheet--dialog`）

### 4.2 审计（COVERAGE 矩阵）
按 20 区块 × 8 维度做了全量审计，四路并行，结论在 [`COVERAGE.md`](redesign-demo/design-review/v6-redesign/COVERAGE.md)（第五~八节）。
量化手段：截图 + 自写只读探针（量 DOM）。

**十条共性问题**里最要紧的：
1. **契约组件库几乎全是空头支票** —— PLAN §4.2 列 19 个小组件，只落地 1 个（这是"每做一个页面就多发明一套写法"的直接原因）
2. **零骨架屏 / 成功反馈静默** —— `/notes` 勾掉一件事得到零反馈；toast 在门户布局下完全不渲染
3. **折叠失控** —— 四种折叠组件、深度 1~3 层；`/plan` 单页 21 处；报告页把核心证据压在最后一层折叠里
4. **内部页面从导航裂缝漏回学生入口** —— `workspace-nav.ts` 注释写着"设计规范不进学生导航"，同一文件 `HELP_LINKS` 又把它塞了回去

### 4.3 组件工艺规范
[`CRAFT-BRIEF.md`](redesign-demo/design-review/v6-redesign/CRAFT-BRIEF.md)（568 行）。诊断"组件为什么丑"三条：**只有一层白 / 阴影形同不存在 / 强调色超配额**。

> ⚠️ **该文档有一处已被作废**：§2.3 要求结论块加「结论」语义标签，但 `DESIGN-LANGUAGE.md` §215 与本项目取向禁止"结构自述词"。**现网代码选择不加标签，是对的**。评审（`DESIGN-REVIEW-V7.md` §5）判定现网正确、建议作废该段。
> ⚠️ 该文档里"蓝色占比 >25%"是**估感不是实测**；实测是 **4.73%**。真正的问题是"蓝色出现在哪些地方"（非白名单用蓝 17 处 → 0）。

### 4.4 组件基础设施（9 个，已建）
`redesign-demo/src/components/`：
`SkeletonBlock.vue`（骨架屏）、`EmptyState.vue`（空态，9+4 类）、`StatusBanner.vue`（四态状态条）、`InfoSheet.vue`（三形态弹层）、`Foldable.vue`（折叠）、`SourceChip.vue`（来源）、`StatTile.vue`（读数瓦片）、`ConfidenceBadge.vue`（把握档）、`charts/MeterRow.vue`（同刻度对照）

**关键设计**：
- `MeterRow` 只接受 **0–1**（`normalize01()` 是三个组件**共用唯一入口**）；`data/student.ts` 是 **0–100 整数**，调用点必须 `/100`
- `InfoSheet` 形态：`dialog`（确认/表单，居中）/ `sheet`（抽屉，**移动端底部面板**）/ `panel`（大面板）
- `Foldable`：`variant`（inline/section/group）、`static`（给主信息，永远可见）、`forceOpen`（受控，如打印）、`headless`/`titleLevel`

### 4.5 令牌层修复（P0-1 / P0-2 / P0-4）
评审判决的根因是"**结构量低于感知阈值**"。改前改后（实测）：

| 结构量 | 改前 | 改后 |
|---|---|---|
| 页底 → 纸面 | 1.079 | **1.204** |
| 局部面 → 纸面 | 1.044 | **1.142** |
| 发丝线 → 纸面 | 1.262 | **1.506** |
| 强描边 | 1.506 | **2.141** |
| **控件边** | 1.506 | **3.017**（新增 `--c-border-control`，过 WCAG 1.4.11 的 3:1） |
| **侧栏内外像素** | `#f7f6f6`/`#f7f6f6`（Δ0，完全同色） | `#ffffff`/`#e8eaef`（Δ23） |
| 近白占屏 @1280 | 93–97% | **75–81%** |
| 图表刻度字 | 1.98:1 | **5.80:1** |
| `h2` | **12px（小于正文）** | 14px |
| 10px 档 / 第四档 700 字重 | 存在 | **归零** |
| 密度皮肤 | **完全无效**（dense 也是 27.2px） | **生效**（dense 24.8px） |
| 控件高度档位 | report@390 3 档、plan@1280 7 档 | report@390 **1 档**、plan@1280 **5 档** |

### 4.6 顾问形象进驻
`AgentAvatar.vue` 按 c2-hbu 卡通画法重做：材质层 4→2、眼睛是主角、40px 下三层可辨（眼白 5.86×6.37px / 瞳 3.85px / 高光 1.42px）。
修掉 `dialogue.css` 里一个空的 40×40 占位；空态加 96px 在场者（消息出现即消失，**没有**恢复已删的头部身份牌）。

### 4.7 wave1：七路页面铺设 + wave2：组件缺陷与死代码
见 §5 与 §6。执行清单在 [`MIGRATION.md`](redesign-demo/design-review/v6-redesign/MIGRATION.md)。

---

## 5. 当前状态（最重要的部分）

### 5.1 提交历史（分支 `新前端4`）
```
e48829c  feat(redesign): wave1 七路页面铺设 + wave2 组件缺陷修复与死代码清理
0b6b51e  chore: 清理误入库的编辑备份产物并补齐 .gitignore
4f6e398  fix(redesign): 顾问进驻真实页 + 画像页字号阶梯正过来
a914bcf  feat(redesign): 选定 c2-hbu 方向、补齐组件基础设施、把结构量调到感知阈值以上
```
**远端没有 `新前端4`**，未推送。

### 5.2 ⚠️ 最大的欠账：**c2-hbu 从未铺到真实页面**

需求方批准的靶子是 [`directions/c2-hbu/index.html`](redesign-demo/design-review/v6-redesign/directions/c2-hbu/index.html)。
**真实页面与它差得远**，且七个 agent 的简报写的是"迁移组件"，**没有一条是"让页面长得像 c2-hbu"**。

对照（c2-hbu vs 当前真实页）：

| | c2-hbu（靶子） | 当前真实页 |
|---|---|---|
| **结论块** | 「结论」小标 + 左侧粗色条 + 极大字（约 30px+，占屏宽 2/3） | **无标、无色条、约 20px**，与正文同重 |
| **顾问在场** | 96px 头像 + 名字 + 职责 + **待命/思考/说话切换** + 「正在想」状态点，整块卡片 | **该块不存在** |
| **页头** | 大标题 + 「今天 14:20 开始」+「职业分析顾问 主理」+ 演示数据 + 总结/导出 | **一行小字会话名 + 2 个按钮** |
| **顶栏** | **搜索输入框（⌘K）** + 铃铛 + 账号 | 面包屑 + 图标，**无搜索框** |
| **侧栏** | **深蓝品牌块** + "陪你走完这一段" + 图标 + 计数 + 底部人名带专业年级 | 白侧栏，浅色小标志 |
| **右栏** | 有边界与内边距、**大号数字**（3 项 / 8/12）、勾选图标、**虚线进度条**、「看全部成果 →」 | 更小更素、**无大号数字、无进度条** |

**下一步该做的就是这件事**，且验收方式要改：不再看百分比，而是**把真实页截图与 c2-hbu 对应区域并排对照，逐项打勾或解释为什么不一致**。

### 5.3 页面矩阵（20 区块）
| 状态 | 区块 |
|---|---|
| **已改造（结构迁移）** | 导航与应用外壳、咨询对话、个人画像、诊断报告、阶段计划/今日行动/待办、日历与课表、学籍与资料、复盘与记录、岗位资讯 |
| **部分改造** | 门户（`PortalClassicView` 的清动效 + 居中修复）、登录/账号（壳层重构） |
| **仅审计未改** | 方向方案、通用组件与状态的剩余项、工具页、使用指南、设计规范、提醒、异常页 |

### 5.4 全站关键数字（Lead 独立复量）
- `vue-tsc` **零错误**；`npm run build` 成功
- **11 个路由 × 1280 控制台全部干净**（0 error / 0 warning）
- 全站 `.ws-sheet--wide` / `--inspector` = **0**；`.meter__fill` = **0**
- **`<44px`：@1280 9→4、@390 19→4**（10 路由 × 2 档，磁盘复算）；剩余 3 类为**有意为之或非问题**：`.btn--sm` 82×36（项目自订小档 `--btn-h-sm: 36px`）、`.ws-task__check` 18×18（`::after` 命中区 44×44）、`input.sr-only` 1×1
  > ⚠️ 订正：我先前口头报的 "9→5 / 17→4" **与实测不符**。@390 改前的 19 条里有 10 条是 `.ws-demo-badge`（25×44），已整体消失。这就是本项目的"**Lead 复量也要被复量**"。

- ⚠️ **弹层调用点只迁移了 12/18**：磁盘上只有 12 处传了显式 `shape`，**6 处仍走缺省 `dialog`** —— `AuthLayer:33`、`CommandMenu:45`、`ConversationView:915`、`WorkspaceNav:52`、`WorkspaceHeader:128/169`。其中 **4 处正是原定要改成 `panel`/`sheet` 的，属未做**。
  > ⚠️ 另一处易被误读：`InfoSheet.vue:18-25` 的注释写"全站 4 个曾经的调用点都已物理删除"——那说的是**旧 prop**（`wide`/`inspector`）被删掉，**不是**"调用点形状都迁移完了"。组件侧已完成，调用点欠 6 处。

### 5.5 逐页实测（改前 → 改后）
| 页面 | 关键指标 |
|---|---|
| `/report` | 交互式折叠 4→**0**；**12 个 MeterRow 从"要点 10 次"→ 0 次点击可见**；雷达 0→1；打印稿仍 12/1 |
| `/plan` | 折叠 21（20 收起、**嵌套 3 层**）→ **2（0 收起、1 层）**；三层嵌套拆成 4 个 44px 筛选 chip |
| `/home` | 折叠 2→**0** |
| `/intel` | 「阅读全文」零增益被修：弹层 **120 → 527 字（+417）**，新增 3 块卡片上没有的信息（未编造全文） |
| `/profile` | `confidence` **3 套印法 → 1 套**；12px 占比 **63.2% → 32.2%**；页高 +886/+1275 |
| `/chat` | `.ws-fold`（交接记录）1→0 改 `static`；`InfoSheet` 实测生效；`SkeletonBlock overlay` 证明内容留 DOM |
| `/academic` | "核对学籍"从默认收起的折叠里提到**首屏可见** |
| `/review` | 嵌套 2 层 → **1 层** |
| `/schedule` | 折叠 2→1 |

---

## 6. 已知问题与盲区（必须知道）

### 6.1 ⚠️ `Foldable` 嵌套检测器有盲区（我独立复量发现的）
- wave2 把判据改成"只数可折叠的 `.fold`"（排除 `.fold--static`），为修"static 容器 + inline 内部"的误报
- **副作用**：`/plan` 上 3 对结构嵌套里，**2 对是「可折叠外层 + static 内层」，而嵌套告警 0 条**——这个组合从检测器里消失了
- wave2 的隔离测试覆盖了 A（static 外 + inline 内，合法）与 B（可折叠外 + inline 内，真嵌套），**漏了 C（可折叠外 + static 内）**，而 C 正是 `/plan` 的真实形态
- **裁定**：用户视角只有 **1 次点击**（static 内层不需要再点），**不算违规**；但检测器看不到这个组合是真实盲区
- **以后怎么检**：加一条能识别"被可折叠祖先遮住的 static"的独立断言

### 6.2 三族 CSS 仍是"迁移未完成"（**不是死代码，删了会当场坏**）
- `.ws-context` —— 活调用点：`ToolsView:8`、`TodoSuggestions:12`（`<details>`）、`StudentView:1342`（`.ws-context__body`）
- `.desk-status` —— 活调用点：`AcademicView:119`、`LiveDirectionCompare:25`；且 **redesign.css 与 workspace.css 里有两份互相覆盖的定义**
- `.ws-empty` 本体与 `p` —— 删了会丢 36px 内距与居中

### 6.3 未处置的遗留
- `redesign.css:329` 的 `.ws-context > summary > svg { display:none !important }` 保留（`.ws-context` 本体还活着）；**不会**影响 `Foldable` 的 chevron（实测 `.fold__chevron` display=block）
- `motion.ts` 的 `useCountUp`（0 调用，与 `DESIGN-LANGUAGE` 反例冲突；`StudentView` 另有一份自写 rAF）
- `SpecView.vue:474-476` 手写了 `.meter-row__*`，与 `MeterRow.vue` 的 `.mtr__*` **并行**（订正：`MIGRATION.md` 曾说它"全库无样式定义"，实测它自己 scoped `:760-777` 有四条）
- `TodayView:71` / `ReflectionView:57` 里裸写的 `<button>收起</button>`，只靠 CSS 兜底
- 门禁 `check-contrast.mjs` 仍是红的（6 处，全在 `src/components/`，`--c-text-4` 当文字色）
- `.btn--sm` 82×36 —— 若要"任何可点元素 ≥44"需**产品拍板**（会影响所有卡片内次要动作）
- **门户在桌面**：`PortalProposalView` 仍是 1100/760/360 断点，未对齐 1120/768

### 6.4 你**不该**做但可能想做的事
- **全局 `.ws-sheet` 是"活依赖"，且应该被修掉而不只是"别删"** —— `background` / `box-shadow` / `::backdrop` **只在全局定义**（`workspace.css:420,422`），`InfoSheet.vue` 里没有。`MIGRATION.md §2.5` 说"删之前先确认已移进 scoped"，**实测没有移**。所以正确处置不是永久保留，而是：**把这些属性搬进 `InfoSheet.vue` 的 scoped，再删全局一族**。删除之前，单独删会让 18 个弹层一起透明无遮罩
- **不要用跨文件覆盖去改别的文件**（例如 `StudentView.vue` 里写 `:deep(#app .p7-*)`）——这正是本项目"**规范被后加载文件覆盖**"这个系统性病灶的成因（出现 4 次，见 §9）
- **不要通过改语义令牌去修"有人用错了语义"**（例如为修深色骨架黑带去调 `--c-primary-weak`）

---

## 7. 下一步该做什么（建议顺序）

1. **回填文档执行状态**（进行中，见 §11 的待办）
2. **把 c2-hbu 铺到真实页面**——这是 §5.2 的欠账。做法：
   - 先把 c2-hbu 拆成**可执行的清单**（结论块尺度与色条、在场卡、页头三行、搜索框、右栏大号数字与进度条、侧栏品牌块……每项给 c2 里的实测值）
   - 逐页对齐，**每页改完把真实页截图与 c2 对应区域并排**，逐项打勾或解释
   - 验收标准从"数字达标"改成"**与靶子的差异逐条有交代**"
   - 建议从 **对话页** 开始（需求方点名过，差异最集中）
3. **处置 §6.2 的三族 CSS**（等各自页面处置完）
4. **剩余的"仅审计未改"区块**（方向方案、工具页、使用指南、设计规范、提醒、异常页）
5. **推送到远端**（`新前端4` 目前只存在本地）

---

## 8. 可复跑的工具（都在 `_tools/`，**脚本入库、产物不入库**）

| 工具 | 用途 |
|---|---|
| `_tools/probe-elements.mjs` | 逐元素盘点：所有可点元素的尺寸/区域/`<44px`。改视觉必用它 |
| `_tools/shot.mjs` | 通用截图（支持 `--routes` / `--widths` / `--height`） |
| `_tools/shot-current.mjs` | 截当前真实页面 6 路由 × 2 档 |
| `_tools/png-color.mjs` | 纯 Node 解 PNG 取色（用来量官方资产的真实色值） |
| `_tools/p0-tokens/` | 结构量对比度 / 字号直方图 / 控件档位度量（`measure.mjs` / `summarize.mjs` / `skins.mjs`） |
| `_tools/p0-2-profile/` | 画像页字号分布 + 哈希校验的往返测量（`roundtrip.mjs`，不匹配置退出码 3） |
| `_tools/wave2-fixes/` | `InfoSheet` 形状 / `Foldable` 层级 / `StatusBanner` 尺寸等验证探针 |
| `_tools/probe-shell.mjs` | 壳层控件盘点（只算壳层拥有的元素） |

**证据截图**（`.gitignore` 已忽略，可复跑）：`_shots/`、`_shots-now/`、`redesign-demo/_shots/`、`redesign-demo/design-review/**/shots/`、`redesign-demo/design-review/**/*.png`

---

## 9. 过程教训（这份文档里最该记住的部分）

### 9.1 组件 API 按"设想的用法"设计，而不是按"代码里真实存在的用法"
证据（每条都是**独立撞上**）：
- `SourceChip` 的 `source` 收成必填 7 值枚举 → **三路 agent 独立撞上**：资讯 `source_name`、AI `citation.source`、对话方法卡来源**都是自由文本**，喂不进去，只能退回灰字
- `EmptyState` 只有 3 个 kind → **三路各自借用语义不符的 kind** 并留注释
- `Foldable` 层级判据把 `.fold--static` 算一层 → 一路 agent **被迫放弃**按需折叠
- `SkeletonBlock` 根写死 `<div>` → 放进 `<button>` 是**非法 HTML**，一路 agent **直接没做**那 8 处

**结论**：建组件前先 grep 真实调用点，不要照着契约清单设计。

### 9.2 `<script setup>` 没有模块作用域
`Foldable.vue` 里 `let foldSeq = 0` 是**每实例重新执行的局部变量** → 全站 11 个折叠体 id 全是 `fold-body-1`，**`aria-controls` 全员指向文档里第一个折叠体**。
修法：`useId()`（Vue 3.5+）或另开普通 `<script>` 块。
**教训**：`<script setup>` 里任何"全局计数 / 单例缓存 / 只跑一次"的写法都会变成"每实例各来一次"。

### 9.3 修一个问题造一个新问题
- `MeterRow` 收紧 API（`:score` 0–100 → `:value` 0–1）**静默打断了 `/report` 的 12 个实例**（显示"暂无依据"，页面看起来没崩但数据全丢）
- `Foldable` 判据改动带来 §6.1 的检测器盲区
- 画像页"压缩高度"是**拿触控目标换的**（「支撑 N 条判断」被压成 22px）
**纪律**：改组件 props 前先 grep 全部调用点 + 保留废弃别名；收紧 API 必须同批迁移。

### 9.4 规范被后加载文件覆盖（**系统性病灶，出现 4 次**）
| 现象 | 位置 |
|---|---|
| 侧栏丢边界（`background:transparent` 覆盖） | `experience.css:3` 覆盖 `workspace.css:67` |
| `--lh-normal` 与**密度皮肤完全失效** | `.app--workspace{line-height:1.7}` 特异度压过 `body` |
| 8 类控件被写回 40px（违反 44px 硬约束） | `redesign.css` 最后加载 |
| 用 `clamp()`/`vw` **绕过字号与字距门禁** | `views/PortalProposalView.vue` |

**这是层叠纪律缺失，不是个别疏漏**——建议作为独立一项处理。`check-classes.mjs` 对 BEM 修饰符式撞车抓不到，`check-contrast.mjs` 对"装饰令牌当文字色"只认多行规则（一行写法从来没被拦过）。

### 9.5 我的判断失误（都要记住）
1. **三次盲改对话页**：没有靶子时，改多少轮都到不了位。你四次说"丑"，我四次都在猜
2. **写了 19 个组件的清单，只建了 1 个**：等于没写
3. **拿估感当数据**：`CRAFT-BRIEF` 说"蓝占比 >25%"，实测 **4.73%**；真正的问题是"蓝色出现在错的地方"（17 处非白名单）
4. **数字报告掩盖了观感**：我一直报"折叠 21→2、12px 63%→32%、<44px 9→5"——都真，但**不代表页面变好看了**。审阅者容易把"数字达标"读成"差不多了"
5. **❗ 有了批准的靶子却没安排铺它**：七路 agent 的简报写的是"迁移组件"，没有一条是"让页面长得像 c2-hbu"。**这是本轮最大的组织失误**（后果见 §5.2）
6. **你给的设计资源拖到被提醒才读**：[`DESIGNEEER-DIRECTORY.md`](DESIGNEEER-DIRECTORY.md)、[`DESIGN-RESEARCH.md`](DESIGN-RESEARCH.md)、`redesign-demo/design-review/full-audit-2026-10-13/总调研报告.md`

---

## 10. 操作注意事项（踩过的坑）

| 坑 | 说明 |
|---|---|
| **中文文件不要走 PowerShell 文本管道** | `Get-Content \| Set-Content` 按 GBK 往返会把文件弄坏（本轮弄坏过一次 `build.mjs`，重写为无 BOM UTF-8 才恢复） |
| **命令行里路径含撇号** | 仓库路径是 `C:\Users\y'm'y\...`，PowerShell 单引号会解析失败。用 `read` / `edit` 工具，或改 `workdir` 参数 |
| **`node -e` 带撇号路径** | 同样会失败；用 `--input-type=module` + 绝对路径，或用 `workdir` |
| **并发写者** | 本轮最多同时 8 个 agent 写同一仓库。**文件范围必须互斥**，共享依赖的行为变化（如删 prop）要让所有写者知道 |
| **并发期间的 typecheck 瞬时失败不是结论** | 多路都撞到过别人的中间态（`ConfidenceBadge` 找不到模块、`StudentView` 的 `EmptyStateHeadingLevel`、Vite "Duplicate attribute" 覆盖层）。**必须以全部写者停下后的复跑为准** |
| **截图等产物不入库** | `.gitignore` 已有对应条目（`:60-79` 与本轮追加的一节）。本轮 `_shots/` 等合计 100MB+，一次性提交会让仓库体积**永久不可逆** |
| **hash 路由** | Playwright 里要用 `http://127.0.0.1:5180/#/report`，不是 `/#/report` 之外的写法 |

---

## 11. 待办（接手后可直接开工）

- [ ] **回填文档执行状态** —— `COVERAGE.md` / `MIGRATION.md` 里"哪些已改、哪些没改、哪些是错的"仍有一部分只活在对话里（正有一个 agent 在做）
- [ ] **把 c2-hbu 铺到真实页面**（§5.2 / §7.2）—— **最高优先级**
- [ ] §6.1 的 `Foldable` 检测器盲区：加独立断言
- [ ] §6.2 三族 CSS 的页面级处置
- [ ] `check-contrast.mjs` 的 6 处红（`--c-text-4` 当文字色）
- [ ] `.btn--sm` 是否要提到 44px（需产品拍板）
- [ ] `PortalProposalView` 断点对齐 1120/768
- [ ] 剩余"仅审计未改"区块
- [ ] 推送到远端 `新前端4`

---

## 12. 文档索引（全部路径）

### 本项目的核心文档（都在 `redesign-demo/design-review/v6-redesign/`）
| 文档 | 用途 |
|---|---|
| [`PLAN.md`](redesign-demo/design-review/v6-redesign/PLAN.md) | **施工契约**。§4.5 记录了方向选定与两处已知限制 |
| [`DESIGN-LANGUAGE.md`](redesign-demo/design-review/v6-redesign/DESIGN-LANGUAGE.md) | **"活"的判定口径**（截屏测试 / 过程可见 / 组织可见 / 反例表） |
| [`COLORS.md`](redesign-demo/design-review/v6-redesign/COLORS.md) | 配色来源与可靠性分级 |
| [`COVERAGE.md`](redesign-demo/design-review/v6-redesign/COVERAGE.md) | **20 区块 × 8 维度矩阵** + 全站审计汇总（第五~八节） |
| [`CRAFT-BRIEF.md`](redesign-demo/design-review/v6-redesign/CRAFT-BRIEF.md) | 组件工艺规范（⚠️ §2.3 的「结论」标签要求已作废；"蓝占比 25%"是估感） |
| [`DESIGN-REVIEW-V7.md`](redesign-demo/design-review/v6-redesign/DESIGN-REVIEW-V7.md) | **设计评审**：判决主因是"结构量低于感知阈值"而非配色/配图 |
| [`MIGRATION.md`](redesign-demo/design-review/v6-redesign/MIGRATION.md) | **组件 → 17 页面的迁移清单**（含 7 条硬耦合 H1~H7） |
| [`directions/`](redesign-demo/design-review/v6-redesign/directions/) | 四套方向样张，`index.html` 可直接双击打开 |

### 仓库根的既有文档
| 文档 | 用途 |
|---|---|
| [`DESIGN.md`](DESIGN.md) | 项目原有设计说明 |
| [`HANDOFF.md`](HANDOFF.md) | **项目原有交接文档**（先于本次整改，仍有效） |
| [`CHANGELOG.md`](CHANGELOG.md) | 变更日志 |
| [`README.md`](README.md) | 项目说明 |
| [`DESIGN-RESEARCH.md`](DESIGN-RESEARCH.md) | 设计调研 |
| [`DESIGNEEER-DIRECTORY.md`](DESIGNEEER-DIRECTORY.md) | **需求方提供的设计工具与网站目录**（59.8KB） |
| `.tmp-research/raw/directory.csv` | 上述目录的原始条目（96.7KB，已被 `.gitignore` 忽略） |
| `redesign-demo/design-review/full-audit-2026-10-13/总调研报告.md` | 上一轮全站调研报告 |
| `信息采集与快速回答问题定位.md` | 作者自有笔记（作者要求不入库，`.gitignore:85`） |

### 环境与配置
| 路径 | 内容 |
|---|---|
| `~/.dsh/profiles/desktop/cordis.patch.yml` | DSH 插件补丁（MCP 条目在 `- insert:` 下） |
| `C:\Users\y'm'y\.dsh\.env` | `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:7897` |
| `.gitignore` | 产物忽略规则（`:60-79` 是原有口径，末尾一节是本轮追加） |
