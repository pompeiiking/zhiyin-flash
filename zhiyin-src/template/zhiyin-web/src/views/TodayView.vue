<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { backendClient } from '../api/backend-client'
import { studentApi } from '../api/student-capabilities'
import { backendDemo } from '../lib/backend-demo'
import { actionRows, dateKey, deadline } from '../lib/action-insights.mjs'
import type { ActionTaskView } from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import AssetNotice from '../components/AssetNotice.vue'
import TaskBrief from '../components/TaskBrief.vue'
import DetailPopover from '../components/DetailPopover.vue'
import StatusBanner from '../components/StatusBanner.vue'
import TaskEditor from '../components/TaskEditor.vue'
import TodayTaskRow from '../components/TodayTaskRow.vue'

const plan = computed(() => backendDemo.state.liveAction)
const tasks = computed(() => actionRows(plan.value) as ActionTaskView[])
const doneCount = computed(() => tasks.value.filter(task => task.done).length)
const activeTasks = computed(() => tasks.value.filter(task => !task.done))
const today = computed(() => dateKey(new Date().toISOString()))
const todayDate = new Date()
const todayDay = String(todayDate.getDate()).padStart(2, '0')
const todayMonth = todayDate.toLocaleDateString('zh-CN', { month: 'short' })
const todayWeekday = todayDate.toLocaleDateString('zh-CN', { weekday: 'short' })

const busy = ref(false)
const savingId = ref('')
const error = ref('')
const arrangementError = ref('')
const lastDone = ref<ActionTaskView | null>(null)
const suggestionsOpen = ref(false)

const phaseByTask = computed(() => new Map(
  (plan.value?.phases ?? []).flatMap(phase => (phase.tasks ?? []).map(task => [task.task_id, phase] as const)),
))

function actionable(task: ActionTaskView) {
  const phase = phaseByTask.value.get(task.task_id)
  return !task.done && task.status !== 'waiting' && !(phase?.blocked_by?.length)
}

function taskTimestamp(task: ActionTaskView) {
  const value = task.scheduled_at || task.due_date
  if (!value) return Number.POSITIVE_INFINITY
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? Number.POSITIVE_INFINITY : time
}

const specifiedFocus = computed(() => {
  const id = plan.value?.next_task?.task_id
  return id ? tasks.value.find(task => task.task_id === id && !task.done) : undefined
})
const focusTask = computed(() => specifiedFocus.value ?? [...activeTasks.value]
  .filter(actionable)
  .sort((a, b) => {
    const aOverdue = deadline(a.due_date).overdue ? 0 : 1
    const bOverdue = deadline(b.due_date).overdue ? 0 : 1
    return aOverdue - bOverdue || taskTimestamp(a) - taskTimestamp(b)
  })[0])
const focusIsSpecified = computed(() => !!specifiedFocus.value)

const queueTasks = computed(() => tasks.value.filter(task => task.task_id !== focusTask.value?.task_id))
const todayTasks = computed(() => queueTasks.value
  .filter(task => actionable(task) && (
    dateKey(task.scheduled_at) === today.value
    || deadline(task.due_date).days === 0
    || task.status === 'in_progress'
  ))
  .sort((a, b) => taskTimestamp(a) - taskTimestamp(b)))
const todayIds = computed(() => new Set(todayTasks.value.map(task => task.task_id)))
const overdueTasks = computed(() => queueTasks.value
  .filter(task => actionable(task) && !todayIds.value.has(task.task_id) && deadline(task.due_date).overdue)
  .sort((a, b) => taskTimestamp(a) - taskTimestamp(b)))
const overdueIds = computed(() => new Set(overdueTasks.value.map(task => task.task_id)))
const suggestedTasks = computed(() => queueTasks.value
  .filter(task => actionable(task) && !todayIds.value.has(task.task_id) && !overdueIds.value.has(task.task_id))
  .sort((a, b) => taskTimestamp(a) - taskTimestamp(b)))
