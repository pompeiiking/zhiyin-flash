# V5 学生端与后端实质核对 · 2026-10-12

结论：主要业务页面可以对应后端学生端能力，但当前前端不能认定为完整对齐或完成接入。`69 schema / 50 operation` 通过只说明类型快照和接口 method/path 有效；页面使用本地演示状态，且存在下列字段、返回结果和业务行为差异。本检查读取实际 controller、DTO、Facade、业务服务和动态资源，未启动真实后端或执行端到端测试。

## 需要优先处理的差异

| 优先级 | 当前前端 | 后端依据与接入要求 |
| --- | --- | --- |
| P1 · 数据接入 | 活跃页面没有调用 `backendClient` 或 `streamBackend`，登录、消息、资产与写操作均在本地 | [backend-client.ts](../src/api/backend-client.ts)、[backend-stream.ts](../src/api/backend-stream.ts) 只是接入准备。正式接入须保存真实 token、读取服务端结果、处理失败回滚及加载/空状态，不能用 fixture 覆盖失败请求。 |
| P1 · 画像字段 | [student.ts](../src/data/student.ts) 固定 15 个演示字段，仅 `major`、`interest` 与当前规范词表的键一致；`grade/style/time/rank/family/weakness/city/pipeline/award/schedule/internship/jobtype/salary` 不能原样用于更正接口。覆盖度还按年级与演示对话数量推算 | 后端 [profile.py](../../zhiyin-src/template/zhiyin-business/zhiyin_business/services/profile.py) 只允许登记过的规范键；词表在 [copies.json](../../zhiyin-src/template/data/registry/copies.json)，采集规则在 [collection_rules.json](../../zhiyin-src/template/data/registry/collection_rules.json)。应渲染 `WorkspacePageView.profile_panel.fields/gaps/coverage/overall_confidence`。`grade` 的后端模型别名指向 `degree_level`，但“本科”等层次不等于“大三”等年级，不能机械替换。 |
| P1 · 学校资料撤回 | [backend-demo.ts](../src/lib/backend-demo.ts) 撤回会清空学籍快照并影响课表；固定画像中的成绩层级、课程空档等示例仍保留 | 后端 [academic.py](../../zhiyin-src/template/zhiyin-business/zhiyin_business/services/academic.py) 同时删除快照与 `courses/scores` 画像摘要。正式撤回成功后应重读 workspace，不能留下“已取得”的摘要。当前演示未完整模拟这一联动。 |
| P1 · 对话结果 | [ConversationView.vue](../src/views/ConversationView.vue) 使用本地 `reply()`，主题只是发送示例文本；选项元数据和材料 ID 的请求形状已预留 | 后端 [conversation.py](../../zhiyin-src/template/zhiyin-api/zhiyin_api/dto/conversation.py) 还返回 `renderables`、`intel_refs`、`theory_refs`、`pipeline_cards`、`changed_assets` 与结构化 `disclosure/guide`。当前页面没有消费这些正式返回字段。需按 kind 渲染已登记可视件、保留可回溯链接、显示环节状态，并刷新变化资产；不能只把结果转成一段文字。 |
| P1 · 完整报告与版本状态 | 当前 [AssessmentView.vue](../src/views/AssessmentView.vue) 展示三组九个示例维度与固定第三版详细内容，版本页为预置快照 | 后端 [asset.py](../../zhiyin-src/template/zhiyin-api/zhiyin_api/dto/asset.py) 定义 15 维结构化正文、目录、SWOT、方法论、事实来源及 `needs_recompute` 标记。应按实际返回的 sections/items 渲染，不能把九个示例当作完整 15 维报告。待重算状态需要明确展示；现有“未自动重算”说明只覆盖了部分边界。 |
| P2 · 方向方案 | 概览与逐项对照已包含依据、风险、选择，但缺少后端 `target_desc/gaps[].requirement/current_state/suggestion` 的完整展开 | 后端方向结构包含目标、现状、要求和补齐建议。改选是选择状态更新而非重新生成报告。当前演示也没有按后端区分首次选择 `decision_select` 与改选 `decision_reselect` 的事件记录。 |
| P2 · 行动与复盘 | 完成/恢复可对应正式写接口；“拆分为 5 分钟”、建议采纳/拒绝、添加调整任务及未完成归因属于本地交互 | 后端直接的行动写接口是 `PATCH /app/plan/action/tasks`，载荷为 `{task_id, done}`。本次核对的学生 controller 中没有等价的直接拆分/采纳/归因写接口，部分调整通过 AI 待办建议、咨询编排及 [plan_patch.py](../../zhiyin-src/template/zhiyin-business/zhiyin_business/services/plan_patch.py) 完成。正式版要走对应业务链路，不可假设一个通用 PATCH 可保存全部操作。 |
| P2 · AI 能力 | 今日焦点、画像解释、日历建议、职业匹配和学校核验当前为示例或说明，没有正式生成结果 | [ai_controller.py](../../zhiyin-src/template/zhiyin-api/zhiyin_api/controllers/ai_controller.py) 实际提供今日简报、维度解读、画像整体分析、当天建议、缺口追问、报告结论、学信网绑定、课表可投入时间、待办建议、职业匹配共 10 个 SSE 入口。接入需使用 progress/result/error，UI 已有的展示不能代表这些能力已执行。 |
| P2 · 模块、配置与提醒 | 应用工具列出两个示例入口；菜单、主题入口和提醒队列取本地数据 | 后端 [module_controller.py](../../zhiyin-src/template/zhiyin-api/zhiyin_api/controllers/module_controller.py) 按启用状态提供模块、数据、动作、调用和已发布工作流；bootstrap/portal 提供动态配置，通知关闭要发已读回执。正式版不能只显示静态两项或仅在浏览器移除提醒。 |

