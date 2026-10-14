<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'
import ActionPlanNav from '../components/ActionPlanNav.vue'
import LiveActionPlan from '../components/LiveActionPlan.vue'
import AssetNotice from '../components/AssetNotice.vue'
import TaskList from '../components/TaskList.vue'
import Foldable from '../components/Foldable.vue'
import StatTile from '../components/StatTile.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import UiIcon from '../components/UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
import { taskOriginLabel } from '../lib/presentation'
import { DEMO_PHASE_TASK_IDS } from '../data/phase-tasks'
const scenario = computed(() => demo.use.scenario.value)
const books = computed(() => ['计划拆下来的', '建议的', '自己写的', '关键节点'].map(label => ({ label, tasks: demo.state.tasks.filter(t => t.origin === label) })))
const pending = computed(() => [...demo.use.now.value, ...demo.use.waiting.value])
const stages = computed(() => scenario.value.milestones.map(m => ({ ...m, tasks: demo.state.tasks.filter(t => DEMO_PHASE_TASK_IDS[m.id]?.includes(t.id)) })))
const ungrouped = computed(() => pending.value.filter(t => !stages.value.some(s => s.tasks.some(item => item.id === t.id))))
/* 进度读数（MIGRATION §3.3 T1/T2）：分母取自同一批任务，进度条由 StatTile 自己长出来 */
const doneCount = computed(() => demo.use.done.value.length)
const totalCount = computed(() => pending.value.length + doneCount.value)
const stageDone = (tasks: { bucket: string }[]) => tasks.filter(t => t.bucket === 'done').length
/* 「按任务来源查看」原来是一行里套两层的 <details>（外层 .ws-context + 内层 v-for .ws-fold），
   是全站最该拆的一行（MIGRATION §1.3 A7/D6、审计"嵌套 3 层"的元凶）。
   这里按审计给的第二条路收成**一条筛选**：筛选行本身不是折叠层，选中哪一类就重组出哪一类任务。 */
const origin = ref<string | null>(null)
const originGroups = computed(() => books.value.filter(b => b.tasks.length))
const activeOrigin = computed(() => origin.value ?? originGroups.value[0]?.label ?? null)
const shownBook = computed(() => originGroups.value.find(b => b.label === activeOrigin.value) ?? null)
/* LiveActionPlan 正在读计划时，本页不先说"阶段计划还没有形成"（MIGRATION §4.1 K5：假空态） */
const planBusy = ref(false)
</script>
<template>
<div class="ws-page plan-page"><PageHeading title="行动计划" :description="scenario.grade + ' · ' + scenario.focus"><RouterLink class="btn btn--primary" to="/home">查看当前任务<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading><ActionPlanNav/><AssetNotice/><LiveActionPlan @busy="planBusy = $event"/><template v-if="!backendDemo.state.liveAction">
<!-- 空态：`.ws-empty` → EmptyState（MIGRATION §4.2 E4）。整块正文被顶掉，所以显式 heading-level="2"（H5）。 -->
<section v-if="!backendDemo.state.planAvailable" class="plan-empty" :aria-busy="planBusy"><SkeletonBlock v-if="planBusy" variant="list" :lines="3"/><EmptyState v-else kind="report" :heading-level="2" :next="false" title="阶段计划还没有形成" description="在咨询中明确方向后，再安排阶段目标和任务。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><button class="ws-text-button" type="button" @click="backendDemo.loadPlanSample()">查看阶段计划示例</button></EmptyState></section>
<template v-else><section class="plan-current"><div class="plan-current__main"><h2>当前安排</h2><StatTile class="plan-current__tile" label="已完成" :value="doneCount" :denominator="totalCount" :trend="{ label: pending.length + ' 件待推进' }"/></div><RouterLink class="ws-text-link" to="/review">查看执行记录<UiIcon name="arrow" :size="16" /></RouterLink></section>
<!-- 阶段：当前阶段（i===0）static＝永远可见（审计"当前阶段默认收起＝用户看不到自己该做什么"）；
     其余阶段保留可折叠、但默认展开（审计"第二三阶段默认一屏看不到"）。两者同一形状，
     LiveActionPlan 的阶段头用同一套规则，/plan 与 /home 不再漂移。 -->
<section class="plan-stages"><h2>阶段目标</h2><Foldable v-for="(m,i) in stages" :key="m.id" variant="group" :static="i === 0" :default-open="i > 0" :title="m.title"><template #title><span class="plan-stage__title"><span class="plan-stage__mark fold-index">{{ i + 1 }}</span><span class="plan-stage__copy"><strong>{{ m.title }}</strong></span><StatTile class="plan-stage__tile" label="已完成" :value="stageDone(m.tasks)" :denominator="m.tasks.length" :trend="m.window ? { label: m.window } : null"/></span></template><p>{{ m.note }}</p><TaskList v-if="m.tasks.length" :items="m.tasks"/><p v-else class="ws-muted">此阶段尚未关联执行任务。</p><RouterLink class="ws-text-link" :to="'/chat?topic=' + encodeURIComponent(m.title)">讨论本阶段的下一步<UiIcon name="arrow" :size="16" /></RouterLink></Foldable></section><section v-if="ungrouped.length" class="ws-section"><h2 class="ws-section-title">其他待推进任务</h2><TaskList :items="ungrouped"/></section>
<section class="plan-sources ws-section"><h2 class="ws-section-title">按任务来源查看</h2><div class="plan-sources__filter" role="group" aria-label="按任务来源筛选"><button v-for="b in originGroups" :key="b.label" type="button" class="plan-sources__chip" :aria-pressed="activeOrigin === b.label" @click="origin = b.label">{{ taskOriginLabel(b.label) }}<b>{{ b.tasks.length }}</b></button></div><TaskList v-if="shownBook?.tasks.length" :items="shownBook.tasks"/><p v-else class="ws-muted ws-section">这一类还没有任务。</p></section>
<nav class="ws-related" aria-label="计划相关操作"><RouterLink to="/schedule">查看日历与课表<UiIcon name="calendar" :size="16" /></RouterLink><RouterLink to="/directions">调整方向<UiIcon name="directions" :size="16" /></RouterLink><RouterLink to="/review">复盘并调整任务<UiIcon name="review" :size="16" /></RouterLink></nav></template></template><p v-if="!backendDemo.state.liveAction" class="ws-demo-note">阶段目标及任务关联为演示配置；任务计数随完成与恢复更新。没有关联任务的阶段不显示推测进度。</p></div>
</template>
<style scoped>
/* ---- 读数：StatTile 是单列右对齐的，必须给一个**确定宽度**，进度条才不是"和文字一样宽" ---- */
.plan-current__main { display: flex; flex-direction: column; gap: var(--sp-2); min-width: 0; }
.plan-current__tile { max-width: 320px; }
.plan-stage__title { display: flex; align-items: center; gap: var(--sp-4); width: 100%; min-width: 0; }
.plan-stage__mark { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border: 1px solid var(--c-border-strong); border-radius: var(--r-sm); font-size: var(--fs-14); color: var(--c-text-2); }
.plan-stage__copy { flex: 1; min-width: 0; }
.plan-stage__copy strong { display: block; font-size: var(--fs-16); font-weight: var(--fw-medium); line-height: 1.7; }
.plan-stage__tile { flex: none; width: min(220px, 46%); }

/* ---- 空态块（整块顶掉正文时的上下留白；EmptyState 自己不带外距） ---- */
.plan-empty { padding: var(--sp-6) 0; }

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
