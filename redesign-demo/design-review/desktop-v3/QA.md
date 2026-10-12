# 桌面侧栏版验证 · 2026-10-12

目标为 D:\zhiyin-flash\redesign-demo 的 5275 服务。5273/5274 属于另一份 checkout，未修改或停止。

截图：十二个 desktop 页1440×1000；chat/profile/schedule/notes mobile 页390×844；chat-user 页1280×720。采集时断言单一 main h1 匹配目标页，均无横向溢出。九个学生导航在720高度可见，更小高度可滚动。

浏览器确认：门户按钮进入chat；布局切换保留内容；移动新对话；会话创建与历史恢复；待办创建、完成、恢复；JSON 导入课程和等级成绩同步课表；缺时间明确待补充；单节第2节课程可见。

独立评审初次要求修正移动新对话和单节课遗漏，修复后源码复核为 ship，并由主任务完成浏览器确认。Impeccable CLI 未运行。

发布前执行 build（包含 vue-tsc）、backend 校验、class、contrast 与 git diff --check。UI 为本地演示，未验证正式认证、实时岗位、学校文件解析、CHSI 或在线 AI。
