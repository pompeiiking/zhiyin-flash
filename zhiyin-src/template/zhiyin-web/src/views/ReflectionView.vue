<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { backendClient } from '../api/backend-client'
import { backendDemo } from '../lib/backend-demo'
import { systemData, loadRecords } from '../lib/system-data'
import { actionRows, dateKey, deadline } from '../lib/action-insights.mjs'
import { usePagedItems } from '../lib/paged-items'
import type { Review } from '../api/student-capabilities'
import StructuredReview from '../components/StructuredReview.vue'
import PageHeading from '../components/PageHeading.vue'
import DetailPopover from '../components/DetailPopover.vue'
import ResultPager from '../components/ResultPager.vue'
import StatusBanner from '../components/StatusBanner.vue'

const busy = ref(false)
const error = ref('')
const status = ref('')
const selectedId = ref('')
const query = ref('')
const filter = ref('all')
const reviews = ref<Review[]>([])
const reviewPanel = ref<InstanceType<typeof StructuredReview> | null>(null)

const tasks = computed(() => actionRows(backendDemo.state.liveAction))
const completed = computed(() => tasks.value.filter((task) => task.done))
const pending = computed(() => tasks.value.filter((task) => !task.done))
const overdue = computed(() => pending.value.filter((task) => deadline(task.due_date).overdue))
const reviewedTaskIds = computed(() => new Set(reviews.value.map((review) => review.task_id)))
// 默认优先带出「最近逾期」与「最近完成」的任务，新手不用先手动去"切换任务"里挑。
const overdueSorted = computed(() => [...overdue.value].sort((a, b) =>
  (dateKey(a.due_date) || '9999-12-31').localeCompare(dateKey(b.due_date) || '9999-12-31')))
const recentCompleted = computed(() => [...completed.value].sort((a, b) =>
  (b.done_at || '').localeCompare(a.done_at || '')))
const upcomingPending = computed(() => [...pending.value]
  .filter((task) => !deadline(task.due_date).overdue)
  .sort((a, b) => (dateKey(a.due_date) || '9999-12-31').localeCompare(dateKey(b.due_date) || '9999-12-31')))
const focusTaskPool = computed(() => {
  const rows = [
    ...overdueSorted.value,
    ...recentCompleted.value.filter((task) => !reviewedTaskIds.value.has(task.task_id)),
    ...pending.value.filter((task) => !deadline(task.due_date).overdue && reviewedTaskIds.value.has(task.task_id)),
    // 兜底：所有已完成（已复盘过的也可回看）与未到期任务，保证有任务时不会空着。
    ...recentCompleted.value,
    ...upcomingPending.value,
  ]
  const seen = new Set<string>()
  return rows.filter((task) => !seen.has(task.task_id) && seen.add(task.task_id))
})
const focusIndex = computed(() => focusTaskPool.value.findIndex((task) => task.task_id === selectedId.value))
const queuePosition = computed(() => focusIndex.value >= 0 ? focusIndex.value + 1 : 0)

watch(focusTaskPool, (items) => {
  if (!selectedId.value || !items.some((task) => task.task_id === selectedId.value)) {
    selectedId.value = items[0]?.task_id ?? ''
  }
}, { immediate: true })

function legacyReviewTaskId(text: string) {
  return text.match(/^【任务复盘:([^】]+)】/)?.[1] ?? ''
}

const records = computed(() => [
  ...reviews.value.map((review) => ({
    id: review.id,
    title: review.task_text,
    date: review.updated_at,
    kind: 'review',
    label: review.applied_at ? '复盘已应用' : review.result === 'continue' ? '仅保留记录' : '待应用',
    body: `${review.reason}${review.note ? ` · ${review.note}` : ''}`,
  })),
  ...completed.value.map((task) => ({
    id: `task-${task.task_id}`,
    title: task.text,
    date: task.done_at || '',
    kind: 'done',
    label: '任务完成',
    body: task.phase,
  })),
  ...systemData.events
    .filter((event) => !(event.type === 'milestone_done' && completed.value.some((task) => task.task_id === event.related_task_id)))
    .map((event) => ({
      id: `event-${event.id}`,
      title: event.title,
      date: event.occurred_at || '',
      kind: 'event',
      label: '系统记录',
      body: event.detail || '',
    })),
  ...backendDemo.state.notes
    .filter((note) => note.text.startsWith('【任务复盘:') && !reviewedTaskIds.value.has(legacyReviewTaskId(note.text)))
    .map((note) => ({
      id: `note-${note.id}`,
      title: tasks.value.find((task) => task.task_id === legacyReviewTaskId(note.text))?.text || '历史任务复盘',
      date: note.created_at,
      kind: 'review',
      label: '历史复盘说明',
      body: note.text.slice(note.text.indexOf('】') + 1),
    })),
].sort((a, b) => b.date.localeCompare(a.date)))

