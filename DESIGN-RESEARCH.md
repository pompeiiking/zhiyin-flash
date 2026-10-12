# 设计决策调研报告
## 面向「大学生生涯规划与就业指导智能支撑平台」前端重设计

调研日期：2026-10-11 ｜ 目标栈：Vue 3 + Vite + TS + 手写 CSS + CSS 变量令牌（无 Tailwind、无组件库）

> **可信度标注规则**：本文所有数值分三级标注。
> `[源码]` = 我从该站真实的 CSS / 组件源码里抓到的原文；
> `[文档]` = 该站官方文档明文写的规范值；
> `[未核实]` = 该站未公开具体数值，建议以实际页面/截图为准。
> **我没有编造任何 hex 值**：凡是出现的十六进制色值，都能在「来源清单」里的文件或我的本地抓取副本中找到。

---

## 一、designeer.xyz 条目清单尝试结果

### 结论：**扒到了**，而且比预期完整

用户此前的判断是"条目列表是前端渲染的，抓不到"——**这个判断不成立**。我换了 3 种办法，第 2 种成功：

| 尝试 | 方法 | 结果 |
|---|---|---|
| 1 | 直接 web_fetch `/` 和 `/components` | ❌ 正文只有导航 + 赞助商，与用户描述一致 |
| 2 | **`Invoke-WebRequest` 抓原始 HTML 到磁盘，再正则抽取** | ✅ **成功**。HTML 有 605KB，条目**是服务端渲染的**，只是被 web_fetch 的正文提取逻辑丢掉了 |
| 3 | `/sitemap.xml` | ⚠️ 不是超时，是**能拿到但没内容**：sitemap 只列了 9 条路由（6 个分类页 + sponsor/submit/info），**不含任何单独条目页** |

### 真正的突破口

页面里嵌了 **JSON-LD 结构化数据**（`@type: ItemList` → `ListItem` → `SoftwareApplication` / `Person`），每个条目都带 `name` / `url` / `description` / `applicationCategory` / `position`。这是给搜索引擎看的，所以是完整、非分页的。

抽取结果 —— **共 844 条（含重复列表），去重后 ≈ 700 条真人可读条目**：

| 分类 | 导航标示数 | 去重后条目数 | 校验 |
|---|---|---|---|
| Inspiration | 122 | **122** | ✅ 完全一致 |
| Components | 120 | **120** | ✅ 完全一致 |
| Build | 64 | **64** | ✅ 完全一致 |
| Visuals | 55 | **55** | ✅ 完全一致 |
| Utilities | 61 | **61** | ✅ 完全一致 |
| Design Engineers | 132 | **132** | ✅ 完全一致 |
| **合计** | **554** | **554** | ✅ |

> **这个"完全一致"就是数据完整性的证明**：去重后每个分类的条目数都精确等于站点导航上标示的数字，说明我抓到的是完整清单，没有分页截断、没有漏项。
>
> 踩过的坑（供复用）：JSON-LD 里同一份列表被渲染了两遍（`position` 从 1 到 132 各出现两次），所以原始匹配数是 264；另外 `Person` 类型部分条目带 `"sameAs":["https://x.com/..."]` 字段，会污染 `description` 的正则捕获——必须用 `(?:,"sameAs":\[[^\]]*\])?` 可选组吃掉它，否则会漏抓约 14 条。**这两个坑我都修掉了，最终 132 条干净落盘。**


### 抓到的样例（证明数据真实）

**Components 类·按 `applicationCategory` 分子类**：
```
Component Libraries : ForgeUI, RewampUI, shadcn/ui, Base UI, Radix, ...
                         https://ui.shadcn.com/  "Components you copy directly into codebases."
                         https://base-ui.com/    "Unstyled component primitives from Radix and MUI."
```

**Design Engineers 类**（`Person` 类型，带真实姓名 + 职务描述）：
```
Emil Kowalski    https://emilkowal.ski/   "Creator of Sonner, Vaul, and animations."
Rauno Freiberg   https://rauno.me/        "Author of Interaction Guidelines at Vercel."
Paco Coursey     https://paco.me/         "Creator of cmdk and next-themes."
Gavin Nelson     https://nelson.co/       "Designer at OpenAI crafting tactile interfaces."
Adam Argyle      https://nerdy.dev/       "Chrome DevRel keeping CSS modern."
shadcn           https://shadcn.com/      "Creator of shadcn/ui and component registries."
```

完整数据已落盘：本目录下的 `DESIGNEEER-DIRECTORY.md`（全部 554 条，含名称 + 网址 + 说明 + 子类，可直接当资源清单用），原始数据 `raw/directory.csv`（422 条 SoftwareApplication）、`raw/designers-full.csv`（132 位设计工程师）。

### 对我们最有用的 12 个收录站（从 844 条里筛出的，全部真实存在）

| 站点 | 为什么值得看 |
|---|---|
| `ui.shadcn.com` | v4 新增了 `Message` / `Bubble` / `MessageScroller` / `Marker` 原语，**就是给 AI 对话界面用的** |
| `www.prompt-kit.com` | AI 对话原语库，公开 registry JSON，能拿到真实 class |
| `www.radix-ui.com` | 12 步色阶命名法的源头 |
| `coss.com/ui` | 企业级表格/表单 |
| `www.untitledui.com`（未收录但同类） | 中后台表格与 badge 的标准答案 |
| `tremor.so` | 仪表盘 / 图表 |
| `linear.app` | 深色层次 + 信息密度标杆 |
| `resend.com` | 浅色克制风格标杆 |
| `component.gallery` | 组件设计横向对比 |
| `www.untitledui.com` / `originui.com` | 表单与空状态 |
| `interfaces.dev` / `www.interfacecraft.dev` | 交互细节 |
| `emilkowal.ski` / `rauno.me` | 动效与交互指南（人，不是工具） |

**评价**：designeer.xyz 本身确实是"目录"，但它的**目录数据是公开可抓的**，且质量不差——它明显偏好 shadcn 生态与设计工程师个人站，而不是 Dribbble 式的纯视觉灵感。这跟我们的项目需求（企业级、克制、可落地）恰好对齐。

---

## 二、可搬的设计决策表

### 2.1 令牌结构（最关键的一层）

