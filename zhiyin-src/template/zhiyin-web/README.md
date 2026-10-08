# 职引 · 前端（zhiyin-web）

Vue 3 + TypeScript + Vite。三条路由，全是**真实数据驱动**：门户、控制台、报告。

产品与业务口径以 [docs/职引-完整设计文档.md](../../../docs/职引-完整设计文档.md) 为准，
本文件只讲前端自己的事：怎么跑、东西放哪、数据从哪来。

## 一、怎么跑

```bash
cd zhiyin-src/template/zhiyin-web

npm install
npm run dev          # http://127.0.0.1:5173（vite 把 /api 代理到 8000）
npm run typecheck    # vue-tsc
npm run build        # typecheck + 产出 dist/
```

后端没起时界面**如实报错**（"连不上后端"），不回落本地假数据 ——
假数据会让"没实现"看起来像"已经实现"，那比报错贵得多。

开发期要指到别的后端：`ZHIYIN_API_TARGET=http://127.0.0.1:8012 npm run dev`。

### 一个会骗人的坑：改完看起来"没生效"

同一秒里连着改同一个文件的多处（例如批量替换），vite 的文件监听可能只捕到**中间那一版**，
然后一直供那份转换结果：源码是新的、页面是旧的，浏览器里怎么刷新都一样，
`?t=` 也停在旧时间戳。**症状**是"我明明改了，真机上没变"。

遇到过就做其中之一（都能立刻恢复）：

- 碰一下入口：改一处 `src/main.ts` 的注释（入口变了，整张模块图作废）；
- 或者重启 `npm run dev`。

排查时先在页面里 `fetch('/src/…/Xxx.vue')` 看服务端供的是哪一版 —— 别靠肉眼猜。

### 部署形态

`Dockerfile` 是两段构建：Node 装依赖 + `npm run build` → nginx 托管 `dist/`。
`nginx.conf` 里两条规则：SPA 回退（`try_files … /index.html`）与 `/api` 反代到
应用容器（`proxy_buffering off`，否则 SSE 会被攒住不下发）。
前端产物里的接口基地址是**相对路径** `/api/v1`，所以两种形态同一条路径。

## 二、页面 → 组件 → 接口

「页面文件」与「主要组件」两列必须是真实存在的文件（`tests/test_frontend_alignment.py` 双向校验）。

| 页面 / 区块 | 路由 | 页面文件 | 主要组件 | 后端接口 |
| --- | --- | --- | --- | --- |
| 门户 | `/portal` | `views/PortalView.vue` | `portal/HeroMap`、`portal/InkField`、`portal/InkButton`、`portal/MapStopNode`、`vendor/vuebits/{BlurText,VariableProximity,Magnet,MagnetLines,ClickSpark}` | `GET /app/bootstrap` |
| 控制台 · 画布 | `/` | `views/ConsoleView.vue` | `console/{AgentRail,Bubble,PortraitBubble,TodoBubble,TalkBubble,MarketBubble,PeopleBubble,ReviewBubble,CollectBubble,CalendarBubble,AchievementsBubble}`、`console/{NextAsk,CanvasMenu}`、`float/{FloatLayer,FloatCard}`、`composables/useCanvasDrag`、`lib/tiling` | `GET /app/workspace`、`POST /app/conversation/message`、`GET /app/notifications/pending` |
| 控制台 · 覆盖层 | `/` | `views/ConsoleView.vue` | `console/{PortraitOverlay,TasksOverlay,TalkOverlay,CollectOverlay,IntelOverlay,BriefOverlay,BindOverlay,TimetableOverlay,MatchOverlay,PlansOverlay,ActionOverlay,SessionsOverlay,ReviewOverlay,CalendarOverlay,AchievementsOverlay,BlocksOverlay}`、`console/{Overlay,EvidenceDrawer}`、`portrait/{PortraitSummary,PortraitChart,PortraitFieldList,PortraitDetail,PortraitEmpty}`、`render/RenderableBlock`、`charts/MatchMatrix`、`charts/Timetable` | `POST /app/dimensions/{id}`、`POST /app/gaps/{id}/clarify`、`POST /app/brief/today`、`GET /app/plan/directions`、`POST /app/plan/directions/{id}/select`、`GET /app/plan/action`、`PATCH /app/plan/action/tasks`、`GET /app/calendar`、`GET /app/achievements`、`GET /app/sessions`、`GET /app/sessions/{id}/turns`、`GET /app/track/events`、`POST /app/plan/timetable`、`POST /app/plan/todos/suggestions`、`POST /app/match/careers`、`POST /app/chsi/bind`、`GET|POST|PATCH|DELETE /app/notes`、`POST /app/academic/import`、`POST /app/academic/import/file`、`POST /app/conversation/material`、`GET /app/theory-cards/{id}`、`GET /app/intel`、`POST /app/intel/refresh` |
| 报告 | `/report` | `views/ReportView.vue` | `ai/AiFrame`、`charts/{TrendLine,ChartFrame,SketchPath}` | `GET /app/report/full-text`、`POST /app/report/summary`、`GET /app/assets/report/versions`（版本历史）、`POST /app/assets/export` |
| 全局外壳 | 全部 | `App.vue` | `auth/{AuthLayer,AccountMenu}`、`guide/GuideDock`、`theme/{LookPanel,LookTrigger}`、`ui/GlyphIcon` | `POST /app/auth/login`、`POST /app/auth/register`、`POST /app/auth/logout` |
| 登录态与路由 | — | `router.ts` | — | `GET /app/task/enter` |