const todayCommitment = computed(() => [focusTask.value, ...todayTasks.value].filter((task): task is ActionTaskView => !!task))

const timeFact = computed(() => backendDemo.state.liveWorkspace?.profile_panel?.fields?.find(field => ['time', 'weekly_hours', 'weekly_available_minutes'].includes(field.key)))
// 「可投入」优先读学期设置算出的每周课外剩余（与课表检查同一口径），没有再用画像里的旧字段兜底。
const capacityMinutes = ref<number | null>(null)
const capacityLabel = computed(() => {
  if (typeof capacityMinutes.value === 'number') return `${Math.round(capacityMinutes.value)} 分钟`
  return timeFact.value?.value || '未填写'
})
const capacityKnown = computed(() => typeof capacityMinutes.value === 'number' || !!timeFact.value?.value)
const estimatedMinutes = computed(() => todayCommitment.value.reduce((sum, task) => sum + (task.estimated_minutes || 0), 0))

function weekStartKey() {
  const start = new Date()
  start.setDate(start.getDate() - (start.getDay() + 6) % 7)
  return `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`
}

async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  arrangementError.value = ''
  try {
    const [actionResult, workspaceResult, capacityResult] = await Promise.allSettled([
      backendClient.action(),
      backendClient.workspace(),
      studentApi.workload(weekStartKey()),
    ])
    if (actionResult.status === 'fulfilled') backendDemo.setAction(actionResult.value)
    else error.value = (actionResult.reason as Error).message
    if (workspaceResult.status === 'fulfilled') backendDemo.setWorkspace(workspaceResult.value)
    if (workspaceResult.status === 'rejected' && capacityResult.status === 'rejected') arrangementError.value = '可投入时间暂时未读取到，不影响查看行动任务。'
    if (capacityResult.status === 'fulfilled') {
      const week = capacityResult.value.weeks?.[0]
      capacityMinutes.value = typeof week?.remaining_minutes === 'number' ? week.remaining_minutes : null
    }
  } finally {
    busy.value = false
  }
}

