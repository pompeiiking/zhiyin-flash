<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { localDateTime, reviewDraft } from '../lib/form-values.mjs'
import { studentApi, type Review } from '../api/student-capabilities'
import type { ReviewEdit } from '../api/backend-types'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import { actionRows, dateKey, deadline } from '../lib/action-insights.mjs'
import DetailPopover from './DetailPopover.vue'
import StatusBanner from './StatusBanner.vue'

const props = defineProps<{ taskId?: string; loadingTasks?: boolean }>()
const emit = defineEmits<{ loaded: [items: Review[]]; selectedTask: [id: string] }>()
const tasks = computed(() => actionRows(backendDemo.state.liveAction))
const selectedId = ref('')
const reason = ref('')
const note = ref('')
const result = ref<ReviewEdit['result']>('continue')
const adjustedText = ref('')
const adjustedDate = ref('')
const editing = ref('')
const busy = ref(false)
const error = ref('')
const status = ref('')
const items = ref<Review[]>([])
const loading = ref(false)
const form = ref<HTMLFormElement | null>(null)
const opened = ref('')
const reasonOptions = ['达到预期', '任务太大', '方法不对', '时间不足', '等待他人', '方向要重估', '其他']
type LocalReviewDraft = {
  reason: string
  note: string
  result: ReviewEdit['result']
  adjustedText: string
  adjustedDate: string
  editing: string
}
const localDrafts = new Map<string, LocalReviewDraft>()

const selected = computed(() => tasks.value.find((task) => task.task_id === selectedId.value))
const selectedReview = computed(() => items.value.find((item) => item.task_id === selectedId.value))
const pendingReviews = computed(() => items.value.filter((item) => item.result !== 'continue' && !item.applied_at))

const outcomeCopy = computed(() => {
  if (result.value === 'adjust') return '先保存这次判断，再确认应用。应用后会修改阶段计划中的任务内容或截止时间。'
  if (result.value === 'complete') return '先保存这次判断，再确认应用。应用后会把这项任务标记为完成。'
  return '只保存本次复盘，不改变阶段计划。'
})

const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value)) : '日期未提供'
const formatDateTime = (value?: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '时间未提供'

watch(selectedId, (id, previousId) => {
  if (previousId) {
    localDrafts.set(previousId, {
      reason: reason.value,
      note: note.value,
      result: result.value,
      adjustedText: adjustedText.value,
      adjustedDate: adjustedDate.value,
      editing: editing.value,
    })
  }
  const draft = reviewDraft(selected.value)
  const localDraft = localDrafts.get(id)
  editing.value = localDraft?.editing ?? ''
  reason.value = localDraft?.reason ?? ''
  note.value = localDraft?.note ?? ''
  adjustedText.value = localDraft?.adjustedText ?? draft.text
  adjustedDate.value = localDraft?.adjustedDate ?? draft.due
  result.value = localDraft?.result ?? 'continue'
  status.value = ''
  error.value = ''
  emit('selectedTask', selectedId.value)
})
watch(() => props.taskId, (id) => { if (id && id !== selectedId.value) selectedId.value = id }, { immediate: true })

async function load(raise = false) {
  loading.value = true
  error.value = ''
  try {
    const data = await studentApi.reviews()
    items.value = data.items
    emit('loaded', data.items)
  } catch (caught) {
    error.value = (caught as Error).message
    if (raise) throw caught
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!selected.value || busy.value) return
  busy.value = true
  error.value = ''
  status.value = ''
  try {
    const task = selected.value
    const phase = backendDemo.state.liveAction?.phases?.find((row) => (row.tasks ?? []).some((item) => item.task_id === task.task_id))
    const item = await studentApi.saveReview({
      task_id: task.task_id,
      reason: reason.value,
      note: note.value,
      result: result.value,
      adjustment: result.value === 'adjust' ? {
        text: adjustedText.value,
        phase_id: phase?.id ?? '',
        status: task.status ?? 'pending',
        progress: task.progress ?? 0,
        waiting_reason: task.waiting_reason ?? '',
        due_date: adjustedDate.value ? new Date(adjustedDate.value).toISOString() : task.due_date,
        scheduled_at: task.scheduled_at,
        estimated_minutes: task.estimated_minutes,
        parent_task_id: task.parent_task_id,
      } : null,
    }, editing.value || undefined)
    editing.value = item.id
    try {
      await load()
      status.value = result.value === 'continue' ? '复盘已保存，阶段计划没有改变。' : '复盘已保存；确认影响后，可应用到阶段计划。'
    } catch {
      status.value = '复盘已保存，但列表暂未刷新。'
    }
  } catch (caught) {
    error.value = (caught as Error).message
  } finally {
    busy.value = false
  }
}

async function apply(item: Review) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  status.value = ''
  try {
    await studentApi.applyReview(item.id)
    backendDemo.setAction(await backendClient.action())
    try {
      await load()
      status.value = item.result === 'complete' ? '任务已标记为完成，阶段计划已更新。' : '任务调整已应用，阶段计划已更新。'
    } catch {
      status.value = '阶段计划已更新，但复盘列表暂未刷新。'
    }
  } catch (caught) {
    error.value = (caught as Error).message
  } finally {
    busy.value = false
  }
}

