---
name: 职引 · 学生产品工作空间
description: 精确、安静、紧凑的中文学生工作空间，以真实任务与证据组织各页。
colors:
  primary: "#2563eb"
  primary-weak: "#eff5ff"
  primary-weak-2: "#dbe8ff"
  primary-border: "#b9d0ff"
  background: "#f7f8fa"
  surface: "#ffffff"
  surface-secondary: "#f6f7f9"
  surface-tertiary: "#eef0f3"
  text: "#20252d"
  text-secondary: "#505967"
  text-muted: "#656d79"
  border: "#e7e9ed"
  border-strong: "#cbd0d8"
  attention: "#96000e"
  attention-strong: "#7d000c"
  on-primary: "#ffffff"
  dark-background: "#181a20"
  dark-nav: "#1e2128"
  dark-surface: "#20232a"
  dark-surface-secondary: "#242830"
  dark-surface-tertiary: "#2e333d"
  dark-text: "#edf0f5"
  dark-text-secondary: "#c2cad7"
  dark-text-muted: "#a3adbc"
  dark-border: "#343a45"
  dark-border-strong: "#515c6d"
  dark-float: "#252931"
typography:
  headline:
    fontFamily: "'Segoe UI','Microsoft YaHei','PingFang SC','Noto Sans CJK SC',sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-.02em"
  headline-mobile:
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.4
  section-title:
    fontSize: "16px"
    fontWeight: 600
  body:
    fontFamily: "'Segoe UI','Microsoft YaHei','PingFang SC','Noto Sans CJK SC',sans-serif"
    fontSize: "14px"
    lineHeight: 1.6
  control:
    fontSize: "13px"
    fontWeight: 500
  detail:
    fontFamily: "'PingFang SC','Noto Sans CJK SC','Microsoft YaHei UI',sans-serif"
    fontSize: "14px"
    lineHeight: 1.75
  annotation:
    fontSize: "12px"
  metadata:
    fontSize: "11px"
rounded:
  flat: "0px"
  sm: "6px"
  nav: "7px"
  control: "8px"
  summary: "10px"
  surface: "12px"
spacing:
  micro: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  content: "20px"
  section: "24px"
  page-side: "32px"
  page-bottom: "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  nav-active:
    backgroundColor: "{colors.primary-weak}"
    textColor: "{colors.primary}"
    rounded: "{rounded.nav}"
    padding: "7px 10px"
  input-search:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  detail-popover:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.detail}"
    rounded: "{rounded.surface}"
    padding: "20px"
  workspace-surface:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
    padding: "20px"
---

# Design System: 职引 · 学生产品工作空间

## Overview

**Creative North Star: "精确、安静、紧凑的学生工作空间"**

当前视觉权威为运行实现、本文及 `design-review/navigation-rethink/BRIEF.md` 最后的2026-10-15完整产品重构契约。用户已撤销C2复刻要求，并授权整个学生端独立重构。参考截图和GenieLink仅解释品质期待，不规定构图，也不将范围缩为两个页面。根PRODUCT.md承载产品事实。

信息以学生正在处理的任务为单位：比较展示差别，报告展示当前值和门槛，计划展示阶段与真实进度，日历展示日期与完整日程，记录展示可操作条目。共享的是尺度与控件，不是每页相同的大卡片。语言自然、中性、清楚。最新参考站Finsight的逐界面实地检查仍在进行，本规范不宣称它已完成。

**Key Characteristics:**
- 浅灰工作底、白色任务表面、克制蓝色行动强调。
- 分类导航与紧凑工具栏稳定，主体结构随任务变化。
- 当前状态、真实名称、主要操作优先，短依据附近查看。
- 四个获批机器人造型与独立采集变体承担实际身份和处理状态。

`src/main.ts` 仍加载旧样式；最终加载的 `workspace-modern.css` 中“Product workspace”起及其后续修正规则定义当前替换系统。前半段240px侧栏、64px顶栏、30px标题是被覆盖的旧值，不能抽取为当前标准。根文档另保留历史模板说明。

## Colors

### Primary

