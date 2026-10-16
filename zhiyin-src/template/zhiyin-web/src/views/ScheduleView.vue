<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import type { ActionTaskView } from '../api/backend-types'
import { courseTimeLabel, hasCourseTime } from '../lib/academic'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import DetailPopover from '../components/DetailPopover.vue'
import DayAdvicePanel from '../components/DayAdvicePanel.vue'
import ScheduleCapacity from '../components/ScheduleCapacity.vue'
import TimetableAdvice from '../components/TimetableAdvice.vue'
import TaskEditor from '../components/TaskEditor.vue'
import Foldable from '../components/Foldable.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusBanner from '../components/StatusBanner.vue'
import InfoSheet from '../components/InfoSheet.vue'

type CalendarMode = 'week' | 'month'

const today = new Date()
const selected = ref(new Date(today.getFullYear(), today.getMonth(), today.getDate()))
const month = ref(new Date(today.getFullYear(), today.getMonth(), 1))
const mode = ref<CalendarMode>('week')
const adviceOpen = ref(false)
const calendarBusy = ref(false)
const calendarError = ref('')
const readOnce = ref(false)
const timetableScroll = ref<HTMLElement | null>(null)
const capacityOpen = ref(false)
const timePlanOpen = ref(false)
const weekdays = ['一', '二', '三', '四', '五', '六', '日']

function dateKey(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
function nodeDate(value?: string | null) {
  if (!value) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '' : dateKey(parsed)
}
function formatDay(value: Date, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('zh-CN', options).format(value)
}
function formatMoment(value?: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(parsed)
}

const selectedDate = computed(() => dateKey(selected.value))
const weekDates = computed(() => {
  const start = new Date(selected.value)
  start.setDate(start.getDate() - (start.getDay() + 6) % 7)
  return Array.from({ length: 7 }, (_, index) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + index))
})
const weekTitle = computed(() => `${formatDay(weekDates.value[0], { month: 'long', day: 'numeric' })} — ${formatDay(weekDates.value[6], { month: 'long', day: 'numeric' })}`)
const monthTitle = computed(() => formatDay(month.value, { year: 'numeric', month: 'long' }))
const allTasks = computed<ActionTaskView[]>(() => backendDemo.state.liveAction?.phases?.flatMap(phase => phase.tasks ?? []) ?? [])
const pendingTasks = computed(() => allTasks.value.filter(task => !task.done))
const selectedTasks = computed(() => pendingTasks.value.filter(task => nodeDate(task.scheduled_at || task.due_date) === selectedDate.value))
const undatedTasks = computed(() => pendingTasks.value.filter(task => !nodeDate(task.scheduled_at || task.due_date)))

const calendarEntries = computed(() => {
  const nodes = [...(backendDemo.state.liveCalendar ?? [])]
  for (const task of allTasks.value) {
    const when = task.scheduled_at || task.due_date
    if (!when) continue
    if (!nodes.some(node => node.related_task_text === task.text && nodeDate(node.due_at) === nodeDate(when))) {
      nodes.push({ node_id: `task-${task.task_id}`, title: task.text, due_at: when, source: 'manual', related_task_text: task.text })
    }
  }
  return nodes
})
const selectedNodes = computed(() => calendarEntries.value.filter(node => nodeDate(node.due_at) === selectedDate.value && !selectedTasks.value.some(task => task.text === node.title)))
function entriesFor(date: Date) { return calendarEntries.value.filter(node => nodeDate(node.due_at) === dateKey(date)) }
function coursesForDate(date: Date) {
  const weekday = (date.getDay() + 6) % 7 + 1
  return timedCourses.value.filter(course => course.weekday === weekday)
}
function countFor(date: Date) { return entriesFor(date).length + coursesForDate(date).length }
function dayCountLabel(date: Date) {
  const courses = coursesForDate(date).length
  const items = entriesFor(date).length
  if (!courses && !items) return '空'
  return [courses ? `${courses} 课` : '', items ? `${items} 事` : ''].filter(Boolean).join(' · ')
}

