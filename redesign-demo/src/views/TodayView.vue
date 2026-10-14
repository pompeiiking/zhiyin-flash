<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'
import ActionPlanNav from '../components/ActionPlanNav.vue'
import LiveActionPlan from '../components/LiveActionPlan.vue'
import TaskBrief from '../components/TaskBrief.vue'
import { backendDemo } from '../lib/backend-demo'
import AssetNotice from '../components/AssetNotice.vue'
import TaskList from '../components/TaskList.vue'
import EmptyState from '../components/EmptyState.vue'
import StatTile from '../components/StatTile.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import { taskOriginLabel } from '../lib/presentation'
import PanelTabs from '../components/PanelTabs.vue'

const smallest = computed(() => demo.use.smallestNow.value)
const group = ref('now')
const groups = computed(() => [
  { key: 'now', label: '其他待执行', items: demo.use.now.value.filter(t => t.id !== smallest.value?.id) },
  { key: 'waiting', label: '等待中', items: demo.use.waiting.value },
  { key: 'done', label: '已完成', items: demo.use.done.value },
])
const active = computed(() => groups.value.find((g) => g.key === group.value)!)
const lastDone = computed(() => demo.use.done.value.find((t) => t.id === demo.state.lastDoneId))
/* 执行记录那一段原本只有一句分母文案（"已完成 N 件任务…"）—— 换成 StatTile，
   读数和进度条一起长出来（MIGRATION §3.3 T8）。与 /plan 的"当前安排"是同一形状。 */
const doneCount = computed(() => demo.use.done.value.length)
const totalCount = computed(() => demo.use.done.value.length + demo.use.now.value.length + demo.use.waiting.value.length)
const addOpen = ref(false)
const title = ref('')
const minutes = ref(5)
const error = ref('')
function add() {
  if (!title.value.trim()) { error.value = '先写下你准备做什么。'; return }
  demo.planChatTask(title.value.trim(), minutes.value)
  title.value = ''; error.value = ''; addOpen.value = false; group.value = 'now'
}
</script>
<template>
  <div class="ws-page journey-page">
    <PageHeading title="行动计划" description="从一件具体的小事开始，让想好的方向往前走。"><RouterLink class="btn" to="/notes"><UiIcon name="plus" :size="16" />添加个人待办</RouterLink></PageHeading>
    <ActionPlanNav/><AssetNotice/><LiveActionPlan today/><TaskBrief/><template v-if="!backendDemo.state.liveAction">
    <section v-if="lastDone" :key="lastDone.id" class="journey-complete" role="status">
      <span class="journey-complete__mark"><UiIcon name="check" :size="24" /></span>
      <div><h2>又完成了一步</h2><p>{{ lastDone.title }}</p></div>
      <button class="ws-text-button" @click="demo.reopenTask(lastDone.id)">恢复任务</button>
    </section>
    <section v-if="smallest" class="journey-focus">
      <div class="journey-focus__copy">
        <h2>{{ smallest.title }}</h2><p>{{ smallest.why }}</p>
        <div class="journey-focus__meta"><span><UiIcon name="review" :size="17" />约 {{ smallest.minutes }} 分钟</span><span><UiIcon name="action" :size="17" />{{ taskOriginLabel(smallest.origin) }}</span><span v-if="smallest.due"><UiIcon name="calendar" :size="17" />{{ smallest.due }}</span></div>
        <div class="journey-focus__actions"><button class="btn btn--primary" @click="demo.completeTask(smallest.id)">标记完成<UiIcon name="check" :size="18" /></button><button v-if="smallest.minutes > 5" class="ws-text-button" @click="demo.shrinkTask(smallest.id)">先拆成 5 分钟</button><RouterLink v-else class="ws-text-link" to="/chat">需要调整，和顾问聊聊<UiIcon name="arrow" :size="16" /></RouterLink></div>
      </div>
    </section>
    <!-- 空态：`.ws-empty` → EmptyState（MIGRATION §4.2 E1，kind=notes）。
         整块正文被空态顶掉，所以显式 heading-level="2"（H5：不显式传会从 h2 掉成 h3）。 -->
    <section v-else class="ws-paper"><EmptyState kind="notes" :heading-level="2" :title="demo.use.done.value.length ? '当前任务已完成' : '暂无行动任务'" description="完成咨询并明确方向后，可生成行动任务。"><RouterLink class="btn btn--primary" to="/chat">开始咨询</RouterLink></EmptyState></section>
    <div class="journey-action-grid">
      <section class="ws-paper journey-task-list">
        <div class="ws-section-head"><h2>执行队列</h2><span class="ws-muted">按状态查看</span></div>
        <PanelTabs v-model="group" label="任务分组" :items="groups.map(g => ({ key: g.key, label: g.label, count: g.items.length }))"><TaskList :items="active.items.filter(t => group !== 'now' || t.id !== smallest?.id)" :mode="group" /></PanelTabs>
      </section>
      <aside class="journey-action-aside ws-related-block">

        <section><h2>执行记录</h2><StatTile v-if="lastDone" label="已完成" :value="doneCount" :denominator="totalCount" :trend="{ label: '可在完成记录中查看' }"/><p v-else>完成任务后，将在此显示最近的执行记录。</p><RouterLink class="ws-text-link" to="/review">查看复盘记录<UiIcon name="arrow" :size="16" /></RouterLink></section>
        <section><p>执行遇到困难时，可通过咨询调整任务或方案。</p><RouterLink class="ws-text-link" to="/chat">回到对话<UiIcon name="arrow" :size="16" /></RouterLink></section>
      </aside>
    </div>
    <div v-if="!demo.state.guidesClosed.home" class="ws-guide"><UiIcon name="info" :size="18" /><p>优先完成当前建议任务。其他任务可按状态查看，完成后支持恢复。</p><button @click="demo.closeGuide('home')">收起</button></div>
    <p class="ws-demo-note">任务与档案为预置示例，操作会改变当前演示中的记录。</p>
    </template><InfoSheet :open="addOpen" shape="dialog" title="记一件今天能做的事" @close="addOpen = false"><form @submit.prevent="add"><label class="ws-field">做什么<input v-model="title" maxlength="100" placeholder="例如：给学长发一条消息" /></label><label class="ws-field">大约需要多久<select v-model.number="minutes"><option :value="5">5 分钟</option><option :value="15">15 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">排进今天</button><button class="ws-text-button" type="button" @click="addOpen = false">先不记</button></div></form></InfoSheet>
  </div>
</template>
