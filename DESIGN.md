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

---

# 历史模板设计记录（保留，不适用于当前 redesign-demo）

以下为本仓库早期 `zhiyin-src/template/zhiyin-web` 的七轴系统说明，仅供仍维护该模板时参考。它不约束当前 `redesign-demo`，不代表现代工作区仍使用草稿纸、手写字体或3888种组合。当前前端视觉以本文件上半部、`redesign-demo/DESIGN.md` 与末层 `workspace-modern.css` 为准；产品事实以根 `PRODUCT.md` 为准。历史正文及模板验收命令按原样保留。
# 职引 · 视觉设计

本文件只放**视觉与前端外观**的口径：七条轴、世界、令牌、零件、怎么加。
产品与业务口径不在这里 —— 那唯一一份在 [`docs/职引-完整设计文档.md`](docs/职引-完整设计文档.md)。
两份文件各管一头，不要互相抄：一处改了另一处没改，读的人就会照错的那份去改代码。

---

## 一、七条轴：一台可以由用户自己配的调配台

外观不是一个开关，是**七条互不相干的轴**。每条轴一个 `data-<轴>` 属性、一个 CSS 目录、
一段注册表；每条轴的默认档都**没有文件**（默认值就是 `tokens.css` 与 `base.css` 里今天的样子），
所以"不切"与改动前逐字一致，回退只有一条路：删掉属性。

| 轴 | 属性 | 管什么 | 选项 | 允许声明 |
| --- | --- | --- | --- | --- |
| **配色** `theme` | `data-theme` | 色、材质、质感、光标、动效节奏 | 4 | 61 条颜色与材质令牌（契约） |
| **组件** `ui` | `data-ui` | 形（圆角/描边/影）、密度（间距/字号/行高/画布缝） | 6 | 43 条形/密度/字令牌 |
| **交互** `feedback` | `data-feedback` | 反馈落在哪一层：位移、描边，还是底色 | 3 | **一个都不许**（纯规则） |
| **排版** `type` | `data-type` | 章节编号、行宽、对齐、段距 | 3 | 一个都不许 |
| **形状** `shape` | `data-shape` | 角的写法：手绘（四角长短不一） | 2 | 一个都不许 |
| **骨架** `skeleton` | `data-skeleton` | 覆盖层怎么打开：居中、抽屉、全幅 | 3 | 一个都不许 |
| **字体** `font` | `data-font` | 字族与字形：手写 / 精修 / 衬线 | 3 | 只 `--font-*`（8 条） |

组合数：4 × 6 × 3 × 3 × 2 × 3 × 3 = **3888 种**，用户自己搭。

**逐条轴只许声明自己那一类令牌，是这七条轴不互相顶掉的唯一机制**：
配色写色、组件写形/密度/字、其余四条只写规则。越界的后果不是"难看"，而是两条轴开始抢同一个
变量 —— 症状永远是"某一处没跟着变"，而且没有任何报错。守卫逐档钉着这条。

**顺序就是胜负**：七条轴的特异度全是 (0,1,1)，冲突时谁后加载谁赢。
`base.css` 里的顺序是 配色 → 组件 → 交互 → 排版 → 形状 → 骨架 → **字体**；
`tests/test_theme_contract.py` 会比对 `base.css` 与这张表，顺序改错会被拦下。

## 二、轴一 · 配色：四个世界

默认世界是**草稿台**：暖草稿纸、记号笔绿、站酷快乐体手写字、手绘光标。
另外三套不是它的明暗变体，而是**三个完整世界**：各有材料、字体、形状、质感、动效节奏与光标。