const monthOffset = computed(() => (month.value.getDay() + 6) % 7)
const monthLength = computed(() => new Date(month.value.getFullYear(), month.value.getMonth() + 1, 0).getDate())
function monthDate(day: number) { return new Date(month.value.getFullYear(), month.value.getMonth(), day) }
function monthAriaLabel(day: number) {
  const date = monthDate(day)
  const labels = [...coursesForDate(date).map(course => course.name), ...entriesFor(date).map(item => item.title)]
  return `${formatDay(monthDate(day), { month: 'long', day: 'numeric' })}${labels.length ? `，${labels.length} 项：${labels.join('、')}` : '，没有已记录事项'}`
}

const timedCourses = computed(() => backendDemo.state.academic?.courses?.filter(hasCourseTime) ?? [])
const untimedCourses = computed(() => backendDemo.state.academic?.courses?.filter(course => !hasCourseTime(course)) ?? [])
const selectedCourses = computed(() => coursesForDate(selected.value))
const lastPeriod = computed(() => Math.min(20, Math.max(10, ...timedCourses.value.map(course => course.end_period ?? 0))))
const courseBlocks = computed(() => weekdays.flatMap((_weekday, index) => {
  const laneEnds: number[] = []
  const courses = timedCourses.value.filter(course => course.weekday === index + 1 && (course.end_period ?? 0) <= 20).slice().sort((a, b) => (a.start_period ?? 0) - (b.start_period ?? 0))
  const assigned = courses.map(course => {
    let lane = laneEnds.findIndex(end => end < (course.start_period ?? 0))
    if (lane < 0) lane = laneEnds.length
    laneEnds[lane] = course.end_period ?? course.start_period ?? 0
    return { ...course, lane }
  })
  return assigned.map(course => ({ ...course, lanes: laneEnds.length }))
}))
function courseTone(name: string) {
  let hash = 0
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return `tone-${hash % 5}`
}
function centerTodayCourse() {
  void nextTick(() => {
    const el = timetableScroll.value
    if (!el || el.scrollWidth <= el.clientWidth) return
    const todayIndex = (today.getDay() + 6) % 7
    const dayWidth = 104
    const target = 48 + todayIndex * dayWidth - (el.clientWidth - dayWidth) / 2
    el.scrollTo({ left: Math.max(0, target), behavior: 'auto' })
  })
}

function selectDate(value: Date) {
  selected.value = new Date(value.getFullYear(), value.getMonth(), value.getDate())
  month.value = new Date(value.getFullYear(), value.getMonth(), 1)
  adviceOpen.value = false
}
function move(amount: number) {
  if (mode.value === 'month') {
    selectDate(new Date(month.value.getFullYear(), month.value.getMonth() + amount, 1))
    return
  }
  const next = new Date(selected.value)
  next.setDate(next.getDate() + amount * 7)
  selectDate(next)
}
function resetDate() { selectDate(today) }
function toggleMode() { mode.value = mode.value === 'week' ? 'month' : 'week' }

async function loadCalendar() {
  if (calendarBusy.value) return
  calendarBusy.value = true
  calendarError.value = ''
  try {
    const [calendar, plan, workspace] = await Promise.all([backendClient.calendar(), backendClient.action(), backendClient.workspace()])
    if (!Array.isArray(calendar)) throw new Error('Incomplete calendar')
    backendDemo.setCalendar(calendar)
    backendDemo.setAction(plan)
    backendDemo.setWorkspace(workspace)
    readOnce.value = true
    centerTodayCourse()
  } catch {
    calendarError.value = '最新日程没有取得。请重试；当前日期不会改变。'
  } finally {
    calendarBusy.value = false
  }
}

onMounted(() => { centerTodayCourse(); void loadCalendar() })
</script>

