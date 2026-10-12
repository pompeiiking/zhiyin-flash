---
name: 职引 · V5 学生空间
description: 延续蓝红灰令牌，以清晰阅读、独立导航和状态反馈支持学生咨询与行动。
colors:
  primary: "#154494"
  primary-hover: "#113a7d"
  primary-weak: "#eff3fa"
  attention: "#96000e"
  text: "#1e232c"
  text-secondary: "#4b5157"
  text-muted: "#61666b"
  background: "#f7f6f6"
  surface: "#ffffff"
  surface-secondary: "#fafafa"
  border: "#e1e5ee"
  border-strong: "#cfd3d6"
  dark-background: "#151517"
  dark-surface: "#1b1b1d"
  dark-text: "#f9fafb"
  dark-primary: "#6e93c9"
  dark-attention: "#d98a92"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Source Han Sans SC', 'Noto Sans CJK SC', sans-serif"
    fontSize: "38px"
  headline:
    fontSize: "30px"
    lineHeight: 1.3
  title:
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.45
  body:
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.7
  control:
    fontSize: "14px"
    fontWeight: 500
  label:
    fontSize: "12px"
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  inspector: "16px"
  desktop-canvas: "20px"
  pill: "999px"
spacing:
  sp-1: "4px"
  sp-2: "8px"
  sp-3: "12px"
  sp-4: "16px"
  sp-5: "20px"
  sp-6: "24px"
  sp-7: "32px"
  sp-8: "40px"
  sp-9: "56px"
  sp-10: "72px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  button-ghost:
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
  field:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    height: "38px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "32px"
  chip-primary:
    backgroundColor: "{colors.primary-weak}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    height: "22px"
---

# Design System: 职引 · V5 学生空间

## 2026-10-12 · 三页面视觉试改

### 对话页修订：消息层次

对话页现以 `src/styles/dialogue.css` 与 `dialogue-page` 为准。去掉常驻右侧画像和路线图，画像、成果与历史仍按需打开。单列阅读区上限 800px，用户消息右对齐浅蓝底，顾问回复使用左侧角色标识，依据与复制归入回复底部。交接为独立的可展开系统分隔；任务则单独表达建议、具体行动、时长与加入按钮。

