# 后端能力与页面设计对应

依据当前仓库 Python 控制器、DTO、facade 与业务服务静态核对。表示代码存在，不表示当前环境服务及外部依赖已运行验证。范围为学生端 `/app`，不将 `/developer` 运维发布能力带入学生界面。

## 能力清单

| 用户任务 | 后端依据（均在 /api/v1 下） | 界面与操作 |
| --- | --- | --- |
| 开始或继续咨询 | GET /app/sessions、GET /app/sessions/{task_id}/turns、POST /app/task/enter、POST /app/conversation/message | 对话与可收起历史；入口使用 bootstrap task_code；选项回传 option_id/value，材料传 material_ids |
| 提供材料 | POST /app/conversation/material | 输入框材料附件；展示文件回执，不把全文塞进气泡 |
| 理解与更正个人资料 | GET /app/workspace、POST /app/profile/fields/{key} | 画像分组字段可更正；来源证据就近展开；单字段字符串，业务层长度上限 40 字 |
| 导入课程和成绩 | POST /app/academic/import、POST /app/academic/import/file、DELETE /app/academic | 学业资料中的文件/粘贴导入；分别展示读到课程数及已解析时间的课程数；成绩保持原口径 |
| 学籍核验 | POST /app/chsi/bind（SSE） | 在线验证码入口，不索取校园账号密码；完成以服务真实结果为准 |
| 理解诊断 | GET /app/report/full-text、GET /app/assets/{asset_type}/versions | 判断分组与证据浮层；全文阅读、历史版本、待重算标记；不编造连续数值分数 |
| 比较和选方案 | GET /app/plan/directions、POST /app/plan/directions/{option_id}/select | 改称生涯方案：目标/契合依据/风险/差距对齐比较，选中及更换方案；没有独立清空选择接口 |
| 执行行动计划 | GET /app/plan/action、PATCH /app/plan/action/tasks | 阶段与可完成任务；支持 done=true/false，返回服务器完整计划。改任务内容及日期通过咨询，不假设 CRUD |
| 查看时间安排 | GET /app/calendar、workspace.academic_panel | 周历、日议程、课程详情、计划节点；没有公开手动增删改日历接口，不提供假拖拽改期 |
| 写下待办和目标 | GET/POST /app/notes、PATCH/DELETE /app/notes/{note_id} | 自建内容可创建、完成/恢复、删除；PATCH 只有 done，不支持就地改文字或日期 |
| 了解外部机会 | GET /app/intel?q=、POST /app/intel/refresh?q= | 有来源的资讯列表与阅读详情；接口没有薪资/城市等结构化字段，不伪装为完整职位投递平台 |
| 复盘过程 | GET /app/track/events、GET /app/achievements | 活动时间线、完成记录；完成记录不是自行颁发勋章；复盘讨论回到咨询 |
| 查看提醒 | GET /app/notifications/pending、POST /app/notifications/{message_id}/read | 未读通知、标记已读；没有频率设置、推送订阅管理接口 |
| 使用扩展工具 | GET /app/modules、GET /app/modules/{id}/data、POST actions/invoke、POST /app/workflows/{id}/run | 按发布模块清单与 policy 渲染，不写死不存在的简历工具/面试工具 |
| 账户访问 | POST /app/auth/register/login/logout、GET /app/bootstrap | 注册登录退出；无密码重置、个人头像修改、账户删除接口 |
| 请求专项解读 | POST brief/today、dimensions/{id}、portrait/analysis、day/{day}/advice、gaps/{key}/clarify、report/summary、plan/timetable、plan/todos/suggestions、match/careers | 按需调用 SSE；清楚区分生成中、失败、完成，不用预置文字顶替在线失败 |

## 关键边界

- “方向候选”不是必需页面概念，但方向方案有实际持久化、选择与关联行动计划能力，保留任务价值并重新表达。
- match_score 可空且需要可追溯依据。无分数时比较目标、依据和差距，不虚构匹配百分比。不实现没有后端口径的权重滑杆。
- `/app/assets/export` 第一阶段 available=false。可以使用浏览器打印，不能承诺服务端 Word/PDF 下载。
- 资料更正可标记旧资产 needs_recompute；不是点击保存就宣称报告已重新生成。
- 动态模块、外部检索、模型、学信验证需要运行配置与依赖；只因路由存在不能宣称环境可用。
- DTO 中“三栏”“左侧目录”等描述是历史呈现建议，不约束新的布局。

## 新页面结构

主入口：咨询对话。

了解自己：个人画像、学业资料、诊断报告（含全文及版本）。

规划与行动：生涯方案、行动计划（合并今日与阶段视图）、日历与课表、待办与目标。

发现与回顾：机会资讯、复盘记录（含完成记录）、应用工具。

辅助界面：通知、账号与登录注册、使用帮助、无结果/无数据/加载/错误/404。设计评审与状态展示独立于产品导航。

旧门户通过原入口 `/#/?portal=classic` 保留。原版源文件和样式不做改动。

## 证据位置

- `zhiyin-src/template/zhiyin-api/zhiyin_api/controllers/`：学生端路由。
- 同层 `dto/{conversation,workspace,asset,note,bootstrap}.py`：字段和状态契约。
- 同层 `facade/application.py`：方案选择、行动完成及行为记录。
- `zhiyin-src/template/zhiyin-business/zhiyin_business/services/asset.py`：资产持久化、状态继承和待重算传播。
- 同层 `services/function.py`：导出预留及日历读取。
- `zhiyin-src/template/data/registry/task_entries.json`：七类咨询入口。