行动蓝用于主操作、当前导航、已选方向、真实进度和可操作链接。浅蓝用于选择与少量语义强调。复用语义变量；不能把图表全部染蓝当作完成设计。

### Secondary

注意红沿用现有风险/待处理语义，不作为装饰性第二主色。完成与未完成同时使用文字和形态表达。

### Neutral

浅灰工作底托住不透明白色表面；细灰边界分隔内容、字段和日历。正文、次正文、元信息各用对应灰阶。深色覆盖包含独立背景、侧栏、表面和文字；Portal浮层有自己的深色覆盖。

**The Meaningful Accent Rule.** 主色必须对应当前状态、可执行动作或有尺度的真实数据。

当前末层固定了工作区主色系列，因此旧红/蓝偏好并不保证所有工作区主色切换；旧hover/active变量与偏好设置仍存在。此处记录实际覆盖关系，不把主题间不一致当作新的主题规则，也不宣称全主题重建已验收。

## Typography

界面使用frontmatter中的系统无衬线栈；当前Windows浏览器实际解析中文为Microsoft YaHei。正文和表单共享字体，详情浮层保留独立中文栈。不下载展示字体，不将系统界面字体提升为装饰性展示字体。

页标题使用headline，手机使用headline-mobile；共享章节标题使用section-title。任务名、字段值、正文以body为主；导航、操作、紧凑说明使用control；时间、注解用annotation，类别与少量元信息用metadata。阅读器标题、报告结论、方向分数各保留服务内容的独立层级，不将这些局部字号扩张成全站标题。

**The Working Text Rule.** 真实名称和操作使用清晰可读的工作字号；元信息降级不能取代正文，进度必须保留数值含义。

## Layout

桌面分类侧栏216px，顶栏56px。普通页最大宽1440px，内边距24px 32px 48px；1100px及以下变为20px 24px 48px；767px及以下变为20px 16px 92px。页标题桌面24px、手机22px。分类结构保留，允许调整类下菜单；不恢复撤回的五入口与页头组内导航。

画像使用身份区与对齐字段，桌面两列字段、手机单列。方向桌面三项并排，手机逐项完整阅读。报告用当前值/门槛刻度及语义发现列表。资讯桌面结果列表配阅读面，900px及以下进入单列阅读路径。日历使用完整主区宽度，日议程在旁、手机置下。今日任务和阶段计划保留任务名称、动作、阶段目标及实际完成比例；不使用无名方格作为主体。

常规主辅列使用272px辅助列和24px间隔，1100px及以下折为单列；资讯、日历和复盘有各自适用的折叠规则。成长记录以里程碑及证据组织。记录页保留紧凑新增区、本页计数、搜索及分页结果，空分组省略。复盘原因表单先于历史证据。

对话占工作视口，记录独立滚动，输入区保留在末行；桌面减去56px顶栏，手机视口扣除120px，900px及以下隐藏辅助栏。移动布局要核对实际使用状态，不能只验证空闲首屏。

## Elevation & Depth

表面以浅灰底、白色填充与细边界区分，默认没有环境投影；字段、清单与连续记录用对齐和细分隔组织。被选方向保留1px主色外描影。详情浮层使用 `0 12px 48px -8px #1c263033`；浮动表面变量仍为 `0 16px 48px -12px #1c26302e`，并非所有内容的默认影。

浮层160ms进入，曲线为 `cubic-bezier(.16,1,.3,1)`；减少动效偏好停用进入动画。机器人动作与实际状态关联，减少动效偏好停用部件动画。

**The Nearby Detail Rule.** 短解释、来源与小型选择保留触发上下文；长报告和文章使用独立阅读安排。

## Shapes

普通控件轻圆角，导航使用nav，按钮与搜索用control，主要白色任务表面与浮层用surface。连续字段和条目可保持直边；不是所有内容都需要表面，也不要求所有内容去卡片。小圆角、轨道和圆形状态点按内容语义使用。

## Components

### Buttons / Inputs