`charts/SketchPath` 与 `lib/sketch.ts` 是**门户那张手绘地图**的底座（线、框、圆都经它落到 SVG）。
控制台与报告里的图表（`charts/TrendLine`、`charts/ChartFrame`）走规整 SVG，不走它 —— 
它们画的是数据，笔触会干扰读图。

## 三、数据从哪来（前端不自造数据）

| 数据 | 来源 | 落在哪 |
| --- | --- | --- |
| 路由与鉴权 | 本地 `router.ts`（页面归属） + `GET /app/bootstrap`（**只取 `identity` / `task_entries` / `app_name`**；`menus` / `routes` / `copy_bundle` / `feature_flags` 等字段接口会给，一期前端还没读，属预留） | `stores/session.ts` |
| 画像字段（key / 值 / 把握度 / 来源 / 证据） | `GET /app/workspace` 的 `profile_panel` | `PortraitBubble`、`PortraitOverlay` |
| 采集动线（还缺什么、去哪取） | 同上，`collection_panel` | `CollectBubble`、`CollectOverlay` |
| 课表与成绩单 | 同上，`academic_panel`；导入有两手：`POST /app/academic/import`（粘贴原文）与 `POST /app/academic/import/file`（上传文件，multipart，由后端识别 UTF-8 / GBK 编码） | `TimetableOverlay`、`charts/Timetable`、`BindOverlay` |
| 对话里交的材料（简历等） | `POST /app/conversation/material`（multipart 上传，回执只有"名字 / 大小 / 字数"）；发消息时用 `material_ids` 挂上，正文只在服务端进模型输入 | `TalkOverlay` |
| 气泡编排（哪块先出现） | 同上，`layout_panel` | `ConsoleView` |
| 待办 | `GET|POST|PATCH|DELETE /app/notes` | `TasksOverlay`、`TodoBubble` |
| 通知浮窗 | `GET /app/notifications/pending` | `float/FloatLayer` |
| 报告正文（15 维 / 判定 / SWOT / 来源） | `GET /app/report/full-text` | `ReportView` |
| ③ 方向方案（三套 + 当前选择） | `GET /app/plan/directions`；选择走 `POST /app/plan/directions/{id}/select` | `PlansOverlay` |
| ④ 行动计划（阶段 / 任务 / 现在这一件） | `GET /app/plan/action`；勾任务走 `PATCH /app/plan/action/tasks` | `ActionOverlay` |
| 关键节点日历 | `GET /app/calendar`（规划师写入、界面读取） | `ActionOverlay` |
| 任务会话与逐轮历史 | `GET /app/sessions`、`GET /app/sessions/{id}/turns` | `SessionsOverlay` |
| 跟踪时间线（复盘） | `GET /app/track/events` | `ReviewOverlay` |
| 门户文案（公开） | `GET /app/portal` 的 **`copy_bundle`（`portal.*`）**（**不需要登录**）；同一回包里的 `banners` / `faqs` / `trust_blocks` 一期没读，属预留 | `PortalView`、`HeroMap` |
| 资产版本与导出 | `GET /app/assets/{type}/versions`、`POST /app/assets/export` | `ReportView` |
| 维度解读 / 结论段 / 课件建议… | 8 个 SSE 端点，见 `src/ai/registry.ts` | `ai/AiFrame` 包住的各块 |
| 理论卡正文 | `GET /app/theory-cards/{id}`（回包里只有 id 与名字，正文按需取） | `AgentRail` 的"这一轮的依据" |
| 接口类型 | `npm run gen:api` 由 `../contracts/openapi.json` 生成 `src/api/types.ts` | `src/api/client.ts` 全部视图类型 |

