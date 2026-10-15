<script setup lang="ts">
import PageHeading from '../components/PageHeading.vue'
import AssetNotice from '../components/AssetNotice.vue'
import LiveActionPlan from '../components/LiveActionPlan.vue'
</script>
<template><div class="ws-page plan-page journey-page"><PageHeading title="阶段计划" description="按阶段核对目标、任务、截止日期与完成情况。"><RouterLink class="btn btn--primary" to="/home">查看当前任务</RouterLink></PageHeading><AssetNotice/><LiveActionPlan/></div></template>
<style scoped>
/* ---- 读数：StatTile 是单列右对齐的，必须给一个**确定宽度**，进度条才不是"和文字一样宽" ----
   `flex: 1 1 auto` 是 2026-10-14 补的：主列收进 `.journey-action-grid` 之后，
   `.plan-current` 里的这一块原来是 shrink-to-fit，StatTile 的进度条实测只有 80×6
   （报告 G-02 记的就是这个"尺度过小"）。撑满之后由 `.plan-current__tile` 的
   max-width:320px 收口 —— 条宽从 80 回到 300 上下，读数才看得见。 */
.plan-current__main { display: flex; flex: 1 1 auto; flex-direction: column; gap: var(--sp-2); min-width: 0; }
.plan-current__tile { max-width: 320px; }
.plan-stage__title { display: flex; align-items: center; gap: var(--sp-4); width: 100%; min-width: 0; }
.plan-stage__mark { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border: 1px solid var(--c-border-strong); border-radius: var(--r-sm); font-size: var(--fs-14); color: var(--c-text-2); }
.plan-stage__copy { flex: 1; min-width: 0; }
.plan-stage__copy strong { display: block; font-size: var(--fs-16); font-weight: var(--fw-medium); line-height: 1.7; }
.plan-stage__tile { flex: none; width: min(220px, 46%); }

/* ---- 空态块（整块顶掉正文时的上下留白；EmptyState 自己不带外距） ---- */
.plan-empty { padding: var(--sp-6) 0; }

/* ---- 主列进 `.journey-action-grid` 之后，块自身的 margin-top 与列间距会叠起来
   （28 + 40 = 68px），所以把它们归零，只留列间距那一档。选择器带主列前缀 → 只作用于
   本页这一列，不动 redesign.css 里 `.plan-stages` / workspace.css 里 `.ws-section` 的共享规则。 ---- */
.journey-page .journey-action-main .plan-stages,
.journey-page .journey-action-main .ws-section { margin-top: 0; }

/* =============================================================================
 * 右栏（G-02）—— 这里只写 /plan 独有的两块形状。
 * 两列、粘性、段间分隔线、h2 / p / 链接的字号字重**全部**来自 journey.css 的
 * `.journey-page …`（与 /home 同一套），一个值都不在这里重写；否则同一条规范就有了
 * 第二份拷贝（journey.css:24-38 那段注释记的正是这件事）。
 * ========================================================================== */
.plan-side__facts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-1) var(--sp-2); margin-top: var(--sp-1); }
.plan-side__stage { margin-top: var(--sp-4); }
.plan-side__stage-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--sp-3); margin-bottom: var(--sp-2); font-size: var(--fs-14); font-weight: var(--fw-medium); line-height: var(--lh-snug); color: var(--c-text); }
.plan-side__stage-head > span:last-child { flex: none; color: var(--c-text-2); font-variant-numeric: tabular-nums; }
.plan-side__empty, .plan-side__when { font-size: var(--fs-12); }
.plan-side__cmp { display: flex; flex-direction: column; gap: var(--sp-5); margin-top: var(--sp-4); }
.plan-side__notes { display: flex; flex-direction: column; gap: var(--sp-2); margin-top: var(--sp-4); padding-left: 0; list-style: none; font-size: var(--fs-12); line-height: var(--lh-normal); color: var(--c-text-3); }
.plan-side__notes b { font-weight: var(--fw-semibold); color: var(--c-text-2); }

/* ---- 按来源：一条筛选。不做成 PanelTabs：那是页面级视图切换，
        这里是同一批任务的**重组**（DESIGN-LANGUAGE §4.2），而且它必须 ≥44px 触控目标 ---- */
.plan-sources__filter { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-3); }
.plan-sources__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 44px;
  padding: 0 var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: var(--fs-14);
  transition: background-color var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out), color var(--dur-1) var(--ease-out);
}
.plan-sources__chip:hover { border-color: var(--c-border-strong); color: var(--c-text); }
.plan-sources__chip[aria-pressed='true'] { background: var(--c-primary-weak); border-color: var(--c-primary-border); color: var(--c-primary); font-weight: var(--fw-medium); }
.plan-sources__chip b { font-weight: var(--fw-medium); color: var(--c-text-3); font-variant-numeric: tabular-nums; }
.plan-sources__chip[aria-pressed='true'] b { color: inherit; }

@media (prefers-reduced-motion: reduce) {
  .plan-sources__chip { transition: none; }
}
/* 窄屏：阶段头一行放不下"序号 + 标题 + 读数"，挤在一起标题会碎成三行。
   让读数换到自己的整行 —— 顺序不变（先标题后读数），进度条也因此拿满宽度。 */
@media (max-width: 480px) {
  .plan-stage__title { flex-wrap: wrap; row-gap: var(--sp-2); }
  .plan-stage__tile { width: 100%; }
}
</style>