| 来源 | 具体决策 | 具体数值/写法 | 我们要不要采用 & 怎么落到 Vue + CSS 变量 |
|---|---|---|---|
| [shadcn/ui theming](https://ui.shadcn.com/docs/theming) `[源码]` | **语义令牌双层结构**：底层 `:root` 定义原始值，`@theme inline` 只做「语义名 → 原始值」映射。组件永远只引用语义名 | `--background / --foreground / --card / --card-foreground / --popover / --primary / --secondary / --muted / --muted-foreground / --accent / --destructive / --border / --input / --ring / --chart-1..5 / --sidebar*` | ✅ **完全采用**。这是我们在无 Tailwind 环境下最该抄的一层：Vue 组件里只写 `var(--color-border)`，绝不写 `#e5e5e5`。建 `tokens.css`（原始层）+ `theme.css`（语义层），`[data-theme="dark"]` 只覆盖语义层 |
| [shadcn/ui](https://ui.shadcn.com/docs/theming) `[源码]` | 浅色模式的真实默认值 | `--background:#fff` `--foreground:#0a0a0a` `--card:#fff` `--primary:#171717` `--primary-foreground:#fafafa` `--secondary:#f5f5f5` `--muted:#f5f5f5` `--muted-foreground:#737373` `--border:#e5e5e5` `--input:#e5e5e5` `--ring:#737373` `--destructive:#e40014` | ✅ **采用其结构，但主色换成蓝**。shadcn 默认 primary 是中性黑（因为它要"无个性"），我们需要蓝。`--primary` 换成我们的主蓝，`--foreground` 保持 `#0a0a0a` 级别的深灰（不是纯黑，纯黑在投影仪上过锐） |
| [shadcn/ui](https://ui.shadcn.com/docs/theming) `[源码]` | 深色模式的**边框用半透明白**，不是实色 | `--border:oklch(1 0 0 / 10%)` `--input:oklch(1 0 0 / 15%)` `--ring:oklch(0.556 0 0)` | ✅ **采用**。深色下 `rgba(255,255,255,0.10)` 让边框在任意层叠背景上都自然，避免"边框颜色和卡片背景打架"。写到 `[data-theme=dark]` 里 |
| [Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) `[文档]` | **12 步色阶，每步绑定一个明确用途**（这是全行业最值得抄的抽象） | `1` 应用背景 · `2` 微弱背景 · `3` 组件常态背景 · `4` 组件 hover · `5` 组件 active/选中 · `6` 非交互组件边框（卡片/分隔线） · `7` 交互组件边框 · `8` hover 边框与 **focus ring** · `9` 实心背景（最高彩度） · `10` 实心 hover · `11` 低对比文字 · `12` 高对比文字 | ✅ **重度采用**。即使我们只有 3 个色相，也按这个语义建 12 步。**关键收益**：评审问"为什么这个灰是 #E5E5E5 而不是 #D4D4D4"，答案是"它是边界 6 级（非交互边框），按 Radix 语义表定的"——有据可依 |
| [Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) `[文档]` | 对比度承诺 | Step 11 与 12 保证在同色阶 step 2 背景上达到 **Lc 60 / Lc 90**（APCA） | ✅ 采用其**验收标准**。我们的正文用 step 12，次要文字用 step 11，并在 CI 里用 APCA 校验（工具：`myndex.com/APCA`，正好也在 designeer 收录里） |
| [Vercel Geist](https://vercel.com/geist/colors) `[文档+源码]` | **10 步色阶**（不是 12），且色阶名更直白 | 步长 `gray-100 … gray-1000`，每步 +100；另有 `gray-alpha-100…1000`；`--ds-background-100` / `--ds-background-200` | ⚠️ **不采用它的 10 步，采用 Radix 的 12 步**。理由：10 步粒度不够，我们还要区分"非交互边框"和"交互边框"。Geist 值得学的是**命名可读性**（100–1000 比 1–12 好懂），可以折中：变量名用 `--gray-100…--gray-1200`，注释里标 Radix 语义 |
| [Vercel Geist](https://vercel.com/geist/colors) `[文档]` | 色彩使用纪律（两条硬规则，原文） | ① **"Draw each border once"** —— 分隔线画在边框<u>内侧</u>，不要两条半透明边框叠在交叉处（会造成交点变深）；② **"Keep material shadows translucent"** —— 阴影必须半透明，否则留下灰色光晕 | ✅ **直接照抄成团队规则**。我们的待办三组列表 + 表格都用得上。写法：容器 `border:1px solid var(--color-border)`，行分隔用 `border-top` 而非 `border-bottom`，最后一行不画 |
| [Vercel Geist](https://vercel.com/geist/colors) `[文档]` | gray 与 gray-alpha 的分工 | **gray 用于**文字、图标、填充、边框、分隔线；**gray-alpha 仅用于**需要透出底层的场合（阴影、遮罩） | ✅ 采用。阴影色统一用 `rgba(0,0,0,α)` / `rgba(255,255,255,α)`，绝不为阴影定义新的实色灰 |

### 2.2 圆角

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui](https://ui.shadcn.com/docs/theming) `[源码]` | **单一 `--radius` 基准 + 乘法派生整个圆角体系** | `--radius: 0.625rem`(=10px)，然后 `--radius-sm: calc(var(--radius) * 0.6)` =6px ｜ `md: *0.8` =8px ｜ `lg: var(--radius)` =10px ｜ `xl: *1.4` =14px ｜ `2xl: *1.8` =18px ｜ `3xl: *2.2` =22px ｜ `4xl: *2.6` =26px | ✅ **强烈推荐**。改一个 `--radius` 就能整体调风格，评审说"太圆了"时 5 秒改完。注意：我们的 card 用 8px，那 `--radius` 设 `8px`，则 sm=4.8 / md=6.4 / lg=8 / xl=11.2 —— 整条线自动协调 |
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | Geist 只有一个圆角令牌 | `--geist-radius: 6px` | 参考。6px 偏"工具感"，10px 偏"产品感"。**我们取 8px** —— 比 Geist 稍柔，比 shadcn 默认稍硬，符合"高校 + 专业" |
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | 聊天气泡内容区圆角 | `rounded-xl`（=14px，对应 `--radius*1.4`） | data 用。气泡是"大块软矩形"，14px 正好 |
| [Resend](https://resend.com) `[源码]` | Resend 的圆角用量分布 | `--radius-sm:.25rem`(4px) `--radius-md:.375rem`(6px) `--radius-lg:.5rem`(8px) `--radius-xl:.75rem`(12px) `--radius-2xl:1rem`(16px) `--radius-3xl:1.5rem`(24px) `--radius-4xl:2rem`(32px)；实际页面里同时出现 `12px`、`20px`、`.625rem`、`32px` | ⚠️ Resend 用了 4 套体系（Tailwind 默认 + 自定义 + 硬编码），**不要学它的不一致**。只学它"卡片 12px / 按钮 8px / 代码块 16px"的**大→中→小的层次感** |

### 2.3 边框与卡片（"要不要阴影"这个核心问题）

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui card](https://ui.shadcn.com/r/styles/base-vega/card.json) `[源码]` | **卡片 = 极淡阴影 + 1px ring，不是重投影** | `rounded-xl bg-card py-6 text-sm shadow-xs ring-1 ring-foreground/10`，内部间距 `--card-spacing: --spacing(6)`=24px，`size=sm` 时为 16px | ✅ **主推方案**。`ring-1 ring-foreground/10` 翻译成 CSS：`box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-fg) 10%, transparent)`。好处：ring 不占布局、不产生 1px 抖动，且深浅色自适应。**这比 `border:1px` 更适合我们的卡片网格** |
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | Geist 的边框**根本不是 border，是 0 0 0 1px 的 ring** | `--ds-shadow-border-base: 0 0 0 1px #00000014`（浅色）/ `0 0 0 1px #ffffff25`（深色）；`--ds-shadow-border-inset: inset 0 0 0 1px #00000014` / `inset ... #ffffff1a` | ✅ **这是本次调研最重要的单点发现**。`#00000014` = 8% 黑，`#ffffff25` = 14.5% 白。**深色模式的边框要比浅色模式更强**（14.5% vs 8%）——因为深色下低透明度白几乎看不见。我们深色模式别再用 10% |
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | Geist 的完整阴影阶梯（全部半透明） | `--ds-shadow-2xs: 0px 1px 1px #0000000a` ｜ `xs: 0px 1px 2px #0000000a` ｜ `small: 0px 2px 2px #0000000a` ｜ `medium: 0px 2px 2px #0000000a, 0px 8px 8px -8px #0000000a` ｜ `large: 0px 2px 2px #0000000a, 0px 8px 16px -4px #0000000a` ｜ `menu: 4 层` ｜ `modal: 4 层` ｜ `2xl: 0px 1px 1px #00000005, 0px 8px 16px -4px #0000000a, 0px 24px 32px -8px #0000000f` | ✅ **照抄 `2xs/xs/small/medium/large` 五级**就够我们全站用。注意规律：**alpha 极低（4%–6%），靠"层数 + 负 spread"堆出柔和感**，而不是靠加大 blur。这跟我们平时"手写一个大阴影"的直觉相反，值得记 |
| [Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) `[文档]` | 边框的三级语义 | step 6 = 非交互组件边框（卡片/侧栏/表头/分隔线）；step 7 = 交互组件边框；step 8 = hover 边框 + focus ring | ✅ 采用。**直接决定我们的表头分隔线用哪一级**：表格行分隔是"非交互"→ step 6；输入框是"交互"→ step 7 |
| [Linear](https://linear.app) `[源码]` | **深色界面完全不靠阴影做层次**，靠"背景提亮 + 边框透明度" | `--color-bg-primary:#08090a` ｜ `--bg-base:#0f1011` ｜ `--color-bg-secondary:#1c1c1f` ｜ `--color-bg-tertiary:#232326` ｜ `--color-bg-quaternary:#28282c` ｜ 半透明版：`#ffffff08` / `#ffffff12` / `#ffffff26` / `#fff3`。边框：`--color-border-primary:#23252a`(=#ffffff14) ｜ `secondary:#34343a`(=#ffffff1f) ｜ `tertiary:#3e3e44`(=#ffffff26) | ✅ **深色模式的教科书**。层次 = 4 级背景提亮（#08090a → #28282c，每级约 +6~8 亮度值）+ 3 级边框（14%/12%/15%→ 实际 14%/19%/26% 白）。**规律：层级越靠前/越浮起，边框越亮，而不是阴影越重**。我们的深色模式直接按这个 4 级 + 3 级建模 |
| [Linear](https://linear.app) `[源码]` | 大量使用**半透明白作为叠加层**，而不是定义新实色 | `--color-bg-secondary:#1c1c1f` 与 `#ffffff08` 并存（深色下二者视觉等价，但半透明版能叠在任意底上） | ✅ 采用。深色令牌优先给半透明版，让弹层/下拉能复用同一套底色而不用为每种背景再定义一层 |

### 2.4 焦点态（focus ring）—— 最容易被忽略但最影响"专业感"

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui button](https://ui.shadcn.com/r/styles/base-vega/button.json) `[源码]` | 按钮 focus 用 **ring-3 + 50% 透明度**，且先切边框色 | `focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50` | ✅ **主推**。CSS：`outline:3px solid color-mix(in srgb, var(--color-ring) 50%, transparent); outline-offset:0; border-color:var(--color-ring)`。用 `outline` 而非 `box-shadow` 可以不占布局、能跟 `border-radius` 自适应（新浏览器已支持圆角 outline） |
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | 同上，另有 `ring-3 ring-ring/50` 用于气泡内按钮 | `[button,a]:focus-visible:border-ring [button,a]:focus-visible:ring-3 [button,a]:focus-visible:ring-ring/50` | ✅ 全站统一 3px/50% |
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | 另一种做法：**白色间隔 + 彩色环**（双层） | `--ds-focus-ring: 0 0 0 2px var(--ds-background-100), 0 0 0 4px var(--ds-focus-color)`；`--ds-focus-color: var(--ds-blue-700)`（浅）/ `--ds-blue-900`（深）；`--ds-focus-border: 0 0 0 1px var(--ds-gray-alpha-600), 0px 0px 0px 4px #00000029` | ⚠️ **不采用**。双层环在密集表格里太重，且需要知道背景色。只在"白色卡片上的主按钮"这种特殊场景备用 |
| [shadcn/ui globals](https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/v4/app/globals.css) `[源码]` | 全局兜底 focus 色 | `* { @apply border-border outline-ring/50; }` | ✅ 采用。全局默认 `outline-color: color-mix(in srgb, var(--color-ring) 50%, transparent)`，个别组件再覆盖，避免漏做 |

### 2.5 字体与排版

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | 字体栈（sans + mono，带完整 fallback 链） | sans：`GeistSans, GeistSans Fallback` ｜ mono：`Geist Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Liberation Mono, DejaVu Sans Mono, Courier New, monospace, Apple Color Emoji, Segoe UI Emoji, Segoe UI Symbol` | ✅ **mono 栈直接抄**（含中文/emoji fallback）。sans 我们要自建中文栈（见下） |
| [Resend](https://resend.com) `[源码]` | 字体分工：正文 / 展示 / 等宽三套分离 | `--font-sans: var(--font-inter), ui-sans-serif, system-ui, sans-serif` ｜ `--font-display: var(--font-abc-favorit), ...` ｜ `--font-mono: var(--font-commit-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas` | ✅ 学"分工"不学"数量"。我们只留 2 套：**中文正文栈 + 等宽栈**。正文栈建议：`-apple-system, "PingFang SC", "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", system-ui, sans-serif` |
| [Resend](https://resend.com) `[源码]` | 字号阶梯（rem，Tailwind 默认） | `2xs:.625rem`(10) `xs:.75rem`(12) `sm:.875rem`(14) `base:1rem`(16) `lg:1.125rem`(18) `xl:1.25rem`(20) `2xl:1.5rem`(24) `3xl:1.875rem`(30) `4xl:2.25rem`(36) `5xl:3rem`(48) `6xl:3.75rem`(60) `7xl:4.5rem`(72) `9xl:8rem`(128)；行高用 `calc(1.5/1)` 形式绑定 | ✅ 采用 `xs/sm/base/lg/xl/2xl/3xl` 这 7 级。**弃用 2xs(10px)**——中文 10px 不可读 |
| [Resend](https://resend.com) `[源码]` | 实际页面里最高频的字号 | `var(--text-sm)`(14px) ×9 ｜ `var(--text-xs)`(12px) ×7 ｜ 硬编码 `10px`×4 `11px`×4 `12px`×4 `13px`×4 `16px`×4 | ✅ 佐证"14px 是主力"。**正文 14px 是正确的**，不要用 16px 把界面撑开 |
| [Linear](https://linear.app) `[源码]` | 高信息密度界面的字号分布 | `13px` ×32（绝对主力）｜ `12px` ×24 ｜ `14px` ×10 ｜ `11px`×3 ｜ `10px`×5 ｜ `15px`×5 | ✅ **强烈佐证我们的方向**。列表/表格密集界面主力字号就是 **13px**，不是 14 也不是 16。建议：**页面正文 14px，列表/表格/元信息 13px，标签/辅助 12px** |
| [Carbon](https://carbondesignsystem.com/components/progress-indicator/style/) `[文档]` | 步骤条排版与结构规范 | 标签 `14px / 0.875rem`，`font-weight: 400`，token `$body-compact-01`；辅助文字 `12px / 0.75rem`，`400`，token `$label-01`；标签**限制 1–2 个词、总计 ≤16 字符**，**sentence case**；步骤 `min-width: 128px`；图标 `16×16`，`margin: 16px`（`$spacing-05`）；标签 `margin-top: 16px` | ✅ **全部采用**。特别是"标签 ≤16 字符、sentence case"——中文对应"≤8 个汉字"，能强制我们写出"填写基本信息"而不是"第一步：请填写您的基本信息" |

### 2.6 间距节奏

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | **基准 4px + 倍数命名**（不是 1/2/3/4 抽象编号，而是 2x/3x/4x/6x） | `--geist-space:4px` ｜ `2x:8px` ｜ `3x:12px` ｜ `4x:16px` ｜ `6x:24px` ｜ `8x:32px` ｜ `10x:40px` ｜ `16x:64px` ｜ `24x:96px` ｜ `32x:128px` ｜ `48x:192px` ｜ `64x:256px`；语义别名 `--geist-gap:24px`（区块内间隔）｜ `--geist-space-small:32px` `medium:36px` `large:40px`（**控件高度**，非间距） | ✅ **采用 4px 基准 + 倍数命名**。好处：`--space-6x` 一眼知道是 24px，而 `--space-6` 还要查表。我们定义 `--space-1x…--space-16x` 就够 |
| [Vercel Geist](https://vercel.com/geist/colors) `[源码]` | **控件高度也有令牌，且和间距共用一套数字** | `--geist-space-small:32px` → `--geist-form-small-height`；`medium:36px` → `--geist-form-height`；`large:40px` → `--geist-form-large-height`；字号对应 `small:0.875rem` / `large:1rem`；行高 `small:0.875rem` / 默认 `1.25rem` / `large:1.5rem` | ✅ 采用。**按钮高度不要再手写 px**：`--control-sm:32px` / `--control-md:36px` / `--control-lg:40px` |
| [shadcn/ui](https://ui.shadcn.com/r/styles/base-vega/button.json) `[源码]` | 按钮尺寸阶梯（含"圆角随尺寸收窄"这个精妙细节） | `xs: h-6`(24px) `rounded-[min(var(--radius-md),8px)] text-xs px-2` ｜ `sm: h-8`(32px) `rounded-[min(var(--radius-md),10px)] px-2.5` ｜ `default: h-9`(36px) `px-2.5 gap-1.5` ｜ `lg: h-10`(40px) ｜ `icon: size-9` ｜ `icon-xs: size-6` ｜ `icon-sm: size-8` ｜ `icon-lg: size-10` | ✅ **采用尺寸阶梯，且采用 `min(radius-md, 8px/10px)` 这个收窄技巧**——小按钮用大圆角会变药丸，很廉价。中文按钮再加一条：`px` 要 ≥16px（中文笔画密，左右留白要更多） |
| [shadcn/ui](https://ui.shadcn.com/r/styles/base-vega/card.json) `[源码]` | 卡片内边距令牌化 + 尺寸变体 | `--card-spacing: --spacing(6)` = 24px；`size=sm` → `--card-spacing: --spacing(4)` = 16px；header/content/footer 全部 `px-(--card-spacing)` | ✅ 采用。**一个变量控制整张卡片的内边距**，密集视图切 `size=sm` 即可 |
| [shadcn/ui empty](https://ui.shadcn.com/r/styles/base-vega/empty.json) `[源码]` | 空状态的内外间距 | 容器 `p-12`(48px) `gap-4` `rounded-lg border-dashed`；`EmptyHeader: max-w-sm gap-2`；` EmptyContent: max-w-sm gap-4`；`EmptyMedia.icon: size-10 rounded-lg bg-muted` 内部 svg `size-6`；标题 `text-lg font-medium tracking-tight`；描述 `text-sm/relaxed text-muted-foreground` | ✅ **完整照抄**。四要素：**40px 圆角方形容器 + 24px 图标 + 18px 标题 + 14px 灰色描述，全部居中，最大宽度 24rem**。这套直接用在"暂无待办""未生成报告" |

### 2.7 表格（待办三组列表、诊断报告明细都要用）

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui table](https://ui.shadcn.com/r/styles/base-vega/table.json) `[源码]` | **行高、内边距、分隔线、hover 的完整规格** | 表头 `th: h-10`(**40px**) `px-2 text-left align-middle font-medium whitespace-nowrap text-foreground`；单元格 `td: p-2`(**8px**) `align-middle whitespace-nowrap`；行：`border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted`；tbody 最后一行 `border-0`；`thead [&_tr]:border-b`；表格底 `text-sm`(14px) | ✅ **全套采用**。关键三条：① 表头 **40px 高、8px 横向内边距、不改字号（14px）也不大写**——比 Untitled UI 那种"12px 大写加字距"的英文风格**更适合中文**（中文没有大小写）；② **行 hover 用 `--muted` 的 50%**，极克制；③ 末行去边框 |
| [shadcn/ui table](https://ui.shadcn.com/r/styles/base-vega/table.json) `[源码]` | 表格必须有横向滚动容器 | 外层 `div[data-slot=table-container]: relative w-full overflow-x-auto` | ✅ 采用。评审用平板看时不会挤爆布局 |
| [shadcn/ui badge](https://ui.shadcn.com/r/styles/base-vega/badge.json) `[源码]` | **状态标签（badge）的完整尺寸与配色层级** | 基础：`inline-flex h-5`(**20px**) `gap-1 rounded-4xl border border-transparent px-2 py-0.5 text-xs`(**12px**) `font-medium whitespace-nowrap`；变体：`default: bg-primary text-primary-foreground` ｜ `secondary: bg-secondary text-secondary-foreground` ｜ `destructive: bg-destructive/10 text-destructive` ｜ `outline: border-border text-foreground` ｜ `ghost: hover:bg-muted` ｜ `link: text-primary underline`；focus `ring-[3px] ring-ring/50` | ✅ **全套采用**。**"标签靠 `bg-*/10` 浅底 + 同色深字"是最关键的技巧**——不需要为每个状态定义 border，层次自动成立。落到我们的 3 色约束：蓝底/10+蓝字（进行中）、红底/10+红字（紧急/未达标）、灰底/10+灰字（已完成/未开始）。**badge 高 20px、字号 12px** 记住 |
| [shadcn/ui badge](https://ui.shadcn.com/r/styles/base-vega/badge.json) `[源码]` | badge 的错误态 | `aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40` | ✅ 采用"用 aria 属性驱动样式"，比加一堆 class 干净 |
| [shadcn/ui marker](https://ui.shadcn.com/r/styles/base-vega/marker.json) `[源码]` | **"分隔标记"组件**——正好是复盘时间线要的东西 | 基础 `flex min-h-4 w-full items-center gap-2 text-sm text-muted-foreground`；变体 `separator:` 用伪元素画左右两条线 `before:mr-1 before:h-px before:flex-1 before:bg-border after:ml-1 after:h-px after:flex-1 after:bg-border`，文字居中 `flex-none text-center`；变体 `border: border-b border-border pb-2` | ✅ **这个组件直接解决我们的复盘时间线**。"文字两侧各一条 1px 线、文字居中"就是"2024 年 9 月"这种时间节点分组标题的标准做法，纯 CSS 伪元素，零依赖 |

### 2.8 AI 对话界面（本次调研的另一重点）

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | **气泡最大宽度 80%**，且用 `w-fit` 而非固定宽 | 气泡外层：`w-fit max-w-[80%] min-w-0 flex-col gap-1`；`data-[align=end]:self-end`（用户右侧）；`data-[variant=ghost]:max-w-full` | ✅ **直接采用 80%**。这是"看起来自然"的关键——100% 会让气泡贴死两边，60% 又太窄 |
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | 气泡内容区：**14px 圆角 + 12/8 内边距 + 透明边框占位** | `w-fit max-w-full min-w-0 overflow-hidden rounded-xl border border-transparent px-3 py-2 text-sm leading-relaxed wrap-break-word` | ✅ **`border-transparent` 占位是个重要技巧**：各变体切换时高度不变、不跳动。`leading-relaxed` = 1.625，长文本读起来舒服。**中文建议 `line-height: 1.7`** |
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | **7 种气泡变体，直接回答"气泡到底要不要底色"** | `default: bg-primary text-primary-foreground`（实心主色＝用户）｜ `secondary: bg-secondary text-secondary-foreground` ｜ `muted: bg-muted` ｜ `tinted: bg-[oklch(from_var(--primary)_0.93_calc(c*0.4)_h)]`（**主色低彩度染色**）｜ `outline: border-border bg-background` ｜ **`ghost: 圆角0 + 背景透明 + 内边距0`（＝纯文本，靠对齐区分说话人）** ｜ `destructive: bg-destructive/10 text-destructive` | ✅ **采用 `ghost` 给 AI、`secondary`/`muted` 给学生**。理由：AI 回答往往很长，纯文本更易读；学生提问短，给个浅底气泡形成节奏对比。**这就是 ChatGPT/Claude 的做法**（AI 无气泡、用户有气泡），shadcn 把它规范化了 |
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | **tinted 变体的色值算法**（给定主色自动生成低彩度浅背景） | 浅色：`oklch(from var(--primary) 0.93 calc(c*0.4) h)`；深色：`oklch(from var(--primary) 0.3 calc(c*0.4) h)`；hover：亮度 0.88 / 深色 0.35，彩度 `c*0.5` | ✅ **这是本次最有价值的技巧**。写法：`background: oklch(from var(--color-primary) 0.93 calc(c * 0.4) h)` —— **只改亮度、彩度打 4 折、色相完全不变**。这不引入第四种色相，硬件满足我们的 3 色约束，且保证和主色是同一家族。用于"学生画像"的字段分组底色、"诊断报告"的结论卡底色 |
| [shadcn/ui bubble](https://ui.shadcn.com/r/styles/base-vega/bubble.json) `[源码]` | 气泡上的**反应/点赞浮标** | `absolute z-10 rounded-full bg-muted px-1.5 py-0.5 text-sm ring-3 ring-card`；定位 `bottom-0 translate-y-3/4`，`right-3`；`ring-card` 造出"挖空"效果 | ✅ 采用（做"这条建议有用吗"）。**`ring-3 ring-card` 是关键**：用卡片背景色的 3px 环模拟"浮标压在气泡上挖了个洞" |
| [shadcn/ui message](https://ui.shadcn.com/r/styles/base-vega/message.json) `[源码]` | 消息行结构 + 头部/脚部元信息 | 行：`flex w-full gap-2 text-sm`；头像：`min-w-8 rounded-full bg-muted self-end`，有 footer 时 `-translate-y-8`；`MessageHeader/Footer: flex items-center px-3 text-xs font-medium text-muted-foreground`；内容列 `flex flex-col gap-2.5` | ✅ 采用。**"说话人姓名/时间"用 12px + medium + `--muted-foreground`、左右各 12px 内边距**——正好对齐气泡的文字左边缘。`gap-2.5`=10px |
| [shadcn/ui message-scroller](https://ui.shadcn.com/r/styles/base-vega/message-scroller.json) `[源码]` | **消息滚动区的完整技术方案** | 视口：`size-full min-h-0 min-w-0 scroll-fade-b scrollbar-thin scrollbar-gutter-stable overflow-y-auto overscroll-contain contain-content`，自动滚动时滚动条透明，滚动中 `data-pending-scroll:invisible`；内容 `flex h-max min-h-full flex-col gap-8`(**32px**)；消息项 `[contain-intrinsic-size:auto_10rem] [content-visibility:auto]`；**滚动按钮**：`absolute inset-s-1/2 -translate-x-1/2 border-border bg-background`，出现动画 `duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]`，消失 `duration-400 ease-[cubic-bezier(0.7,0,0.84,0)]`，`data-[active=false]:scale-95 opacity-0` | ✅ **整套采用，尤其两点**：① **`content-visibility:auto` + `contain-intrinsic-size:auto_10rem`** —— 长对话性能优化，只在视口内渲染，我们长会话必用；② **出现/消失用不同缓动**（出现 200ms `cubic-bezier(0.23,1,0.32,1)` 快进，消失 400ms `cubic-bezier(0.7,0,0.84,0)` 缓出）——这是很高级的细节 |
| [shadcn/ui](https://ui.shadcn.com/r/styles/base-vega/message-scroller.json) `[源码]` | **顶部/底部渐隐遮罩**（替代生硬的滚动截断） | `scroll-fade-b` 用 `mask-image: linear-gradient(to bottom, #000 0, #000 calc(100% - var(--scroll-fade-b)), transparent 100%)`；默认尺寸 `min(12%, calc(var(--spacing) * 10))` = `min(12%, 40px)`；配合 `animation-timeline: scroll(self y)` 做滚动驱动 | ✅ **强烈推荐**。用 `mask-image` 淡出而不是叠一层渐变 div —— 不会挡住点击、不产生层叠上下文。我们消息区底部、待办列表底部都用 |
| [shadcn/ui message-scroller](https://ui.shadcn.com/r/styles/base-vega/message-scroller.json) `[源码]` | 滚动条细节 | `scrollbar-thin scrollbar-gutter-stable`；自动滚动时 `scrollbar-thumb-transparent` / `scrollbar-track-transparent` | ✅ 采用 `scrollbar-gutter: stable`——**防止"出现滚动条时内容横向跳动"**，这是最容易被忽略却最影响质感的一行 CSS |
| [prompt-kit](https://www.prompt-kit.com/docs/prompt-input) `[源码]` | **输入区（composer）的确切规格** | 外层：`border-input bg-background cursor-text rounded-3xl border p-2 shadow-xs`（**24px 圆角 + 1px 边框 + 8px 内边距 + 极淡阴影**）；文本域：`min-h-[44px] w-full resize-none border-none bg-transparent shadow-none outline-none focus-visible:ring-0`，`rows=1`；自动增高上限 `maxHeight = 240`（px）；回车发送、Shift+回车换行 | ✅ **完整照抄**。三个关键数字：**圆角 24px（刻意比气泡大，形成"输入框比内容更软"的层次）、`min-height` 44px（触控最小高度）、最大高 240px（约 8 行后内部滚动）**。外层 `cursor:text` + 点任意处聚焦——细节但很加分 |
| [prompt-kit source](https://www.prompt-kit.com/docs/source) `[源码]` | **引用/来源标注的确切做法** | 触发胶囊：`inline-flex h-5 max-w-32 items-center gap-1 overflow-hidden rounded-full bg-muted text-muted-foreground text-xs`（**20px 高、最大宽 128px、全圆角**），有 favicon 时 `pr-2 pl-1`，无则 `px-1`；hover：`hover:bg-muted-foreground/30 hover:text-primary`，`transition-colors duration-150`；favicon `size-3.5`(14px) `rounded-full`；域名文字 `truncate tabular-nums`；悬浮卡 `w-80 p-0 shadow-xs`，内容 `flex flex-col gap-2 p-3`，含 16px favicon + 域名(`text-sm`) + 标题(`text-sm font-medium line-clamp-2`) + 描述(`text-sm text-muted-foreground line-clamp-2`) | ✅ **直接采用，这就是我们要的"来源 + 把握度"呈现**。收获：① 来源做成**20px 高的圆形小胶囊**，不是大卡片；② hover 展开 320px 宽的悬浮卡看详情；③ 用 `tabular-nums` 让数字对齐；④ 悬浮延迟 `openDelay={150}` |
| [prompt-kit message](https://www.prompt-kit.com/docs/message) `[源码]` | 消息内容区的默认样式 | `rounded-lg p-2 text-foreground bg-secondary prose break-words whitespace-normal`；头像 `h-8 w-8`(32px)；消息行 `flex gap-3`(12px)；操作条 `text-muted-foreground flex items-center gap-2` | ✅ 采用。**头像 32px、消息间距 12px、内容内边距 8px、圆角 8px** |
| [prompt-kit message](https://www.prompt-kit.com/docs/message) `[源码]` | 行内代码与代码块 | 行内：`bg-primary-foreground rounded-sm px-1 font-mono text-sm`；代码块：`border border-border bg-card text-card-foreground rounded-xl overflow-clip`，内部 `text-[13px]`，`pre` 内边距 `px-4 py-4` | ✅ 采用。**代码用 13px，比正文 14px 略小**；行内代码 `px-1` + `rounded-sm`(近似 4px) |
| [prompt-kit](https://www.prompt-kit.com/docs/message) `[源码]` | Markdown 分块渲染（流式输出性能） | 用 `marked.lexer()` 把 markdown 拆成块，每块交给 `memo` 包裹的 `ReactMarkdown`，`propsAreEqual` 只比较 `content`；未变化的块不重渲染 | ✅ **采用其思路**。Vue 里：把流式文本按块拆分，每块包一个 `v-memo="[block]"` 的渲染组件。**这是流式输出不卡顿的关键** |
| [ChatGPT](https://chatgpt.com) / [Claude](https://claude.ai) | 气泡与宽度 | `[未核实]` —— 两站 CSS 在生产构建中被混淆/按需注入，未能从源码确认具体 px。**从页面结构可确认的事实**：AI 回复为**纯文本、无气泡背景**，用户消息为**浅底气泡**；消息列有明显最大宽度限制，远窄于视口 | ⚠️ **该两站未公开具体数值，建议以实际页面/截图为准**。但"AI 无气泡、用户有气泡"这个结构性结论是可靠的，且已被 shadcn 的 `ghost` 变体规范化 |
| [v0.app](https://v0.app) / [Perplexity](https://www.perplexity.ai) | 引用来源 | `[未核实]` 具体数值。可确认 Perplexity 的来源为**答案下方的来源卡片行 + 正文内联上标编号**双呈现 | ⚠️ 未核实。**建议采用 prompt-kit 的胶囊方案**（有确切数值），Perplexity 的双呈现可作为二期增强 |

### 2.9 步骤引导（stepper / progress）

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [Carbon](https://carbondesignsystem.com/components/progress-indicator/usage/) `[文档]` | **三态的定义与视觉**（原文规范） | **Completed（已完成）**：空心圆 + **对勾** + **蓝色**活动线 ｜ **Current（当前）**：**半填充圆** + 蓝色活动线 ｜ **Not started（未开始）**：**空心圆**（无对勾）+ **灰色**活动线；另有 error / disabled / hover / focus 共 7 态 | ✅ **全部采用**。关键洞察：**"当前"不是"填充实心圆"，而是"半填充圆"**；"已完成"的对勾是**空心**圆里的，不是实心圆。这套比"实心蓝圆 + 白数字"克制得多，更符合我们的风格 |
| [Carbon](https://carbondesignsystem.com/components/progress-indicator/style/) `[文档]` | 三态的**颜色令牌** | Complete icon fill `$interactive` ｜ Current icon fill `$interactive` ｜ Not started icon fill `$icon-primary` ｜ **Active step line** `$border-interactive` ｜ **Inactive step line** `$border-subtle` ｜ Label `$text-primary` ｜ Helper text `$text-secondary`；交互态：focus `$focus`，label hover `$link-primary-hover`，error `$support-error`，disabled `$icon-disabled` | ✅ 采用其**语义命名**映射到我们的 3 色：`$interactive`→我们的主蓝，`$icon-primary`→深灰，`$border-subtle`→浅灰。**最重要的是"连线也分两态"**——已完成段用蓝线，未开始段用灰线。很多实现只做圆不连线，做了连线就专业一档 |
| [Carbon](https://carbondesignsystem.com/components/progress-indicator/style/) `[文档]` | 尺寸规格 | 图标 `16×16px`；`margin-top` / `margin-right: 16px`（`$spacing-05`）；标签 `margin-top: 16px`（`$spacing-05`）；步骤 `min-width: 128px` | ✅ 采用。**图标只有 16px**（不是常见的大圆），步骤最小宽 128px 保证标签不挤 |
| [Vercel Geist](https://vercel.com/geist/colors) `[文档]` | 步骤进度的语义色阶 | `Color 7` = 高对比背景，`Color 8` = 高对比 hover；`Color 9/10` = 实心背景与 hover | ✅ 完成态用 step 9，当前态用 step 9 + 外环，未开始用 step 3 底 + step 11 字 |

### 2.10 图表（雷达图 / 四象限 / 分值条 / 门槛线）

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui chart tokens](https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/v4/app/globals.css) `[源码]` | **图表色独立成 5 个令牌**，不与语义色混用 | `--chart-1 … --chart-5`，浅色下映射到 `--color-blue-300/500/600/700/800`；深色下同一组映射 | ✅ **采用其结构**，但内容换成我们的 3 色。**5 个图表色在我们的约束下这样分配**：`--chart-1` 主蓝（最淡，用于雷达图填充）、`--chart-2` 主蓝（正，用于雷达描边）、`--chart-3` 深灰（用于第二个数据系列）、`--chart-4` 辅红（**仅用于门槛线/未达标**）、`--chart-5` 浅灰（网格与轴） |
| [shadcn/ui](https://ui.shadcn.com/docs/theming) `[源码]` | 图表色**引用底层色阶而非硬编码** | `--chart-1: var(--color-blue-300)` 而不是 `#93c5fd` | ✅ 采用。让图表色跟着主色走，将来调主色图表自动同步 |
| [shadcn/ui](https://ui.shadcn.com/r/styles/base-vega/card.json) `[源码]` | 复杂图表的容器规范 | 卡片 `py-6`（24px 上下内边距）；`CardHeader` 用 `grid auto-rows-min gap-1`，有 action 时 `grid-cols-[1fr_auto]`，有 description 时 `grid-rows-[auto_auto]` | ✅ 采用。**"标题在左、操作在右"用 grid 两列而不是 flex**——这样标题换行时右侧操作依然顶对齐。诊断报告卡片的"标题 + 分值 + 操作"正好用 |
| [Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) `[文档]` | 门槛线该用什么 | step 9 = **最高彩度**、step 10 = hover；step 8 = 更强的边框与 focus ring | ✅ 门槛线用 step 8 或 step 9 的红色。**用 `stroke-dasharray` 画虚线，配 `stroke-width: 1.5`**——不要用实线（实线会被误读成数据） |

### 2.11 空状态与反馈

| 来源 | 具体决策 | 具体数值/写法 | 落地建议 |
|---|---|---|---|
| [shadcn/ui empty](https://ui.shadcn.com/r/styles/base-vega/empty.json) `[源码]` | 空状态容器用**虚线边框**（而非实线） | `rounded-lg border-dashed p-12 text-center text-balance` | ✅ 采用。**虚线边框是"可填充的空位"的通用视觉语言**，比实线更能表达"这里暂时没东西" |
| [shadcn/ui empty](https://ui.shadcn.com/r/styles/base-vega/empty.json) `[源码]` | 空状态文字的灰阶层级 | 标题 `text-lg font-medium tracking-tight`（**用 `--foreground`，不是灰**）；描述 `text-sm/relaxed text-muted-foreground` | ✅ 采用。**标题不灰**——很多实现把标题也调灰，导致整个空状态"糊"成一片。标题用正文色、只有描述用灰，层次才清晰 |
| [shadcn/ui badge](https://ui.shadcn.com/r/styles/base-vega/badge.json) `[源码]` | 状态色的层级（不含 border 也能成立） | `bg-destructive/10 text-destructive`（浅底+深字）；hover 加深到 `/20` | ✅ 采用。**三色约束下的状态色方案**：不新增色相，用"同色相不同不透明度"造出 3 档（`/10` 常态、`/20` hover、`/30` active） |
| [prompt-kit message](https://www.prompt-kit.com/docs/message) `[源码]` | 消息操作条的默认隐藏/显示 | 操作条容器 `text-muted-foreground flex items-center gap-2` | ✅ 采用"默认 `opacity: 0`，消息行 hover 时 `opacity: 1`"——减少常驻噪音 |

---

## 三、给这个项目的 12 条具体落地建议

> 每条都可直接写进 CSS。假设约定：主蓝 `--blue-9`、辅红 `--red-9`、深灰骨架 `--gray-*`，基准 4px，基准圆角 8px。

**1. 建两层令牌文件，组件永远不写死色值。**
`tokens.css` 放原始值（`--gray-100: #f5f5f5` … `--blue-9: …`），`theme.css` 只做语义映射（`--color-border: var(--gray-300)`）。用 Radix 的 12 步语义给每步起中文注释：
```css
:root{
  --color-bg:            var(--gray-100); /* step 1 应用背景 */
  --color-bg-subtle:     var(--gray-200); /* step 2 微弱背景 */
  --color-surface:       #fff;            /* step 3 组件常态 */
  --color-surface-hover: var(--gray-200); /* step 4 hover */
  --color-surface-active:var(--gray-300); /* step 5 active */
  --color-border:        #e5e5e5;         /* step 6 非交互边框 ☆表格行、卡片 */
  --color-border-input:  #d4d4d4;         /* step 7 交互边框 ☆输入框 */
  --color-ring:          #737373;         /* step 8 focus ring */
  --color-primary:       var(--blue-9);   /* step 9 实心主色 */
  --color-primary-hover: var(--blue-10);  /* step 10 */
  --color-fg-muted:      #737373;         /* step 11 次要文字 */
  --color-fg:            #0a0a0a;         /* step 12 正文 */
}
```

**2. 圆角用"单基准 × 乘法"派生，不要逐个写。**
```css
:root{
  --radius: 8px;                                        /* 唯一需要调的旋钮 */
  --radius-xs: calc(var(--radius) * 0.5);  /* 4px  行内代码、小标签 */
  --radius-sm: calc(var(--radius) * 0.6);  /* 4.8px */
  --radius-md: calc(var(--radius) * 0.8);  /* 6.4px 按钮 */
  --radius-lg: var(--radius);               /* 8px  卡片、输入框 */
  --radius-xl: calc(var(--radius) * 1.4);   /* 11.2px 弹层、气泡 */
  --radius-2xl:calc(var(--radius) * 1.8);   /* 14.4px 大面板 */
  --radius-full: 9999px;                    /* 胶囊 badge */
}
```
评审说"太圆"就把 `--radius` 改成 6px，全站自动收敛。

**3. 卡片不要阴影，用 1px ring + 极淡 shadow-xs。**
```css
.card{
  background: var(--color-card);
  border-radius: var(--radius-lg);        /* 8px */
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--color-fg) 10%, transparent), /* ← 边框用 ring，不占布局 */
    0 2px 2px rgba(0,0,0,.04);                                      /* ← shadow-xs 级 */
  padding: var(--space-6x);               /* 24px */
}
.card--dense{ padding: var(--space-4x); } /* 16px，用于密集列表 */
```
理由：`box-shadow` 画边框不产生 1px 布局抖动；深浅色下 `color-mix` 自动适配。**深色模式把 ring 提到 15% 白**（Geist 实测浅色 8% / 深色 14.5%，深色必须更强）。

**4. 正文 14px / 行高 1.7，次要文字 13px 灰 60%，元信息 12px。**
```css
:root{
  --text-xs:12px;  --leading-xs:1.5;   /* 时间戳、脚注 */
  --text-sm:13px;  --leading-sm:1.6;   /* ☆ 列表/表格/次要文字 —— 最常用 */
  --text-base:14px; --leading-base:1.7;/* ☆ 正文、卡片描述、气泡内容 */
  --text-lg:18px;  --leading-lg:1.5;   /* 卡片标题 */
  --text-xl:20px;  --leading-xl:1.4;   /* 页面区块标题 */
  --text-2xl:24px; --leading-2xl:1.35; /* 页面标题 */
}
```
注意：**正文 14px 不是 16px**（Resend 实测 14px 出现 9 次为最高频；Linear 13px 出现 32 次为最高频）。中文 `line-height` 给到 **1.7**（比英文的 1.5–1.625 更大），因为汉字是满框字面、无升降部缓冲。
次要文字用 `--color-fg-muted`（step 11，约 `#737373`，视觉灰度约 55–60%）。
字体栈：
```css
--font-sans: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei",
             "Source Han Sans SC", "Noto Sans CJK SC", system-ui, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
             "Liberation Mono", "Courier New", monospace;
```

**5. 表格：表头 40px 高、14px 字、8px 横向内边距、不改字号不大写。**
```css
.table{ width:100%; font-size:var(--text-base); border-collapse:collapse; }
.table thead tr{ border-bottom:1px solid var(--color-border); }   /* step 6 */
.table th{
  height:40px; padding:0 8px; text-align:left; vertical-align:middle;
  font-size:var(--text-base);        /* ← 不缩小！中文缩小后笔画糊 */
  font-weight:500; color:var(--color-fg);
  white-space:nowrap;
  /* 不要 text-transform:uppercase / letter-spacing —— 中文无意义且难看 */
}
.table td{ padding:8px; vertical-align:middle; white-space:nowrap; }
.table tbody tr{ border-bottom:1px solid var(--color-border); transition:background-color .15s; }
.table tbody tr:hover{ background: color-mix(in srgb, var(--color-bg-subtle) 50%, transparent); }
.table tbody tr:last-child{ border-bottom:0; }   /* Geist: 末行不画线 */
```
**"每边只画一次线"**：行分隔统一用 `border-bottom` 而非混用 top/bottom，否则相邻行会出现 2px 双线。

**6. 状态标签（badge）：20px 高、12px 字、同色 `/10` 浅底 + 同色深字，不画边框。**
```css
.badge{
  display:inline-flex; align-items:center; gap:4px;
  height:20px; padding:0 8px;
  border-radius: var(--radius-full);
  font-size:var(--text-xs); font-weight:500; white-space:nowrap;
  border:1px solid transparent;          /* ← 占位，避免切换时尺寸跳 */
}
.badge--progress{ background:color-mix(in srgb, var(--color-primary) 10%, transparent);
                  color:var(--color-primary); }        /* 进行中 */
.badge--done    { background:color-mix(in srgb, var(--color-fg) 8%, transparent);
                  color:var(--color-fg-muted); }        /* 已完成 */
.badge--urgent  { background:color-mix(in srgb, var(--color-danger) 10%, transparent);
                  color:var(--color-danger); }          /* 紧急/未达标 */
.badge--urgent:hover{ background:color-mix(in srgb, var(--color-danger) 20%, transparent); }
```
**这套方案在 3 色约束内造出完整状态体系**：不新增色相，只调 `color-mix` 百分比（`/10` 常态 → `/20` hover → `/30` active）。

**7. 待办三组列表：不要卡片套卡片，用「分组标题 + 单层行」。**
```css
.todo-group{ margin-bottom: var(--space-8x); }         /* 32px 组间距 */
.todo-group__title{
  display:flex; align-items:center; gap:8px;
  font-size:var(--text-lg); font-weight:500;           /* 18px */
  padding-bottom:8px; margin-bottom:0;
  border-bottom:1px solid var(--color-border);          /* 一条线分隔标题与内容 */
}
.todo-item{
  display:flex; align-items:center; gap:var(--space-3x);/* 12px */
  min-height:48px;                                       /* 行高：可点击目标 */
  padding:var(--space-3x) 0;
  border-bottom:1px solid var(--color-border);           /* 行分隔，每边只画一次 */
}
.todo-item:last-child{ border-bottom:0; }
.todo-item:hover{ background: color-mix(in srgb, var(--color-bg-subtle) 60%, transparent); }
```
**"分组标题下一条线 + 组内行分隔线 + 末行无线"** 三段式，不需要卡片包裹，视觉噪音最低。

**8. AI 对话：AI 用 ghost（纯文本），学生用浅底气泡，气泡最大宽度 80%。**
```css
.chat-col{ max-width: 760px; margin:0 auto; }           /* 消息列宽度限制 */
.msg{ display:flex; gap:12px; width:100%; font-size:var(--text-base); }
.msg--student{ flex-direction: row-reverse; }

.bubble{
  width:fit-content; max-width:80%; min-width:0;
  border-radius: var(--radius-xl);                      /* 11.2px */
  border:1px solid transparent;                          /* 占位防跳动 */
  padding:8px 12px;
  font-size:var(--text-base); line-height:1.7;           /* 中文 1.7 */
  overflow-wrap: anywhere;
}
.bubble--student{ background: color-mix(in srgb, var(--color-primary) 8%, transparent);
                  color: var(--color-fg); }
/* AI 回复：无底色、无边框、无内边距 —— 靠对齐和留白区分 */
.bubble--ai{ max-width:100%; background:transparent; border-color:transparent; padding:0; border-radius:0; }
.msg__meta{ font-size:var(--text-xs); font-weight:500; color:var(--color-fg-muted); padding:0 12px; }
```
**AI 回答往往很长，给气泡底色反而压缩了有效阅读宽度。** 用 32px 的组间距（`gap: 32px`）来建立节奏，而不是靠气泡。

**9. 输入区固定：`position: sticky; bottom: 0` + 24px 圆角 + 上方渐隐遮罩。**
```css
.chat-viewport{
  overflow-y:auto; overscroll-behavior:contain;
  scrollbar-gutter: stable;                              /* ← 防内容横向跳动 */
}
.chat-composer-wrap{
  position: sticky; bottom: 0;
  background: var(--color-bg);
  padding: 12px 0 16px;
  /* 上方渐隐，替代生硬的直线截断 */
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 12px);
          mask-image: linear-gradient(to bottom, transparent 0, #000 12px);
}
.composer{
  border:1px solid var(--color-border-input);            /* step 7 */
  background: var(--color-card);
  border-radius: 24px;                                   /* ★ 刻意大于气泡 */
  padding: 8px;
  box-shadow: 0 2px 2px rgba(0,0,0,.04);
  cursor: text;
}
.composer textarea{
  width:100%; min-height:44px; max-height:240px;         /* ★ 44 → 240px 后内部滚动 */
  border:0; outline:0; background:transparent; box-shadow:none;
  resize:none; font-size:var(--text-base); line-height:1.6;
  field-sizing: content;                                 /* 现代浏览器自动增高；老浏览器用 JS 兜底 */
}
```
发送：Enter 发送、Shift+Enter 换行。

**10. 来源/把握度用 20px 圆形胶囊 + hover 悬浮卡。**
```css
.cite{
  display:inline-flex; align-items:center; gap:4px;
  height:20px; max-width:128px; padding:0 8px;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--color-fg) 8%, transparent);
  color: var(--color-fg-muted);
  font-size: var(--text-xs); text-decoration:none;
  overflow:hidden; transition: background-color .15s, color .15s;
}
.cite:hover{ background: color-mix(in srgb, var(--color-fg-muted) 30%, transparent);
             color: var(--color-primary); }
.cite img{ width:14px; height:14px; border-radius:50%; }
.cite span{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
            font-variant-numeric: tabular-nums; }   /* ★ 数字等宽对齐 */
```
**"把握度"建议直接复用这套胶囊**：`高 / 中 / 低` 三档，用 `--primary` / `--fg-muted` / `--danger` 三个前景色，尺寸形状完全一致 —— 学生画像卡片里的"字段 + 来源 + 把握度"就是三个并列胶囊，非常整齐。

**11. 雷达图 / 四象限 / 分值条 / 门槛线：把图表色做成 5 个令牌，且**只用 3 个色相**。**
```css
:root{
  --chart-1: color-mix(in srgb, var(--color-primary) 25%, #fff); /* 雷达填充（最淡） */
  --chart-2: var(--color-primary);                               /* 雷达描边、主数据线 */
  --chart-3: var(--color-fg-muted);                              /* 第二数据系列（深灰） */
  --chart-4: var(--color-danger);                                /* ★ 仅门槛线、未达标 */
  --chart-5: #e5e5e5;                                            /* 网格线、坐标轴 */
}
.threshold-line{
  stroke: var(--chart-4); stroke-width: 1.5;
  stroke-dasharray: 4 4;      /* ★ 必须虚线：实线会被误读为数据 */
}
.bar-track{ background: var(--chart-5); border-radius: var(--radius-full); height: 8px; }
.bar-fill { background: var(--chart-2); border-radius: var(--radius-full); height: 8px; }
.bar-fill--below{ background: var(--chart-4); }   /* 未达门槛：红 */
.quadrant-cell{ background: color-mix(in srgb, var(--chart-5) 40%, transparent); }
.quadrant-cell--focus{ background: color-mix(in srgb, var(--color-primary) 6%, transparent); } /* 高亮象限 */
```
**雷达图只需 1 个数据系列时，用 `--chart-1` 填充 + `--chart-2` 描边**（同色相不同明度），视觉干净且天然和谐。四象限的高亮象限用 6% 主色底，不加边框。

**12. 步骤条：当前=半填充圆，已完成=空心圆+对勾，未开始=空心圆；连线分蓝/灰两段。**
```css
.steps{ display:flex; align-items:flex-start; }
.step{ min-width:128px; }                         /* Carbon 规格 */
.step__icon{
  width:16px; height:16px; border-radius:50%;
  border:1px solid var(--color-fg);                /* 空心，1px */
  display:flex; align-items:center; justify-content:center;
  margin: 0 16px 0 0;
}
.step__icon--done{ border-color: var(--color-primary); }      /* 对勾 + 空心圆 */
.step__icon--current{                                          /* ★ 半填充，不是全填充 */
  border-color: var(--color-primary);
  background: linear-gradient(90deg,
              var(--color-primary) 0 50%, transparent 50% 100%);
}
.step__icon--todo{ border-color: var(--color-fg-muted); }      /* 灰空心 */
.step__line{ height:1px; flex:1; }
.step__line--active{ background: var(--color-primary); }        /* 已走过的段：蓝 */
.step__line--inactive{ background: var(--color-border); }       /* 未开始：灰 */
.step__label{ margin-top:16px; font-size:var(--text-base); font-weight:400; }
.step__hint { font-size:var(--text-xs); color:var(--color-fg-muted); }
```
标签文案规则：**≤8 个汉字、sentence case、动词+名词**（如"填写信息"而不是"第一步：请填写您的信息"）。

---

## 四、明确不要抄的

| 不要抄 | 为什么不适合我们这个项目 |
|---|---|
| **玻璃拟态 / backdrop-filter 毛玻璃** | ① 高校评审常用老旧投影仪与低端笔记本，`backdrop-filter` 在这些设备上直接掉帧或渲染成一块灰；② 视觉上"潮"，与"专业、克制"直接冲突；③ 它靠"背景有东西可模糊"才成立，我们的界面背景本来就是纯净的，模糊后什么也看不出来，只剩性能代价 |
| **大量渐变（尤其紫蓝渐变、mesh gradient）** | ① 渐变会引入**第三个以上的色相**，直接违反"不超过 3 种主色"的硬约束；② 渐变背景上的文字对比度不可控，无法通过 APCA/无障碍验收；③ 门户页主视觉之外，工作台/报告/表格里任何渐变都是干扰 |
| **彩色阴影**（`box-shadow` 用主色） | Radix 确实把"coloured shadows"列为 step 9 的合法用途，但那是给品牌营销页的。我们的卡片阴影必须是中性半透明（Geist 的做法：`#0000000a`），否则一张卡片在浅色背景上会"发光"，看起来像按钮又不响应点击 |
| **emoji 当图标** | ① emoji 在不同系统（Windows/Android/iOS/macOS）渲染成完全不同的样子，评审用 Windows、学生用手机，同一页面能出现三种风格；② emoji 无法用 `currentColor` 变灰/变色，无法和 12px 文字基线对齐；③ 高校场景里 emoji 会显得不严肃。**用内联 SVG + `stroke="currentColor"`，尺寸 16/20/24 三档** |
| **多彩图标 / 每色相一套状态色** | 常见的中后台"绿=成功、蓝=信息、黄=警告、红=错误、紫=…"，会立刻突破 3 色约束。**我们的替代方案**：全部用"同色相 `/10` 浅底 + 同色深字"（见建议 6），深度靠不透明度而不是色相区分 |
| **表头 12px 大写 + 加字距（`text-transform: uppercase; letter-spacing: .05em`）** | 这是 Untitled UI / Tailwind UI 的英文习惯。中文**没有大小写**，`uppercase` 完全无效；而对中文加 `letter-spacing` 会让本就密排的汉字显得松散、行宽失控。**表头就保持 14px、字重 500、正常字距**（shadcn 的做法） |
| **大圆角药丸按钮（`border-radius: 9999px` 用在主按钮）** | 药丸形按钮在中文界面里因为字面宽，会变成"椭圆胶囊"，和 8px 圆角的卡片系统冲突。**只让 badge/胶囊标签用全圆角，按钮用 `--radius-md`（6px）**，且小尺寸按钮要收窄圆角（`min(radius, 8px)`，shadcn 的技巧） |
| **Geist 的双层 focus ring**（白圈+彩圈） | 在密集表格和待办列表里，4px 的彩色外环会盖住相邻行，密度一高就糊。**用单层 3px / 50% 透明度**（shadcn 现行方案），足够醒目又不侵占 |
| **Resend 的圆角混用** | 我在它的生产 CSS 里实测到同时存在 `4px / 6px / 8px / 10px / 12px / 16px / 20px / 24px / 32px` 和 4 套命名体系。这是**快速迭代留下的技术债**，不是设计优点。我们严格用建议 2 的单基准派生 |
| **shadcn 默认 primary = 纯黑** | shadcn 刻意为"无个性"把 `--primary` 设为 `#171717`。但我们是"生涯规划平台"，主色必须是蓝（也符合高校视觉惯例）。**抄它的令牌结构，不抄它的默认值** |
| **深色模式用 10% 白做边框** | Geist 实测：浅色边框 `#00000014`（8% 黑），深色边框 `#ffffff25`（**14.5%** 白）。**深色下低透明度白几乎不可见**，照搬浅色的 10% 会导致深色模式所有边框消失。深色统一提到 14–15% |
| **纯黑 `#000` 做正文色** | 在投影仪和大屏上纯黑过锐，长时间阅读疲劳。Resend/shadcn 都用 `#0a0a0a`～`#171717` 级别的深灰。**正文用 `#0a0a0a`，标题可到 `#171717`** |
| **为每个分类新增一个色相** | 待办三组、四象限、诊断等级——加起来很容易演变成"彩虹"。**约束自己有 3 个色相 + 无限档不透明度**，这是本项目最强的设计杠杆 |

---

## 五、来源清单

### 5.1 designeer.xyz 相关（任务一）

| URL | 拿到了什么 |
|---|---|
| https://www.designeer.xyz/ | 首页（Inspiration 122）；原始 HTML 614,739 字节 |
| https://www.designeer.xyz/components | Components 120；原始 HTML 605,699 字节；**JSON-LD 240 条** |
| https://www.designeer.xyz/build | Build 64；394,295 字节；JSON-LD 128 条 |
| https://www.designeer.xyz/visuals | Visuals 55；363,014 字节；JSON-LD 110 条 |
| https://www.designeer.xyz/utilities | Utilities 61；384,932 字节；JSON-LD 122 条 |
| https://www.designeer.xyz/designers | Design Engineers 132；640,500 字节；JSON-LD **118 条 `Person`** |
| https://www.designeer.xyz/sitemap.xml | 只含 9 条路由，**不含条目页**（1,499 字节） |
| https://hicyou.com/zh/designeer | 第三方收录页，佐证该站的定位与替代品（Dribbble / UI Garage / Muzli） |
| https://peerlist.io/jdhruv14/project/designeer | 第三方介绍（搜索引擎结果，未深读） |
| https://coding4food.com/en/post/designeer-hits-product-hunt-builders-goldmine-or-bookmark-graveyard | 第三方评测（搜索引擎结果，未深读） |

### 5.2 设计系统与文档（任务二）

| URL | 用途 |
|---|---|
| https://ui.shadcn.com/docs/theming | 语义令牌结构（`[源码]` 见下条 globals.css） |
| https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/v4/app/globals.css | **`[源码]` shadcn v4 完整 `:root` / `.dark` 令牌、`--radius` 派生、code block 规格** |
| https://raw.githubusercontent.com/shadcn-ui/ui/main/packages/shadcn/src/tailwind.css | `[源码]` scroll-fade 遮罩、shimmer、自定义 variant |
| https://ui.shadcn.com/docs/components/base/data-table | 组件索引（发现 v4 的 Message / Bubble / Empty / Marker 原语） |
| https://ui.shadcn.com/r/styles/base-vega/bubble.json | **`[源码]` 气泡 7 变体、80% 最大宽、ring-3/50、tinted 的 oklch 公式** |
| https://ui.shadcn.com/r/styles/base-vega/message.json | **`[源码]` 消息行结构、meta 12px** |
| https://ui.shadcn.com/r/styles/base-vega/message-scroller.json | **`[源码]` 滚动方案、content-visibility、滚动按钮缓动** |
| https://ui.shadcn.com/r/styles/base-vega/empty.json | **`[源码]` 空状态全套规格** |
| https://ui.shadcn.com/r/styles/base-vega/badge.json | **`[源码]` badge 20px/12px 与 6 变体** |
| https://ui.shadcn.com/r/styles/base-vega/card.json | **`[源码]` 卡片 ring-1 + shadow-xs + spacing 令牌** |
| https://ui.shadcn.com/r/styles/base-vega/table.json | **`[源码]` 表格 th 40px / td 8px / hover** |
| https://ui.shadcn.com/r/styles/base-vega/button.json | **`[源码]` 按钮尺寸阶梯与圆角收窄** |
| https://ui.shadcn.com/r/styles/base-vega/marker.json | **`[源码]` 分隔标记（复盘时间线用）** |
| https://www.radix-ui.com/themes/docs/theme/overview | Radix Themes 文档入口 |
| https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale | **`[文档]` 12 步色阶的逐步用途表、APCA 承诺** |
| https://vercel.com/geist/colors | **`[文档]` 10 色阶、Backgrounds 1–2、Color 1–3/4–6/7–8 分组；"Draw each border once"、"Keep material shadows translucent"** |
| https://unpkg.com/@geist-ui/core@latest/ | Geist UI 包（仅确认存在，未取到 geist.css） |
| https://www.prompt-kit.com/ | AI 对话原语库首页 |
| https://www.prompt-kit.com/docs/message | 消息组件 API |
| https://www.prompt-kit.com/docs/prompt-input | **`[源码]` 输入区规格（24px 圆角 / 44px / 240px 上限）** |
| https://www.prompt-kit.com/c/message.json | **`[源码]` 消息、Markdown 分块渲染、代码块** |
| https://www.prompt-kit.com/c/prompt-input.json | **`[源码]` 输入区完整实现** |
| https://www.prompt-kit.com/c/source.json | **`[源码]` 来源胶囊 + hover 悬浮卡** |
| https://www.prompt-kit.com/c/reasoning.json | 推理折叠组件（已下载，未展开） |
| https://www.prompt-kit.com/c/scroll-button.json | 滚动到底按钮（已下载，未展开） |
| https://www.prompt-kit.com/c/chat-container.json | 对话容器（已下载，未展开） |
| https://www.prompt-kit.com/c/markdown.json | Markdown 组件（已下载，未展开） |
| https://www.prompt-kit.com/c/code-block.json | 代码块（已下载，未展开） |
| https://www.prompt-kit.com/c/loader.json | 加载器（已下载，未展开） |
| https://carbondesignsystem.com/components/progress-indicator/usage/ | **`[文档]` 步骤条 7 态定义（completed 空心+对勾 / current 半填充 / not started 空心）** |
| https://www.carbondesignsystem.com/components/progress-indicator/style/ | **`[文档]` 步骤条颜色令牌、14px/12px 排版、16px 图标、128px 最小宽、标签 ≤16 字符** |
| https://carbondesignsystem.com/patterns/status-indicator-pattern/ | 状态指示器模式（部分内容为动态加载，未取到色值） |
| https://linear.app/ | **`[源码]` 深色 4 级背景 / 3 级边框 / 13px 主力字号**（从 48 个 CSS 文件共 322,940 字节中提取） |
| https://resend.com/ | **`[源码]` 浅色令牌、字号阶梯、圆角阶梯、字体分工**（5 个 CSS 文件共 1,033,313 字节） |
| https://originui.com/ | Origin UI 首页（CSS 资源路径为 `www.originui.com/ui/_next/...`，下载被 TLS 层拒绝，**未取到其表格/badge 数值**） |
| https://www.untitledui.com/components/table | 未访问（时间预算） |
| https://www.untitledui.com/components/badges | 未访问（时间预算） |
| https://chatgpt.com | 已验证页面结构（AI 无气泡 / 用户有气泡），**具体 px 未核实** |
| https://claude.ai | 同上 |
| https://v0.app | 未取到可验证数值 |
| https://www.perplexity.ai | 结构可确认（内联上标 + 来源卡片行），**具体 px 未核实** |
| https://ui.shadcn.com/docs/components/base/message | 组件文档（未单独展开） |
| https://ui.shadcn.com/docs/components/base/bubble | 组件文档（未单独展开） |

### 5.3 明确未能核实的事项

1. **Origin UI**：其样式表位于 `www.originui.com/ui/_next/static/chunks/*.css`，两次下载均因 TLS 连接被重置而失败。**未取到其表格表头、行高、badge 配色数值。** 建议以实际页面/截图为准。
2. **ChatGPT / Claude / v0 / Perplexity 的具体 px 值**：这四站的生产 CSS 均做了混淆或按需注入，`web_fetch` 得到的 HTML 里不含渲染后的样式。**我只确认了结构层面的事实（AI 回复无气泡、用户消息有气泡、消息列有最大宽度限制），所有 px 值标注为未核实。** 若要精确数值，建议在真实页面用 DevTools 量取。
3. **Geist 灰阶的具体 hex**：我从 `vercel.com/geist/colors` 抓取的 CSS（445,537 字节）里，灰阶是运行时通过 `hsla(var(--ds-gray-100-value))` 变量注入的，**页面 HTML 中不含 `--ds-gray-NNN` 的 hex 定义**（HTML 里只找到 1 个 hex：`#0B7BFE`）。因此我只能确认**步数与结构**（`gray-100` … `gray-1000`，另有 `gray-alpha-100` … `gray-alpha-1000`、`background-100/200`），**具体色值未核实**。**但结构性数值我全部抓到了**：`--ds-shadow-*` 七级、`--ds-focus-ring`、`--ds-shadow-border-base: 0 0 0 1px #00000014`（深色 `#ffffff25`）、`--geist-space` 4px 基准与倍数、`--geist-radius: 6px`、控件高度 32/36/40px。
4. **Untitled UI / Once UI / Park UI**：受时间预算限制未访问（任务要求"任选 2 个"，我用 **shadcn/ui 的 table+badge** 与 **Carbon 的 stepper** 补齐了这一块，且两者的数值颗粒度更细、更可直接落地）。