| id | 名字 | 世界 | 一句话 | 亮/暗 |
| --- | --- | --- | --- | --- |
| `sketch` | 草稿台 | 疯狂艺术家的草稿台 | 暖纸、记号笔绿、手写字（默认，值在 `tokens.css` 的 `:root`） | 亮 |
| `exam` | 阅卷 | 试卷与答题卡 | 冷白试卷纸、印刷黑、**一支阅卷红**、硬框、直角、**零阴影** | 亮 |
| `darkroom` | 暗房 | 安全灯下的显影 | 近黑相纸、琥珀显影液、0.26 胶片颗粒、Fraunces 数字 | 暗 |
| `transit` | 线路图 | 城市轨道导视 | 站牌黑、**信号绿本线色**、大写等宽标签、站点圆环、无底纹 | 暗 |

每个世界都回答产品里的一件事：**阅卷**对应"诊断与判分"（把握度、差距、短板本来就是被批改
出来的，所以它的结构是线与规则，`--e-*` 全部置空）；**暗房**对应"画像不是填出来的，是显影
出来的"（红光晕 + 重颗粒，动效慢一档）；**线路图**对应"求职是一步一步走出来的"（本线色横带 +
站点标记 + 大写加字距的导视字）。

## 三、轴二 · 组件：七种形与密度

| id | 名字 | 形 | 密度 |
| --- | --- | --- | --- |
| `card` | 卡片 | 细边 + 柔影 + 中圆角（默认，无文件） | 默认 |
| `float` | 浮片 | 无边框、大圆角、重而柔的影；控件全药丸；薄片顶部一道高光 | 默认 |
| `sticker` | 贴纸 | 2px 墨色粗边 + 偏右下的柔影（带偏移与模糊）；按下时下沉一小步、影收紧 | 默认 |
| `plain` | 极简 | 无框无影，靠内嵌底色（`--n-3`）与留白分层 | 默认 |
| `dense` | 紧凑 | 圆角收小、影极浅 | **收紧**（间距与字号各收一档、行高 1.55、画布缝 12→8px） |
| `roomy` | 舒展 | 圆角放大、影更深更远、按钮与标签片放宽 | **放大**（间距 ×1.25、字号上浮、行高 1.8、画布缝 12→20px） |

**2026-10-08 砍掉三处"同一件事的两种说法"**（依据：像素审计每一档都有变化，所以砍的是**重复**）：
「表格」（`ledger`）与「档案」（`archive`）都是"印刷件"语言 —— 留了特征更多的档案，但随后
**档案也砍了**：它的辨识度全靠 `0 Npx 0` 那条**零模糊硬边影**，而设计底线把这种影点名为"戏服"
（新粗野主义那一套世界的语法），而这套界面是手绘草稿台。同一天还砍掉了「票根」（把卡片当票据）
与组件轴里的「等宽」（字族归字体轴）。

**密度是怎么真的生效的（一条纠正）**：`密集/舒展` 原先只改 `--s*`，而控制台的卡片外框由
`.canvas` 那张 12 列网格决定 —— `--s*` 全被吃掉，实测"同屏块数、卡外框一个像素没动"。
现在给画布加了一条 `--canvas-gap`（默认 12px = 今天的样子），紧凑 8px、舒展 20px，
**卡间距与卡内距一起收/放**，密度才看得见。
**一条做不到的事，写在这里**：每屏**块数**（9 块变 12 块）改不了 ——
块数由后端 `layout.json` 放了几块决定，`tiling.ts` 只负责把那几块铺满整屏，
所以"一屏多看几条"在 CSS 层的承诺是"每条里更紧、缝更小"，不是"多出几块"。

八种风格都**不碰颜色**：粗边取 `var(--ink-1)`（暗色配色下自动翻成亮边），影取黑，
硬边取 `var(--line-2)`。所以任意配色 × 任意组件都成立，不会串色。

## 四、轴三 · 交互：反馈落在哪一层

默认 `rise`（抬升：悬停抬 1px、按下压回、焦点 2px 实线环）没有文件。另外两档：

- `edge` **描边**：块一律不动，只有线与字的深浅在变；焦点用"双环"；选中改用描边 + 极淡底。
  文字入口（`.foot__cta` / `.foot__why`）的"线"是下划线 —— 悬停时长出一条线来。