## 四、目录职责

| 目录 / 文件 | 职责 |
| --- | --- |
| `src/api/client.ts` | 唯一请求出口：相对基址 `/api/v1`、令牌注入、信封解析（1004 登录 / 1007 依赖不可用 / 其余如实抛）、各端点函数 |
| `src/api/types.ts` | **生成物**：`npm run gen:api` 按 `contracts/openapi.json` 生成。不要手改；`npm run check:api` 在 CI 里比对 |
| `src/ai/` | AI 任务清单（`registry.ts` 的 key ↔ 后端端点）、SSE Provider（`httpProvider.ts`）、任务状态机（`useAiTask.ts`）、`AiFrame` 用的形状（`types.ts`） |
| `src/stores/session.ts` | 会话状态：后端回包与工作台数据的唯一落点；组件只读它 |
| `src/views/` | 三个页面；`src/router.ts` 是路由与登录拦截 |
| `src/components/` | `console/` 控制台、`float/` 浮窗、`portal/` 门户、`auth/` 登录、`render/` 可视件按 kind 分发、`charts/` 图表、`ai/` 生成外壳、`guide/` 便签、`vendor/vuebits/` 引用的开源动效件 |
| `src/lib/` | 纯函数：`sketch`（手绘路径）、`tiling`（气泡布局）、`asks`（下一步编排）、`guide`（便签内容）、`identity`（首字母与角色名）、`failure`（把读取失败翻成用户能懂的一句话）、`theme`（皮肤注册表与换肤） |
| `src/styles/` | `tokens.css` 设计令牌（三层：原始值 → 语义别名 → 具体物件；组件只认令牌）、`themes/` 配色（每套一个文件：覆盖令牌 + 自己世界里的少量零件规则）、`ui/` 组件风格（每套一个文件：只覆盖形状令牌 + 零件形状规则，不许碰颜色）、`base.css` 基础样式与通用零件（`surface` / `sheet` / `btn` / `chip`）、`glass.css` 磨砂的开关与实底、`motion.css` 动效、`fonts.css` 自托管字体（站酷快乐体 + MiSans） |
| `src/data/` | **只放界面形状**（`content.ts` / `student.ts` 的刻度 / `portal.ts` 的八站坐标与曲线）。业务数据和文案一律来自后端 —— 门户的主张、按钮、八站标签都在 `data/registry/copies.json` 的 `portal.*` 里 |

### 四.1 换一套样子（七条轴的调配台）

外观不是一个开关，是**七条互不相干的轴**，各自切换、自由组合（4 × 6 × 3 × 3 × 2 × 3 × 3 = **3888 种**）：

