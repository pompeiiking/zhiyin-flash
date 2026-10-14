# C2 交互原型 → Vue 演示前端

2026-10-15修复记录。依据为 directions/c2-hbu/index.html、共享CSS与各页面行为脚本，落地为实际Vue路由与状态操作。当前样式由最后加载的 src/styles/c2-fidelity.css 控制，令牌见项目 DESIGN.md；门户及 /portal 别名保留。

20条受测工作空间路由与门户共同对应21个原型职责。额外 /path 和未知地址兜底保留。这里的对应表示原型职责具有实际页面入口，不表示逐像素相同、全部状态已穷尽迁移或正式业务接入完成。

## 当前落地

| 范围 | 实际实现 |
| --- | --- |
| 外壳 | 264px完整侧栏、76px图标栏、手机全宽贴底底栏；默认浅色、C2正文栈；七档字号新增24px手机统计数；通用辅助列312px |
| 咨询 | C2预置阅读内容；旧未修改seed迁移，用户消息保留；显式演示顾问状态，服务及实际生成状态仍真实驱动；记录之后的静态输入区；咨询辅助列296px已恢复，通用列312px保持 |
| 画像 / 报告 | 来源、时间、主题、贡献重组，保留可信度等既有轴；报告三条具体判断关联具体维度 |
| 复盘 | 执行与已发生成长合为recordPool，四轴实分组；周活动仅算items，完成重组复验 |
| 方向 | 五项固定合成刻度、1–5优先级、加权平均取整与重置；SPA切页保留权重；选择与确认独立 |
| 今日 / 阶段 | 到期优先、同期限取小任务；来源及依据可追；当前步骤与四项store派生指标；阶段与任务展开 |
| 学籍 / 日历 | 四类资料来源与导入撤回示例；日历侧月历；课程与任务在同一时间尺度查看 |
| 待办 / 资讯 | 同一待办目标记录池，类型/完成/来源三轴；资讯类别chips、热词与排序 |
| 工具 | 六工具、四步依赖流程；原服务端发布工具与执行记录在 PublishedTools.vue 披露入口保留 |
| 系统页 | settings、reminders、login、guide、gallery、achievements原生页面及命令目录入口；notfound与spec独立可达 |

账号的桌面顶栏及侧栏页脚入口打开同一抽屉，共享状态。提醒处理历史由 rememberSession 缓存，换账号清空。设置的授权与安静时间仅是本地演示偏好。今日与阶段计数取现有store，不能用原型固定申请、面试数字冒充发生过的行为。方向分数仍是明确标注的合成示例。

最后收口已实际完成：报告默认demo两项依赖待核对，requestReportReview标记记住并跨route保留原分数；提醒read保留queue，later持久化完整Notice/action/deadline，可恢复队列或现在处理，done沿用resolve，三轴组织。成长记录为原五条实际badge条件加核验条件，证据转为人类事件名，有来源/时间/主题/确认轴。指南四FAQ七词汇，gallery十二族两轴样例及四流程 × 四状态矩阵；日历第三概览统计课程至少四小时的天数，选中日期显示无due真实任务；junior计划使用ISO dueAt、dependsOn、handoff及可见2026-10-14快照基准。danger明确底色、前景和hover。

## 验证与复现

在 redesign-demo 运行本地开发服务器与检查：

~~~text
npm.cmd run dev -- --host 127.0.0.1 --port 5199
npm.cmd run build
node scripts/check-contrast.mjs
node scripts/check-c2.mjs
~~~

构建、类型与对比度通过。check-c2.mjs 当前通过行为断言及20条工作空间路由在1440、1280、900、390px下的控制台、整页横向溢出与桌面导航检查；本轮detect仅运行一次，结果为[]。行为断言覆盖方向权重/路由保留/确认、报告依赖、信息重组、任务反馈、待办、资讯、工具、提醒记录、异常状态、换肤与命令搜索。最终又通过复盘四轴fingerprint变化不丢条目、growth六条、danger可见、报告跨route标记、gallery十二族与四行矩阵、FAQ展开、日历三概览、阶段逾期和可见日期basis，以及提醒pending→read→later→跨route→restore→later→done。它不穷尽每页所有加载、错误、空态或服务端交互。

capture-c2.mjs 默认仍只取12路由与两档宽度；本轮通过 C2_ROUTES、C2_WIDTHS、C2_SHOTS 扩展为21路由 × 1440/390/858px，在仓库根 .tmp-shots/c2-repair-final 生成63组、126张PNG。需要已安装Playwright；PW_PATH可指定模块路径，C2_URL可指定服务器。scripts/capture-c2-states.mjs另生成提醒read/later/done × 同三宽的九张操作态图；实际共135张PNG，其中126张配对、九张非配对。改变路由已按同三宽覆写复拍。截图不入库。

check-classes只列出原五份全局CSS，排除redesign.css与c2-fidelity.css；不能将其旧通过结论外推到覆盖层。前轮check-design几何纠正与旧审核属于历史记录，本轮不据此补造新的完整验收结论。

独立finish reviewer初次给出fix，最后修复与复验已完成；最终七项实质修复复核已完成。最终七项实质修复均resolved，每项2/2，汇总7 resolved / 0 partial / 0 unresolved。该结论不扩大为21个界面的全部状态或像素一致性验收。旧C2-PARITY-AUDIT保留为审计历史；本轮修复对应及真实限制见 [C2-REPAIR-RESULT.md](C2-REPAIR-RESULT.md)。