<template>
  <div class="ws-page schedule-page">
    <PageHeading title="日历与课表" description="把本周任务、关键节点和课程放在同一条时间线上。">
      <template #meta>
        <div class="schedule-meta" aria-label="当前资料概况">
          <span>{{ backendDemo.state.academic?.term || '学期未导入' }}</span>
          <span>{{ timedCourses.length }} 门课程</span>
          <span v-if="readOnce">{{ pendingTasks.length }} 项待执行</span>
        </div>
      </template>
      <button class="btn" :disabled="calendarBusy" @click="loadCalendar">
        <UiIcon name="refresh" :size="16" aria-hidden="true" />
        {{ calendarBusy ? '正在读取…' : readOnce ? '更新日程' : '读取日程' }}
      </button>
      <RouterLink class="btn" to="/academic"><UiIcon name="upload" :size="16" aria-hidden="true" />管理导入资料</RouterLink>
    </PageHeading>

    <p v-if="calendarError" class="ws-field-error" role="alert">{{ calendarError }}</p>

    <section class="schedule-surface" :aria-busy="calendarBusy">
      <header class="schedule-toolbar">
        <div><p>{{ mode === 'week' ? '本周' : '月度' }}</p><h2>{{ mode === 'week' ? weekTitle : monthTitle }}</h2></div>
        <div class="schedule-toolbar__actions">
          <button class="calendar-mode-switch" :aria-label="mode === 'week' ? '切换到月度节点' : '切换到本周安排'" @click="toggleMode">
            <UiIcon :name="mode === 'week' ? 'calendar' : 'action'" :size="16" aria-hidden="true" />
            {{ mode === 'week' ? '月度节点' : '本周安排' }}
          </button>
          <button class="ws-icon-button" :aria-label="mode === 'week' ? '上一周' : '上个月'" @click="move(-1)"><UiIcon name="back" /></button>
          <button class="btn" @click="resetDate">今天</button>
          <button class="ws-icon-button" :aria-label="mode === 'week' ? '下一周' : '下个月'" @click="move(1)"><UiIcon name="arrow" /></button>
        </div>
      </header>

      <div v-if="mode === 'week'" class="week-strip" aria-label="选择本周日期">
        <button v-for="date in weekDates" :key="dateKey(date)" :class="{ 'is-selected': dateKey(date) === selectedDate, 'is-today': dateKey(date) === dateKey(today) }" :aria-pressed="dateKey(date) === selectedDate" :aria-label="`${formatDay(date, { weekday: 'long', month: 'long', day: 'numeric' })}，${dayCountLabel(date)}`" @click="selectDate(date)">
          <span>周{{ weekdays[(date.getDay() + 6) % 7] }}</span><strong>{{ date.getDate() }}</strong><small>{{ dayCountLabel(date) }}</small>
        </button>
      </div>

      <div v-if="mode === 'month'" class="month-grid">
        <span v-for="weekday in weekdays" :key="weekday" class="month-grid__weekday">{{ weekday }}</span>
        <span v-for="empty in monthOffset" :key="`empty-${empty}`" aria-hidden="true" />
        <button v-for="day in monthLength" :key="day" :class="{ 'is-selected': selected.getDate() === day && selected.getMonth() === month.getMonth(), 'has-items': countFor(monthDate(day)) }" :aria-label="monthAriaLabel(day)" :aria-pressed="selected.getDate() === day && selected.getMonth() === month.getMonth()" @click="selectDate(monthDate(day))">
          <span>{{ day }}</span><small v-if="countFor(monthDate(day))">{{ dayCountLabel(monthDate(day)) }}</small>
        </button>
      </div>

      <section class="day-agenda" aria-labelledby="day-agenda-title">
        <div class="day-agenda__head"><div><p>{{ formatDay(selected, { weekday: 'long' }) }}</p><h2 id="day-agenda-title">{{ formatDay(selected, { month: 'long', day: 'numeric' }) }}</h2></div><span>{{ selectedCourses.length }} 课 · {{ selectedNodes.length + selectedTasks.length }} 事</span></div>
        <div v-if="selectedCourses.length || selectedNodes.length || selectedTasks.length" class="agenda-list">
          <article v-for="(course, index) in selectedCourses" :key="`${course.name}-${index}`" class="agenda-row agenda-row--course">
            <span class="agenda-row__marker" aria-hidden="true"><UiIcon name="academic" :size="17" /></span>
            <div class="agenda-row__body"><p>课程 · {{ course.start_period }}–{{ course.end_period }} 节</p><h3>{{ course.name }}</h3><small>{{ course.place || '地点未提供' }}<span v-if="course.teacher"> · {{ course.teacher }}</span></small></div>
          </article>
          <article v-for="node in selectedNodes" :key="node.node_id" class="agenda-row">
            <span class="agenda-row__marker" aria-hidden="true"><UiIcon name="calendar" :size="17" /></span>
            <div class="agenda-row__body"><p>关键节点 <span v-if="formatMoment(node.due_at)">· {{ formatMoment(node.due_at) }}</span></p><h3>{{ node.title }}</h3><small v-if="node.related_task_text && node.related_task_text !== node.title">{{ node.related_task_text }}</small></div>
          </article>
          <article v-for="task in selectedTasks" :key="task.task_id" class="agenda-row agenda-row--task">
            <span class="agenda-row__marker" aria-hidden="true"><UiIcon name="action" :size="17" /></span>
            <div class="agenda-row__body"><p>计划任务 <span v-if="task.estimated_minutes">· 约 {{ task.estimated_minutes }} 分钟</span></p><h3>{{ task.text }}</h3><div class="agenda-row__actions"><TaskEditor :task="task" /><RouterLink class="ws-text-link" to="/home">查看行动</RouterLink></div></div>
          </article>
        </div>
        <EmptyState v-else kind="schedule" size="sm" :heading-level="3" title="这天没有已记录的安排" description="可以切到其他日期，或在行动页为任务补上日期。" action-to="/home" action-label="去安排行动" />
        <div class="day-advice">
          <div class="day-advice__actions">
            <button class="btn" :aria-expanded="adviceOpen" @click="adviceOpen = !adviceOpen"><UiIcon name="spark" :size="16" aria-hidden="true" />{{ adviceOpen ? '收起当日建议' : '查看当日建议' }}</button>
            <button v-if="mode === 'week'" class="ws-text-button" @click="timePlanOpen=true">安排本周可用时间</button>
          </div>
          <DayAdvicePanel v-if="adviceOpen" :date="selectedDate" />
        </div>
      </section>
    </section>
    <InfoSheet :open="timePlanOpen" shape="panel" title="本周时间建议" description="结合已导入课表、限制和行为记录，生成可执行时间窗。" @close="timePlanOpen=false"><TimetableAdvice /></InfoSheet>

    <section class="schedule-surface timetable-surface" aria-labelledby="course-view-title">
      <header class="course-view__head"><h2 id="course-view-title">{{ backendDemo.state.academic?.term || '课程表' }}</h2><div class="course-view__meta"><span>{{ timedCourses.length }} 门课程</span><button type="button" class="ws-text-button" @click="capacityOpen=true">检查时间冲突</button><RouterLink class="btn" to="/academic">核对导入资料</RouterLink></div></header>
      <div v-if="timedCourses.length" ref="timetableScroll" class="timetable-scroll" tabindex="0" aria-label="一周课程表，可横向滚动">
        <div class="timetable-grid" :style="{ '--periods': lastPeriod }">
          <div class="timetable-corner">节次</div>
          <div v-for="(weekday, index) in weekdays" :key="weekday" class="timetable-day" :class="{ 'is-today': index + 1 === (today.getDay() + 6) % 7 + 1 }" :style="{ gridColumn: index + 2, gridRow: 1 }">
            <strong>周{{ weekday }}</strong><small>{{ weekDates[index].getMonth() + 1 }}/{{ weekDates[index].getDate() }}</small>
          </div>
          <div v-for="period in lastPeriod" :key="`period-${period}`" class="timetable-period" :style="{ gridColumn: 1, gridRow: period + 1 }"><span>{{ period }}</span></div>
          <div v-for="index in 7" :key="`column-${index}`" class="timetable-column" :class="{ 'is-today': index === (today.getDay() + 6) % 7 + 1 }" :style="{ gridColumn: index + 1, gridRow: `2 / span ${lastPeriod}` }" />
          <div v-for="(course, index) in courseBlocks" :key="`${course.name}-${course.weekday}-${course.start_period}-${index}`" class="timetable-course" :class="courseTone(course.name)" :style="{ gridColumn: (course.weekday ?? 1) + 1, gridRow: `${(course.start_period ?? 1) + 1} / span ${(course.end_period ?? course.start_period ?? 1) - (course.start_period ?? 1) + 1}`, width: `calc((100% - 8px) / ${course.lanes})`, marginLeft: `calc(4px + (100% - 8px) * ${course.lane} / ${course.lanes})` }">
            <DetailPopover :title="course.name" :label="`查看${course.name}详情`" side="bottom">
              <template #trigger><strong>{{ course.name }}</strong><span>{{ course.start_period }}–{{ course.end_period }} 节</span><small>{{ course.place || '地点未提供' }}</small></template>
              <dl class="course-detail"><div><dt>上课时间</dt><dd>{{ courseTimeLabel(course) }}</dd></div><div><dt>地点</dt><dd>{{ course.place || '未提供' }}</dd></div><div><dt>周次</dt><dd>{{ course.weeks || '未提供' }}</dd></div><div><dt>教师</dt><dd>{{ course.teacher || '未提供' }}</dd></div></dl>
            </DetailPopover>
          </div>
        </div>
      </div>
      <EmptyState v-else kind="schedule" :heading-level="2" title="课表还没有放进来" description="导入已有课表后，课程会按星期与节次排列。" action-to="/academic" action-label="去导入课表" />
      <StatusBanner v-if="untimedCourses.length" tone="warning" :message="`有 ${untimedCourses.length} 门课程缺少星期或节次，没有排进课表。`" />
      <Foldable v-if="untimedCourses.length" title="时间待补充的课程" variant="section" :count="untimedCourses.length"><ul class="ws-mini-list"><li v-for="(course, index) in untimedCourses" :key="`${course.name}-${index}`">{{ course.name }} · {{ courseTimeLabel(course) }}</li></ul></Foldable>
    </section>
    <InfoSheet :open="capacityOpen" shape="panel" title="课表检查" description="核对所选日期前后三周的课程、任务和时间重叠。" @close="capacityOpen=false"><ScheduleCapacity :date="selectedDate" /></InfoSheet>
    <StatusBanner v-if="calendarEntries.some(node => !nodeDate(node.due_at))" tone="warning" :message="`有 ${calendarEntries.filter(node => !nodeDate(node.due_at)).length} 条事项缺少日期，没有显示在日历中。`" />
    <Foldable v-if="calendarEntries.some(node => !nodeDate(node.due_at))" title="日期待补充的事项" variant="section" :count="calendarEntries.filter(node => !nodeDate(node.due_at)).length"><ul class="ws-mini-list"><li v-for="node in calendarEntries.filter(item => !nodeDate(item.due_at))" :key="node.node_id">{{ node.title }}</li></ul></Foldable>
    <Foldable v-if="undatedTasks.length" title="尚未排期的计划任务" variant="section" :count="undatedTasks.length"><ul class="ws-mini-list"><li v-for="task in undatedTasks" :key="task.task_id">{{ task.text }} <TaskEditor :task="task" /></li></ul></Foldable>
  </div>
