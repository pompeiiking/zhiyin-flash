# V4 二级导航与内容验证 · 2026-10-12

目标为 `D:\zhiyin-flash\redesign-demo` 的 [5275 本地服务](http://127.0.0.1:5275/)。5273 / 5274 属于其他 checkout。范围仅为独立前端演示，后端、原前端与管理员端未修改，本轮无 Sites 发布。

## 审查结果

V4 独立 finish review 结论为 **ship**，覆盖二级菜单与路由同步、历史位置、重复导航移除、唯一账号、内容表达、动效与减少动效。Impeccable CLI 未安装，结果来自独立源码与视觉审阅。内容判断见 [CONTENT-AUDIT.md](../CONTENT-AUDIT.md)。

画像和学籍独立；诊断仅结果/版本记录，方向独立无重复报告导航；行动今日/阶段共用功能，日历独立，阶段仅里程碑、执行任务与来源。文案改为正常书面表达。

生涯分析 4 子项、计划管理 3 子项、资讯与记录 2 子项，Reka UI Accordion 受控单选展开并同步路由。历史在桌面全部业务菜单下方；账号桌面仅左下、移动仅右上，移动咨询保留历史入口。菜单尺寸动画、任务 TransitionGroup 与页面轻量入场均遵循 reduced motion。

## 最终浏览器证据

主任务采集并实际呈现目标图像，独立审阅逐图验证 V4。早期截图调用出现错误帧，已重采集；以最终 Cua 目标截图为准，V3 与更早图片不作 V4 验收依据。

| 范围 | 尺寸 | 文件 |
| --- | --- | --- |
| 12 个业务桌面页 | 1440×1000 | chat、profile、academic、report、directions、home、plan、schedule、notes、intel、review、tools 的 `*-desktop.jpg` |
| 门户 | 1440×1000 | [portal-desktop.jpg](portal-desktop.jpg) |
| 4 个业务移动页 | 390×844 | [chat-mobile.jpg](chat-mobile.jpg)、[profile-mobile.jpg](profile-mobile.jpg)、[schedule-mobile.jpg](schedule-mobile.jpg)、[notes-mobile.jpg](notes-mobile.jpg) |
| 移动更多菜单 | 390×844 | [menu-mobile.jpg](menu-mobile.jpg) |
| 横屏咨询 | 1280×720 | [chat-user.jpg](chat-user.jpg) |

移动菜单最终首帧跨调用重采集并实际呈现确认：面板不透明，「计划管理」展开为行动计划、日历与课表、待办与目标三个子项。门户也完成目标重采集。逐图匹配目标标题、路由与内容，检查未见横向溢出。操作路径使用 `public/shots/v4-*.jpg`，其余补充图不代替此清单的最终证据。

最终新咨询欢迎页在1280×720下验证：记录区 scrollTop=0，scrollHeight 与 clientHeight 均为368，主题和四个入口完整显示。空会话不再自动滚动到末尾；较矮桌面窗口压缩欢迎图形和留白，长对话继续跟随最新消息。

浏览器确认包括门户进入咨询、导航布局切换、移动新对话、会话创建与恢复、待办创建/完成/恢复、JSON 课程与等级成绩导入同步、缺时间待补充和单节课程显示。会话切换清空草稿附件、旧版进入版本记录和当前视图打印由源码及独立审查确认。方向说明与待办文案已按当前上下文修正。

## 静态检查

最终 `build`（包含 vue-tsc）、`check:backend`、类名门禁、颜色/字号门禁均已通过。后端目录输出 69 个 schema、50 个学生操作的 method/path；不表示界面已接入 50 项 API。文档更新后的 `git diff --check` 已通过。

```powershell
npm.cmd run build
npm.cmd run check:backend
node scripts/check-classes.mjs
node scripts/check-contrast.mjs
git diff --check
```

## 验证边界

UI 为预置示例与当前会话状态，未测试正式认证、真实文件解析、在线 AI、学信网、实时招聘或真实 API 端到端。方向只展示影响范围，不自动重算；版本为预置记录，详细分值仍第 3 版示例。

Stitch 无可用服务、未生成设计；Taste 仅局部审查参考，未套用整套产品界面；Designeer 使用本地目录。已有 Sites 地址为历史发布，本轮没有更新该站点。当前 QA 替代 V3 作为本轮验收记录。
