# 学生工作空间 · 本轮改版

## Direction contract

THESIS：以学生此刻要做的事组织内页。替换并列长列表与多栏说明，让对话、行动、档案、报告、复盘分别拥有明确的阅读顺序。

OWN-WORLD：沿用门户的河大蓝、红与中性灰。系统中文无衬线字体，正文提升到 16px，说明优先 14px。单一白色工作表面，留白与列宽表达主次，统一圆角和按钮。

STORY：门户先进入对话；学生可以直接前往任何功能。底部浮动书签始终列出五个功能名称，顶端只保留身份与工具。每页明确给出主要动作与按需展开的依据。

FIRST VIEWPORT：对话正文居中，输入区紧接正文，档案和产出按需展开；行动页先呈现今天的一件事，其他任务分组切换；报告先结论和差距，再方向选择；档案先已有事实，再来源与缺口；复盘先已推进的事，再归因与下一步。

FORM：代码直接实现的学生工作空间。保留既有业务与公开门户，重做内页结构。Impeccable 引擎未安装，直接用项目证据与官方 Operate 指南作设计判断，无随机种子与图片方案。

FINISH：完成桌面与手机的实际浏览器检查、核心交互检查、构建、对比度/字号与类名门禁，记录审查结果与实际设计系统。

## Research

- Impeccable Operate：产品界面重视任务、可读性、一致性，动效用于状态变化，150–250ms；解释按需展开。https://github.com/pbakaus/impeccable/blob/main/.agents/skills/impeccable/reference/operate.md
- NN/g 隐藏导航研究：完全隐藏导航会降低功能发现。五个主要入口保留文字标签；命令面板只作快捷操作。https://www.nngroup.com/articles/hamburger-menus/
- Every Layout：布局由内容与可用空间决定，窄屏需要结构性重排。https://every-layout.dev/layouts/
- Taste Skill 的当前主技能注明不适用于多步骤产品界面；本次只参考其避免同重卡片、先读需求的思想，不套用营销页的动画与模板。https://github.com/Leonxlnx/taste-skill

## 保留功能与页面

原有地址继续有效：/chat、/home、/plan、/profile、/report、/review。计划是行动空间的第二个视图，方向对比是报告的第二个视图。/path 与 /spec 通过“更多”与命令面板可达。不要求用户按顺序完成。