const filtered = computed(() => records.value.filter((record) =>
  (filter.value === 'all' || record.kind === filter.value)
  && [record.title, record.body, record.date].join(' ').includes(query.value.trim()),
))
const { page, paged } = usePagedItems(filtered, 5, () => [query.value, filter.value])

function selectRelativeTask(offset: number) {
  const next = focusTaskPool.value[focusIndex.value + offset]
  if (next) selectedId.value = next.task_id
}

async function load(includeReviews = false) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  status.value = ''
  try {
    const requests: Promise<unknown>[] = [backendClient.action(), backendClient.notes(), loadRecords()]
    if (includeReviews && reviewPanel.value) requests.push(reviewPanel.value.reload())
    const results = await Promise.allSettled(requests)
    if (results[0].status === 'fulfilled') backendDemo.setAction(results[0].value as Awaited<ReturnType<typeof backendClient.action>>)
    if (results[1].status === 'fulfilled') backendDemo.setNotes(results[1].value as Awaited<ReturnType<typeof backendClient.notes>>)
    const failure = results.find((result) => result.status === 'rejected')
    if (failure?.status === 'rejected') throw failure.reason
    if (includeReviews) status.value = '记录已刷新。'
  } catch (caught) {
    error.value = (caught as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(() => load(false))
</script>

<template>
  <div class="ws-page review-page">
    <PageHeading title="任务复盘" description="回看一次行动，把经验变成更清楚的下一步。">
      <button class="btn" :disabled="busy" @click="load(true)">{{ busy ? '正在刷新…' : '刷新记录' }}</button>
      <RouterLink class="btn" to="/home">回到今日行动</RouterLink>
    </PageHeading>

    <StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load(true)" />
    <p v-if="status" class="review-page__status" role="status">{{ status }}</p>

    <section class="review-workspace" aria-labelledby="review-workspace-title">
      <nav class="review-session-bar" aria-label="复盘队列" :aria-busy="busy">
        <div class="review-session-bar__copy">
          <span id="review-workspace-title">本次回看</span>
          <strong v-if="busy && !tasks.length">正在整理任务…</strong>
          <strong v-else-if="focusTaskPool.length">{{ overdue.length }} 项逾期，{{ completed.length }} 项已完成</strong>
          <strong v-else>还没有可复盘的任务</strong>
        </div>
        <div v-if="focusTaskPool.length" class="review-session-bar__progress">
          <span>{{ queuePosition || '自由选择' }}<template v-if="queuePosition"> / {{ focusTaskPool.length }}</template></span>
          <progress :value="queuePosition" :max="focusTaskPool.length" aria-label="复盘进度"></progress>
        </div>
        <div v-else-if="!busy" class="review-session-bar__empty">
          <p>先安排并完成一项任务，再回来记录实际发生的事。</p>
          <RouterLink class="btn btn--sm" to="/home">去今日行动</RouterLink>
        </div>
        <div class="review-session-bar__actions">
          <button class="btn btn--sm" :disabled="focusIndex <= 0" @click="selectRelativeTask(-1)">上一项</button>
          <button class="btn btn--sm" :disabled="focusIndex < 0 || focusIndex >= focusTaskPool.length - 1" @click="selectRelativeTask(1)">下一项</button>
        </div>
      </nav>

      <StructuredReview
        ref="reviewPanel"
        :task-id="selectedId"
        :loading-tasks="busy"
        @selected-task="selectedId = $event"
        @loaded="reviews = $event"
      />
    </section>

    <details class="review-records">
      <summary>
        <span><strong>最近发生</strong><small>复盘、任务完成和系统事件都保留在这里。</small></span>
        <span>{{ records.length }} 条记录</span>
      </summary>
      <div class="review-records__body" aria-labelledby="review-records-title">
        <div class="review-records__head">
          <h2 id="review-records-title">执行记录</h2>
          <RouterLink to="/achievements">查看成长记录</RouterLink>
        </div>

        <div class="review-record-tools">
          <label class="information-search">查找记录
            <input v-model="query" name="review-search" type="search" autocomplete="off" placeholder="例如：程序设计或复盘原因…" />
          </label>
          <label class="ws-field">记录类型
            <select v-model="filter" name="review-type" autocomplete="off">
              <option value="all">全部记录</option>
              <option value="done">任务完成</option>
              <option value="review">复盘记录</option>
              <option value="event">系统记录</option>
            </select>
          </label>
        </div>

        <ol class="review-timeline">
          <li v-for="record in paged" :key="record.id">
            <time>{{ dateKey(record.date) || '日期未提供' }}</time>
            <div class="review-timeline__body">
              <strong>{{ record.title }}</strong>
              <DetailPopover :title="record.title" :label="`查看记录：${record.title}`" side="right">
                <template #trigger>查看详情</template>
                <p>{{ record.body || '没有补充说明。' }}</p>
                <p class="ws-muted">{{ record.label }} · {{ record.date ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(record.date)) : '时间未提供' }}</p>
              </DetailPopover>
            </div>
            <span class="review-timeline__state">{{ record.label }}</span>
          </li>
        </ol>
        <div v-if="!filtered.length && !busy" class="review-records__empty">
          <strong>没有符合条件的记录</strong>
          <p>可以调整关键词或记录类型。</p>
        </div>
        <ResultPager v-model:page="page" :total="filtered.length" :size="5" label="复盘记录" />
      </div>
    </details>
  </div>
</template>

<style scoped>
/* Keep the page layout local: older global review grids reserve an unused rail. */
:global(.app.app--workspace .review-page.review-page) { display: block; }
:global(.app[data-route='/review'] .app__main) { scrollbar-gutter: stable; }
.review-page__status { margin: -8px 0 18px; color: var(--c-text-2); font-size: var(--fs-14); }
.review-workspace { display: grid; gap: 12px; max-width: 900px; margin-inline: auto; }
.review-session-bar { position: sticky; top: 12px; z-index: 5; display: grid; grid-template-columns: minmax(180px, auto) minmax(140px, 1fr) auto; gap: 22px; align-items: center; min-height: 66px; padding: 10px 12px 10px 18px; border: 1px solid var(--c-border-strong); border-radius: var(--r-lg); background: var(--workspace-float); box-shadow: 0 12px 30px -26px rgba(22,31,44,.55); }
.review-session-bar__copy { display: grid; gap: 2px; min-width: 0; }
.review-session-bar__copy > span { color: var(--c-primary); font-size: var(--fs-12); font-weight: var(--fw-semibold); }
.review-session-bar__copy strong { overflow: hidden; font-size: var(--fs-14); text-overflow: ellipsis; white-space: nowrap; }
.review-session-bar__progress { display: grid; grid-template-columns: auto minmax(80px, 1fr); gap: 10px; align-items: center; min-width: 0; color: var(--c-text-3); font-size: var(--fs-12); font-variant-numeric: tabular-nums; }
.review-session-bar__progress progress { width: 100%; height: 5px; overflow: hidden; border: 0; border-radius: var(--r-pill); background: var(--c-surface-3); color: var(--c-primary); }
.review-session-bar__progress progress::-webkit-progress-bar { background: var(--c-surface-3); }
.review-session-bar__progress progress::-webkit-progress-value { border-radius: var(--r-pill); background: var(--c-primary); }
.review-session-bar__progress progress::-moz-progress-bar { border-radius: var(--r-pill); background: var(--c-primary); }
.review-session-bar__empty { display: flex; align-items: center; gap: 14px; min-width: 0; color: var(--c-text-2); font-size: var(--fs-12); }
.review-session-bar__empty p { overflow: hidden; margin: 0; text-overflow: ellipsis; white-space: nowrap; }
.review-session-bar__empty .btn { flex: none; min-height: 40px; white-space: nowrap; }
.review-session-bar__actions { display: flex; gap: 6px; }
.review-session-bar__actions .btn { min-height: 44px; }
.review-records { max-width: 900px; margin: 28px auto 0; overflow: hidden; border: 1px solid var(--c-border); border-radius: var(--r-lg); background: var(--c-surface); }
.review-records > summary { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 68px; padding: 14px 18px; cursor: pointer; list-style: none; }
.review-records > summary::-webkit-details-marker { display: none; }
.review-records > summary:hover { background: var(--c-surface-2); }
.review-records > summary > span:first-child { display: grid; gap: 3px; min-width: 0; }
.review-records > summary strong { font-size: var(--fs-14); }
.review-records > summary small { overflow: hidden; color: var(--c-text-3); font-size: var(--fs-12); text-overflow: ellipsis; white-space: nowrap; }
.review-records > summary > span:last-child { flex: none; color: var(--c-text-3); font-size: var(--fs-12); }
.review-records > summary > span:last-child::after { content: '展开'; margin-left: 12px; color: var(--c-primary); }
.review-records[open] > summary > span:last-child::after { content: '收起'; }
.review-records__body { padding: 24px; border-top: 1px solid var(--c-border); }
.review-records__head { display: flex; align-items: start; justify-content: space-between; gap: 24px; }
.review-records__head a { display:inline-flex; align-items:center; min-height:44px; }
.review-records__head h2 { font-size: var(--fs-18); letter-spacing: -.015em; }
.review-record-tools { display: flex; flex-wrap: wrap; gap: 16px; align-items: end; margin: 20px 0 8px; }
.review-record-tools .information-search { flex: 1; min-width: 220px; }
.review-record-tools .ws-field { min-width: 180px; margin: 0; }
.review-record-tools input,.review-record-tools select { background-color: var(--c-surface); }
.review-timeline { margin: 0; padding: 0; list-style: none; }
.review-timeline li { position: relative; display: grid; grid-template-columns: 100px minmax(0, 1fr) auto; gap: 18px; align-items: start; padding: 18px 0 18px 20px; border-top: 1px solid var(--c-border); }
.review-timeline li::before { content: ''; position: absolute; top: 24px; left: 2px; width: 6px; height: 6px; border-radius: 50%; background: var(--c-border-strong); }
.review-timeline time,.review-timeline__state { color: var(--c-text-3); font-size: var(--fs-12); }
.review-timeline__body { min-width: 0; }
.review-timeline__body > strong { display: block; overflow-wrap: anywhere; font-size: var(--fs-14); line-height: 1.6; }
.review-timeline__body :deep(.detail-trigger) { min-height: 44px; min-width: 0; justify-content: start; margin-top: 3px; padding: 8px 0; color: var(--c-primary); font-size: var(--fs-12); }
.review-timeline__state { padding: 4px 8px; border: 1px solid var(--c-border); border-radius: var(--r-pill); white-space: nowrap; }
.review-records__empty { padding: 32px 0; border-top: 1px solid var(--c-border); text-align: center; }
.review-records__empty p { margin-top: 4px; color: var(--c-text-3); font-size: var(--fs-12); }
@media (max-width: 900px) {
  .review-session-bar { grid-template-columns: minmax(0, 1fr) auto; }
  .review-session-bar__progress { grid-column: 1 / -1; grid-row: 2; }
  .review-session-bar__empty { grid-column: 1 / -1; grid-row: 2; flex-wrap: wrap; }
  .review-session-bar__empty p { white-space: normal; }
  .review-session-bar__actions { grid-column: 2; grid-row: 1; }
}
@media (max-width: 767px) {
  .review-session-bar { position: static; gap: 12px; padding: 12px; }
  .review-session-bar__copy strong { white-space: normal; }
  .review-session-bar__actions .btn { min-height: 44px; padding-inline: 11px; }
  .review-records { margin-top: 20px; }
  .review-records > summary { min-height: 72px; padding: 14px; }
  .review-records > summary small { white-space: normal; }
  .review-records__body { padding: 18px 14px; }
  .review-records__head { display: block; }
  .review-records__head a { display: inline-flex; margin-top: 6px; }
  .review-record-tools { display: grid; grid-template-columns: minmax(0, 1fr); }
  .review-record-tools .information-search,.review-record-tools .ws-field { min-width: 0; }
  .review-timeline li { grid-template-columns: minmax(0, 1fr) auto; gap: 6px 10px; padding-left: 18px; }
  .review-timeline time { grid-column: 1; }
  .review-timeline__state { grid-column: 2; grid-row: 1; }
  .review-timeline__body { grid-column: 1 / -1; }
}
</style>