</template>

<style scoped>
.schedule-page { max-width: 1280px; overflow-x: clip; }
.schedule-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--c-text-3); font-size: 13px; }
.calendar-mode-switch, .week-strip button, .month-grid button, .timetable-scroll:focus-visible { outline: 0; }
.calendar-mode-switch:focus-visible, .week-strip button:focus-visible, .month-grid button:focus-visible, .timetable-scroll:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.schedule-surface { margin-top: 18px; border: 1px solid var(--c-border); border-radius: 16px; background: var(--c-surface); box-shadow: var(--e-1); overflow: hidden; }
.schedule-toolbar, .course-view__head { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 22px 24px; border-bottom: 1px solid var(--c-border); }
.schedule-toolbar p, .course-view__head p, .day-agenda__head p { margin: 0 0 4px; color: var(--c-text-3); font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.schedule-toolbar h2, .course-view__head h2, .day-agenda__head h2 { margin: 0; font-size: 20px; text-wrap: balance; }
.schedule-toolbar__actions { display: flex; align-items: center; gap: 8px; }
.calendar-mode-switch { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 12px; border: 1px solid var(--c-border); border-radius: 9px; color: var(--c-primary); background: var(--c-surface); font-weight: 700; cursor: pointer; }
.calendar-mode-switch:hover { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 7%, var(--c-surface)); }
.week-strip { display: grid; grid-template-columns: repeat(7, minmax(80px, 1fr)); border-bottom: 1px solid var(--c-border); }
.week-strip button { position: relative; display: grid; place-items: center; gap: 5px; min-height: 112px; padding: 14px 8px; border: 0; border-right: 1px solid var(--c-border); color: var(--c-text-2); background: transparent; cursor: pointer; }
.week-strip button:last-child { border-right: 0; }
.week-strip button:hover { background: var(--c-surface-2); }
.week-strip button.is-selected { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 8%, var(--c-surface)); box-shadow: inset 0 -3px var(--c-primary); }
.week-strip button.is-today span::after { content: '今天'; margin-left: 5px; color: var(--c-primary); font-size: 10px; }
.week-strip strong { font-size: 24px; font-variant-numeric: tabular-nums; }
.week-strip small { color: var(--c-text-3); }
.month-grid { display: grid; grid-template-columns: repeat(7, minmax(68px, 1fr)); padding: 16px 18px 4px; }
.month-grid__weekday { padding: 8px; color: var(--c-text-3); font-size: 12px; text-align: center; }
.month-grid button { display: grid; align-content: start; gap: 7px; min-height: 76px; padding: 10px; border: 1px solid transparent; border-radius: 10px; color: var(--c-text); background: transparent; text-align: left; cursor: pointer; }
.month-grid button:hover { background: var(--c-surface-2); }
.month-grid button.is-selected { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 7%, var(--c-surface)); }
.month-grid button.has-items small { color: var(--c-primary); font-weight: 700; }
.month-grid button > span { font-variant-numeric: tabular-nums; }
.day-agenda { padding: 24px; }
.day-agenda__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.day-agenda__head > span { padding: 6px 10px; border-radius: 999px; color: var(--c-text-2); background: var(--c-surface-2); font-size: 12px; font-variant-numeric: tabular-nums; }
.agenda-list { display: grid; }
.agenda-row { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 12px; padding: 16px 0; border-top: 1px solid var(--c-border); }
.agenda-row__marker { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.agenda-row--task .agenda-row__marker { color: var(--c-text-2); background: var(--c-surface-2); }
.agenda-row__body { min-width: 0; }
.agenda-row__body > p { margin: 0 0 5px; color: var(--c-text-3); font-size: 12px; }
.agenda-row__body h3 { margin: 0; overflow-wrap: anywhere; font-size: 15px; line-height: 1.55; }
.agenda-row__body small { display: block; margin-top: 5px; color: var(--c-text-3); overflow-wrap: anywhere; }
.agenda-row__actions { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 9px; }
.day-advice { margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--c-border); }
.day-advice__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 18px; }
.timetable-surface { margin-top: 28px; }
.course-view__meta { display: flex; align-items: center; gap: 14px; color: var(--c-text-3); font-size: 13px; }
.timetable-scroll { width: 100%; overflow-x: auto; overflow-y: hidden; overscroll-behavior-x: contain; overscroll-behavior-y: auto; scrollbar-gutter: stable; touch-action: pan-x pan-y; }
.timetable-grid { display: grid; grid-template-columns: 54px repeat(7, minmax(108px, 1fr)); grid-template-rows: 62px repeat(var(--periods), 56px); min-width: 840px; position: relative; isolation: isolate; background: var(--c-surface); }
.timetable-corner, .timetable-day, .timetable-period { background: var(--c-surface); }
.timetable-corner { position: sticky; left: 0; z-index: 5; display: grid; place-items: center; grid-column: 1; grid-row: 1; border-right: 1px solid var(--c-border); border-bottom: 1px solid var(--c-border); color: var(--c-text-3); font-size: 11px; }
.timetable-day { z-index: 3; display: grid; place-items: center; align-content: center; gap: 4px; border-right: 1px solid var(--c-border); border-bottom: 1px solid var(--c-border); color: var(--c-text-2); }
.timetable-day strong { font-size: 14px; }
.timetable-day small { color: var(--c-text-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.timetable-day.is-today { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 7%, var(--c-surface)); box-shadow: inset 0 -3px var(--c-primary); }
.timetable-period { position: sticky; left: 0; z-index: 4; display: grid; place-items: center; border-right: 1px solid var(--c-border); border-bottom: 1px solid var(--c-border); color: var(--c-text-3); font-size: 13px; font-variant-numeric: tabular-nums; }
.timetable-period span::after { content: '节'; margin-left: 2px; font-size: 10px; }
.timetable-column { z-index: 0; border-right: 1px solid var(--c-border); background-image: repeating-linear-gradient(to bottom, transparent 0 55px, var(--c-border) 55px 56px); }
.timetable-column.is-today { background-color: color-mix(in srgb, var(--c-primary) 3%, transparent); }
.timetable-course { z-index: 2; min-width: 0; padding: 3px 0; }
.timetable-course :deep(.detail-trigger) { display: flex; flex-direction: column; align-items: stretch; gap: 4px; width: 100%; height: 100%; min-width: 0; padding: 9px; overflow: hidden; border: 1px solid var(--course-border); border-radius: 8px; color: var(--c-text); background: var(--course-bg); text-align: left; }
.timetable-course :deep(.detail-trigger:hover) { border-color: var(--course-accent); filter: saturate(1.08); }
.timetable-course :deep(.detail-trigger strong) { display: -webkit-box; overflow: hidden; font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.timetable-course :deep(.detail-trigger span) { color: var(--course-accent); font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; }
.timetable-course :deep(.detail-trigger small) { overflow: hidden; color: var(--c-text-2); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.timetable-course.tone-0 { --course-accent: #2563eb; --course-border: color-mix(in srgb, #3b82f6 42%, var(--c-border)); --course-bg: color-mix(in srgb, #3b82f6 15%, var(--c-surface)); }
.timetable-course.tone-1 { --course-accent: #0f766e; --course-border: color-mix(in srgb, #14b8a6 42%, var(--c-border)); --course-bg: color-mix(in srgb, #14b8a6 15%, var(--c-surface)); }
.timetable-course.tone-2 { --course-accent: #b45309; --course-border: color-mix(in srgb, #f59e0b 45%, var(--c-border)); --course-bg: color-mix(in srgb, #f59e0b 17%, var(--c-surface)); }
.timetable-course.tone-3 { --course-accent: #7c3aed; --course-border: color-mix(in srgb, #8b5cf6 42%, var(--c-border)); --course-bg: color-mix(in srgb, #8b5cf6 15%, var(--c-surface)); }
.timetable-course.tone-4 { --course-accent: #be123c; --course-border: color-mix(in srgb, #f43f5e 42%, var(--c-border)); --course-bg: color-mix(in srgb, #f43f5e 14%, var(--c-surface)); }
.course-detail { display: grid; gap: 12px; margin: 0; }
.course-detail div { display: grid; grid-template-columns: 72px 1fr; gap: 12px; }
.course-detail dt { color: var(--c-text-3); }
.course-detail dd { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 700px) {
  .schedule-page { padding-bottom: 90px; }
  .schedule-toolbar, .course-view__head { padding: 18px 16px; }
  .schedule-toolbar h2, .course-view__head h2 { font-size: 18px; }
  .schedule-toolbar { align-items: flex-start; }
  .schedule-toolbar__actions { flex-wrap: wrap; justify-content: flex-end; }
  .calendar-mode-switch { order: 4; width: 100%; min-height: 44px; justify-content: center; }
  .week-strip { display: flex; overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: none; }
  .week-strip::-webkit-scrollbar { display: none; }
  .week-strip button { flex: 0 0 68px; min-height: 96px; }
  .month-grid { grid-template-columns: repeat(7, minmax(0, 1fr)); padding: 10px 8px 0; }
  .month-grid button { min-height: 58px; padding: 7px 5px; text-align: center; }
  .month-grid button small { font-size: 10px; }
  .day-agenda { padding: 20px 16px; }
  .course-view__head { align-items: stretch; flex-direction: column; gap: 12px; }
  .course-view__meta { align-items: center; flex-direction: row; flex-wrap: wrap; gap: 8px 14px; }
  .course-view__meta > span { margin-right: auto; }
  .timetable-grid { grid-template-columns: 48px repeat(7, 104px); grid-template-rows: 58px repeat(var(--periods), 54px); min-width: 776px; }
  .timetable-column { background-image: repeating-linear-gradient(to bottom, transparent 0 53px, var(--c-border) 53px 54px); }
  .timetable-course :deep(.detail-trigger) { padding: 7px; }
}
</style>