本轮实际参考 [Ant Design X Bubble](https://x.ant.design/components/bubble/)、[AI Elements Message](https://elements.ai-sdk.dev/components/message)、[Sources](https://elements.ai-sdk.dev/components/sources)、[Plan](https://elements.ai-sdk.dev/components/plan) 及 [Ant Design Proximity](https://ant.design/docs/spec/proximity/)。取舍与访问边界见 `design-review/chat-hierarchy/REFERENCES.md`。以下三页面说明保留为第一轮记录，不再代表当前对话页。

同步移除方向页的设备示意图与今日行动的路线图，删除相应组件和闲置样式。现行页面以任务状态、支持依据、风险和逐项对照表达内容。

本轮先在咨询、今日行动和方向方案上验证路径图形与更明确的内容层次。新增样式位于 `src/styles/journey.css`，通过页面类限定作用范围，沿用蓝红灰语义颜色与系统字体。今日行动与方向方案页标题采用既有 38px 档，手机回到 30px；咨询保持 30px，正文仍为 16px。

`JourneyMap` 是目标、当前行动与复盘关系的概念图，不代表实际环节完成状态。`CareerDiagram` 是半导体、电池与材料检测的几何示意图，不代表企业、设备规格或职业评分。咨询概览的画像计数与行动建议直接取现有演示状态；手机隐藏侧栏概览，原画像和成果面板入口保留。

导航调整为咨询、画像与诊断、方向选择、行动与安排、复盘与成长；岗位资讯归入方向，个人待办保留独立入口。移动快捷入口为对话、行动、画像、方向及更多，报告可从画像与诊断目录独立访问。

路径线首次绘制为 800ms，完成反馈为 240ms，选择反馈为 180ms；减少动效偏好关闭新增动画。预览与验证记录见 `design-review/journey-pilot/QA.md`。本轮保持本地演示边界，不代表正式后端接入。

## Overview

本文件记录 2026-10-12 已实现的 V5，是版本控制中的设计系统主依据；`.impeccable/design.json` 为本地补充记录。V5 是既有操作界面的代码延伸，沿用蓝红灰配色与系统字体，没有新的品牌世界或获批视觉稿。产品约束见 [PRODUCT.md](PRODUCT.md)，本轮范围见 [DESIGN-BRIEF.md](DESIGN-BRIEF.md)。

界面以稳定工作表面、合适列宽和按需解释组织阅读。桌面导航融入背景，内嵌主画布承载内容；标题、间距、描边与少量主色表面表达主次。说明使用正常书面语言，交互反馈明确操作结果。

**Key Characteristics:**

- 延续蓝、红、中性灰，状态同时提供文字或图标。
- 正文保持 16px，密度变化不缩放字号。
- 二级目录与历史分区，页内视图支持键盘切换。
- SVG 图形用于咨询引导和空态，内容区保持稳定阅读表面。

## Colors

frontmatter 记录默认浅色、蓝主、plain 样式的常用值；运行以 `src/styles/tokens.css` 的语义变量和主题覆盖为准。V5 的布局与组件覆盖在 `workspace.css`、`experience.css`。

### Primary

主蓝用于入口、选中视图、链接、依据编号与进度，浅主色表面用于局部重点。深色主题将文字蓝提亮、按钮使用亮底深字。可选红主主题替换交互主色，组件继续使用语义变量。颜色来源属于项目实测记录，不宣称已核实官方 VI。

### Secondary

注意红表达截止、风险和差距，已完成用中性灰。红主主题通过实心操作与浅底注意区域区分角色，不增加新色相。

### Neutral

暖灰底与白色工作表面分层，主文字、次要文字和来源注解分级。深色主题使用提亮表面与更强描边，不做简单反相。

**The 三色规则 Rule.** 组件通过既有语义令牌表达状态，不新增绿、琥珀等状态色；状态不能只靠颜色。

## Typography

展示与正文共用 frontmatter 的系统中文无衬线栈，无字体下载。正文、咨询和输入内容保持 body 尺寸；工作空间行高为 body，咨询为 1.85。字重使用 400 / 500 / 600。

| 层级 | 用途 |
| --- | --- |
| display | 关键数字；门户主张另用 38–68px 响应式字号 |
| headline | 页标题与主要结论 |
| title | 节标题、品牌与手机重点标题 |
| body | 正文、咨询、任务标题与输入 |
| control | 说明、控件与桌面导航 |
| label | 来源、时间、短标签与注解 |

顾问正文最大行宽约 40em，自己的消息桌面最大宽 80%、手机最大宽 90%。plain / soft / dense 调整间距、圆角和行高，不改变正文尺寸。

## Layout

展开时桌面侧栏宽 228px、距边缘 16px，主区预留 252px；顶栏高 76px。侧栏可整体收起，内容区扩展；顶栏提供展开入口，重新展开保留本次菜单展开状态，收起偏好存入 localStorage。V5 主画布右侧与底部各留 16px，形成有描边的内嵌表面。常规页最大宽 1200px、左右内距 40px、底部 64px；咨询最大宽 1060px。宽度不超过 1200px 时侧栏为 208px、页面左右内距为 28px，辅助区按空间重排。常规主辅列比例为 1.6:1，辅助列至少 280px。

窄于 1000px 自动采用移动导航，桌面可主动切换布局。移动导航模式常规页最大宽 1160px；手机左右内距 20px、底部留 132px，内容重排为单列。短于 700px 的咨询使用文档流，记录区有自身滚动范围，输入区可通过页面滚动到达。

门户保留蓝红灰配色与左右构图，原版通过 `?portal=classic` 对比；登录与已登录入口均进入咨询。桌面咨询置顶，生涯分析、计划管理、资讯与记录为二级目录；全部历史位于业务导航下方、共用滚动区。侧栏展开时账号仅左下，收起时转到顶栏右上，始终只有一个可见入口。手机底栏为对话、行动、画像、报告、更多；更多使用同一目录，账号仅右上。

方向对照表最小宽 760px，仅在自身容器内横向滚动；手机有左右滑动提示，首列固定。补充面板在桌面靠右、最大宽 460px、四周距边 12px；不超过 760px 时改为全宽底部面板、最高 88dvh，标题固定、正文独立滚动。

## Elevation & Depth

工作表面主要用底色、1px 描边和留白分层。选中导航与咨询输入使用轻影，返回最新入口使用中影，浮动导航和 dialog 使用较高投影；阴影由 `--e-1` / `--e-2` / `--e-3` 随主题覆盖。辅助文字不会全部包成同重卡片，页面没有持续背景运动。

## Shapes

默认控件使用 sm / md 圆角，工作表面与普通面板使用 lg。V5 主画布使用 desktop-canvas，右侧面板使用 inspector，手机仅上角圆；返回最新入口与头像使用 pill。soft / dense 沿用圆角变量调整形态，主画布与 inspector 保持布局专用圆角。

图标统一 Phosphor Vue。`WorkspaceMotif` 是本地编写的稀疏点阵与分支路线 SVG，使用独立 pattern ID；用于欢迎和空态。没有生成位图、第三方图片或新字体。

## Components

### Buttons / Inputs

工作空间普通按钮最小高 42px、小按钮 36px；颜色、描边、圆角、禁用状态沿用令牌。键盘焦点为 2px 轮廓。咨询输入与材料、发送整合在带描边的区域，聚焦时强化主色描边；Enter 发送、Shift + Enter 换行，并处理中文输入法合成状态。材料仍为演示流程。

### Navigation / PanelTabs

`DesktopSidebar` / `WorkspaceNav` 共用目录，用 `aria-current` 标识路由。桌面 Reka UI Accordion 受控多组展开，路由变化只补充展开当前所属组，保留其它已展开组；V4 的单选模式为历史。整体收起使用保留组件状态的显隐切换，收起/展开后将焦点交给相应按钮，并提供 `aria-controls` / `aria-expanded`。`PanelTabs` 使用 Reka UI Tabs，提供方向键/Home/End、ARIA 关联与按需数量；允许动效时指示线以 180ms 更新。任务、阶段、资料、课表、待办与方向等页内视图共用此结构。命令面板支持 Ctrl/Cmd + K、方向键与 Enter。

### Conversation / EvidenceList / InfoSheet

咨询上读历史时暂停跟随，主动“回到最新消息”后恢复；新会话或切会话清空草稿与附件。回复复制显示成功或失败反馈，逐字期间不可复制。`EvidenceList` 显示既有依据数量和可展开编号列表，不把内部演示文本冒充外部引用。

`InfoSheet` 使用原生 dialog；咨询画像、成果、历史采用 inspector 变体，支持关闭、Esc、背景点击与焦点恢复。普通导入和更正表单保留模态布局。inspector 入场为 220ms，减少动效规则关闭该动画。

### DirectionCompare / TaskOverview / EmptyState

`DirectionCompare` 按匹配判断、支持依据、风险和选择比较三个既有方案，与概览共享方向状态；选择只展示影响范围。`TaskOverview` 从当前任务状态派生完成数/总数、待执行、等待、已完成，完成与恢复同步变化；环形图为 220ms 状态过渡，不是职业评分。

`EmptyState` 给出状态解释与下一步，配合本地 SVG；待办与目标各自保留独立草稿。历史会话仅在内容变化时更新活跃日期，恢复查看不改日期。复盘时间线以点与连接线组织既有记录，资讯正文与来源分层，系统提示使用书面状态文案。

### Motion / Print

继承菜单展开 200ms、收起 170ms、箭头 200ms；页面入场 180ms/5px，任务移动 200ms、入场 180ms/6px，没有路由离场等待。本地咨询逐字为 320–900ms。CSS 与 Vue TransitionGroup 实现动效，无新增动画库或 npm 依赖。`prefers-reduced-motion` 下关闭相关动画与过渡，跳过逐字和数字滚动；本轮仅检查源码，未用浏览器验证系统减少动效设置。

报告、方向和版本打印当前视图，展开对应证据并隐藏导航工具。旧版记录不冒充完整旧报告，详细诊断仍为第 3 版示例。

## Do's and Don'ts

- **Do** 延续语义颜色、系统字体与 16px 正文，使用标题、位置和间距表达主次。
- **Do** 保持功能独立可达、导航下方历史和唯一账号入口；解释和来源按需展开。
- **Do** 以真实当前任务状态、已有依据和演示标识表达结果，空态给出下一步。
- **Don't** 将本地状态、69 schema / 50 operation 目录校验描述为正式 API、AI、学校核验或实时岗位接入。
- **Don't** 将 SVG 引导图或浏览器截图标记为 AI 生成图片，或以历史截图替代当前验收证据。

当前证据为 [desktop-v5/QA.md](design-review/desktop-v5/QA.md)、[操作摘要](design-review/desktop-v5/browser-checks.json)与 [独立收尾审阅](design-review/desktop-v5/FINISH-REVIEW.md)：33 张实际浏览器 JPEG，12 个桌面业务页、6 个手机业务页、13 个基线特殊视图与 2 个追加导航视图。测试视口与图像像素尺寸分别记录，实际文件尺寸见 [SHOT-PROVENANCE.json](design-review/desktop-v5/SHOT-PROVENANCE.json)。指南副本为 `public/shots/v5-{portal,chat,profile,report,directions,home,review}.jpg`，各 `.jpg.json` 记录截图来源。

最终构建/类型、目录、类名、对比度和六档字号检查通过；独立 finish reviewer 重新逐一打开全部当前 33 图并检查追加导航实现，视觉与导航结论为 SHIP。审阅者未重跑浏览器、构建或 detector。剪贴板调用与反馈通过，但读回为空，未验证字节相等。V4 的 [QA](design-review/desktop-v4/QA.md)及 `v4-*.jpg` 保留为历史。

项目仍为本地 UI 演示，正式 API、模型、文件解析、学校/学信网核验与实时岗位未接入，方向未真实自动重算。Impeccable CLI/detector 未安装，Stitch 无生成结果，Taste 仅局部参考。本轮未发布 Sites。

[后端实质核对](design-review/BACKEND-AUDIT-V5.md) 结论为主要页面能力有对应，但仍存在字段、返回结果与业务行为差异，不能认定完整对齐；视觉 SHIP 与 69/50 目录检查均不替代业务接入验收。

## 全站后续改造研究 · 2026-10-13

[全站设计审查与组件选型](design-review/component-research/全站设计审查与组件选型.md) 覆盖 16 个路由与 60 类组件、交互细节，按用户任务重新判断布局、信息层级、排版、状态和响应式。每页记录现状、方案、参考与业务条件；[请求证据](design-review/component-research/evidence.json) 保存近期版本日期及真实访问结果。该文件是后续设计方案，尚未全部实施，不能替代当前界面验收。
