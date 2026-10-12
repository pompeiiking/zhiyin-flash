# 职引 · 学生空间演示

对话页已修订：去掉右侧常驻画像与路线图，按用户消息、顾问回答、依据、交接和行动建议分层。实际参考及取舍见 [chat-hierarchy/REFERENCES.md](design-review/chat-hierarchy/REFERENCES.md)。访问 `http://127.0.0.1:5276/#/chat` 查看当前版本。

2026-10-12 三页面视觉试改：咨询、今日行动、方向方案新增路径图形、职业示意图、成果概览与完成反馈，导航同步调整分组。本地预览端口为 5276，运行命令为 `npm.cmd run dev -- --port 5276`。最新截图与验证记录位于 [journey-pilot/QA.md](design-review/journey-pilot/QA.md)；下文 V5 记录保留作为此前基线。

独立的 Vue 3 + TypeScript + Vite 前端工程，演示学生通过咨询了解个人情况、比较职业方向、安排任务与复盘。本次 V5 仅修改 `redesign-demo`，后端、原前端与管理员端不在范围内。

门户保留品牌主张、蓝红灰配色与原版对比，登录成功和已登录入口均进入咨询。V5 延伸完整学生空间：内嵌主画布、页内视图、方向对照、任务概览、咨询依据与复制反馈、响应式补充面板、空态及来源层次。正文保持 16px，新增图形为本地 SVG，未增加 npm 依赖。资源取舍见 [RESOURCE-SELECTION.md](design-review/RESOURCE-SELECTION.md)，内容判断见 [CONTENT-AUDIT.md](design-review/CONTENT-AUDIT.md)，接口边界见 [BACKEND-ALIGNMENT.md](BACKEND-ALIGNMENT.md)。

## 运行

```powershell
cd D:\zhiyin-flash\redesign-demo
npm.cmd ci
npm.cmd run dev -- --port 5275
```