桌面普通按钮最小高36px、手机40px；工作文字13px。主按钮实心蓝配白字，次按钮白底细边；搜索使用真实标签、输入值与空结果。控件保留hover和2px主色键盘焦点；详情触发器焦点偏移3px。手机任务勾选和记录切换为44px，部分说明与小动作仍小于44px，不宣称全站触点统一达标。

### Navigation / PageHeading

分类侧栏保持简短入口与历史会话；普通导航最小36px，活动项浅蓝底和蓝字，圆角7px。PageHeading复用标题、说明与操作结构，不强加一套页内菜单。移动保留当前底栏/导航机制与返回路径。

### Task surfaces / Comparison / Progress

白色表面集中承载一个任务，内距通常18–22px。方向同时展示分项差别、风险和确认操作，排序与方向确认不是同一状态。报告刻度分别标记当前数值和门槛。TaskProgressMap与阶段路径保留名称、时间、目标和实际完成数量；计划目标百分比不能冒充完成百分比。完成/恢复任务引发的页面反馈应来自真实状态。

### DetailPopover / Reading

非模态锚定浮层宽不超过384px、两侧保留16px，最大高580px且受可用视口限制；内距20px，与锚点相隔8px。鼠标180ms打开、离开280ms关闭未固定内容；焦点打开、点击固定、Esc关闭、关闭后焦点返回。原生dialog内的浮层挂在所属dialog中以维持交互。长文本可换行、内部可滚动。完整打印使用打印专用正文，不依赖用户逐个打开浮层。

IntelArticle提供正文、来源和行动检查；移动结果与阅读有明确往返路径。查找和分页计数必须说明作用范围。

### RobotAvatar / AchievementsSection

复用四个获批SVG：职业分析、行动规划、行动支持、就业资讯；第五信息采集身份使用独立变体，自己与系统使用中性图标。每个实例的SVG paint server ID独立。待命眨眼、思考眼睛/天线、实际回复口部/声条、真实完成单次点头；停止或失败不能产生完成点头。减少动效停用动画。

成长记录以实际里程碑与可追溯证据呈现；不把系统说明或预置计数伪装为学生已取得的成果。本地状态、契约目录与预览不证明真实服务已上线。

## Do's and Don'ts

### Do:
- **Do** 用最终覆盖源码、实际字体与真实变更状态核对全站，而非只看初始截图。
- **Do** 让比较、阅读、日历、任务和记录使用适合各自用途的主体结构。
- **Do** 保留分类导航、键盘焦点、手机阅读顺序与真实状态反馈。
- **Do** 使用自然中性中文，显示真实任务名称、阶段目标和实际完成情况。

### Don't:
- **Don't** 将C2历史、两张参考截图或不可用生成稿当成当前构图约束。
- **Don't** 将无名矩阵、重复大卡片或整页文章式说明作为通用解决方案。
- **Don't** 将服务契约、本地演示、合成刻度或停止响应说成在线成功或完成。
- **Don't** 将有限截图、专项检查或七项修复复核等同于全站品质终审或完整WCAG认证。


## 2026-10-16 用户确认版本与旧门户恢复

本轮确认保留 index.html 对应的学生端（侧栏“做决定”下含“方向方案”和“岗位资讯”），发布分支为 frontend-student-portal。后续 workspace.html、proposals.html、studies.html 等试验稿不属于该发布版本。

旧门户入口为 /#/?portal=classic。动态背景从历史提交 60d4e4f 的 PortalClassicView.vue 恢复：两片漂移光晕、呼吸网格、扫光与三个沿路线移动的节点。保留现有门户切换、登录/进入咨询逻辑、布局及窄屏适配。减少动态效果偏好下停止动画、移除移动节点，同时保留静态背景。

验证：Vue 类型检查与 Vite 生产构建通过；浏览器确认四项 CSS 背景动画运行、三节点在前后采样中位置变化；已登录状态下门户主按钮进入 /chat，1280 宽视口无页面横向溢出。未声称本轮重新验证在线后端或未登录认证流程。

旧远端新前端分支清理前保存为 archive/frontend-20261016-1 至 archive/frontend-20261016-4 标签，对应原新前端、新前端2、新前端3、新前端4。
