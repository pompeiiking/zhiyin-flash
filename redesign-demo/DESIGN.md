---
name: 职引 · C2 河北大学陪伴式学生空间
description: 将获批 c2-hbu 交互原型落实为可操作的 Vue 学生工作空间。
colors:
  primary: "#0058a7"
  primary-hover: "#004885"
  primary-active: "#003a6b"
  primary-weak: "#eef5fc"
  primary-weak-2: "#dbeafa"
  primary-border: "#b8d5f2"
  attention: "#96000e"
  attention-weak: "#fdf7f4"
  text: "#1e232c"
  text-secondary: "#4b5157"
  text-muted: "#61666b"
  background: "#f5f6f7"
  field-top: "#fbfcfd"
  field-middle: "#f3f5f7"
  field-bottom: "#eceff2"
  surface: "rgba(255,255,255,.78)"
  surface-secondary: "rgba(250,250,251,.72)"
  surface-tertiary: "#ebedf2"
  glass-top: "rgba(255,255,255,.90)"
  glass-bottom: "rgba(255,255,255,.66)"
  border: "#e1e5ee"
  border-strong: "#cfd3d6"
  border-control: "#8f959e"
  on-primary: "#ffffff"
  dark-background: "#151517"
  dark-surface: "rgba(35,35,36,.82)"
  dark-surface-secondary: "rgba(44,44,46,.62)"
  dark-surface-tertiary: "#353638"
  dark-border-strong: "#45464a"
  dark-text: "#f9fafb"
  dark-primary: "#6fa8dc"
  dark-attention: "#d98a92"
typography:
  display:
    fontFamily: "'Microsoft YaHei UI', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', 'Segoe UI Variable Display', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "38px"
    fontWeight: 700
  headline:
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.45
  title:
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.45
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Source Han Sans SC', 'Noto Sans CJK SC', sans-serif"
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
  row: "12px"
  surface: "16px"
  companion: "20px"
  avatar-chip: "9px"
  identity-edge: "3px"
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
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    height: "44px"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    height: "44px"
    padding: "8px 16px"
  appearance-chip:
    backgroundColor: "{colors.primary-weak}"
    textColor: "{colors.primary}"
    rounded: "{rounded.pill}"
    height: "36px"
    padding: "6px 12px"
  command-search:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.pill}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
    padding: "20px"
  companion-presence:
    rounded: "{rounded.companion}"
    padding: "20px"
  avatar-chip:
    backgroundColor: "{colors.surface-tertiary}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.avatar-chip}"
---

# Design System: 职引 · C2 河北大学陪伴式学生空间

## Overview

**Creative North Star: "C2 · 陪你走完这一段"**

本文件记录 2026-10-14 已实现的学生空间。获批视觉与交互来源为 [c2-hbu/index.html](design-review/v6-redesign/directions/c2-hbu/index.html) 及其页面原型；Vue 实现仍保留原产品的数据、会话与操作链路。当前工作空间样式以最后加载的 [c2-fidelity.css](src/styles/c2-fidelity.css) 为准，位于 redesign.css 之后；基础语义、主题与密度来自 tokens.css，组件局部样式继续参与层叠。

浅灰渐变背景、半透明白色表面、宽而柔软的负扩散投影及同主色伙伴头像共同建立陪伴感。导航与控件保持清楚，来源、解释与任务状态支持实际操作。门户是独立表面，保留原行为与原版对比入口。

**Key Characteristics:**

- 蓝、红、灰白语义颜色；切主色时伙伴形象同步。
- 透明表面与柔软投影形成连续工作背景。
- 平铺功能目录、保留历史，响应式侧栏、图标栏与底栏。
- 状态与来源来自当前演示字段，比较评分明确标为合成刻度。

## Colors

frontmatter 的默认值对应浅色、蓝主、常规密度的 C2 工作空间。主题覆盖以运行时语义变量为准。

### Primary

校徽蓝承担主要操作、链接、选中状态与伙伴主体。来源记录见 [COLORS.md](design-review/v6-redesign/COLORS.md)：是官方资产实际像素值，不能表述为公开 VI 标准色定义。主色可切为河大红，深色主题使用提亮版本。

### Secondary

注意红用于风险、截止与差距；完成状态使用中性灰。红主设置保留主操作与注意区域的不同表面、文字和状态表达。

### Neutral

主文字、次要文字与注解使用三档灰；卡片与顶栏使用透明白色而非纯白板。背景从 field-top 经 field-middle 过渡至 field-bottom；最后一档来自批准原型，属于背景阴影色，不新增状态色。深色使用透明深灰表面与较亮文字。

