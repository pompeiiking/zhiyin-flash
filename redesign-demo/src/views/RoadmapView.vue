<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'
import ActionPlanNav from '../components/ActionPlanNav.vue'
import LiveActionPlan from '../components/LiveActionPlan.vue'
import AssetNotice from '../components/AssetNotice.vue'
import TaskList from '../components/TaskList.vue'
import UiIcon from '../components/UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
import { taskOriginLabel } from '../lib/presentation'
import { DEMO_PHASE_TASK_IDS } from '../data/phase-tasks'
const scenario = computed(() => demo.use.scenario.value)
const books = computed(() => ['计划拆下来的', '建议的', '自己写的', '关键节点'].map(label => ({ label, tasks: demo.state.tasks.filter(t => t.origin === label) })))
const pending = computed(() => [...demo.use.now.value, ...demo.use.waiting.value])
const stages = computed(() => scenario.value.milestones.map(m => ({ ...m, tasks: demo.state.tasks.filter(t => DEMO_PHASE_TASK_IDS[m.id]?.includes(t.id)) })))
const ungrouped = computed(() => pending.value.filter(t => !stages.value.some(s => s.tasks.some(item => item.id === t.id))))
</script>
<template>
<div class="ws-page plan-page"><PageHeading title="行动计划" :description="scenario.grade + ' · ' + scenario.focus"><RouterLink class="btn btn--primary" to="/home">查看当前任务<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading><ActionPlanNav/><AssetNotice/><LiveActionPlan/><template v-if="!backendDemo.state.liveAction">
<section v-if="!backendDemo.state.planAvailable" class="ws-empty"><h2>阶段计划还没有形成</h2><p>在咨询中明确方向后，再安排阶段目标和任务。</p><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><button class="ws-text-button" @click="backendDemo.loadPlanSample()">查看阶段计划示例</button></section>
<template v-else><section class="plan-current"><div><h2>当前安排</h2><p>{{ pending.length }} 件待推进 · {{ demo.use.done.value.length }} 件已完成</p></div><RouterLink class="ws-text-link" to="/review">查看执行记录<UiIcon name="arrow" :size="16" /></RouterLink></section>
<section class="plan-stages"><h2>阶段目标</h2><details v-for="(m,i) in stages" :key="m.id" class="plan-stage" :open="i === 0"><summary><span class="plan-stage__index">{{ i + 1 }}</span><span><strong>{{ m.title }}</strong><small>{{ m.window }} · {{ m.tasks.filter(t=>t.bucket==='done').length }} / {{ m.tasks.length }} 件任务已完成</small></span><UiIcon name="chevron" :size="18" /></summary><div class="plan-stage__body"><p>{{ m.note }}</p><TaskList v-if="m.tasks.length" :items="m.tasks"/><p v-else class="ws-muted">此阶段尚未关联执行任务。</p><RouterLink class="ws-text-link" :to="'/chat?topic=' + encodeURIComponent(m.title)">讨论本阶段的下一步<UiIcon name="arrow" :size="16" /></RouterLink></div></details></section><section v-if="ungrouped.length" class="ws-section"><h2 class="ws-section-title">其他待推进任务</h2><TaskList :items="ungrouped"/></section>
<details class="ws-context"><summary>按任务来源查看<UiIcon name="chevron" :size="16" /></summary><div class="ws-context__body ws-context__body--single"><details v-for="b in books" :key="b.label" class="ws-fold"><summary>{{ taskOriginLabel(b.label) }} · {{ b.tasks.length }} 件</summary><TaskList :items="b.tasks" /></details></div></details>
<nav class="ws-related" aria-label="计划相关操作"><RouterLink to="/schedule">查看日历与课表<UiIcon name="calendar" :size="16" /></RouterLink><RouterLink to="/directions">调整方向<UiIcon name="directions" :size="16" /></RouterLink><RouterLink to="/review">复盘并调整任务<UiIcon name="review" :size="16" /></RouterLink></nav></template></template><p v-if="!backendDemo.state.liveAction" class="ws-demo-note">阶段目标及任务关联为演示配置；任务计数随完成与恢复更新。没有关联任务的阶段不显示推测进度。</p></div>
</template>