打开 [本次预览](http://127.0.0.1:5275/)。默认端口为 5273；本次使用 5275，5273 / 5274 属于其他 checkout。

## 导航与地址

桌面咨询置顶，一级菜单「生涯分析、计划管理、资讯与记录」可同时展开；进入页面时只补充展开所属组，保留其它组。侧栏可整体收起，内容区随之扩展，顶栏按钮可重新展开并保留本次菜单状态。账号保持唯一入口：侧栏展开时在左下，收起时在顶栏右上。全部历史会话位于业务菜单下方。移动底栏为「对话、行动、画像、报告、更多」；更多面板使用同一二级目录，账号仅右上，咨询保留新对话与历史入口。顶部可切换布局，窄于 1000px 时使用移动导航。

以下 hash 路径接在预览地址之后：

| 路径 | 内容 |
| --- | --- |
| `#/` | 公开门户；进入后首先到咨询 |
| `#/?portal=classic` | 改版前门户 |
| `#/chat?as=mid` | 咨询、会话恢复、材料与成果 |
| `#/profile?as=mid` | 个人画像、来源、更正与待补充项 |
| `#/academic?as=mid` | 独立学籍与资料页；导入、撤回与核验示例 |
| `#/report?as=mid` | 诊断结果、分值与依据 |
| `#/report?as=mid&focus=versions` | 预置版本记录 |
| `#/directions?as=mid` | 独立方向比较、选择与影响范围 |
| `#/home?as=mid` | 行动计划的今日行动视图 |
| `#/plan?as=mid` | 同一行动计划的阶段视图；里程碑、执行任务、来源 |
| `#/schedule?as=mid` | 独立日历与课表 |
| `#/notes?as=mid` | 待办与目标、去重、完成与恢复 |
| `#/intel?as=mid` | 岗位资讯来源示例与检索 |
| `#/review?as=mid` | 任务分析、调整建议、执行时间线与完成记录 |
| `#/tools?as=mid` | 应用工具演示入口 |
| `#/chat?as=fresh` | 空白账号 |
| `#/review?as=stale` | 三天未行动账号提醒示例 |
| `#/home?as=mid&grade=freshman` | 大一场景；另支持 sophomore / junior / senior |
| `#/path?as=mid` | 四个年级的场景与操作路径 |
| `#/spec` | 公开设计规范 |

旧地址 `/report?focus=choose` 自动转向 `/directions`。报告只保留诊断结果与版本记录；方向没有重复报告页签。画像与学籍独立，阶段计划不再内置日历。

未登录直达内页进入 `mid` 演示账号。`as` 仅在未登录时初始化账号，切换账号先通过账号面板退出。`dir=d1` 可预置尚未选择的方向。外观参数支持 `theme=light|dark|system`、`accent=blue|red`、`style=plain|soft|dense`，地址参数本身不保存偏好。

## 演示与接口边界

学校资料、报告分值、岗位统计、阶段百分比、历史时间线与 2026 年 10 月日历均为预置示例。对话返回本地示例，UI 未调用正式 API、真实模型、学校系统、学信网或实时招聘服务。

任务完成/恢复、建议采纳/拒绝、拆小、安排执行、画像更正、方向改选、复盘归因与待办操作更新当前会话。方向变化只展示影响范围，不自动重算。版本为预置快照；诊断结果和详细分值使用第 3 版示例，选旧版进入版本记录，打印当前视图。

账号、外观、导航布局与桌面侧栏收起偏好存入 localStorage。菜单展开集合保留在本次组件会话，不承诺刷新后恢复。业务修改、引导收起和草稿仅为当前页面会话状态，刷新恢复预置数据；切年级重置场景任务与采集进度。账号面板提供复位演示数据与恢复操作引导。

`sync:backend` 生成 69 个 schema 与后端功能目录；`check:backend` 校验生成文件及 50 个学生操作的 method/path。50 项目录校验不表示 50 项 API 已接入。JSON/multipart 与 SSE transport 已提供，页面仍用本地状态，未执行真实端到端测试。

实际 controller、DTO、业务服务与动态资源的核对见 [BACKEND-AUDIT-V5.md](design-review/BACKEND-AUDIT-V5.md)：主要页面能力有对应，但当前不能认定完整业务对齐。固定画像键与服务端词表、撤回后的画像摘要、消息可视件/管线/变化资产、完整 15 维报告/SWOT/来源/待重算状态，以及 AI 和动态模块仍有接入或展示差异。69/50 属于契约目录检查，视觉 SHIP 仅评价演示界面，均不能替代业务接入验收。

## 检查与设计记录

```powershell
npm.cmd run build
npm.cmd run check:backend
node scripts/check-classes.mjs
node scripts/check-contrast.mjs
git diff --check
```

V5 构建（含类型检查）、后端目录、类名与颜色/字号门禁已通过：69 schema / 50 学生操作 method/path，必过文字对比度项在四套颜色组合下 ≥ 4.5:1，六档字号登记通过。浏览器证据与交互边界见 [desktop-v5/QA.md](design-review/desktop-v5/QA.md)。当前 33 张浏览器 JPEG 位于 `design-review/desktop-v5/`：12 个业务桌面页、6 个业务手机页、13 个基线特殊视图及 2 个追加导航视图。测试视口包括 1280×720、390×844、1440×900 宽屏、1280×600 短屏；截图像素尺寸见 [SHOT-PROVENANCE.json](design-review/desktop-v5/SHOT-PROVENANCE.json)。

操作路径使用 `public/shots/v5-{portal,chat,profile,report,directions,home,review}.jpg`，各 `.jpg.json` 记录浏览器截图来源，无 AI 生成位图。复制调用成功且按钮反馈正确，但剪贴板读回为空，未验证字节相等；减少动效仅检查源码。V4 的 [QA](design-review/desktop-v4/QA.md)、截图与指南副本保留为历史，V3 及更早图片同样不替代当前证据。

产品约束见 [PRODUCT.md](PRODUCT.md)，方向见 [DESIGN-BRIEF.md](DESIGN-BRIEF.md)，tracked [DESIGN.md](DESIGN.md) 是当前设计系统主依据；本地 `.impeccable/design.json` 为补充记录。Reka UI Accordion 用于受控菜单、路由同步与键盘交互，Tabs 用于页内视图；CSS 与 Vue TransitionGroup 提供动效。Motion 仅作研究，未安装。Impeccable CLI/detector 未安装，本轮独立收尾审阅见 [FINISH-REVIEW.md](design-review/desktop-v5/FINISH-REVIEW.md)；Stitch 没有生成结果，Taste 仅局部审查参考，Designeer 使用本地目录。

## 历史发布

既有 Sites 配置在 `.openai/hosting.json`，历史发布副本为本地忽略的 `.sites/frontend`。此前公开地址为 [职引前端演示 V2](https://zhiyin-frontend-demo-v2.peppy-sugar-7626.chatgpt.site)。本次 V5 未执行 Sites 发布，该地址不能作为当前 V5 在线验收地址。
