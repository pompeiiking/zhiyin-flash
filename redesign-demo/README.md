# 职引 · 学生空间演示

独立的 Vue 3 + TypeScript + Vite 前端工程，演示大学生从对话、了解自己到方向选择、行动与复盘的使用过程。原工程与管理员端不在本次范围内。

门户采用左右布局的试稿：左侧品牌主张与入口，右侧可切换对话、依据和行动示例。顶栏提供「新版 / 原版」切换，方便演示比较。保留已有配色；点击入口或完成登录后均进入对话。学生空间顶端放身份与工具，底部始终显示「对话、任务与计划、学生档案、评估报告、复盘记录」五个入口，各功能可以独立进入。

## 运行

在 PowerShell 中执行：

```powershell
cd D:\zhiyin-flash\redesign-demo
npm.cmd ci
npm.cmd run dev -- --port 5274
```

打开 [本次预览](http://127.0.0.1:5274/)。`vite.config.ts` 默认端口仍为 `5273`，并启用 `strictPort`；本次明确使用 `5274`，因为 `5273` 属于另一个 checkout。

## 常用地址

Sites 站点配置在 .openai/hosting.json；本轮按用户要求设为公有。发布源码副本在本地忽略的 .sites/frontend，与原项目 Git 分支分开，由 Sites 的 source helper 同步。站点地址：https://zhiyin-frontend-demo-v2.peppy-sugar-7626.chatgpt.site

地址使用 hash 路由，以下路径接在 `http://127.0.0.1:5274/` 后面。

| 路径 | 当前内容 |
| --- | --- |
| `#/` | 公开门户，进入后的第一页是对话 |
| `#/?portal=classic` | 改版前门户，保留供对比 |
| `#/chat?as=mid` | 已有内容的示例对话；档案与聊出的事按需展开 |
| `#/home?as=mid` | 今日最小任务、任务分组与完成记录 |
| `#/plan?as=mid` | 里程碑、本周任务、关键日历、任务来源 |
| `#/profile?as=mid` | 已有事实、来源筛选、依据与更正 |
| `#/report?as=mid` | 结论与差距、可展开的分值与依据 |
| `#/report?as=mid&focus=choose` | 三条方向对比、选择与改选 |
| `#/report?as=mid&focus=versions` | 预置报告版本与变化 |
| `#/review?as=mid` | 完成记录、任务/方法/方向归因与下一步 |
| `#/chat?as=fresh` | 空白账号，从第一个问题开始 |
| `#/review?as=stale` | 三天未动账号的陪伴提醒示例 |
| `#/home?as=mid&grade=freshman` | 大一场景；另可用 `sophomore`、`junior`、`senior` |
| `#/path?as=mid` | 四个年级的场景与操作路径 |
| `#/spec` | 公开设计规范 |

未登录直达内页会自动进入 `mid` 演示账号。`as` 参数只在未登录时生效；切换 `fresh` / `mid` / `stale` 前，可在右上角账号面板退出登录。`dir=d1` 可预置尚未选择的方向。外观可用 `theme=light|dark|system`、`accent=blue|red`、`style=plain|soft|dense` 指定，地址参数本身不保存为外观偏好。

## 演示边界

所有学校信息、岗位依据、报告分值、历史记录、里程碑与 2026 年 10 月日历均为预置示例。对话按本地关键词返回示例回答，未接入真实模型、学校系统、核验服务或业务后端。

任务完成/恢复、采纳/否决建议、拆小、加入今天、档案更正、方向改选和复盘归因会改变当前页面状态。方向切换展示影响范围，不自动重算报告与计划；报告版本页切换的是预置快照，详细分值仍使用第 3 版示例。

仅登录账号和外观偏好写入 `localStorage`。其余演示修改保存在当前页面会话的内存中，刷新会回到预置状态；切换年级会重置该场景的任务与采集进度。右上角账号面板提供「复位演示数据」和「恢复操作引导」。

## 检查与设计记录

```powershell
npm.cmd run build
node scripts/check-contrast.mjs
node scripts/check-classes.mjs
```

构建包含类型检查；对比度脚本检查已登记的颜色组合及字号令牌，类名脚本检查全局样式与组件 scoped 样式的布局类冲突。它们不能替代浏览器里的排版与交互检查。实际检查结果和剩余问题见 [视觉与交互检查记录](design-review/QA.md)。

当前浏览器截图保存在 `design-review/`：桌面为 `*-desktop.jpg`，手机包含 [对话](design-review/chat-mobile.jpg)、[今日任务](design-review/home-mobile.jpg) 和 [报告](design-review/report-mobile.jpg)，另有横屏对话。它们是实际浏览器捕获的 JPEG；操作路径页使用 `public/shots/v2-*.jpg`。`public/shots/` 中旧 PNG 是历史资产，不作为本轮改版的验收依据。

产品约束见 [PRODUCT.md](PRODUCT.md)，本轮方向见 [DESIGN-BRIEF.md](DESIGN-BRIEF.md)，实际设计系统见 [DESIGN.md](DESIGN.md) 与 [.impeccable/design.json](.impeccable/design.json)。当前六个业务页面由 `ConversationView`、`TodayView`、`StudentView`、`AssessmentView`、`RoadmapView`、`ReflectionView` 实现；版式与令牌分别在 `src/styles/workspace.css` 和 `src/styles/tokens.css`。旧业务视图与外壳组件保留作参考，当前路由和 `App.vue` 使用新组件。