async function finish(task: ActionTaskView) {
  if (savingId.value) return
  savingId.value = task.task_id
  error.value = ''
  try {
    backendDemo.setAction(await backendClient.actionDone({ task_id: task.task_id, done: !task.done }))
    lastDone.value = task.done ? null : { ...task, done: true }
  } catch (caught) {
    error.value = (caught as Error).message
  } finally {
    savingId.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="ws-page today-page">
    <PageHeading title="今日行动" description="把计划收成一条可执行队列：先看现在这一件，再处理接下来的任务。">
      <TaskEditor class="btn" />
      <RouterLink class="btn" to="/plan">阶段计划</RouterLink>
    </PageHeading>

    <AssetNotice />
    <StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" :retrying="busy" @retry="load" />

    <div class="today-layout">
      <div class="today-main">
        <section v-if="focusTask" class="today-focus" aria-labelledby="today-focus-title">
          <div class="today-focus__body">
            <header class="today-focus__head">
              <div>
                <h2 class="today-focus__label">现在做</h2>
                <p class="today-focus__source">{{ focusIsSpecified ? '计划指定的下一项' : '按截止与安排时间显示' }}</p>
              </div>
              <span class="today-focus__deadline" :class="{ 'today-urgent': deadline(focusTask.due_date).overdue }">{{ deadline(focusTask.due_date).label }}</span>
            </header>
            <p class="today-focus__phase">{{ focusTask.phase || '阶段任务' }}<span v-if="focusTask.scheduled_at"> · {{ new Date(focusTask.scheduled_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) }}</span><span v-if="focusTask.estimated_minutes"> · 预计 {{ focusTask.estimated_minutes }} 分钟</span></p>
            <h2 id="today-focus-title">{{ focusTask.text }}</h2>
            <div class="today-focus__actions">
              <button class="btn btn--primary" type="button" :disabled="!!savingId" @click="finish(focusTask)">{{ savingId === focusTask.task_id ? '正在保存…' : '完成' }}</button>
              <TaskEditor :task="focusTask" trigger-text="调整" />
              <DetailPopover title="这项任务需要帮助？" label="打开当前任务帮助" side="right">
                <template #trigger>帮助</template>
                <TaskBrief />
                <RouterLink class="ws-text-link today-help-link" :to="'/chat?question=' + encodeURIComponent('我想讨论这项任务：' + focusTask.text + '；所属阶段：' + (focusTask.phase || '未提供'))">和生涯助手讨论这项任务</RouterLink>
              </DetailPopover>
            </div>
          </div>
        </section>

        <section v-else class="today-empty today-empty--focus">
          <template v-if="busy"><h2>正在读取行动计划…</h2></template>
          <template v-else-if="plan?.has_plan === false"><h2>还没有行动计划</h2><p>先从咨询中明确目标，再把建议保存为阶段与任务。</p><RouterLink class="btn btn--primary" to="/chat">开始咨询</RouterLink></template>
          <template v-else-if="tasks.length && !activeTasks.length"><h2>计划内任务已全部完成</h2><p>可以查看复盘，或回到阶段计划安排下一步。</p><RouterLink class="btn" to="/review">查看复盘</RouterLink></template>
          <template v-else><h2>当前没有可直接执行的任务</h2><p>任务可能仍在等待依赖；请先核对等待条件或阶段计划。</p><RouterLink class="btn" to="/plan">查看阶段计划</RouterLink></template>
        </section>

        <StatusBanner
            v-if="lastDone"
            class="today-undo"
            tone="success"
            :message="`已完成“${lastDone.text}”`"
            action-label="撤销"
            :auto-dismiss="0"
            @action="finish(lastDone)"
            @dismiss="lastDone = null"
        />

        <section v-if="todayTasks.length || overdueTasks.length || suggestedTasks.length" class="today-queue" aria-label="今日任务队列">
          <section v-if="todayTasks.length" class="today-next" aria-labelledby="today-queue-title">
            <div class="today-section-head">
              <h2 id="today-queue-title">接下来</h2>
              <span>{{ todayTasks.length }} 项</span>
            </div>

            <TodayTaskRow v-for="task in todayTasks" :key="task.task_id" :task="task" :busy="!!savingId" @toggle="finish" />
          </section>

          <section v-if="overdueTasks.length" class="today-decision" aria-labelledby="today-decision-title">
            <div class="today-decision__head">
              <div><h2 id="today-decision-title">{{ overdueTasks.length }} 项需要改期</h2><p>已过截止日，不再默认算作今天的任务。</p></div>
            </div>
            <TodayTaskRow v-for="task in overdueTasks" :key="task.task_id" :task="task" :busy="!!savingId" @toggle="finish" />
          </section>

          <section v-if="suggestedTasks.length" class="today-suggestions" aria-labelledby="today-suggestions-title">
            <header class="today-suggestions__head">
              <div>
                <h2 id="today-suggestions-title">下一步候选</h2>
              </div>
              <button
                v-if="suggestedTasks.length > 1"
                class="ws-text-button"
                type="button"
                :aria-expanded="suggestionsOpen"
                @click="suggestionsOpen = !suggestionsOpen"
              >{{ suggestionsOpen ? '收起候选' : `查看其余 ${suggestedTasks.length - 1} 项` }}</button>
            </header>
            <TodayTaskRow :task="suggestedTasks[0]" mode="candidate" />
            <template v-if="suggestionsOpen">
              <TodayTaskRow v-for="task in suggestedTasks.slice(1, 5)" :key="task.task_id" :task="task" mode="candidate" />
              <RouterLink v-if="suggestedTasks.length > 5" class="ws-text-link today-suggestions__more" to="/plan">在阶段计划查看其余 {{ suggestedTasks.length - 5 }} 项</RouterLink>
            </template>
          </section>

        </section>
      </div>

      <aside class="today-aside" aria-label="今日概览">
        <section class="today-date-card">
          <p>{{ todayMonth }} · {{ todayWeekday }}</p>
          <strong>{{ todayDay }}</strong>
          <span>今天</span>
        </section>
        <section class="today-capacity" aria-labelledby="today-capacity-title">
          <div class="today-capacity__identity">
            <h2 id="today-capacity-title">今日容量</h2>
            <p v-if="arrangementError">{{ arrangementError }}</p>
          </div>
          <dl>
            <div><dt>可投入</dt><dd>{{ capacityLabel }}</dd></div>
            <div><dt>预计用时</dt><dd>{{ estimatedMinutes ? `${estimatedMinutes} 分钟` : '未估算' }}</dd></div>
            <div><dt>逾期待处理</dt><dd>{{ overdueTasks.length }} 项</dd></div>
          </dl>
          <div class="today-progress">
            <span>阶段计划</span><strong>{{ doneCount }} / {{ tasks.length }}</strong>
            <progress v-if="tasks.length" :value="doneCount" :max="tasks.length" aria-label="计划任务完成进度" />
          </div>
          <RouterLink class="btn today-capacity__action" :to="capacityKnown ? '/schedule' : '/schedule?setup=1'">{{ capacityKnown ? '检查日程' : '填写时间' }}</RouterLink>
          <p v-if="!capacityKnown" class="today-capacity__hint">在「日历与课表」的课表检查里打开「设置学期时间」，填写每周课外可用分钟并保存，就会用于计算这里的可投入时间。</p>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.today-page { max-width: 1080px; margin-inline: auto; }
.today-layout { display: grid; grid-template-columns: minmax(0, 1fr) 248px; gap: 22px; align-items: start; margin-top: 16px; }
.today-main { min-width: 0; }
.today-focus { overflow: hidden; color: var(--c-text); background: var(--c-surface); border: 1px solid var(--c-border); border-top: 4px solid var(--c-primary); border-radius: 12px; box-shadow: var(--e-2); }
.today-focus__body { padding: 24px 28px 26px; }
.today-focus__head,.today-section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.today-focus__label { color: var(--c-primary); font-size: var(--fs-14); font-weight: var(--fw-semibold); }
.today-focus__source,.today-focus__phase { color: var(--c-text-3); font-size: var(--fs-12); }
.today-focus__phase { margin-top: 22px; }
.today-focus__body > h2 { max-width: 22em; margin-top: 6px; color: var(--c-text); font-size: clamp(23px, 2.5vw, 30px); font-weight: 650; line-height: 1.38; letter-spacing: -.02em; }
.today-focus__deadline { flex: none; padding: 5px 9px; color: var(--c-text-2); background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: var(--r-sm); font-size: var(--fs-12); }
.today-focus__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 20px; margin-top: 22px; }
.today-focus__actions .btn--primary { box-shadow: none; }
.today-focus__actions :deep(.detail-trigger) { min-height: 42px; color: var(--c-text-2); }
.today-focus__actions :deep(.detail-trigger:hover) { color: var(--c-primary); }
.today-help-link { display: block; margin-top: 18px; }
.today-focus .today-urgent { color: var(--c-attention-strong); background: var(--c-attention-weak); border-color: color-mix(in srgb, var(--c-attention) 30%, transparent); }
.today-urgent { color: var(--c-attention); font-weight: var(--fw-semibold); }
.today-empty--focus { padding: 28px; background: var(--c-surface); }
.today-empty--focus p { margin: 8px 0 20px; color: var(--c-text-2); }
.today-undo { margin-top: 12px; }
.today-queue { margin-top: 14px; padding: 20px 24px 18px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; box-shadow: var(--e-1); }
.today-next { padding-top: 16px; }
.today-section-head h2 { color: var(--c-text); font-size: var(--fs-20); }
.today-section-head > span { color: var(--c-text-3); font-size: var(--fs-12); }
.today-decision { padding-top: 0; }
.today-next + .today-decision { margin-top: 10px; border-top: 1px solid var(--c-border); }
.today-decision__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.today-decision__head h2 { color: var(--c-text); font-size: var(--fs-16); }
.today-decision__head p { margin-top: 4px; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.7; }
.today-suggestions { margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--c-border); }
.today-suggestions__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.today-suggestions__head h2 { font-size: var(--fs-16); }
.today-suggestions__head p { margin-top: 3px; color: var(--c-text-3); font-size: var(--fs-12); }
.today-suggestions__head .ws-text-button { flex: none; min-height: 44px; color: var(--c-primary); }
.today-suggestions__more { display: inline-flex; min-height: 44px; align-items: center; margin-top: 8px; }
.today-aside { position: sticky; top: 16px; display: grid; gap: 12px; }
.today-date-card { position: relative; overflow: hidden; min-height: 164px; padding: 20px; color: var(--c-on-primary); background: var(--c-primary-brand); border-radius: 12px; box-shadow: var(--e-2); }
.today-date-card::after { content: ''; position: absolute; right: -36px; bottom: -54px; width: 150px; height: 150px; border: 28px solid rgba(255,255,255,.11); border-radius: 50%; }
.today-date-card p { color: var(--c-on-primary); font-size: var(--fs-13); }
.today-date-card strong { display: block; margin-top: 15px; font-family: Georgia, 'Times New Roman', serif; font-size: 58px; font-weight: 400; line-height: .9; }
.today-date-card span { display: block; margin-top: 8px; font-size: var(--fs-14); }
.today-capacity { padding: 20px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; box-shadow: var(--e-1); }
.today-capacity__identity h2 { font-size: var(--fs-16); }
.today-capacity__identity p { margin-top: 5px; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.65; }
.today-capacity dl { display: grid; gap: 0; margin: 16px 0 0; }
.today-capacity dl div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--c-border); }
.today-capacity dt { color: var(--c-text-3); font-size: var(--fs-12); }
.today-capacity dd { margin: 0; color: var(--c-text); font-size: var(--fs-14); font-weight: var(--fw-semibold); font-variant-numeric: tabular-nums; }
.today-progress { display: grid; grid-template-columns: 1fr auto; gap: 7px 10px; margin-top: 16px; color: var(--c-text-3); font-size: var(--fs-12); }
.today-progress strong { color: var(--c-text); font-variant-numeric: tabular-nums; }
.today-progress progress { grid-column: 1 / -1; width: 100%; height: 5px; accent-color: var(--c-primary); }
.today-capacity__action { width: 100%; margin-top: 18px; white-space: nowrap; }
.today-capacity__hint { margin-top: 10px; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.65; }
@media (max-width: 720px) {
  .today-layout { grid-template-columns: minmax(0, 1fr); }
  .today-aside { position: static; grid-template-columns: 150px minmax(0, 1fr); }
  .today-date-card { min-height: 100%; }
}
@media (max-width: 600px) {
  .today-layout { margin-top: 8px; }
  .today-aside { grid-template-columns: minmax(0, 1fr); }
  .today-date-card { min-height: 132px; }
  .today-date-card strong { font-size: 48px; }
  .today-focus__body { padding: 20px 16px 22px; }
  .today-focus__head { flex-direction: column; gap: 8px; }
  .today-focus__phase { margin-top: 18px; }
  .today-focus__body > h2 { font-size: 21px; }
  .today-focus__actions .btn { flex: 1 1 140px; }
  .today-focus__actions :deep(.detail-trigger) { min-height: 44px; }
  .today-queue { padding: 18px 16px 8px; }
  .today-decision__head { flex-direction: column; gap: 6px; }
  .today-suggestions__head { align-items: flex-start; }
  .today-suggestions__head p { max-width: 22em; }
}
</style>