async function edit(item: Review) {
  selectedId.value = item.task_id
  await nextTick()
  editing.value = item.id
  reason.value = item.reason
  note.value = item.note ?? ''
  result.value = item.result
  adjustedText.value = item.adjustment?.text ?? item.task_text
  adjustedDate.value = localDateTime(item.adjustment?.due_date)
  opened.value = ''
  await nextTick()
  form.value?.querySelector<HTMLElement>('select')?.focus()
}

function reviewState(item: Review) {
  if (item.applied_at) return '已应用'
  if (item.result === 'continue') return '仅保留记录'
  return '等待应用'
}

defineExpose({ reload: () => load(true) })
onMounted(() => { void load() })
</script>

<template>
  <section class="structured-review" aria-label="任务复盘工作区">
    <section class="review-editor">
      <form ref="form" @submit.prevent="save">
        <fieldset :disabled="busy">
          <header class="review-editor__masthead">
            <div class="review-editor__topline">
              <span class="review-editor__mode">{{ editing ? '正在修订' : '本次复盘' }}</span>
              <span v-if="selectedReview" class="review-editor__saved">已有记录</span>
              <label class="review-task-switcher">
                <span>切换任务</span>
                <select v-model="selectedId" name="review-task" autocomplete="off" required>
                  <option value="">选择一项任务</option>
                  <option v-for="task in tasks" :key="task.task_id" :value="task.task_id">
                    {{ task.done ? '已完成' : deadline(task.due_date).overdue ? '已逾期' : '进行中' }} · {{ task.text }}
                  </option>
                </select>
              </label>
            </div>

            <template v-if="selected">
              <h2>{{ selected.text }}</h2>
              <div class="review-editor__context">
                <span>{{ selected.phase }}</span>
                <span aria-hidden="true">/</span>
                <span :class="{ 'is-overdue': deadline(selected.due_date).overdue && !selected.done }">
                  {{ selected.done ? `${dateKey(selected.done_at) || '日期未提供'} 完成` : deadline(selected.due_date).label }}
                </span>
              </div>
            </template>
            <template v-else>
              <h2>{{ props.loadingTasks ? '正在读取任务…' : '选择一项任务开始复盘' }}</h2>
              <p>{{ props.loadingTasks ? '正在整理阶段计划和最近完成记录。' : '把实际发生的事写清楚，再决定下一步。' }}</p>
            </template>
          </header>

          <template v-if="selected">
            <section class="review-step review-step--observation" aria-labelledby="review-step-observation">
              <header class="review-step__head">
                <span>1</span>
                <div>
                  <h3 id="review-step-observation">先写事实</h3>
                  <p>只记录发生了什么，不急着评价自己。</p>
                </div>
              </header>
              <label class="review-note-field">
                <span class="sr-only">实际发生的情况</span>
                <textarea v-model="note" name="review-note" rows="5" maxlength="3000" autocomplete="off" placeholder="例如：原计划今天完成，但整理资料比预计多用了 40 分钟…" />
              </label>
              <span class="review-note-count" aria-hidden="true">{{ note.length }} / 3000</span>
            </section>

            <section class="review-step" aria-labelledby="review-step-reason">
              <header class="review-step__head">
                <span>2</span>
                <div>
                  <h3 id="review-step-reason">判断主要原因</h3>
                  <p>选最关键的一项，避免把所有问题混在一起。</p>
                </div>
              </header>
              <fieldset class="review-reasons">
                <legend class="sr-only">主要原因</legend>
                <label v-for="item in reasonOptions" :key="item" :class="{ 'is-selected': reason === item }">
                  <input v-model="reason" type="radio" name="review-reason" :value="item" required />
                  <span>{{ item }}</span>
                </label>
              </fieldset>
            </section>

            <section class="review-step review-step--decision" aria-labelledby="review-step-decision">
              <header class="review-step__head">
                <span>3</span>
                <div>
                  <h3 id="review-step-decision">决定下一步</h3>
                  <p>选择后先保存判断；需要改计划时，再单独确认应用。</p>
                </div>
              </header>
              <fieldset class="review-outcomes">
                <legend class="sr-only">下一步结论</legend>
                <label :class="{ 'is-selected': result === 'continue' }">
                  <input :checked="result === 'continue'" type="radio" name="review-result" value="continue" @change="result = 'continue'" />
                  <span class="review-outcomes__marker" aria-hidden="true"></span>
                  <span><strong>继续</strong><small>方法可行，照原计划推进</small></span>
                </label>
                <label :class="{ 'is-selected': result === 'adjust' }">
                  <input :checked="result === 'adjust'" type="radio" name="review-result" value="adjust" @change="result = 'adjust'" />
                  <span class="review-outcomes__marker" aria-hidden="true"></span>
                  <span><strong>调整</strong><small>修改任务内容或截止时间</small></span>
                </label>
                <label :class="{ 'is-selected': result === 'complete' }">
                  <input :checked="result === 'complete'" type="radio" name="review-result" value="complete" @change="result = 'complete'" />
                  <span class="review-outcomes__marker" aria-hidden="true"></span>
                  <span><strong>完成</strong><small>确认这项任务已经完成</small></span>
                </label>
              </fieldset>

              <div v-if="result === 'adjust'" class="review-adjustment">
                <label class="ws-field">新的任务内容
                  <input v-model="adjustedText" name="review-adjusted-task" autocomplete="off" required />
                </label>
                <label class="ws-field">新的截止时间
                  <input v-model="adjustedDate" name="review-adjusted-date" type="datetime-local" autocomplete="off" />
                </label>
              </div>

              <div class="review-impact" :class="`review-impact--${result}`">
                <div>
                  <strong>{{ result === 'continue' ? '本次只保存复盘' : '保存后不会立即改计划' }}</strong>
                  <p>{{ outcomeCopy }}</p>
                </div>
                <div v-if="result === 'adjust'" class="review-impact__diff">
                  <span><b>当前</b>{{ selected.text }}</span>
                  <span><b>调整后</b>{{ adjustedText || '尚未填写' }}</span>
                </div>
              </div>
            </section>

            <footer class="review-editor__actions">
              <div>
                <strong>{{ editing ? '保存这次修订' : '完成本次复盘' }}</strong>
                <span>{{ result === 'continue' ? '阶段计划保持不变' : '稍后可从已保存复盘中确认应用' }}</span>
              </div>
              <button class="btn btn--primary" :disabled="busy">{{ busy ? '正在保存…' : editing ? '保存修订' : '保存复盘' }}</button>
            </footer>
          </template>

          <div v-else class="review-editor__empty">
            <strong>{{ props.loadingTasks ? '正在读取任务…' : '选择任务后开始' }}</strong>
            <p v-if="tasks.length">完整列表中有 {{ tasks.length }} 项任务。</p>
            <p v-else>阶段计划中还没有可复盘的任务。</p>
            <RouterLink v-if="!tasks.length" to="/home">去安排今日行动</RouterLink>
          </div>
        </fieldset>
      </form>

      <StatusBanner v-if="error" tone="error" :message="error" retry-label="重新读取" @retry="load" />
      <p v-if="status" class="review-editor__status" role="status">{{ status }}</p>
    </section>

    <section v-if="loading || pendingReviews.length" class="saved-reviews" aria-labelledby="saved-reviews-title">
      <header class="saved-reviews__head">
        <div>
          <h2 id="saved-reviews-title">待确认调整</h2>
          <p>这些复盘已经保存，但还没有改变阶段计划。</p>
        </div>
      </header>

      <p v-if="loading" class="saved-reviews__loading" role="status">正在读取复盘…</p>
      <div v-else class="saved-reviews__list">
        <article v-for="item in pendingReviews.slice(0, 5)" :key="item.id" class="review-entry">
          <div class="review-entry__head">
            <div>
              <h3>{{ item.task_text }}</h3>
              <p>{{ item.reason }} · {{ formatDate(item.updated_at) }}</p>
            </div>
            <span :class="{ 'is-pending': item.result !== 'continue' && !item.applied_at }">{{ reviewState(item) }}</span>
          </div>
          <p v-if="item.note" class="review-entry__note">{{ item.note }}</p>
          <div v-if="item.result !== 'continue' && !item.applied_at" class="review-entry__impact">
            <strong>{{ item.result === 'complete' ? '将把任务标记为完成' : '将修改阶段计划中的任务' }}</strong>
            <p v-if="item.result === 'adjust' && item.adjustment">{{ item.task_text }} → {{ item.adjustment.text }}</p>
          </div>
          <div class="review-entry__actions">
            <button class="btn btn--sm" :disabled="busy" @click="edit(item)">修订复盘</button>
            <button v-if="item.result !== 'continue' && !item.applied_at" class="btn btn--primary btn--sm" :disabled="busy" @click="apply(item)">应用到计划</button>
            <DetailPopover
              v-if="item.history.length || item.applied_at"
              :model-value="opened === item.id"
              @update:model-value="opened = $event ? item.id : ''"
              :label="`${item.task_text}：查看状态与修订记录`"
              :title="`${item.task_text} · 记录详情`"
              side="right"
            >
              <template #trigger>记录详情</template>
              <p>{{ item.applied_at ? `已应用于 ${formatDateTime(item.applied_at)}` : '尚未应用到计划' }}</p>
              <p v-for="(version, index) in item.history" :key="index">修订前：{{ version.reason }} · {{ version.note || '没有补充说明' }}</p>
            </DetailPopover>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.structured-review { display: grid; gap: 24px; min-width: 0; }
