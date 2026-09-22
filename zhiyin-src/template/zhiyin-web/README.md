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
| 控制台 · 画布 | `/` | `views/ConsoleView.vue` | `console/{AgentRail,Bubble,PortraitBubble,TodoBubble,TalkBubble,MarketBubble,PeopleBubble,ReviewBubble,CollectBubble,CalendarBubble}`、`console/{NextAsk,CanvasMenu}`、`float/{FloatLayer,FloatCard}`、`composables/useCanvasDrag`、`lib/tiling` | `GET /app/workspace`、`POST /app/conversation/message`、`GET /app/notifications/pending` |
| 控制台 · 覆盖层 | `/` | `views/ConsoleView.vue` | `console/{PortraitOverlay,TasksOverlay,TalkOverlay,CollectOverlay,IntelOverlay,BriefOverlay,BindOverlay,TimetableOverlay,MatchOverlay,PlansOverlay,ActionOverlay,SessionsOverlay,ReviewOverlay,CalendarOverlay}`、`console/{Overlay,EvidenceDrawer}`、`portrait/{PortraitSummary,PortraitRadar,PortraitFieldList,PortraitDetail,PortraitEmpty}`、`charts/MatchMatrix`、`charts/Timetable` | `POST /app/dimensions/{id}`、`POST /app/gaps/{id}/clarify`、`POST /app/brief/today`、`GET /app/plan/directions`、`POST /app/plan/directions/{id}/select`、`GET /app/plan/action`、`PATCH /app/plan/action/tasks`、`GET /app/calendar`、`GET /app/sessions`、`GET /app/sessions/{id}/turns`、`GET /app/track/events`、`POST /app/plan/timetable`、`POST /app/plan/todos/suggestions`、`POST /app/match/careers`、`POST /app/chsi/bind`、`GET|POST|PATCH|DELETE /app/notes`、`POST /app/academic/import`、`GET /app/theory-cards/{id}`、`GET /app/intel`、`POST /app/intel/refresh` |
| 报告 | `/report` | `views/ReportView.vue` | `ai/AiFrame`、`charts/{TrendLine,ChartFrame,SketchPath}` | `GET /app/report/full-text`、`POST /app/report/summary`、`GET /app/assets/report/versions`（版本历史）、`POST /app/assets/export` |
| 全局外壳 | 全部 | `App.vue` | `auth/{AuthLayer,AccountMenu}`、`guide/GuideDock` | `POST /app/auth/login`、`POST /app/auth/register`、`POST /app/auth/logout` |
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
| 课表与成绩单 | 同上，`academic_panel` | `TimetableOverlay`、`charts/Timetable` |
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
| `src/components/` | `console/` 控制台、`float/` 浮窗、`portal/` 门户、`auth/` 登录、`charts/` 图表、`ai/` 生成外壳、`guide/` 便签、`vendor/vuebits/` 引用的开源动效件 |
| `src/lib/` | 纯函数：`sketch`（手绘路径）、`tiling`（气泡布局）、`asks`（下一步编排）、`guide`（便签内容）、`identity`（首字母与角色名）、`failure`（把读取失败翻成用户能懂的一句话） |
| `src/styles/` | `tokens.css` 设计令牌（丝网印：平涂 / 零阴影 / 发丝线）、`base.css` 基础样式与印刷零件（贴纸 / 胶带 / 折痕）、`glass.css` 玻璃的停用说明、`motion.css` 动效、`fonts.css` 自托管字体（得意黑 + MiSans） |
| `src/data/` | **只放界面形状**（`content.ts` / `student.ts` 的刻度 / `portal.ts` 的八站坐标与曲线）。业务数据和文案一律来自后端 —— 门户的主张、按钮、八站标签都在 `data/registry/copies.json` 的 `portal.*` 里 |

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
