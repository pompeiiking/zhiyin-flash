# 学生前端与后端对齐

以后端 controllers、DTO、services、OpenAPI 与功能注册表为依据。UI 仍是本地演示，尚未调用正式后端；接口目录校验不代表在线接入。

| 界面 | 对应后端能力 | 当前演示 |
| --- | --- | --- |
| 咨询 | sessions/turns/task enter/message/materials/theory | 会话恢复；选项及材料 ID；材料元数据 |
| 画像与学籍 | workspace/profile fields/academic import/delete/CHSI | 更正、JSON 导入、等级成绩、完整时间判定、撤回同步、核验示例 |
| 报告与方向 | report/full text/asset versions/directions/select/AI analysis | 示例报告、版本、依据、方向比较与选择，新账号资产空态 |
| 行动与日历 | action plan/task done/calendar/AI timetable/day advice | 状态、阶段、来源、拆小、导入课表；单节课按区间重叠显示 |
| 待办与目标 | notes GET/POST/PATCH/DELETE | 分类别、去重、完成/恢复、删除 |
| 资讯 | intel/refresh | 来源示例与检索，无实时招聘数据 |
| 复盘与记录 | track events/achievements | 时间线、归因、根据后端规则与事件生成完成记录 |
| 应用工具 | user modules/data/actions/invoke/workflows | action_progress 与 achievements 演示入口 |

`sync:backend` 从 OpenAPI 生成 69 个 schema 和后端功能注册表。`check:backend` 检查生成文件过期及 50 个学生操作的 method/path。数量以当前脚本输出为准。

`src/api/backend-client.ts` 提供后续接入用的类型化 JSON/multipart transport；`backend-stream.ts` 处理 progress/result/error SSE、JSON 前置错误、超时与取消。界面未切换到这些 transport，未执行真实 API、AI 或学信网端到端测试。代理目标可通过 ZHIYIN_API_TARGET 配置。

后端约束：画像更正 1–40 字；笔记 1–200 字且同类去重；材料每轮最多 5 个，每份文件最多 2,000,000 字节；学校文本每栏最多 200,000 字符。正式解析与核验由后端承担。变更资产不能冒充已自动重算。后端导出暂不可用，演示保留浏览器打印。

参考 Taste redesign 审查思路（其范围排除复杂产品 UI，未整体套用）、Impeccable craft floor/operate/独立 finish review、本地 Designeer 目录及 Navbar Gallery。Stitch 未连接可用服务且未生成设计；Impeccable CLI 未安装。此次未执行 Sites 部署。