## 已相符的部分

| 前端场景 | 实际后端能力 | 判断 |
| --- | --- | --- |
| 历史会话和续接 | sessions、session turns、task enter、message | 页面能力对应；每轮正文、选项身份与幂等 ID 的形状已准备，仍未实际发送。 |
| 个人信息更正 | profile fields POST；空值拒绝、最多 40 字 | 长度与来源展示思路相符，字段键和动态读数仍须修正。 |
| 资料导入 | academic JSON/multipart、撤回、CHSI | 前端文件上限 2,000,000 字节、学校 120 字、学期 40 字、原文每栏 200,000 字符与后端一致；JSON 演示导入比后端实际原文/文件解析范围更窄。等级成绩保留字符串，时间不完整时不排入课表。 |
| 材料 | conversation/material + material_ids | 空文件拒绝、单份上限 2,000,000 字节、每轮最多 5 份相符。当前只记录元数据，未上传/解析。 |
| 方向与行动 | directions/select、action、tasks PATCH、calendar | 页面入口、三方向角色、单一选择、任务完成/恢复与关键节点对应。实际读写仍在本地。 |
| 待办与目标 | notes GET/POST/PATCH/DELETE | 1–200 字、去空白、同类去重、完成/恢复和删除相符。 |
| 资讯 | intel GET、refresh POST | 来源名称、原链接和获取时间相符。后端允许未登录读取公开资讯，当前学生空间演示入口会进入演示账号；正式公开访问策略尚未适配。 |
| 记录与提醒 | track/events、achievements、notifications/read | 有对应页面与示例入口。正式完成记录来自业务日志，不应由前端手工解锁；目前示例明确标注。 |
| 应用工具 | action_progress、achievements 模块 manifest | 这两项确为已有可展示应用。`plan_progress_skill` 是无卡片的内部 tool，不应因此增加第三个学生菜单项。 |
| 导出 | ExportResultView.available=False | 前端保留浏览器“打印 / 保存 PDF”符合当前后端可用边界，不冒充服务端 PDF/DOCX 导出。 |
| 新增导航 | 多组菜单、整栏收起、桌面/移动布局 | 属于呈现状态，不改变后端能力或权限。收起侧栏后仍只保留一个可见账号入口。 |

## 建议实施顺序

1. 首先用 workspace 返回替换固定画像池，并同步资料撤回和资产待重算状态。
2. 接入会话、完整消息结果与真实报告/方向/行动资产，保存后以服务端返回结果刷新。
3. 补齐缺口追问、整体画像分析、15 维完整报告、方向差距、动态可视件和版本状态的展示。
4. 再接 AI 建议、学校解析核验、职业匹配、动态模块与提醒回执，移除这些操作的本地模拟分支。

本轮用户要求是“检查是否符合”，因此本记录列出差异，不把待接入工作计为已完成。后端代码及用户已修改的 BACKEND-ALIGNMENT.md 未改动。视觉独立审阅的 ship 仅针对演示界面质量，不等于后端业务接入验收。