- `fill` **填色**：线一律不动，只有底色在变；焦点用**底边线**；选中用**左侧 3px 竖条**。

**覆盖的控件清单是截图核对出来的**：画布上**没有 `.btn`** —— 那里的入口是 `.ask`（块里那颗
"开始对话"）、`.foot__cta` / `.foot__why`（块脚两个文字入口）、`.rail__bar`（右侧主理栏）、
`.bubble__close` / `.bubble__done`（角上两颗）。只写 `.btn` / `.chip` / `.row` 的话，
用户在控制台切这一轴会看到"什么都没变"（2026-10-08 就是这个问题）。

这一层是纯规则（一个变量都不声明），靠"排在 base.css 之后 + 前缀选择器"压过写死的反馈。
已知两处压不过的地方（写明在文件注释里）：覆盖层输入框的 scoped 焦点规则、以及
`PortraitFieldList` 行自己的 1px 上抬 —— 它们的选择器比这一层更具体。

## 五、轴四 · 排版：同一堆内容，怎么读

默认 `plain`（常规）没有文件。另外两档：

- `outline` **章节体**：报告正文（`main.doc`）的二级标题前加 `01 / 02` 编号（纯 CSS 计数器，
  不进 DOM、不进朗读顺序），标题上方一条分节线，段落限宽 64ch，小标签改为栏目名的排法。
  作用范围**只到报告正文那一栏** —— 覆盖层标题与控制台气泡里也有 `h2`，编号只对"一页长文档"有意义。
- `read` **阅读体**：行宽 68ch、行高 1.85、正文与说明各上浮半档、页首大标题与覆盖层标题居中、
  来源小字抬到 12.5px。

## 六、轴五 · 形状：角的种类

默认 `box`（直角，照旧）没有文件。另一档是 `hand` **手绘**：四角的圆角长短不一，像用笔框出来的。

**这一档画的是纸与笔真的会发生的事**：手画的框不是一个正圆角 —— 笔在四个角上收笔的力度不一样。
这正是 `tokens.css` 里那组 `--r-sketch-*` 令牌**本来想表达**、却从未真的抖过的意思
（项目自己的设计注释写着"不规整：圆角每个角不一样长（手抖框）"）。
四角按两套令牌拉开量级（约 1.7×`--r-lg` 与 0.5×`--r-xs` 之间摆动），卡片内侧再压一道 1px 的
**重描**线（手画一个框，收笔处常与起笔重叠一下 —— 与主按钮下那道双下划线同一个道理）。

**差量必须够大，否则等于没做**：第一版用 `--r-sketch-lg/--r-sm/--r-sketch-md/--r-xs` 混（16/8/12/6），
像素审计只有 **0.20%** —— 阈值以下（"看不出变化"）。拉开量级后是 **1.82%**，一眼可辨，
而且仍然跟着每套组件风格走（贴纸那套圆角小，手绘就收着抖）。

**前一版的两档都删了，原因不是"没效果"而是做法错**（用户三次反馈"太丑了"）：

- **「票根」**（上下缘打一排齿孔 + 中缝虚线）把卡片当成票据，而这套界面里的卡片是"一页写满字的稿纸"；
  孔的间距一旦与块宽对不齐（340px 的卡剩半个孔）就显得毛糙。
- **「折角」**（右上角折起来）与 **「斜切」**（对角两刀）都是"几何遮罩冒充有机形态" ——
  设计底线（`craft-floor.md` 的 Refuse 一节）点名这一手法"读起来比不做还差"：
  折角与剪口在真实纸张上是有机的不规则边缘，而 polygon 画出来的是干净的几何形。
  切角还叠了第二个错：四角各 8px 的切角压在 16px 的圆角上，两种"角"在同一张卡上打架。

## 七、轴六 · 骨架：覆盖层怎么打开

默认 `center`（居中弹出）没有文件。另外两档：