**The 语义颜色 Rule.** 调用语义变量，状态同时提供文字、图标或可读数值；不得把演示排序当作岗位事实。

## Typography

正文采用 frontmatter 的系统中文无衬线栈，标题使用更适合显示的系统栈，无新增字体下载。注册字号仅六档；实际角色由字号、字重、位置和留白共同决定。字重使用 400、500、600、700。

| 角色 | 当前用途 |
| --- | --- |
| display | 关键数字及既有门户主张 |
| headline | 桌面主要结论、任务及统计 |
| title | 工作空间页标题与手机主要结论 |
| body | 咨询正文、输入与内容阅读 |
| control | 功能名称、控件与次要说明 |
| label | 来源、时间、计数、短注解及 C2 外观选项 |

C2 页标题使用 title，节标题多使用 body 的尺寸并加粗；页面说明为 control，行高 1.8。手机重点结论回到 title。密度不缩放注册字号。咨询沿用中文宽行距，数据比较与统计使用等宽数字。

## Layout

桌面展开侧栏宽 264px，从顶部身份条下方铺满高度；1024px 起使用完整目录。768–1023px 为 76px 图标栏，每个功能图标仍可达，历史数据保留、列表视觉隐藏。低于 768px 使用底部导航及更多目录。侧栏可整体收起。完整桌面侧栏展开时，顶栏与侧栏页脚均提供账号入口，两者打开同一账号抽屉并共享状态；手机及窄屏图标栏使用顶栏入口，整体收起侧栏时隐藏其页脚入口。

桌面头部高 64px，手机高 60px。头部提供真实命令搜索，外观栏提供主色、主题与密度三轴及全部页面命令入口。手机将外观栏排为两行，每行 36px，选项高 36px，第一行包含全部页面与主色，第二行包含主题与密度。

桌面外壳高 100dvh，主内容独立纵向滚动；没有有边框的内嵌主画布。常规页面最大宽 1200px，内距 24px，底部 64px；手机为左右 16px、顶部 20px，底部为底栏预留空间。主辅列为弹性主列与 296px 辅助列、间距 24px；低于 1280px 收为单列，咨询辅栏隐藏，报告等辅区进入正文流。画像辅区在中等宽度可排为两列，手机再收单列。

咨询是连续文档流，桌面内容上限 1074px并向主区左侧对齐；1440px视口下为706px阅读列、24px间隔与296px辅助列。手机伙伴与概览纵向排列。画像与资讯辅助内容在DOM中位于主内容之后，桌面网格保留右栏位置。输入区位于完整记录之后、参与页面滚动，回复没有覆盖式状态层。表格仅在自身容器横向滚动，方向比较表最小宽 700px。

**The 可达性 Rule.** 功能目录平铺分组，路由与图标保持可达；切外观、宽度或侧栏显隐不会丢失会话与当前操作状态。

## Elevation & Depth

C2 使用透明表面、细线、顶部内高光与大范围负扩散投影的组合。页面背景透过卡片可见，主画布不带投影。阴影数值和主题扩展存于 .impeccable/design.json，并对应 c2-fidelity.css 的 --e-1、--e-2、--e-3。

低层用于选中导航；中层用于内容表面与伙伴概览；高层用于咨询输入。阴影均有纵向偏移和柔软模糊。紧凑密度减少中层投影并将部分表面内距收至 16px。顶栏与输入区域使用有限背景模糊，不能据此给所有内容增加装饰效果。

## Shapes

顶部身份条高 3px，蓝红形成同一品牌标记；选中导航侧标使用同一细尺度及收口圆角。常用内容表面圆角 16px，内部行与重点块 12px，伙伴概览与输入区 20px。按钮、搜索和外观选项使用胶囊；账号头像片为 9px 圆角。紧凑模式覆盖部分内容表面为 12px。形态依据 C2 明确规则，不继续采用 V5 的内嵌画布或旧组件圆角默认值。

图标使用已有 Phosphor Vue 体系，伙伴是内联 SVG，不新增位图。五个主理保留轮廓与身份字段，当前主体均采用运行中的主色；学生和系统使用中性身份色。

## Components

### Buttons / Inputs

普通按钮高 44px、小档 36px，胶囊圆角、细描边与内高光。主要按钮使用实心主色。外观选项按 aria-pressed 标出选中，搜索打开真实命令面板并支持 Ctrl/Cmd + K、方向键与 Enter。全局键盘焦点使用主色轮廓，输入光标、选区与滚动条调用语义颜色。咨询输入保留 Enter 发送、Shift + Enter 换行与中文输入合成处理。

