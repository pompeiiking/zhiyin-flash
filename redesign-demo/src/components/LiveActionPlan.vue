<script setup lang="ts">
import ReportHistory from './ReportHistory.vue'
import { onMounted } from 'vue'
import { computed, ref, watch } from 'vue'
import { backendClient } from '../api/backend-client'
import { backendDemo } from '../lib/backend-demo'
import type { ActionTaskView } from '../api/backend-types'
import Foldable from './Foldable.vue'
import StatTile from './StatTile.vue'
import SkeletonBlock from './SkeletonBlock.vue'
import StatusBanner from './StatusBanner.vue'
import EmptyState from './EmptyState.vue'
defineProps<{ today?: boolean }>()
/* 把"正在读取计划"这件事报给页面：`/plan` 用它在阶段区改出骨架占位（MIGRATION §4.1 K5/K8），
   而不是在读完之前先给用户看"阶段计划还没有形成"那种假空态。 */
const emit = defineEmits<{ busy: [value: boolean] }>()
const plan = computed(() => backendDemo.state.liveAction), busy = ref(false), saving = ref(''), error = ref('')
watch(busy, value => emit('busy', value), { immediate: true })
async function load(){if(busy.value||saving.value)return;busy.value=true;error.value='';try{const result=await backendClient.action();if(!result||!Array.isArray(result.phases))throw new Error('Incomplete plan');backendDemo.setAction(result)}catch{error.value='暂时没有取得最新计划，当前内容仍保留。请重试。'}finally{busy.value=false}}
async function done(task: ActionTaskView){if(saving.value)return;saving.value=task.task_id;error.value='';try{const result=await backendClient.actionDone({task_id:task.task_id,done:!task.done});if(!result||!Array.isArray(result.phases))throw new Error('Incomplete plan');backendDemo.setAction(result)}catch{error.value='任务状态没有保存成功，请重试。原状态仍保留。'}finally{saving.value=''}}
/* 阶段头的读数：与 RoadmapView 的阶段头是同一形状（MIGRATION §1.3 B2 要求两页不许漂移）。
   参数用结构类型而不是 ActionPhaseView —— 模板里的 phase 来自 readonly 的 store 状态。 */
const phaseDone = (phase: { tasks?: readonly { done?: boolean }[] }) => phase.tasks?.filter(t => t.done).length ?? 0
const phaseTotal = (phase: { tasks?: readonly unknown[] }) => phase.tasks?.length ?? 0
const phaseTrend = (phase: { date_range?: string }) => (phase.date_range ? { label: phase.date_range } : null)
onMounted(()=>{ void load() })
</script>
<template><section class="live-action"><div class="ws-section-head"><h2>{{ today?'当前行动':'阶段任务' }}</h2><button class="btn" :disabled="busy||!!saving" @click="load">{{ busy?'正在读取…':'读取最新行动计划' }}</button></div>
<!-- 错误态：换成 StatusBanner（只报错不给下一步＝把问题丢回用户；组件为错误态内建动作位） -->
<StatusBanner v-if="error" class="live-action__error" tone="error" :message="error" retryable retry-label="重新读取" :retrying="busy" @retry="load" @dismiss="error=''" />
<template v-if="plan"><section v-if="today&&plan.next_task" class="report-lead"><h3>{{ plan.next_task.text }}</h3><p>{{ plan.next_task.phase }}</p><p v-if="plan.next_task.due_date" class="ws-muted">计划日期：{{ plan.next_task.due_date }}</p><button class="btn btn--primary" :disabled="!!saving" @click="done(plan.next_task)">{{ saving===plan.next_task.task_id?'正在保存…':plan.next_task.done?'恢复任务':'标记完成' }}</button></section>
<div class="live-action__phases" :aria-busy="busy">
  <!-- 刷新时把骨架**盖在仍在 DOM 的内容上**，不 v-if 摘内容（SkeletonBlock.vue:21-26）。
       旧写法只把按钮文案改成"正在读取…"，正文里那批数字看起来仍是可信的。 -->
  <SkeletonBlock v-if="busy" overlay variant="list" :lines="4" />
  <Foldable v-for="(phase,i) in plan.phases" :key="phase.name" variant="group" :static="i===0&&!today" :default-open="!today" :title="phase.name">
    <template #title><span class="plan-stage__title"><span class="plan-stage__mark fold-index">{{ i+1 }}</span><span class="plan-stage__copy"><strong>{{ phase.name }}</strong></span><StatTile class="plan-stage__tile" label="已完成" :value="phaseDone(phase)" :denominator="phaseTotal(phase)" :trend="phaseTrend(phase)" /></span></template>
    <ul class="ws-mini-list"><li v-for="task in phase.tasks?.filter(t=>!today||t.task_id!==plan?.next_task?.task_id)" :key="task.task_id" class="live-task"><div><strong>{{ task.text }}</strong><p v-if="task.due_date" class="ws-muted">{{ task.due_date }}</p><p v-if="task.done_at" class="ws-muted">完成于 {{ new Date(task.done_at).toLocaleString('zh-CN') }}</p></div><button class="btn" :aria-pressed="!!task.done" :disabled="!!saving" @click="done(task)">{{ saving===task.task_id?'正在保存…':task.done?'恢复任务':'完成任务' }}</button></li></ul>
    <p v-if="!phase.tasks?.length" class="ws-muted">当前阶段尚未安排任务。</p>
  </Foldable>
  <!-- 空态：`kind` 枚举里没有"计划"这一档（MIGRATION §4.2 E4 / §7 U2 的枚举缺口），借用语义最近的 report，
       并关掉它的预设下一步（report 的 NEXT 是"生成第一份诊断"，对阶段计划是错的）。 -->
  <EmptyState v-if="!plan.phases?.length" kind="report" size="sm" :next="false" title="当前尚未形成阶段计划" description="可以在咨询中明确方向，再安排阶段任务。" />
</div>
<p class="ws-muted ws-section">任务完成状态会保存到账号。</p></template>
<!-- 还没读过 = 这里没有内容。旧写法是"标题 + 按钮 + 一片空白"，看不出是没读还是读空了
     （MIGRATION §4.1 P1：口径说明降级成一行小字，不要占正文首屏）。 -->
<p v-else-if="!today" class="ws-muted ws-section">正在连接行动计划；读取失败时可重试。</p><ReportHistory v-if="!today" asset-type="action_plan" /></section></template>
<style scoped>
/* StatTile 自已是单列、右对齐；给它一个确定宽度，进度条才不是"和文字一样宽"。 */
.plan-stage__title { display: flex; align-items: center; gap: var(--sp-4); width: 100%; min-width: 0; }
.plan-stage__mark { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border: 1px solid var(--c-border-strong); border-radius: var(--r-sm); font-size: var(--fs-14); color: var(--c-text-2); }
.plan-stage__copy { flex: 1; min-width: 0; }
.plan-stage__copy strong { display: block; font-size: var(--fs-16); font-weight: var(--fw-medium); line-height: 1.7; }
.plan-stage__tile { flex: none; width: min(220px, 46%); }
.live-action__error { margin-top: var(--sp-4); }
/* 骨架 overlay 的定位参照（SkeletonBlock 要求父元素 position:relative） */
.live-action__phases { position: relative; }
/* 与 RoadmapView 的阶段头同一套窄屏规则（两页不许漂移） */
@media (max-width: 480px) {
  .plan-stage__title { flex-wrap: wrap; row-gap: var(--sp-2); }
  .plan-stage__tile { width: 100%; }
}
</style>