| 轴 | 属性 | 管什么 | 文件 | 允许声明 |
| --- | --- | --- | --- | --- |
| **配色** | `html[data-theme]` | 色、材质、质感、光标、动效节奏 | `src/styles/themes/<档>.css` | 61 条颜色与材质令牌（契约） |
| **组件** | `html[data-ui]` | 形（圆角/描边/影）、密度（间距/字号/行高）、字 | `src/styles/ui/<档>.css` | 43 条形/密度/字令牌 |
| **交互** | `html[data-feedback]` | 反馈落在哪一层：位移 / 描边 / 底色 | `src/styles/feedback/<档>.css` | 一个都不许（纯规则） |
| **排版** | `html[data-type]` | 章节编号、行宽、对齐、段距 | `src/styles/type/<档>.css` | 一个都不许 |
| **形状** | `html[data-shape]` | 角的写法：手绘（四角长短不一） | `src/styles/shape/<档>.css` | 一个都不许 |
| **骨架** | `html[data-skeleton]` | 覆盖层怎么打开：居中 / 抽屉 / 全幅 | `src/styles/skeleton/<档>.css` | 一个都不许 |
| **字体** | `html[data-font]` | 字族与字形（手写 / 精修 / 衬线） | `src/styles/font/<档>.css` | 只 `--font-*` |

注册表在 `lib/theme.ts` 的 `AXES`；每档 = 一个 CSS 文件 + 注册表一项 + 索引一行 `@import` + 首屏表一项（漏一处会被 `tests/test_theme_contract.py` 挡住）。

