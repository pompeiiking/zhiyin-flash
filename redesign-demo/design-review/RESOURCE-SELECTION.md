# V5 设计资源筛选与落地 · 2026-10-12

本轮读取 [用户提供的设计资源站调研](../../docs/AI可读设计资源站调研-2026-10-12.md)，再检查资源站目录和组件官方文档。导航、布局、背景、动效是例子，筛选覆盖完整学生空间的阅读、操作与状态。现有 Vue 3 / Reka UI、蓝红灰令牌、后端业务边界与门户进入对话的规则继续沿用。

## 已采用

| 场景 | 参考来源 | 本地实现与效果 |
| --- | --- | --- |
| 桌面工作空间 | [shadcn/vue Sidebar](https://www.shadcn-vue.com/docs/components/sidebar)，registry.directory 的 sidebar-08 目录条目 | 侧栏融入底层背景，右侧形成完整的内嵌工作表面。保留二级目录、导航下方历史和唯一账号入口；当前页面、分组与历史通过位置和表面区分。未复制 React/Tailwind 模板。 |
| 阅读长对话 | [AI Elements Conversation](https://elements.ai-sdk.dev/components/conversation) | 用户上读时暂停跟随，显示“回到最新消息”；主动返回后继续跟随。增加顾问回复复制与可见结果反馈。保持 16px 正文、限制行宽和清晰的顾问交接。 |
| 判断依据 | [AI Elements Sources](https://elements.ai-sdk.dev/components/sources) | `EvidenceList.vue` 显示依据数量与按需展开的编号列表。使用已有真实演示文本，不伪造来源链接，不把内部依据冒充外部引用。 |
| 输入与材料 | [AI Elements Prompt Input](https://elements.ai-sdk.dev/components/prompt-input) | 输入、材料、发送整合为稳定底部区域；焦点有明确描边。沿用最多 5 份材料、每份小于 2MB 的限制及演示附件说明。未接入示例 AI SDK 或新模型服务。 |
| 页内视图切换 | [Reka UI Tabs](https://www.reka-ui.com/docs/components/tabs) | `PanelTabs.vue` 统一任务、阶段计划、个人画像来源、学籍资料、日历课表、待办目标及方向比较。方向键/Home/End、ARIA 关联、滑动指示线与状态数量共同表达切换。切换待办/目标时各自保留草稿。 |
| 方向选择 | 对照表与 progressive disclosure 的本地组合 | `DirectionCompare.vue` 将三个既有方向按匹配判断、依据、风险及选择逐行对照。与原方案概览共享选择状态；窄屏只在表内横向滚动。没有新增评分或职业数据。 |
| 执行状态 | 现有任务状态派生的数据可视化 | `TaskOverview.vue` 展示完成数/总数及待执行、等待、完成三个数量，完成与恢复任务会同步变化。环形图是当前演示任务状态，不是后端生成的职业评分。 |
| 补充信息 | 原生 dialog + inspector 结构 | 画像、成果、历史作为对话右侧面板；窄屏为底部面板。正文独立滚动，Esc/背景关闭，关闭后恢复焦点。普通导入与更正表单保留原模态布局。 |
| 空状态与咨询引导 | [shadcn Empty](https://ui.shadcn.com/docs/components/base/empty)，[Magic UI Grid Pattern](https://magicui.design/docs/components/grid-pattern) | `EmptyState.vue` / `WorkspaceMotif.vue` 使用自绘稀疏点阵与分支路线，在咨询主题、画像无记录、待办目标、岗位资讯为空时给出解释和下一步。图形为本地 SVG，独立 ID，无远程图片依赖。 |
| 记录与来源 | 原有数据的排版改造 | 复盘时间线增加连接线，资讯正文与来源区分层，页面主次由标题、间距、描边与局部浅蓝表面建立。没有增加不真实的照片、招聘卡或统计。 |
| 动效 | [Ant Design Motion](https://ant.design/docs/spec/motion/) | 视图指示线 180ms、概览进度 220ms、侧面板 220ms；原有菜单/任务移动继续使用既有动效。遵循 prefers-reduced-motion，无持续背景运动，无新增动画库。 |

## 目录与候选的取舍

[registry.directory](https://registry.directory/llms.txt) 及公开 `items.json` 用于发现实际组件名称和来源，随后以官方文档判断适用性。2026-10-12 本次读取的注册表数量为 91，与调研文档的 93 不一致；目录数量不会参与产品展示。

21st、Magic UI 等库大量基于 React/Tailwind。本项目采用可用的交互结构，自行实现 Vue 组件，未为效果引入第二套框架。没有接入目录文档中的提交接口、MCP、账号或计费服务。

没有采用大面积动画网格、粒子背景、照片墙、发光边框、翻滚数字或自动轮播。它们会增加本产品已有的阅读密度，并且无法解释咨询、资料与计划的功能关系。背景和图形放在引导区域，资料与操作区域使用稳定表面。

本轮延续已读取的 Impeccable 操作界面与 craft floor 检查方法；Taste 不整套套用于 dashboard。Stitch 未连接可调用生成服务，本轮没有生成结果；Designeer 使用前序目录研究，不冒充本轮成功访问。独立收尾审阅与记录按 [Impeccable new-work](https://github.com/pbakaus/impeccable/blob/main/skill/reference/new-work.md) 执行，CLI 未安装，不能宣称运行了官方检测器。

## 实现边界

所有新增组件使用原有数据与既有功能。正式 API、模型推理、学校核验、文件解析与实时岗位搜索仍未接入。历史会话仅在内容变化时更新活跃时间，恢复查看不会改变旧会话的日期。门户构图与配色不改，进入后仍是咨询对话。

最终截图及具体操作结果记录在 [desktop-v5/QA.md](desktop-v5/QA.md)。
