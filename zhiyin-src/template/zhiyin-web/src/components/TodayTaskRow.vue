<script setup lang="ts">
import { computed } from 'vue'
import type { ActionTaskView } from '../api/backend-types'
import { dateKey, deadline } from '../lib/action-insights.mjs'
import DetailPopover from './DetailPopover.vue'
import TaskEditor from './TaskEditor.vue'

const props = withDefaults(defineProps<{ task: ActionTaskView; busy?: boolean; mode?: 'task' | 'candidate' }>(), { mode: 'task' })
defineEmits<{ toggle: [task: ActionTaskView] }>()

const due = computed(() => deadline(props.task.due_date))
const scheduled = computed(() => {
  if (!props.task.scheduled_at) return ''
  const value = new Date(props.task.scheduled_at)
  if (Number.isNaN(value.getTime())) return ''
  const today = dateKey(new Date().toISOString())
  const day = dateKey(props.task.scheduled_at)
  const time = value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  return day === today ? `今天 ${time}` : `${value.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${time}`
})
const stateLabel = computed(() => {
  if (props.task.done) return '已完成'
  if (props.task.status === 'waiting') return '等待中'
  if (props.task.status === 'in_progress') return `进行中 · ${props.task.progress ?? 0}%`
  return ''
})
</script>

<template>
  <article class="today-row" :class="{ 'is-done': task.done, 'is-overdue': due.overdue, 'is-candidate': mode === 'candidate' }">
    <button
      v-if="mode !== 'candidate'"
      class="today-row__check"
      type="button"
      :disabled="busy"
      :aria-label="(task.done ? '恢复任务：' : '完成任务：') + task.text"
      :aria-pressed="!!task.done"
      @click="$emit('toggle', task)"
    >
      <span aria-hidden="true">{{ task.done ? '✓' : '' }}</span>
    </button>

    <div class="today-row__body">
      <div class="today-row__lead">
        <p class="today-row__eyebrow">
          <span v-if="stateLabel">{{ stateLabel }}</span>
          <span>{{ task.phase || '阶段任务' }}</span>
        </p>
        <h3>{{ task.text }}</h3>
      </div>

      <div class="today-row__timing" aria-label="任务时间信息">
        <strong v-if="scheduled">{{ scheduled }}</strong>
        <span v-if="task.estimated_minutes">预计 {{ task.estimated_minutes }} 分钟</span>
        <span v-if="task.due_date" :class="{ 'today-row__urgent': due.overdue }">{{ due.label }}</span>
        <span v-if="!scheduled && !task.estimated_minutes && !task.due_date">尚未安排时间</span>
      </div>

      <div class="today-row__actions">
        <TaskEditor :task="task" trigger-text="安排" />
        <DetailPopover :title="task.text" :label="'查看任务详情：' + task.text" side="right">
          <template #trigger>更多</template>
          <dl class="today-row__details">
            <dt>关联阶段</dt><dd>{{ task.phase || '未提供' }}</dd>
            <dt>安排时间</dt><dd>{{ scheduled || '未安排' }}</dd>
            <dt>截止日期</dt><dd>{{ dateKey(task.due_date) || '未设定' }}</dd>
            <dt>当前状态</dt><dd>{{ stateLabel }}</dd>
          </dl>
          <p v-if="task.waiting_reason">等待原因：{{ task.waiting_reason }}</p>
          <RouterLink class="ws-text-link" :to="'/chat?question=' + encodeURIComponent('我想讨论这项任务：' + task.text + '；所属阶段：' + (task.phase || '未提供'))">咨询此任务</RouterLink>
        </DetailPopover>
      </div>
    </div>
  </article>
</template>

<style scoped>
.today-row { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--c-border); }
.today-row__check { display: grid; place-items: center; width: 44px; height: 44px; margin-top: 2px; border: 1px solid var(--c-border-strong); border-radius: 50%; color: var(--c-surface); background: var(--c-surface); box-shadow: 0 0 0 4px var(--c-surface); }
.today-row__check:hover { border-color: var(--c-primary); }
.today-row__check[aria-pressed='true'] { border-color: var(--c-primary); background: var(--c-primary); }
.today-row__body { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 20px; min-width: 0; }
.today-row__lead { min-width: 0; }
.today-row__lead h3 { margin-top: 4px; font-size: var(--fs-14); font-weight: var(--fw-medium); line-height: 1.6; overflow-wrap: anywhere; }
.today-row__eyebrow,.today-row__timing,.today-row__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; color: var(--c-text-3); font-size: var(--fs-12); }
.today-row__eyebrow span + span::before,.today-row__timing span + span::before { content: '·'; margin-right: 12px; color: var(--c-text-3); }
.today-row__timing { justify-content: flex-end; text-align: right; font-variant-numeric: tabular-nums; }
.today-row__timing strong { color: var(--c-text); font-size: var(--fs-14); font-weight: var(--fw-medium); }
.today-row__actions { grid-column: 1 / -1; gap: 4px 18px; }
.today-row__actions :deep(.detail-trigger) { min-height: 40px; font-size: var(--fs-12); }
.today-row__urgent { padding: 4px 8px; color: var(--c-attention-strong); background: var(--c-attention-weak); border-radius: var(--r-sm); font-weight: var(--fw-semibold); }
.today-row__details { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 8px 16px; }
.today-row__details dt { color: var(--c-text-3); }
.today-row__details dd { margin: 0; }
.is-overdue { margin-top: 12px; padding: 12px 16px; background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: var(--r-md); }
.is-candidate { grid-template-columns: minmax(0, 1fr); padding: 15px 0 13px; }
.is-candidate .today-row__lead h3 { font-size: var(--fs-16); }
.is-done .today-row__lead h3 { color: var(--c-text-3); text-decoration: line-through; text-decoration-thickness: 1px; }
@media (max-width: 600px) {
  .today-row { gap: 10px; padding: 14px 0; }
  .today-row__body { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .today-row__timing { justify-content: flex-start; text-align: left; }
  .today-row__actions { grid-column: 1; }
  .today-row__actions :deep(.detail-trigger) { min-height: 44px; }
  .is-overdue { padding-left: 8px; }
}
</style>
