---
name: 职引 · 清晰连续的个人工作空间
description: 以任务、结论和下一步为中心，深入信息就近查看的学生工作空间。
colors:
  primary: "#0058a7"
  primary-hover: "#004885"
  primary-active: "#003a6b"
  primary-weak: "#eef5fc"
  primary-weak-2: "#dbeafa"
  primary-border: "#b8d5f2"
  attention: "#96000e"
  attention-strong: "#7d000c"
  attention-weak: "#fdf7f4"
  background: "#ffffff"
  surface: "#ffffff"
  surface-secondary: "#f6f7f9"
  surface-tertiary: "#eef0f3"
  nav-background: "#f7f8fa"
  text: "#20252d"
  text-secondary: "#505967"
  text-muted: "#656d79"
  border: "#e7e9ed"
  border-strong: "#cbd0d8"
  border-control: "#8f959e"
  on-primary: "#ffffff"
  dark-background: "#191b20"
  dark-surface: "#20232a"
  dark-surface-secondary: "#242830"
  dark-surface-tertiary: "#2e333d"
  dark-nav-background: "#16181d"
  dark-float: "#252931"
  dark-text: "#edf0f5"
  dark-text-secondary: "#c2cad7"
  dark-text-muted: "#a3adbc"
  dark-border: "#343a45"
  dark-border-strong: "#515c6d"
  dark-popover-border: "#414955"
  dark-primary: "#6fa8dc"
  dark-primary-hover: "#86b6e6"
  dark-primary-active: "#b8d5f2"
  dark-primary-brand: "#5b98d2"
  dark-primary-weak: "#1d2137"
  dark-primary-weak-2: "#21284a"
  dark-primary-border: "#38406d"
  dark-on-primary: "#151517"
  dark-attention: "#d98a92"
  dark-attention-weak: "#2f1115"
  dark-attention-border: "#583d41"
  red-primary-weak-2: "#f8f0e9"
  red-primary-active: "#5f0009"
  dark-red-primary-hover: "#e8a7ad"
  dark-red-primary-active: "#f0c4c8"
  dark-red-primary-weak: "#341015"
  dark-red-primary-weak-2: "#410e14"
  dark-red-primary-border: "#67464b"
typography:
  headline:
    fontFamily: "'PingFang SC','Noto Sans CJK SC','Microsoft YaHei UI','Segoe UI',sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-.025em"
  headline-mobile:
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.4
  task-title:
    fontSize: "26px"
    lineHeight: 1.6
  task-title-mobile:
    fontSize: "22px"
  section-title:
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontSize: "16px"
  fact:
    fontSize: "15px"
    fontWeight: 500
    lineHeight: 1.65
  control:
    fontSize: "14px"
    fontWeight: 500
  detail:
    fontFamily: "'PingFang SC','Noto Sans CJK SC','Microsoft YaHei UI',sans-serif"
    fontSize: "14px"
    lineHeight: 1.75
  summary:
    fontSize: "13px"
  annotation:
    fontSize: "12px"
rounded:
  flat: "0px"
  sm: "6px"
  nav: "7px"
  md: "8px"
  summary: "10px"
  lg: "12px"
spacing:
  micro: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  content: "20px"
  section: "24px"
  heading: "28px"
  lg: "32px"
  page-top: "36px"
  columns: "40px"
  page-side: "48px"
  page-bottom: "72px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "0 16px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
  nav-active:
    backgroundColor: "{colors.primary-weak}"
    textColor: "{colors.primary}"
    rounded: "{rounded.nav}"
    padding: "8px 12px"
  detail-popover:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.detail}"
    rounded: "{rounded.lg}"
    padding: "20px"
  task-focus:
    backgroundColor: "{colors.primary-weak}"
    rounded: "{rounded.lg}"
    padding: "28px"
---

# Design System: 职引 · 清晰连续的个人工作空间

## Overview

**Creative North Star: "清晰连续的个人工作空间"**