.review-editor { min-width: 0; overflow: hidden; background: var(--c-surface); border: 1px solid var(--c-border-strong); border-radius: calc(var(--r-lg) + 2px); box-shadow: var(--card-shadow); }
form > fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
form .ws-field { margin: 0; }
.review-editor__masthead { padding: 24px 28px 26px; border-bottom: 1px solid var(--c-border); background: linear-gradient(135deg, var(--c-primary-weak), var(--c-surface) 62%); }
.review-editor__topline { display: flex; align-items: center; gap: 8px; margin-bottom: 22px; }
.review-editor__mode,.review-editor__saved { color: var(--c-primary); font-size: var(--fs-12); font-weight: var(--fw-semibold); }
.review-editor__saved { padding-left: 8px; border-left: 1px solid var(--c-primary-border); }
.review-task-switcher { position: relative; display: flex; align-items: center; gap: 8px; min-width: 0; margin-left: auto; color: var(--c-text-2); font-size: var(--fs-13); }
.review-task-switcher select { max-width: 240px; min-height: 38px; padding: 7px 30px 7px 10px; border-color: var(--c-border-strong); border-radius: var(--r-pill); background-color: var(--c-surface); color: var(--c-text); font-size: var(--fs-13); }
.review-editor__masthead h2 { max-width: 680px; margin: 0; font-size: clamp(22px, 2.4vw, 30px); font-weight: var(--fw-bold); line-height: 1.36; letter-spacing: -.025em; text-wrap: balance; }
.review-editor__masthead > p { margin-top: 8px; color: var(--c-text-3); }
.review-editor__context { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; color: var(--c-text-2); font-size: var(--fs-13); }
.review-editor__context .is-overdue { color: var(--c-attention-strong); font-weight: var(--fw-medium); }
.review-step { position: relative; padding: 28px; border-bottom: 1px solid var(--c-border); }
.review-step__head { display: flex; gap: 14px; align-items: start; margin-bottom: 18px; }
.review-step__head > span { display: grid; flex: none; width: 28px; height: 28px; place-items: center; border-radius: 50%; background: var(--c-text); color: var(--c-surface); font-size: var(--fs-12); font-weight: var(--fw-bold); font-variant-numeric: tabular-nums; }
.review-step__head h3 { font-size: var(--fs-16); line-height: 1.45; }
.review-step__head p { margin-top: 3px; color: var(--c-text-2); font-size: var(--fs-13); line-height: 1.6; }
.review-note-field { display: block; margin-left: 42px; }
.review-note-field textarea { width: 100%; min-height: 142px; padding: 17px 18px; border-color: transparent; border-radius: var(--r-lg); background: var(--c-surface-2); font-size: var(--fs-14); line-height: 1.75; resize: vertical; }
.review-note-field textarea:hover { border-color: var(--c-border-control); }
.review-note-field textarea:focus { border-color: var(--c-primary); background: var(--c-surface); }
.review-note-count { display: block; margin: 8px 2px 0 42px; color: var(--c-text-3); font-size: var(--fs-12); text-align: right; font-variant-numeric: tabular-nums; }
.review-reasons { display: flex; flex-wrap: wrap; gap: 9px; min-width: 0; margin: 0 0 0 42px; padding: 0; border: 0; }
.review-reasons label { position: relative; cursor: pointer; }
.review-reasons input,.review-outcomes input { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; }
.review-reasons span { display: block; min-height: 38px; padding: 8px 14px; border: 1px solid var(--c-border-strong); border-radius: var(--r-pill); color: var(--c-text); font-size: var(--fs-13); transition: border-color 160ms ease, background-color 160ms ease, color 160ms ease; }
.review-reasons label:hover span { border-color: var(--c-primary-border); background: var(--c-primary-weak); }
.review-reasons label.is-selected span { border-color: var(--c-primary); background: var(--c-primary); color: var(--c-on-primary); }
.review-reasons label:has(input:focus-visible) span,.review-outcomes label:has(input:focus-visible) { outline: 3px solid var(--c-focus); outline-offset: 2px; }
.review-outcomes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0; min-width: 0; margin: 0 0 0 42px; padding: 5px; border: 1px solid var(--c-border); border-radius: var(--r-lg); background: var(--c-surface-2); }
.review-outcomes label { position: relative; display: flex; align-items: center; gap: 10px; min-width: 0; min-height: 72px; padding: 12px 14px; border-radius: var(--r-md); cursor: pointer; }
.review-outcomes label:hover { background: var(--c-surface); }
.review-outcomes label.is-selected { background: var(--c-surface); box-shadow: var(--card-shadow); }
.review-outcomes label > span:last-child { display: grid; min-width: 0; }
.review-outcomes strong { font-size: var(--fs-14); }
.review-outcomes small { margin-top: 3px; color: var(--c-text-2); font-size: var(--fs-13); line-height: 1.45; }
.review-outcomes__marker { display: block; flex: none; width: 9px; height: 9px; border: 2px solid var(--c-border-strong); border-radius: 50%; }
.review-outcomes label.is-selected .review-outcomes__marker { border-color: var(--c-primary); background: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-weak); }
.review-adjustment { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(190px, .6fr); gap: 16px; margin: 16px 0 0 42px; padding: 18px; border-radius: var(--r-lg); background: var(--c-surface-2); }
.review-impact { display: grid; gap: 14px; margin: 14px 0 0 42px; padding: 14px 16px; border-radius: var(--r-md); background: var(--c-surface-2); }
.review-impact--adjust,.review-impact--complete { background: var(--c-primary-weak); }
.review-impact strong { font-size: var(--fs-13); }
.review-impact p,.review-impact__diff { margin-top: 4px; color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.65; }
.review-impact__diff { display: grid; gap: 8px; padding-top: 12px; border-top: 1px solid var(--c-primary-border); }
.review-impact__diff span { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 8px; overflow-wrap: anywhere; }
.review-impact__diff b { color: var(--c-text-3); font-weight: var(--fw-medium); }
.review-editor__actions { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 28px; background: var(--c-surface); }
.review-editor__actions > div { display: grid; gap: 3px; min-width: 0; }
.review-editor__actions strong { font-size: var(--fs-14); }
.review-editor__actions span { color: var(--c-text-3); font-size: var(--fs-12); }
.review-editor__actions .btn { min-width: 120px; min-height: 42px; }
.review-editor__empty { padding: 28px 0 8px; border-top: 1px solid var(--c-border); color: var(--c-text-2); }
.review-editor__empty p { margin-top: 4px; color: var(--c-text-3); font-size: var(--fs-12); }
.review-editor__empty a { display: inline-block; margin-top: 10px; }
.review-editor__status { margin-top: 14px; padding: 11px 14px; background: var(--status-success-bg); border: 1px solid var(--status-success-border); border-radius: var(--r-md); color: var(--status-success-text); font-size: var(--fs-14); }
.saved-reviews { min-width: 0; padding: 22px 24px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); }
.saved-reviews__head,.review-entry__head { display: flex; align-items: start; justify-content: space-between; gap: 18px; }
.saved-reviews__head h2 { font-size: var(--fs-16); }
.saved-reviews__head p { margin-top: 4px; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.7; }
.saved-reviews__loading { margin-top: 16px; padding: 22px 0; border-top: 1px solid var(--c-border); color: var(--c-text-2); }
.saved-reviews__list { margin-top: 12px; }
.review-entry { padding: 16px 0; border-top: 1px solid var(--c-border); }
.review-entry h3,.review-entry p { overflow-wrap: anywhere; }
.review-entry h3 { font-size: var(--fs-14); line-height: 1.55; }
.review-entry__head p,.review-entry__note { margin-top: 4px; color: var(--c-text-3); font-size: var(--fs-12); }
.review-entry__head > span { flex: none; padding: 4px 8px; border: 1px solid var(--c-border); border-radius: var(--r-pill); color: var(--c-text-3); font-size: var(--fs-12); }
.review-entry__head > span.is-pending { border-color: var(--c-primary-border); background: var(--c-primary-weak); color: var(--c-primary); }
.review-entry__note { display: -webkit-box; overflow: hidden; color: var(--c-text-2); line-height: 1.65; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.review-entry__impact { margin-top: 12px; padding: 12px 14px; background: var(--c-primary-weak); border-left: 3px solid var(--c-primary); }
.review-entry__impact strong { font-size: var(--fs-12); }
.review-entry__impact p { margin-top: 4px; color: var(--c-text-2); font-size: var(--fs-12); }
.review-entry__actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 12px; }
.review-entry__actions :deep(.detail-trigger) { min-height: 36px; min-width: 0; padding: 6px 8px; color: var(--c-primary); font-size: var(--fs-12); }
@media (max-width: 767px) {
  .review-editor__masthead { padding: 20px 18px 22px; }
  .review-editor__topline { align-items: start; flex-wrap: wrap; margin-bottom: 18px; }
  .review-task-switcher { width: 100%; margin: 4px 0 0; }
  .review-task-switcher select { flex: 1; max-width: none; min-width: 0; }
  .review-step { padding: 24px 18px; }
  .review-step__head { gap: 11px; }
  .review-note-field,.review-note-count,.review-reasons,.review-outcomes,.review-adjustment,.review-impact { margin-left: 0; }
  .review-note-field textarea { min-height: 132px; }
  .review-reasons { gap: 8px; }
  .review-reasons span { min-height: 44px; padding: 10px 13px; }
  .review-outcomes { grid-template-columns: minmax(0, 1fr); }
  .review-outcomes label { min-height: 62px; }
  .review-adjustment { grid-template-columns: minmax(0, 1fr); }
  .review-editor__actions { align-items: stretch; flex-direction: column; padding: 18px; }
  .review-editor__actions .btn { width: 100%; min-height: 46px; }
  .saved-reviews { padding: 20px 18px; }
  .saved-reviews__head { display: block; }
  .review-entry__head { gap: 10px; }
  .review-entry__actions :deep(.detail-trigger) { min-height: 44px; }
}
</style>