- `drawer` **抽屉**：从右侧推进来，通高一条（默认档 900px、`--mid` 760px），开页签的色带从左边挪到顶部，
  入场动画带前缀（`look-drawer-in`）。
- `full` **全幅**：铺满整屏，开页签变成整页的页眉，内容区仍居中一栏（`min(1180px, 100%)`）。

**三处硬要求（都是"难看"换来的，2026-10-08）**：

1. **宽度不能只图"窄"**：覆盖层里的内容（画像那一类）按 760–900px 排，压到 560px 会让两栏网格
   横向溢出 —— 用户看到的是"打开就乱了"。
2. **`.layer` 只改 `padding`，不改 `place-items`**：改成 `stretch` 会把自带壳的覆盖层
   （`.pt` 那一类）一起拉变形。铺满/贴右交给 `.deck` 自己的 `justify-self` / `align-self`。
3. **面板必须自己有材质**：第一版只有里面的 `.deck__bar` 是 `.sheet`，`.deck` 没有底 ——
   于是**页面从面板中间透出来**，抽屉像"贴上去的一层玻璃"。现在两份都自己给底
   （`background: var(--c-paper)`）：抽屉是一整块带左侧分隔影与内侧圆角的抽屉板，
   全幅是**不透明的一整页**（页眉一条底线、正文居中一栏）；`.deck__bar` 相应的底色/影/圆角全部撤掉，
   否则面板里会再套一张纸（两层纸 = 两块边界 = 看着脏）。

这一层不去动组件：`Overlay.vue` 的样式是作用域内的 `.deck[data-v-…]`（0,2,0），
这里写的是 `html[data-skeleton="…"] .deck`（0,2,1），能压过它。

## 八、轴七 · 字体：手写 ↔ 精修 ↔ 衬线

默认 `hand`（手写）没有文件：标题站酷快乐体、正文 MiSans、数字 Fraunces，就是今天的样子。
另外两档只改 `--font-*` 令牌，不动字号、字重与间距（那些归组件轴）：

- `clean` **精修**：标题改用正文字体（`--font-display: var(--font-sans)`）+ 标题字距 −0.012em。
  手写味来自"标题是另一支笔写的"，这一档把那支笔收掉；
- `serif` **衬线**：标题与数字走 **Fraunces**（包里的拉丁衬线）+ 中文走系统字体栈
  `--font-cjk-serif`（Windows 宋体 / macOS Songti SC / Linux 思源宋体）。
  **不下载中文衬线字体**：那类字体动辄十几 MB，为一个可选档下载它，是拿所有人的首屏换一个开关。
  （已知欠账：Windows 上中文落宋体，22px 的合成加粗会发虚 —— 评审点过这一条，
  真要修得做汉字子集，那是一次单独的取舍。）

**三条轴不再重叠**（2026-10-08 的精简）：字体只归这一条轴，组件轴只管形、密度与字号。
原来组件轴的 `roomy` 偷偷声明 Fraunces、`mono` 声明三处等宽栈，于是"组件"那一栏也在动字体，
用户看到"组件:等宽 / 字体:衬线"两栏会不知道谁说了算（而且字体轴不是默认档时那几行就是死代码）。
同一天砍掉的两档：**`noto`（思源）** —— 与 `clean` 是同一件事的两种说法，差的是多数人叫不出
名字的字形差别；**`mono`（等宽）** —— 设计底线把"全站等宽"点名为"技术感的戏服"
（等宽该给代码、数据与度量：这件事由 `.mono` 这个零件承担，不该是一条全局字体档）。

**撤掉的那条轴**：曾经有第八条"线条"轴（`data-draw`，改 roughjs 的抖动系数，手绘 ↔ 精确）。
2026-10-08 撤掉 —— 它的效果只出现在门户地图（与报告里的趋势线）上，在控制台那屏点它毫无变化，
用户会合理地判定"这条轴是坏的"。一处乘法零成本，能力留着（`lib/sketch.ts` 的
`setRoughnessScale` / `bumpSketch`、`tokens.css` 的 `--sketch-rough`），只是暂时没有开关。