当前前端的视觉权威是 `redesign-demo` 的运行实现与本规范。2026-10-15 用户确认全站重新设计，取消 C2 基准；以任务、结论、当前状态和下一步组织首屏，深入信息在触发位置附近查看。语言自然、中性、清楚。

这是已实现系统的记录。标准导航保持稳定，成长档案提供连续记录与就近溯源的结构启发。没有获批视觉效果图或可用 Stitch 生成屏幕；历史原型不是当前验收基准。产品事实见根 `PRODUCT.md`。

**Key Characteristics:**
- 默认信息精简，操作和关键结论优先。
- 连续内容以对齐、留白和细分隔组织。
- 蓝或红主色、灰白底与独立深色覆盖。
- 来源、短说明和筛选通过锚定浮层展开。

`src/main.ts` 仍依次加载 tokens、base、workspace、experience、journey、dialogue、redesign、c2-fidelity、refinement，最后加载 `workspace-modern.css`。最后一层与当前 Vue 结构共同定义替换后的外观；旧样式仍承担未覆盖的路由机制、控件状态和样式。不能据此宣称旧 CSS 已移除，也不能把旧 C2 卡片布局重新当成约束。

## Colors

### Primary

主色沿用现有校徽蓝；红色强调主题仍可切换。蓝、红的色值来源沿用 `tokens.css` 的已有资产取样记录，本轮未重新核验外部品牌标准。主操作、活动导航、选中状态与链接调用 `--c-primary` 系列，不复制固定蓝到组件。

红色也是需要注意的语义色。完成状态采用中性色，不新增绿色或琥珀色体系。

### Neutral

工作区用白色画布、浅灰导航和灰阶文字，表面为不透明底色。深色工作区使用 frontmatter 的 `dark-*` 色值，覆盖原 token 中的旧底色。浮层通过 Portal 挂载，拥有独立深色规则；其分隔线使用 `dark-popover-border`，不能只依赖工作区祖先继承。

### Theme mapping

默认蓝主题使用 `primary-*`；深蓝文字主色使用 `dark-primary`，品牌图形使用 `dark-primary-brand`。红主题以 `attention` 为主色、`attention-strong` 为 hover、`red-primary-active` 为 active，弱底采用 `attention-weak` 与 `red-primary-weak-2`。深红使用 `dark-attention` 和 `dark-red-primary-*`，品牌图形保留原红。深色实心按钮前景沿用 `dark-on-primary`。注意色的深色 strong 与正文注意色同值。

**The Semantic Accent Rule.** 主色表示当前入口或行动，注意色表示风险与待处理事项；在红主题中仍保留文字与结构区分状态。

## Typography

工作区采用系统中文无衬线栈，弹出详情使用对应中文栈；不下载字体。字号按实际使用登记，不再把旧七档变量误写成全站唯一尺度。

页标题使用 headline，手机使用 headline-mobile；任务强调使用 task-title 与 task-title-mobile；章节标题使用 section-title。连续正文保留 body，画像字段使用 fact，控件使用 control，概览及组标题使用 summary，时间和计数使用 annotation。浮层标题与内联概览读数为正文尺度且字重600。今日重点任务另有24px标题；继承页面仍使用20/24/38px等原档，不把它们冒充全部已统一。

数字优先等宽数字特性；不把全站正文改为等宽字体。13/15/18/22/26/30px均为当前实现中的有意层级，不能为了符合旧登记而抹掉。

## Layout

桌面侧栏宽240px，顶栏高64px。普通工作页最大宽1176px，内边距36px 48px 72px；1100px及以下横向收为32px，767px及以下为24px 20px 100px，顶栏高60px。页头标题、说明入口与操作保持同一区域；概览采用内联读数而非统计卡片。

画像主题桌面两列、手机一列。报告和资讯主体与260px侧栏在1000px及以下合并；手机方向比较改为按维度的可读列表。页签可横向滚动，活动项用底部细线表示。不同任务保留不同内容构成，不能把所有页面强行排成同一种卡片网格。

对话使用工作视口内的网格：桌面高度扣除64px、手机扣除128px；记录区域独立滚动，输入区留在网格末行。手机隐藏辅助侧栏。操作、中文输入和实际状态路径由组件保留。