### Navigation / History

桌面功能组平铺所有链接，不再使用 V5 可折叠业务菜单。历史位于业务导航下方，显示恢复入口与真实活跃日期；会话数量、今日行动徽标与专业年级来自当前字段。手机底栏与更多目录复用同一功能体系，手机顶栏菜单打开现有导航面板，搜索保留完整入口。导航使用 aria-current，账号使用同一抽屉。

### Companion / Conversation

顶部伙伴主体使用当前主色、白眼与深灰结构色，状态由 ConversationView 的 thinking 和 streaming 字段派生 idle / thinking / speaking；组件另支持 done 一次性反馈。循环节奏按身份错开，减少动效时保留静态状态区别。不要把 SVG 外观当作新增模型能力。回复来源、复制、交接、成果及历史面板保留原行为；输入位于记录之后。

### Report / Direction Comparison

报告当前摘要放在“判断”区域内；判断选择改变对应维度的强调，诊断正文、依据与版本仍保留。方向页使用同一五项比较尺度、三方向固定合成评分：

| 比较项 | 主攻 | 平行 | 备选 |
| --- | ---: | ---: | ---: |
| 专业对口 | 90 | 74 | 84 |
| 岗位数量 | 90 | 74 | 70 |
| 起薪水平 | 78 | 86 | 58 |
| 稳定性 | 66 | 52 | 92 |
| 通勤与地点 | 70 | 60 | 88 |

权重可调 1–5、初值 3，排序分为加权平均取整；重置恢复同等权重；共享状态位于 src/lib/direction-comparison.ts，同一SPA会话中切路由或视图保留优先级。当前排序、原始分数及方向确认是不同状态。数据来自获批 directions.js 的合成刻度，不能宣称真实薪酬、岗位数量或自动诊断重算。

### Home / Plan / Review / Tools

今日下一任务显示任务来源、推荐理由、证据链接、完成状态及预计时间，并与任务操作相连。阶段计划显示四项真实派生指标，时间线可展开阶段与任务细节。复盘提供周摘要、详细与原始记录视图，完成与恢复继续同步状态。工具页以依赖时间线说明顺序，并在目录之后的可展开状态披露中展示本地契约目录；69 schema / 50 operation 不代表在线后端完成量。

### Motion / Print

状态反馈沿用已注册短时长与缓出曲线；报告判断切换为 200ms，伙伴状态保持可解释的小幅运动。减少动效偏好关闭相关循环与过渡。打印保留当前视图，隐藏导航工具，移除表面投影；旧版本记录不冒充完整旧报告。

## Do's and Don'ts

### Do:

- **Do** 以最后加载的 C2 样式及实际 Vue 组件为准，维护 token-bearing DESIGN.md 与扩展 sidecar。
- **Do** 保持六档注册字号、平铺目录、历史恢复与共享同一账号抽屉和状态。
- **Do** 用真实演示字段派生计数、任务与头像状态，明确标识固定合成比较评分。
- **Do** 以当前路由和宽度截图验证响应式与实际操作。

### Don't:

- **Don't** 将 V5 的 228px 侧栏、内嵌主画布、折叠分组或固定回复覆盖层作为当前规则。
- **Don't** 将本地演示、目录检查或合成比较描述为正式 API、模型、学校核验或实时岗位接入。
- **Don't** 用旧版截图或原型截图替代实际 Vue 页面验收。

当前浏览器检查脚本为 scripts/check-c2.mjs，覆盖实际行为及 12 路由 × 4 宽度。类型、构建、颜色对比、现有类名检查与实际行为及响应式检查通过。check-design 的几何纠正已通过：学生页面没有裁切或硬失败，仍有 /spec 的两项小按钮建议及可滚动步骤建议。check-classes 仅列入原五份全局 CSS，未包含 redesign.css 和 c2-fidelity.css，所以其通过不代表新覆盖文件的全部类名均已静态检查；不得宣称像素完全一致或21个原型视图均已逐一迁移。当前证明图位于仓库 .tmp-shots/c2-fidelity/verdict-app-{route}-{1440,390}.png 与 final-target-* 文件；仅实际生成的文件可作为证据。

V5 的历史 QA、操作记录和截图继续保留在 design-review/desktop-v5；它们记录旧版状态，不构成当前 C2 规则。后端边界仍见 PRODUCT.md 与 design-review/BACKEND-AUDIT-V5.md。当前未发布 Sites。