## 九、令牌是三层，组件只认第二、三层

`src/styles/tokens.css` 里三层，只有第一层出现字面值：

1. **原始值**（`--c-paper`、`--g-100`、`--mk-green`…）：一个值只写一次；
2. **语义别名**（`--n-1` ← `--c-paper`、`--accent` ← `--g-100`、`--warn` ← `--o-80`…）；
3. **具体物件**（`--card-border`、`--glass-solid-*`、`--chart-area`、`--cursor-*`、`--sketch-rough`…）。

组件里不写颜色字面量，也不写死尺寸 —— 除"各条轴的目录"外，样式里出现 `#hex` / `rgb()` 即失败
（掩码用的黑白除外；非配色轴里唯一允许写死的颜色是影的黑白）。

**契约一览**：配色 61 条（表面 3、文字 4、描边 4、填充 3、强调 6、语义 3、彩铅笔 7 对、
玻璃 4、投影 6、底料 3、遮罩 1、图表 2、手绘辅线 5、光标 3）；组件 43 条（形 15、密度 10、字 18）；
交互/排版/形状/骨架 0 条；字体 8 条（`--font-*`）。排版、间距、层级的默认值在 `tokens.css`，
换外观不该动"层级"（`--z-*`）。

## 十、零件（七条轴共用的一批）

| 零件 | 在哪 | 作用 |
| --- | --- | --- |
| `.surface` | `base.css` | **一张卡片**（画布块、通知浮窗、导览便签、画像卷宗都挂它）：`--card-border` + `--e-2` + 圆角。各卡片自己的样式优先级更高，所以挂上它不改默认外观，只让各条轴能接管它们 |
| `.sheet` | `base.css` | 覆盖层那张更大的纸：`--c-paper` + `--e-4` + `--r-lg` |
| `.btn` / `.btn.primary` | `base.css` | 唯一按钮形状；主按钮吃 `--accent` 与 `--accent-shadow` |
| `.chip` | `base.css` | 状态标签：`.live` / `.risk` / `.fact` |
| `.label` / `.mono` / `.editorial` | `base.css` | 中文小标签 / 等宽数据 / 大字编辑体 |
| `.layer` / `.deck` / `.deck__bar` | `Overlay.vue` | 覆盖层那个壳 —— 骨架轴改的就是它 |
| `.bubble` / `.float` / `.note` / `.pt` | 各组件 | 四类卡片本体（画布块 / 通知浮窗 / 导览便签 / 画像卷宗），都同时挂 `.surface` |

**零件必须是"真的挂得上"的名字**：一条规则写了 `.surface { … }` 而模板里从来没有
`class="surface"`，那条规则就永远不生效 —— 样式表照常加载、构建照常通过、面板照常高亮，
只有界面不动。2026-10-08 就踩了这一个坑（`.surface` 与 `.float-card` 都是幽灵零件，
四条轴的卡片规则全是死的），现在由 `test_axis_selectors_name_parts_that_exist` 逐档拦着。

**外观台**（`components/theme/LookPanel.vue` + `LookTrigger.vue`）是这套系统的唯一入口：
三处「外观台」三个字 —— 控制台左上角账号那颗的右边、报告页顶栏左栏、门户页右上角；
点开是一张**矩阵**：一行一条轴、一列一个档，当前档整格点亮，改过的那一行带 ↺ 单独退回，
底部写着"改了几条轴"、可复制这份搭配，另有「随机一套」与「重置为默认」。
面板不做成模态 —— 身后那块界面就是实时预览。账号面板只管身份，不再放外观行：
一个动作一处入口。

