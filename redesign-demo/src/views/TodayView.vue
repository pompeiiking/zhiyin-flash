<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'
import TaskList from '../components/TaskList.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import { taskOriginLabel } from '../lib/presentation'
const progress = computed(() => demo.use.profileProgress.value)
const smallest = computed(() => demo.use.smallestNow.value)
const group = ref('now')
const groups = computed(() => [
  { key: 'now', label: '待执行', items: demo.use.now.value },
  { key: 'waiting', label: '等待中', items: demo.use.waiting.value },
  { key: 'done', label: '已完成', items: demo.use.done.value },
])
const active = computed(() => groups.value.find((g) => g.key === group.value)!)
const lastDone = computed(() => demo.use.done.value.find((t) => t.id === demo.state.lastDoneId))
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
  <div class="ws-page">
    <PageHeading title="行动计划" description="管理当前任务，查看执行状态与阶段计划。"><RouterLink class="btn" to="/notes"><UiIcon name="plus" :size="16" />添加个人待办</RouterLink></PageHeading>
    <nav class="ws-subnav" aria-label="行动计划视图"><RouterLink to="/home" aria-current="page">今日行动</RouterLink><RouterLink to="/plan">阶段计划</RouterLink></nav>
    <section v-if="smallest" class="ws-paper ws-feature">
      <div><div class="ws-feature__caption"><UiIcon name="action" :size="18" /><span>建议优先任务</span><span>{{ taskOriginLabel(smallest.origin) }}</span></div><h2>{{ smallest.title }}</h2><p>{{ smallest.why }}</p></div>
      <div class="ws-feature__action"><p>约 {{ smallest.minutes }} 分钟</p><button class="btn btn--primary" @click="demo.completeTask(smallest.id)">标记完成<UiIcon name="check" :size="18" /></button><button v-if="smallest.minutes > 5" class="ws-text-button" @click="demo.shrinkTask(smallest.id)">拆分为 5 分钟任务</button></div>
    </section>
    <section v-else class="ws-paper"><div class="ws-empty"><h2 class="ws-section-title">{{ demo.use.done.value.length ? '当前任务已完成' : '暂无行动任务' }}</h2><p>完成咨询并明确方向后，可生成行动任务。</p><RouterLink class="btn btn--primary" to="/chat">开始咨询</RouterLink></div></section>
    <div class="ws-two-columns ws-section">
      <section class="ws-paper">
        <div class="ws-section-head"><h2>你的任务</h2><span class="ws-muted">按状态查看</span></div>
        <div class="ws-tabs" aria-label="任务分组"><button v-for="g in groups" :key="g.key" :aria-pressed="group === g.key" @click="group = g.key">{{ g.label }}<span class="ws-tab-count">{{ g.items.length }}</span></button></div>
        <TaskList :items="active.items" :mode="group" />
      </section>
      <aside class="ws-aside">
        <section><h2>信息完整度</h2><div class="ws-status-line"><strong>{{ progress.known }} / {{ progress.total }}</strong><span>{{ progress.gap ? '还有 ' + progress.gap + ' 条待了解' : '已了解完整' }}</span></div><div class="ws-progress"><span :style="{ '--value': progress.known / progress.total }" /></div><p>信息保留来源，支持逐项补充与更正。</p><RouterLink class="ws-text-link" to="/profile">查看个人画像<UiIcon name="arrow" :size="16" /></RouterLink></section>
        <section><h2>最近完成</h2><p v-if="lastDone" role="status">「{{ lastDone.title }}」已记入完成记录。你可以在任务分组中查看或恢复。</p><p v-else>完成任务后，将在此显示最近的执行记录。</p><RouterLink class="ws-text-link" to="/review">查看复盘记录<UiIcon name="arrow" :size="16" /></RouterLink></section>
        <section><p>执行遇到困难时，可通过咨询调整任务或方案。</p><RouterLink class="ws-text-link" to="/chat">回到对话<UiIcon name="arrow" :size="16" /></RouterLink></section>
      </aside>
    </div>
    <div v-if="!demo.state.guidesClosed.home" class="ws-guide"><UiIcon name="info" :size="18" /><p>先做最小的一件。其他任务可以按状态查看，完成后也能放回去。</p><button @click="demo.closeGuide('home')">收起</button></div>
    <p class="ws-demo-note">任务与档案为预置示例，操作会改变当前演示中的记录。</p>
    <InfoSheet :open="addOpen" title="记一件今天能做的事" @close="addOpen = false"><form @submit.prevent="add"><label class="ws-field">做什么<input v-model="title" maxlength="100" placeholder="例如：给学长发一条消息" /></label><label class="ws-field">大约需要多久<select v-model.number="minutes"><option :value="5">5 分钟</option><option :value="15">15 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">排进今天</button><button class="ws-text-button" type="button" @click="addOpen = false">先不记</button></div></form></InfoSheet>
  </div>
</template>