## Elevation & Depth

主要内容平放在画布上，靠留白、对齐和分隔表达层级。任务重点与少量摘要使用浅色填充。浮层使用柔影 `0 12px 48px -8px #1c263033`；工作区另保留浮动表面影变量 `0 16px 48px -12px #1c26302e`。这不是所有表面都无影的承诺，继承控件与覆盖层仍有各自状态。

浮层入场为160ms、`cubic-bezier(.16,1,.3,1)`，轻微上移和缩放；减少动效偏好关闭此动画。指针停留180ms后打开，离开280ms后关闭未固定详情；点击可固定。

**The Nearby Detail Rule.** 短解释、来源和小型筛选保留触发位置上下文，长任务与编辑流程仍使用合适的原有页面或面板。

## Shapes

内容章节默认直边平放，交互控件采用轻圆角。导航与部分切换按钮使用 nav，普通按钮和说明触发器使用 md，浮层与重点任务使用 lg，摘要使用 summary；小关闭控件和部分条目使用 sm。不得将实际导航圆角随意改成统一8px。

主题的 plain/soft/dense 仍影响未被末层覆盖的间距或控件；现代工作区明确覆盖的形状和间距以末层为准，不承诺三种密度对所有元素都有同等效果。

## Components

### Buttons / Inputs

主按钮为实心语义主色，普通按钮为表面色、细描边；工作区按钮最小高42px。说明触发器最小44×44px，部分筛选按钮为36或40px；浮层关闭控件36px。不要宣称全部点击目标都为44px。全局焦点与详情触发器使用2px主色轮廓、3px偏移。搜索及字段保留真实标签、输入和空结果状态。

### Navigation / Tabs

240px桌面侧栏按现有功能分组，活动入口以浅主色底和主色文字表达，40px最小行高。历史与账号路径保留，外观设置进入账号面板。手机使用当前导航机制。页签48px最小高，活动底线2px；可见标签应保持简短。

### Continuous sections / Task focus

章节以18px标题和间距定位，记录行采用细底边；不再给每一组资料套带影卡片。重点任务用主色弱底、桌面28px内距和12px圆角；具体今日任务覆盖为24px内距，手机20px。摘要和结果必须取自现有状态，不能靠视觉重做新增成果。

### DetailPopover / OverviewMetric / PageHeading

PageHeading统一标题、就近说明与操作；OverviewMetric把统计呈现为带详情入口的内联读数。DetailPopover使用 Reka 非模态锚定弹层，宽不超过384px且两侧保留16px，最大高580px并受可用视口限制，内部可滚动；与锚点间隔8px。支持鼠标、焦点、点击固定、Esc、关闭后返回触发器；不能只靠 hover。来源及嵌套正文可换行。

### Local state and service boundaries

保留画像更正、导入导出、报告、方向、行动、日历、复盘、记录、工具、指南、账号、提醒、登录与内部页面的原功能路径。方向比较采用现有合成刻度与可调权重；排序、方向确认和原始分数是不同状态。本地偏好、预置内容、契约目录、核验预览不证明真实服务上线、授权执行或学校核验成功。用户实际消息和修改资料不应被新版预置内容覆盖。

## Do's and Don'ts

### Do:
- **Do** 用当前源码与实际路由截图核对规范，维护 token-bearing 文档及配套 sidecar。
- **Do** 首先呈现关键结论、当前状态和下一步，将短依据放在附近可操作的详情入口。
- **Do** 保留主色主题、独立深色覆盖、键盘焦点与手机内容顺序。
- **Do** 使用自然、中性、清楚的中文，以真实字段和状态派生读数。

### Don't:
- **Don't** 以历史 C2 原型、旧截图或不存在的生成稿覆盖当前全站授权。
- **Don't** 将每段内容重新包装为统计卡片或重复解释栏。
- **Don't** 将本地演示、合成比较或契约数量描述为在线服务成功。
- **Don't** 将有限截图与行为检查等同于完整 WCAG、性能或真实后端验收。
