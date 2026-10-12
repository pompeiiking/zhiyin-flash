# 学生工作空间 · V4 改版方向

## Direction contract

THESIS：让学生找到功能、读懂当前情况并采取行动。以二级业务导航整理功能，移除报告、方向、画像、学籍和日历的重复入口，逐页评估内容价值与表达。

OWN-WORLD：保留门户主张与蓝红灰配色、系统中文无衬线字体和 16px 正文。白色工作表面、留白和合适列宽形成层次，统一 Phosphor 图标。灵动来自菜单、任务位置与状态反馈。

STORY：门户与登录首先进入咨询，各功能独立可达。桌面咨询置顶，二级菜单分为生涯分析、计划管理、资讯与记录；历史在全部业务导航下方。账号唯一入口为桌面左下或移动右上。移动保留四个业务快捷入口和更多目录，咨询保留历史入口。

FIRST VIEWPORT：咨询正文与输入相邻；画像先事实，学籍独立；诊断先结果和差距，版本按需查看，方向独立比较；行动以今日/阶段共享功能，日历独立；复盘显示任务分析与调整建议。解释、来源、分值和影响范围主动展开。

FORM：Vue 3 本地演示工程。Reka UI Accordion 负责受控二级菜单、键盘交互与路由同步；CSS 与 Vue TransitionGroup 负责尺寸、位置和入场动效，遵循 reduced motion。沿用后端契约目录，不宣称 UI 已接入 API。

FINISH：独立 finish review 达到 ship；最终 V4 目标截图逐图审阅，确认导航、内容、唯一账号与移动菜单。最终构建（含类型检查）、后端目录、类名与颜色/字号门禁已通过。V3 历史截图不替代本轮验证。

## 内容取舍

画像和学籍独立，无重复页签。诊断只保留诊断结果/版本记录；方向页移除报告导航和版本选择。今日与阶段属于同一行动计划；阶段只保留里程碑、执行任务、来源，日历单独进入。

咨询保留材料、成果和会话能力，桌面历史集中到导航下方，切会话清空草稿与附件。学籍完整时间和等级成绩按事实显示；课表按区间重叠显示单节课程。资讯保留来源与日期，统计注明演示。复盘归因任务、方法或方向。文案采用正常书面语言。详见 [CONTENT-AUDIT.md](design-review/CONTENT-AUDIT.md)。

## 研究与工具边界

- [Impeccable Operate](https://github.com/pbakaus/impeccable/blob/main/.agents/skills/impeccable/reference/operate.md)：任务组织、可读性、按需解释与状态反馈；本轮独立 finish review，CLI 未安装。
- [Reka UI Accordion](https://www.reka-ui.com/docs/components/accordion)：已采用，受控单选展开、键盘导航和内容尺寸动画。
- [Motion for Vue](https://motion.dev/docs/vue)：研究参考，未安装，现有 CSS 与 TransitionGroup 满足需求。
- [Taste Skill](https://github.com/Leonxlnx/taste-skill)：仅参考需求先行及避免同重卡片的审查方法；范围排除复杂产品 UI，未整套套用。
- [NN/g 隐藏导航研究](https://www.nngroup.com/articles/hamburger-menus/)和 [Every Layout](https://every-layout.dev/layouts/)：功能发现与内容驱动重排的参考。
- Designeer 使用本地目录，Navbar Gallery 用于导航研究；Stitch 未连接可用服务、没有生成设计。

范围仅为 redesign-demo，后端与原前端未修改，本轮无 Sites 部署。69 schema / 50 operation 是目录校验，真实 API、AI、学籍核验和自动重算仍待接入。实际设计系统见 [DESIGN.md](DESIGN.md)，验证见 [desktop-v4/QA.md](design-review/desktop-v4/QA.md)。