- **逐条轴只许声明自己那一类令牌**，这是七条轴不互相顶掉的唯一机制：越界的后果不是"难看"，而是两条轴开始抢同一个变量 —— 症状永远是"某一处没跟着变"，没有任何报错。守卫逐档钉着。
- **顺序就是胜负**：七条轴特异度全是 (0,1,1)，`base.css` 里的顺序是 配色 → 组件 → 交互 → 排版 → 形状 → 骨架 → **字体**；守卫会比对，顺序改错会被拦下。字体排最后是有意的：组件轴的 `roomy`/`mono` 也写 `--font-*`，而"字体"这一栏是用户明确做过的选择，应当压过组件风格附带的字体性格。
- **默认档都没有文件**（`sketch` / `card` / `rise` / `plain` / `box` / `center` / `sketch`）—— 不写属性就是 `tokens.css` 与 `base.css` 里今天的样子，所以"不切"与改动前逐字一致。
- **字体轴只改字**：改 `--font-*`（标题 / 正文 / 大字排版各自的出口），不动字号、字重与间距。三档都用仓库里已有或系统必有的字（站酷快乐体、MiSans、Fraunces、系统宋体），不为一个可选档下载中文衬线（那类字体动辄十几 MB）。
- **轴文件不许写布局属性**：`position` / `inset` / `top` / `z-index` / `float` 这类在轴文件里一律不许出现（伪元素除外）。轴文件叠在组件之上，它看得见 `.sheet`，却不知道那个 `.sheet` 是浮层还是文档流里的一张纸 —— 2026-10-08 折角那档给 `.sheet` 写了 `position: relative`，把外观台面板的 `position: fixed` 顶掉，面板掉进文档流，"外观台打不开了"。需要视觉元素时用背景图（折角现在就这么画），或依赖宿主已有的定位。守卫 `test_axis_files_do_not_reposition_components` 钉着。
- **`--ink-4` 不许承载信息**：它在四套配色里实测只有 2.50–3.14:1，是"装饰线的浓淡"；日期数字、面包屑、字段名、图表标题这类要读的字必须用 `--ink-3`（≥5.6:1）。允许用它当文字色的地方冻在一张白名单里（抓手、箭头、空槽占位），新增一处守卫就失败。
- **字与形分家（2026-10-08 精简）**：字族只归字体轴；组件轴只管形、密度与字号。原来组件轴的 `roomy` 声明过 Fraunces、`mono`（现已改名 `archive`「档案」）声明过三处等宽栈 —— 两条轴抢同一件事，用户不知道哪一栏说了算，而且字体轴不是默认档时那几行就是死代码。字体轴里的 `noto`（思源）也一并砍掉：它与 `clean` 意图重复，只差一个多数人叫不出名字的字形。
- **砍的是重复，不是"没效果"（同一天的第二批）**：外观的每一档都用无头 Chrome 同机位截图 + 逐像素差量过（见下），**没有一档是 0 变化**；被砍的三处都是"两种说法讲同一件事" —— 组件轴的 `ledger`（表格）与 `archive`（档案）都是印刷件语言（留档案：它多了硬边影与大写字段名）、形状轴的 `ticket`（票根齿孔）把卡片当票据且孔距与块宽对不齐（换成折角）、字体轴的 `noto`（思源）。
- **外观的可测流程**：改完外观先跑 `.tmp-shots/audit.py`（无头 Chrome 逐档截图 + 像素差 + 差异区域），再挑几张裁到 100% 看细节（`.tmp-shots/crop.py`）。工具与原因见仓库根的 `DESIGN.md` 第十三条。启动无头 Chrome 需要一次性完整权限（它的进程间通信走命名管道），数据目录与截图都放系统临时区，不落进仓库。
- **曾经还有一条「线条」轴**（`data-draw`，手绘 ↔ 精确：改 roughjs 抖动系数），2026-10-08 撤掉 —— 它的效果只在门户地图与趋势线上看得见，在控制台那屏点它毫无变化，会被合理地当成"坏了"。能力留着（`lib/sketch.ts` 的 `setRoughnessScale`/`bumpSketch`、`tokens.css` 的 `--sketch-rough`），只是暂时没有开关。
- 切换入口：三处「外观台」三个字（`components/theme/LookTrigger.vue`）—— 控制台左上角账号那颗的右边、报告页顶栏左栏、门户页右上角；点开是**矩阵面板**（`components/theme/LookPanel.vue`：一行一条轴、一列一个档，当前档整格点亮，改过的那一行有 ↺ 单独退回，底部显示当前搭配、可复制链接，另有「随机一套」与「重置为默认」；面板不做成模态，身后那块界面就是实时预览）。也可以在账号面板里直接切配色/组件两行，或用 `?theme=<档>&ui=<档>&feedback=<档>&type=<档>&shape=<档>&skeleton=<档>&draw=<档>`（不落盘）。选择只记在 localStorage 的 `zhiyin_<轴>`，不进账号。
- 首屏：`index.html` 里那段同步脚本按同一张表在第一帧前写好这些属性，避免暗色配色闪一屏亮色；那张表由守卫与 `AXES` 比对。
- **在 JS 里落笔的颜色**（ECharts 的 canvas、ClickSpark 的 canvas、rough-notation 的手绘圈）读不到 `var()`，必须由 JS 取已解析的值，并在 `THEME_EVENT` 上重取 —— 见 `lib/theme.ts` 与 `PortraitChart.vue` / `PortalView.vue`。
- 打印（报告页的「打印 / 存 PDF」）会临时把**配色轴**切回默认再换回来：暗色配色打印是一张黑纸。其余六条轴是形、密度、字与字体，打印没有理由改它们。

## 五、几条硬约定

1. **接口字段不许手抄。** 视图类型全部从 `src/api/types.ts` 取；后端改字段 →
   `python scripts/export_openapi.py` → `cd zhiyin-web && npm run gen:api`。
   `npm run check:api` 会在 CI 里比对生成物与快照。
2. **前端不生成业务内容。** 维度得分、结论、证据、匹配矩阵都是后端产出；
   前端只渲染，并把 `citations` 挂到抽屉里让人能核对。
3. **失败要看得见。** 不写本地 mock 回落；后端没起、依赖没配就如实显示错误。
4. **长内容不进对话流。** 对话只说最短结论，全文走覆盖层与报告页。
5. **一个数只有一个来源。** "还差几条""整体把握"这类数字都从 `session` 读，
   组件不自己数 —— 采集策略在后端，前端自己算就会和它说的不一样。
