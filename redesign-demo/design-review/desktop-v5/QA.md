# V5 组件与体验验证 · 2026-10-12

目标工程为 `D:/zhiyin-flash/redesign-demo`，分支 `新前端2`，预览 [5275](http://127.0.0.1:5275/#/chat)。V5 在既有学生空间上改进阅读、操作与状态表达。资源选择见 [RESOURCE-SELECTION.md](../RESOURCE-SELECTION.md)。

## 构建与静态检查

- `npm.cmd run build`：类型检查与 Vite 构建通过。
- `npm.cmd run check:backend`：69 schema 同步、50 学生操作 method/path 匹配。
- `node scripts/check-classes.mjs`：包含新增 `experience.css`，没有全局/scoped 布局撞名；原有 SpecView 外观同名提示不阻断。
- `node scripts/check-contrast.mjs`：四套主题组合的必过文字项 ≥ 4.5:1，六档字号登记通过。
- `git diff --check`：通过。

## 实际交互

门户“开始第一个问题”进入 `/chat`。方向比较用方向键和 End 切换，选择同步至当前方向与关联范围。任务完成后待执行数由 3 变 2、已完成由 3 变 4，概览同步；恢复后数量复原。个人待办重复添加只保留一条，完成与恢复有效；切换目标时使用独立草稿，返回待办保留原草稿。

画像面板支持 Esc，关闭后焦点回到原触发按钮。上读历史后显示返回最新按钮，点击后到达记录底部。支持依据展开显示既有编号列表。复制调用成功并显示“已复制”，但本工具的会话剪贴板读取为空，未验证字节相等。

资讯示例加载后有两个来源条目，筛选无匹配时显示对应空态，清除筛选恢复两个条目。日历/课表切换有效，既有课程数据继续显示。主题切换到深色后检查概览与主内容，再恢复原来的跟随系统偏好。

追加导航验证：三个一级菜单可同时展开，也可独立收起一组；整栏收起使当前测试视口中的主区宽度增加 236px，焦点恢复到展开按钮，重新展开后焦点回到收起按钮、三个组的展开状态保留。桌面账号可见入口计数始终为 1，展开侧栏时左下、收起时右上；刷新保留侧栏收起偏好。菜单展开集合为本次组件会话状态，不承诺刷新后恢复。

## 图像与响应式证据

当前证据共 33 张 JPEG：12 个桌面业务页、6 个手机业务页、13 个基线特殊视图与 2 个追加导航视图。均为本地演示的实际浏览器截图。测试视口：主业务桌面为 1280×720、手机为 390×844、宽屏行动为 1440×900、短屏对话为 1280×600。视口尺寸不等于截图像素尺寸，实际文件尺寸见 [SHOT-PROVENANCE.json](SHOT-PROVENANCE.json)；工具对部分桌面画面输出 1270×714。对照表与执行时间线另有完整页面截图；完整截图不能替代普通高度的滚动边界检查。

十二个桌面业务路由和六个手机路由均无整页横向溢出、无启动错误。手机对照表宽 760px、容器宽 290px，仅内部滚动；已增加滑动提示。手机底部面板覆盖全宽，内容独立滚动。短高度咨询使用文档流，输入区通过页面滚动访问。所有尺寸临时覆盖均已恢复。

主要图像：`chat-welcome-desktop.jpg`、`chat-evidence-desktop.jpg`、`inspector-desktop.jpg`、`inspector-mobile.jpg`、`directions-matrix-desktop.jpg`、`directions-matrix-mobile.jpg`、`home-wide-desktop.jpg`、`home-dark-desktop.jpg`、`intel-sources-desktop.jpg`、`review-timeline-desktop.jpg`。其余以路由名称命名。操作检查摘要在 [browser-checks.json](browser-checks.json)。

追加导航图像为 `sidebar-multiple-desktop.jpg` 与 `sidebar-collapsed-desktop.jpg`，分别记录多组展开、整栏收起及扩展主区。

修正了首轮发现的手机 dialog 默认最大宽度与工具页面包屑，确认后保存图像。依据展开曾捕获到上一帧，已更换为实际展开的画面。使用指南采用 `public/shots/v5-{portal,chat,profile,report,directions,home,review}.jpg` 副本，源为本目录对应桌面截图，各 `.jpg.json` 记录来源、演示属性与实际像素尺寸。截图工具返回 JPEG 字节，早期误用 `.png` 扩展名已通过改名纠正，改名步骤未改变画面字节；后续导航追加的相关画面重新采集。无 AI 生成位图。

## 独立收尾审阅

最终结论：**SHIP（视觉与导航）**，无演示交付阻断或必要修复。独立 reviewer 重新逐一打开全部当前 33 张 JPEG，并只读检查多组展开、整栏显隐、收起偏好、焦点恢复与唯一账号实现。覆盖完整学生空间、蓝红灰与门户进入咨询、二级目录/历史/账号及既有功能。早期 V4 文档引用建议已处理。详细范围与限制见 [FINISH-REVIEW.md](FINISH-REVIEW.md)。

reviewer 未重跑浏览器、构建或 detector，交互结果来自上述实施验证记录。Impeccable CLI/detector 未安装，不以静态检查冒充官方检测器结果。

导航交互以实施记录、源码和最终截图互证；reviewer 对后端仅抽样核对对话资产 DTO、AI controller 与资料撤回，支持业务核对中的主要差异，不能计为完整对齐或接入通过。

## 边界

没有增加 npm 依赖、外部图片或真实数据服务。新组件使用现有后端对应功能与演示状态，正式 API、模型、文件解析、学校核验及实时岗位仍未接入。方向选择展示影响范围，未执行真实自动重算。减少动效通过源码规则检查，本轮浏览器没有切换操作系统的 reduced-motion 设置。V4 与更早截图仅作历史参考。

[BACKEND-AUDIT-V5.md](../BACKEND-AUDIT-V5.md) 已读取实际 controller、DTO、Facade、业务服务和动态资源，未启动真实后端或执行端到端测试。结论为主要页面能力有对应，但不完整对齐：画像规范键、资料撤回后的画像摘要、消息可视件/管线/变化资产、完整 15 维报告/SWOT/来源/待重算状态、方向差距、AI 与动态模块等仍有接入或展示差异。69 schema / 50 operation 仅为契约目录检查；本页视觉 SHIP 不代表完整业务对齐或正式接入验收。