**矩阵按用途分四段**（颜色 / 形与密度 / 字号字体 / 交互与浮层）。七行并排铺开时，
用户第一眼看到的是"七个并列的选择"，而它们其实是四件不同的事 —— 评审的原话是
"用户挑不过来"。分组**不改任何能力**，只把"一次要读几行"降下来。
分组写在注册表里（`lib/theme.ts` 的 `AXIS_GROUPS`）而不是面板里：它是轴自己的属性，
换一个入口也该按同一套分段；守卫 `test_axis_groups_cover_every_axis_in_order`
钉住"每条轴恰好出现一次、组内次序跟随 AXES"（少列一条，那一行会从外观台上整条消失，
而样式表照常加载、构建照常通过 —— 这类错只能靠守卫）。

## 十一、四条全域口径

1. **对比度是硬线**：正文与"真的当文字用"的令牌对纸面 ≥4.5:1，说明文字（`--ink-3`）不破 4.5，
   主按钮字色对强调色 ≥4.5。`--warn` 与 `--mk-yellow` 按现状取 4.4（默认配色自己是 4.42 / 4.46）。
2. **结构靠线，层次靠影**：浅色世界用 `--e-*` 让块浮起来；阅卷世界与"表格"组件一律不投影。
3. **暗色不是反相**：颗粒 `multiply` 要换 `screen` 或 `overlay`；描边要换成"纸的低透明度"；
   影子要更黑；`--inner-hi` 可以回来一点受光；光标三支要整套重给（颜色烤在 data URI 里）。
4. **动效是配色轴的性格**：`--mo-*` 属于配色轴。阅卷果断（110/200ms）、线路图准点（120/220ms）、
   暗房慢一档（180/320ms）。其它轴不动动效。

## 十二、怎么加（缺一步会被守卫挡住）

**给某条轴加一档**：
1. 在 `src/styles/<轴>/` 加一个 `<档>.css`：只写一个 `html[data-<轴>="<档>"]` 根块（要声明令牌的轴）
   或纯规则（不声明令牌的轴），规则一律用该属性作前缀；
2. `src/styles/<轴>/index.css` 加一行 `@import`；
3. `src/lib/theme.ts` 的 `AXES` 里给那条轴加一项（`id` / `name` / `note`，配色轴另有 `swatch` / `dark`）；
4. 若新档要在外观台上显出差异，在 `LookPanel.vue` 的 `GLYPHS` 里补一条小图路径
   （配色用色卡、组件用 CSS 画的形，其余五条轴走路径表）。

**加一条新轴**：除上面四步，还要 `AXIS_DIRS` / `AXIS_IMPORT_ORDER`（守卫）、`base.css` 里加 `@import`、
`index.html` 首屏那张 `AX` 表加一项、`AXIS_DECLARATIONS` 里声明它的令牌预算。

守卫会检查：七条轴的 注册表 ↔ 文件 ↔ `@import` ↔ 首屏表 ↔ 加载顺序 五处对齐、配色契约无漏、
令牌名不拼错、值没写坏、每档配色的对比度、每条规则都挂在自己的属性下、
非配色轴不越界声明令牌、除影的黑白外不写颜色字面量。文件名与选择器里的档名必须相同 ——
不一致时菜单点得动但页面纹丝不动，正是这些守卫存在的理由。

## 十三、验收口径

- `cd zhiyin-src/template && .venv\Scripts\python.exe -m pytest tests/test_theme_contract.py -q`
- `cd zhiyin-src/template/zhiyin-web && npm run typecheck && npm run build`
- 浏览器里逐屏过：门户 / 控制台画布 / 覆盖层 / 报告页 / 登录层，图表（ECharts 雷达条形、课表、
  趋势线）与门户地图。至少过这几组搭配：默认（草稿台+卡片+抬升+常规+直角+居中+手写）、
  阅卷+表格+填色、暗房+浮片+阅读体+字体=衬线、线路图+等宽+章节体+抽屉。
- 切换入口：三处「外观台」三个字（控制台左上角账号右侧 / 报告页顶栏 / 门户页右上角），
  打开矩阵面板点格子；或 `?theme=<档>&ui=<档>&feedback=<档>&type=<档>&shape=<档>&skeleton=<档>&font=<档>`。
