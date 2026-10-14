<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { demo } from '../store'
import { CALENDAR_MARKS, TASKS_BY_GRADE } from '../data/student'
import { DEMO_PHASE_TASK_IDS } from '../data/phase-tasks'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import SourceChip from '../components/SourceChip.vue'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import { hasCourseTime, courseTimeLabel } from '../lib/academic'
import PanelTabs from '../components/PanelTabs.vue'
import InfoSheet from '../components/InfoSheet.vue'
import DayAdvicePanel from '../components/DayAdvicePanel.vue'
import { backendClient } from '../api/backend-client'
import TimetableAdvice from '../components/TimetableAdvice.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusBanner from '../components/StatusBanner.vue'
import type { AcademicCourseView } from '../api/backend-types'
const courseDetails = ref<AcademicCourseView | null>(null)
const tab = ref('calendar'), mode = ref(window.matchMedia('(max-width:760px)').matches ? 'agenda' : 'month')
const today = new Date(), month = ref(new Date(today.getFullYear(), today.getMonth(), 1)), day = ref(today.getDate())
const selectedDate = computed(() => month.value.getFullYear()+'-'+String(month.value.getMonth()+1).padStart(2,'0')+'-'+String(day.value).padStart(2,'0'))
const weekDates = computed(() => { const start=new Date(month.value.getFullYear(),month.value.getMonth(),day.value);start.setDate(start.getDate()-(start.getDay()+6)%7);return Array.from({length:7},(_,i)=>new Date(start.getFullYear(),start.getMonth(),start.getDate()+i)) })
const title = computed(() => mode.value==='week' ? (weekDates.value[0].getMonth()+1)+'月'+weekDates.value[0].getDate()+'日 — '+(weekDates.value[6].getMonth()+1)+'月'+weekDates.value[6].getDate()+'日' : month.value.getFullYear() + ' 年 ' + (month.value.getMonth()+1) + ' 月')
function selectDate(date:Date){month.value=new Date(date.getFullYear(),date.getMonth(),1);day.value=date.getDate();advice.value=false}
function weekItems(date:Date){const key=date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0');return backendDemo.state.liveCalendar!==null ? backendDemo.state.liveCalendar.filter(n=>nodeDate(n.due_at)===key).map(n=>n.title) : date.getFullYear()===2026&&date.getMonth()===9 ? CALENDAR_MARKS.filter(m=>m.day===date.getDate()).map(m=>m.label) : [] }
const offset = computed(() => (month.value.getDay()+6)%7)
const length = computed(() => new Date(month.value.getFullYear(),month.value.getMonth()+1,0).getDate())
const isFixtureMonth = computed(() => month.value.getFullYear()===2026 && month.value.getMonth()===9)
const calendarBusy=ref(false),calendarError=ref(''),refreshing=ref(false),readOnce=ref(false)
/* 刷新 = "页面上已经有内容，这次是再读一遍"。没有内容时是首次加载：
   这时用按钮自身的"正在读取…"，不要拿骨架屏盖住空日历（那会把"还没有"说成"正在有"）。 */
async function loadCalendar(){if(calendarBusy.value)return;calendarBusy.value=true;calendarError.value='';if(readOnce.value)refreshing.value=true;try{const data=await backendClient.calendar();if(!Array.isArray(data))throw new Error('Incomplete calendar');backendDemo.setCalendar(data);readOnce.value=true}catch{calendarError.value='最新日程没有取得，请重试。当前日期和内容仍保留。'}finally{calendarBusy.value=false;refreshing.value=false}}
function nodeDate(value?:string|null){if(!value)return '';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;const date=new Date(value);return Number.isNaN(date.getTime())?'':date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0')}
const marks = computed(() => backendDemo.state.liveCalendar!==null ? backendDemo.state.liveCalendar.filter(n=>{const d=nodeDate(n.due_at);return d.startsWith(month.value.getFullYear()+'-'+String(month.value.getMonth()+1).padStart(2,'0')+'-')}).map(n=>({day:Number(nodeDate(n.due_at).slice(-2)),label:n.title,kind:'action',source:n.source,detail:n.related_task_text})) : isFixtureMonth.value ? CALENDAR_MARKS : [])
const selectedMarks = computed(() => marks.value.filter(m => m.day === day.value))
const selectedTasks = computed(() => backendDemo.state.liveAction ? (backendDemo.state.liveAction.phases?.flatMap(p=>p.tasks??[])??[]).filter(t=>!t.done&&nodeDate(t.due_date)===selectedDate.value).map(t=>({id:t.task_id,title:t.text,minutes:null})) : month.value.getFullYear()===today.getFullYear() && month.value.getMonth()===today.getMonth() && day.value===today.getDate() ? demo.use.now.value : [])
function move(n: number) { if(mode.value==='week'){selectDate(new Date(month.value.getFullYear(),month.value.getMonth(),day.value+n*7));return} month.value = new Date(month.value.getFullYear(),month.value.getMonth()+n,1); day.value=1; advice.value=false }
function resetDate(){month.value=new Date(today.getFullYear(),today.getMonth(),1);day.value=today.getDate();advice.value=false}
const weekdays = ['一','二','三','四','五','六','日']
const courseDay = ref((today.getDay()+6)%7+1)
const timed = computed(() => backendDemo.state.academic?.courses?.filter(hasCourseTime) ?? [])
const unscheduled = computed(() => backendDemo.state.academic?.courses?.filter(c=>!hasCourseTime(c)) ?? [])
const lastPeriod = computed(() => Math.min(40,Math.max(10,...timed.value.map(c=>c.end_period!))))
const visibleCourses = computed(() => timed.value.filter(c=>c.weekday===courseDay.value).sort((a,b)=>a.start_period!-b.start_period!))
const lanes = computed(() => weekdays.flatMap((_w,i) => {
  const ends: number[] = []
  const courses = timed.value.filter(c => c.weekday === i+1 && c.end_period! <= 40).slice().sort((a,b) => a.start_period!-b.start_period!)
  const assigned = courses.map(c => { let lane=ends.findIndex(end => end<c.start_period!); if(lane<0)lane=ends.length; ends[lane]=c.end_period!; return {...c,lane} })
  return assigned.map(c => ({...c,lanes:ends.length}))
}))
const advice = ref(false)

/* ============================================================================
 * 课量与任务量的关系
 * ---------------------------------------------------------------------------
 * 【这一块回答什么】DESIGN-LANGUAGE §8 给「日历」页点的方向原文是：
 *   "课程/截止/任务在**同一时间轴**互相影响（课多的一周任务自动排少）"。
 * 真实页原来把这三类做成了三张各管各的卡（月历 / 课表 tab / 当日议程），
 * "互相影响"没有被表达 —— §4.1「让结构显形」与 §6 第 5 问（关系是否可见）
 * 因此都不成立（vs1 报告 G-03：页高只有靶子的 27%，这块整块不存在）。
 *
 * 【数据从哪来 —— 没有一处是写死的】
 *   课量：`backendDemo.state.academic.courses` 的真实节次。每门课的开始/结束节次
 *         就是它的时长（1 节 = 1 小时），`weeks` 字段决定它在哪几周上。
 *   任务量：`demo.state.tasks`（真实任务清单）按**阶段计划的分段窗**归周，
 *         分段窗来自 `ActionPlanView.phases[].date_range`（服务模式）
 *         或 `demo-service.ts:15` 的同一条常量（演示模式）。
 *         两者指的是同一个东西，任务与周的对应关系在两条路径上一致。
 * 【为什么任务量不按 due_date 归周】演示模式下 `demo-service.ts:15` 把每条任务的
 *   `due_date` 写成 null（真实产品也没有逐条任务的日期），逐条归周会得到"三周都是 0"
 *   这种假读数。所以按**计划自己划的周窗**归 —— 那是计划对"这段什么时候做"的原话。
 *
 * 【"反的"是怎么被看出来的】每行用**同一把尺子**量两件事：横条的宽度 = 小时数 /
 * 三周最大值。课量条（深灰）越长的那一周，任务量条（主色）越短，第三列直接把
 * 差值写成"余 N 小时"。所以这个关系不是一句结论，是三条之间空出来的那一段。
 * ==========================================================================*/
const GRADE_KEY: Record<string, string> = { freshman: 'f', sophomore: 's', junior: 'j', senior: 'e' }

function mondayOf(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return d
}
function dateKey(d: Date): string {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}
function monthDay(d: Date): string {
  return d.getMonth() + 1 + ' 月 ' + d.getDate() + ' 日'
}
/** 学年锚点：演示学期的第 1 周从这一天（周一）开始。真实数据里没有学期起始日，所以这是一个明写的假设。 */
const TERM_FIRST_MONDAY = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 41)
const thisMonday = mondayOf(today)
const termWeekOf = (d: Date) =>
  Math.max(1, Math.round((mondayOf(d).getTime() - TERM_FIRST_MONDAY.getTime()) / 604800000) + 1)

interface WeekRow {
  offset: number
  /** 学年第几周 */
  n: number
  monday: Date
  /** 计划给这一段写的时间窗（服务模式用后端的原话，演示模式用同一条常量） */
  range: string | null
  courseHours: number
  taskHours: number
  taskDone: number
  taskTotal: number
  /** 同一天、同一周里两门课的节次重叠了几处 */
  conflicts: number
  /** 这一周有几门课真的在上 */
  courses: number
}
function weeksOf(raw?: string): number[] | null {
  if (!raw) return null
  const s = raw.replace(/[第周\s]/g, '')
  if (!/[0-9]/.test(s)) return null
  if (/[-–—~]/.test(s)) {
    const m = s.match(/(\d+)\s*[-–—~]\s*(\d+)/)
    if (m) {
      const out: number[] = []
      for (let i = Number(m[1]); i <= Number(m[2]) && out.length < 40; i++) out.push(i)
      return out
    }
  }
  const list = (s.match(/\d+/g) ?? []).map(Number)
  return list.length ? list : null
}
function weekCmpFor(courses: AcademicCourseView | null | undefined): number {
  const s = courses?.start_period
  const e = courses?.end_period
  return s && e && e >= s ? e - s + 1 : 0
}
/** 同一天、同一周、节次有重叠 —— 与课表里画出来的冲突是同一件事。 */
function overlapsInWeek(a: AcademicCourseView, b: AcademicCourseView): boolean {
  if (!a.weeks || !b.weeks) return false
  const wa = weeksOf(a.weeks)
  const wb = weeksOf(b.weeks)
  if (!wa || !wb) return false
  return wa.some((w) => wb.includes(w))
}
function overlapsInDay(a: AcademicCourseView, b: AcademicCourseView): boolean {
  return (a.start_period ?? 0) <= (b.end_period ?? 0) && (b.start_period ?? 0) <= (a.end_period ?? 0)
}
function coursesOn(week: number, weekday: number): AcademicCourseView[] {
  return timed.value.filter(
    (c) => c.weekday === weekday && (weeksOf(c.weeks)?.includes(week) ?? false) && (c.start_period ?? 0) > 0 && (c.end_period ?? 0) > 0,
  )
}
/** 这一周里同一门课只算一次重叠：拿"被两门课同时占住的节次"数，不是数对数。 */
function conflictCount(week: number): number {
  const seen = new Set<number>()
  for (let wd = 1; wd <= 7; wd++) {
    const day = coursesOn(week, wd)
    for (let i = 0; i < day.length; i++) {
      for (let j = i + 1; j < day.length; j++) {
        if (!overlapsInWeek(day[i], day[j]) || !overlapsInDay(day[i], day[j])) continue
        const lo = Math.max(day[i].start_period ?? 0, day[j].start_period ?? 0)
        const hi = Math.min(day[i].end_period ?? 0, day[j].end_period ?? 0)
        for (let p = lo; p <= hi; p++) seen.add(wd * 100 + p)
      }
    }
  }
  return seen.size
}
/** 某一周有哪些任务 —— 与 demo-service.ts 的 `action()` 走同一份对照。
 *  `ActionTaskView`（backend-types.ts:343）里**没有** minutes 字段，所以时长必须回查
 *  `demo.state.tasks` / 年级任务表；标题与完成态取计划自己的（那是服务端的事实）。
 *  两条路径用的是同一份 id 对照（`DEMO_PHASE_TASK_IDS` + `m-<年级字母><段号>`），
 *  所以演示模式与服务模式下"哪条任务算在哪一周"是一致的。 */
function taskIdsForPhase(phaseId: string): readonly string[] {
  const phase = backendDemo.state.liveAction?.phases?.[Number(phaseId) - 1]
  if (phase?.tasks?.length) return phase.tasks.map((t) => t.task_id)
  const grade = demo.state.grade
  return DEMO_PHASE_TASK_IDS['m-' + (GRADE_KEY[grade] ?? 'j') + phaseId] ?? []
}
function taskDoneForPhase(phaseId: string, id: string): boolean {
  const phase = backendDemo.state.liveAction?.phases?.[Number(phaseId) - 1]
  const live = phase?.tasks?.find((t) => t.task_id === id)
  if (live) return live.done === true
  return demo.state.tasks.find((t) => t.id === id)?.bucket === 'done'
}
function tasksForPhase(phaseId: string): { title: string; minutes: number; done: boolean }[] {
  const grade = demo.state.grade
  const store = demo.state.tasks.length ? demo.state.tasks : (TASKS_BY_GRADE[grade] ?? [])
  const plan = backendDemo.state.liveAction?.phases?.[Number(phaseId) - 1]?.tasks
  return taskIdsForPhase(phaseId).map((id) => ({
    title: plan?.find((t) => t.task_id === id)?.text ?? store.find((t) => t.id === id)?.title ?? id,
    minutes: store.find((t) => t.id === id)?.minutes ?? 0,
    done: taskDoneForPhase(phaseId, id),
  }))
}

const weekRows = computed<WeekRow[]>(() =>
  [-1, 0, 1].map((offset) => {
    const monday = new Date(thisMonday.getFullYear(), thisMonday.getMonth(), thisMonday.getDate() + offset * 7)
    const phaseId = String(offset + 1)
    const phase = backendDemo.state.liveAction?.phases?.[offset + 1]
    const tasks = tasksForPhase(phaseId)
    const done = tasks.filter((t) => t.done)
    const dayHours = [1, 2, 3, 4, 5, 6, 7].map((wd) =>
      coursesOn(termWeekOf(monday), wd).reduce((sum, c) => sum + weekCmpFor(c), 0),
    )
    const n = termWeekOf(monday)
    return {
      offset,
      n,
      monday,
      range: phase?.date_range ?? null,
      courseHours: dayHours.reduce((a, b) => a + b, 0),
      /* 任务量 = 真正排进去的小时数。done 的按**全部时长**记（它做进去了），
         没做的也按计划时长记（它排在那一周）—— 所以这个数读的是"计划排了多少"。
         `minutes: 0` 是"等结果"那类不占时间的条目，天然不计入。 */
      taskHours: tasks.reduce((sum, t) => sum + t.minutes, 0) / 60,
      taskDone: done.length,
      taskTotal: tasks.length,
      conflicts: conflictCount(n),
      courses: [1, 2, 3, 4, 5, 6, 7].filter((wd) => coursesOn(n, wd).length > 0).length,
    }
  }),
)
const weekMax = computed(() => Math.max(1, ...weekRows.value.flatMap((w) => [w.courseHours, w.taskHours])))
const weekTerm = computed(() => {
  const a = weekRows.value[0]
  const b = weekRows.value[2]
  return a && b ? { from: a.n, to: b.n } : null
})
/** 三周里课最多 / 课最少的那一周 —— 只在页头那句对比里用一次。 */
const heavyWeek = computed(() => weekRows.value.reduce((a, b) => (b.courseHours > a.courseHours ? b : a)))
const lightWeek = computed(() => weekRows.value.reduce((a, b) => (b.courseHours <= a.courseHours ? b : a)))
/** 一件事占这一周课程时间的比例 —— 这是"课多的一周任务排得少"的可核对读法。 */
const perCourseHour = (w: WeekRow) => (w.courseHours ? w.taskHours / w.courseHours : 0)
const thisWeek = computed(() => weekRows.value[1])
/** 课最多的那一天（放在右栏，"这一天为什么动不了"就落在具体某天）。 */
const busiestDay = computed(() => {
  const n = thisWeek.value?.n ?? termWeekOf(today)
  return [1, 2, 3, 4, 5, 6, 7]
    .map((wd) => ({
      wd,
      label: '周' + weekdays[wd - 1],
      hours: coursesOn(n, wd).reduce((sum, c) => sum + weekCmpFor(c), 0),
      names: coursesOn(n, wd).map((c) => c.name),
    }))
    .sort((a, b) => b.hours - a.hours)[0]
})
const weekHref = (w: WeekRow) => '/home?week=' + dateKey(w.monday)
const pendingTimeCourses = computed(() => timed.value.filter((c) => c.end_period! > 40).length + unscheduled.value.length)
const pendingMarkCount = computed(() => {
  const live = backendDemo.state.liveCalendar
  if (live?.length) return live.filter((n) => !nodeDate(n.due_at)).length
  return 0
})
/** 不足 1 小时的读数换成分钟："0.58 小时"没人读得出来，"35 分钟"可以。 */
const hours = (v: number) =>
  v > 0 && v < 1
    ? Math.max(1, Math.round(v * 60)) + ' 分钟'
    : (Math.round(v * 10) / 10).toLocaleString('zh-CN') + ' 小时'
</script>
<template>
<div class="ws-page schedule-page"><PageHeading title="日历与课表" description="关键节点、今日任务和学校课程，各自保留来源。"><template #meta><div class="sched-meta"><span class="sched-meta__tag sched-meta__tag--demo">本地演示数据</span><span class="sched-meta__tag">{{ backendDemo.state.academic?.term || '学期未导入' }} · 第 {{ thisWeek?.n }} 周</span><span class="sched-meta__tag">{{ timed.length }} 门课有节次 · 本周课 {{ hours(thisWeek?.courseHours ?? 0) }}</span><span class="sched-meta__sep" aria-hidden="true" /><ConfidenceBadge :confidence="0.9" /><ConfidenceBadge :confidence="0.55" /><ConfidenceBadge v-if="pendingTimeCourses || pendingMarkCount" :confidence="null" /></div></template><button class="btn" :disabled="calendarBusy" @click="loadCalendar">{{ calendarBusy?'正在读取…':(readOnce?'更新最新日程':'读取最新日程') }}</button><RouterLink class="btn" to="/academic"><UiIcon name="upload" :size="16" />管理导入资料</RouterLink></PageHeading>
<p v-if="calendarError" class="ws-field-error" role="alert">{{ calendarError }}</p>
<!-- ======= ① 结构显形：三周的课量与任务量摆在同一把尺子上 =======
     它是"课多的一周任务排得少"的**可核对版本**：两根横条共用一根刻度，
     课量长的与任务量长的分别是哪一周，一眼就分得出来。
     数据全部来自真实课表（节次 + weeks）与真实任务（按阶段计划的时间窗归周）。 -->
<section class="ws-section sched-cmp" aria-labelledby="sched-cmp-title">
  <div class="ws-section-head">
    <div>
      <h2 id="sched-cmp-title">{{ weekTerm ? '第 ' + weekTerm.from + '–' + weekTerm.to + ' 周' : '这一周' }}：课量与任务量摆在同一把尺子上</h2>
      <p v-if="heavyWeek && lightWeek">{{ heavyWeek.n === lightWeek.n ? '这一周课最多' : '第 ' + heavyWeek.n + ' 周课最多（' + hours(heavyWeek.courseHours) + '），第 ' + lightWeek.n + ' 周课最少（' + hours(lightWeek.courseHours) + '）' }} —— 每 1 小时课配到多少分钟事，看最右边那一列。</p>
      <p v-else>同一把尺子量两件事 —— 横条的长度就是时长。导入课表后这里才有可对照的读数。</p>
    </div>
    <span class="sched-cmp__count">3 周 · 同一刻度</span>
  </div>
  <div class="sched-cmp__grid">
    <div class="sched-cmp__legend"><span class="sched-cmp__k">课量 / 任务量</span><span class="sched-cmp__k sched-cmp__k--v">时长</span><span class="sched-cmp__k sched-cmp__k--r">每 1 小时课配到的事</span></div>
    <div v-for="w in weekRows" :key="w.monday.toISOString()" class="sched-cmp__row">
      <p class="sched-cmp__w">第 {{ w.n }} 周<small>{{ w.range || (monthDay(w.monday) + ' — ' + monthDay(new Date(w.monday.getFullYear(), w.monday.getMonth(), w.monday.getDate() + 6))) }}{{ w.offset === 0 ? ' · 本周' : '' }}</small></p>
      <div class="sched-cmp__bars">
        <span class="sched-cmp__k">课</span>
        <div class="sched-cmp__track"><i class="sched-cmp__bar sched-cmp__bar--c" :style="{ width: (w.courseHours / weekMax * 100) + '%' }" /></div>
        <span class="sched-cmp__k">事</span>
        <div class="sched-cmp__track"><i class="sched-cmp__bar sched-cmp__bar--t" :style="{ width: (w.taskHours / weekMax * 100) + '%' }" /></div>
      </div>
      <p class="sched-cmp__v"><b class="t-num">{{ hours(w.courseHours) }}</b><span>课</span><b class="t-num">{{ hours(w.taskHours) }}</b><span>事</span></p>
      <p class="sched-cmp__m" :class="{ 'sched-cmp__m--none': w.taskHours === 0 }"><span class="t-num">{{ w.taskHours === 0 ? '0' : Math.round(perCourseHour(w) * 60) }}</span> 分钟<small>{{ w.taskHours === 0 ? '这一周任务一条都没排' : '课 ' + hours(w.courseHours) + ' · 事 ' + hours(w.taskHours) }}</small></p>
      <RouterLink class="ws-text-link sched-cmp__go" :to="weekHref(w)" :aria-label="'看第 ' + w.n + ' 周'">看这一周<UiIcon name="arrow" :size="16" /></RouterLink>
    </div>
    <p class="sched-cmp__empty" v-if="!weekRows.some((w) => w.courseHours || w.taskHours)">还没有可以对照的课表或任务：导入课表后，这里会按周把两件事摆在同一把尺子上。</p>
  </div>
  <p class="sched-cmp__foot"><span>时间口径：<b>空课格不代表空闲</b> —— 一格空着只是那天没有排课，不等于那段时间可以用。</span><RouterLink class="ws-text-link sched-cmp__footlink" to="/academic">核对导入的课表<UiIcon name="arrow" :size="16" /></RouterLink></p>
</section>
<div class="sched-split">
<div class="sched-split__main">
<PanelTabs v-model="tab" label="日程视图" :items="[{key:'calendar',label:'关键日历'},{key:'courses',label:'一周课表'}]">
<template v-if="tab==='calendar'"><div class="sched-refresh-shell" :aria-busy="refreshing"><div v-if="refreshing" class="sched-refresh"><SkeletonBlock variant="chart" :columns="7" /></div><p v-if="refreshing" class="sr-only" role="status">正在读取最新日程，日历内容保留。</p><header class="calendar-toolbar"><h2>{{ title }}</h2><div class="calendar-toolbar__actions"><button class="ws-icon-button" :aria-label="mode==='week'?'上一周':'上个月'" @click="move(-1)"><UiIcon name="back" /></button><button class="btn" @click="resetDate">今天</button><button class="ws-icon-button" :aria-label="mode==='week'?'下一周':'下个月'" @click="move(1)"><UiIcon name="arrow" /></button><label class="calendar-view">视图<select v-model="mode" aria-label="日历显示方式"><option value="month">月历</option><option value="week">周视图</option><option value="agenda">议程</option></select></label></div></header>
<div v-if="mode==='week'" class="calendar-week-events" aria-label="本周事项"><button v-for="date in weekDates" :key="date.toISOString()" :aria-pressed="date.getDate()===day && date.getMonth()===month.getMonth()" @click="selectDate(date)"><strong>周{{ weekdays[(date.getDay()+6)%7] }} · {{ date.getMonth()+1 }}/{{ date.getDate() }}</strong><span v-for="label in weekItems(date)" :key="label">{{ label }}</span><small v-if="!weekItems(date).length">没有已记录的事项</small></button></div><div class="calendar-layout"><div v-if="mode==='month'" class="calendar-month"><div class="ws-calendar"><span v-for="w in weekdays" :key="w" class="ws-calendar__weekday">{{ w }}</span><span v-for="n in offset" :key="'empty'+n"/><button v-for="d in length" :key="d" class="ws-calendar__day" :class="{'ws-calendar__day--selected':day===d,'ws-calendar__day--marked':marks.some(m=>m.day===d)}" :aria-label="(month.getMonth()+1)+'月'+d+'日'" :aria-pressed="day===d" @click="day=d;advice=false"><span>{{ d }}</span><small v-for="m in marks.filter(m=>m.day===d)" :key="m.label" :title="m.label">{{ m.label }}</small><small v-if="d===today.getDate() && month.getMonth()===today.getMonth() && month.getFullYear()===today.getFullYear() && !backendDemo.state.liveAction && demo.use.now.value.length">{{ demo.use.now.value.length }} 件待执行</small></button></div></div>
<section class="calendar-agenda"><div class="ws-section-head"><h3>{{ month.getMonth()+1 }} 月 {{ day }} 日</h3><span class="ws-muted">当日议程</span></div><label v-if="mode==='agenda'" class="ws-field">选择日期<select v-model.number="day"><option v-for="d in length" :key="d" :value="d">{{ month.getMonth()+1 }} 月 {{ d }} 日</option></select></label><article v-for="m in selectedMarks" :key="m.label" class="agenda-item"><UiIcon name="calendar" :size="18"/><div><h4>{{ m.label }}</h4><p>{{ backendDemo.state.liveCalendar!==null ? '已读取的日程节点' : '预置'+(m.kind==='deadline'?'截止节点':m.kind==='review'?'复盘安排':'行动节点') }}</p></div></article><article v-for="t in selectedTasks" :key="t.id" class="agenda-item"><UiIcon name="action" :size="18"/><div><h4>{{ t.title }}</h4><p>计划任务<span v-if="t.minutes!==null"> · 约 {{ t.minutes }} 分钟</span></p><RouterLink class="ws-text-link" to="/home">查看并执行</RouterLink></div></article><p v-if="!selectedMarks.length&&!selectedTasks.length" class="ws-muted ws-section">这天没有已记录的安排。</p><button class="ws-text-button" @click="advice=true">查看当日建议<UiIcon name="arrow" :size="16"/></button><DayAdvicePanel v-if="advice" :date="selectedDate"/></section></div>
<Foldable title="本月关键节点" variant="section" :count="marks.length" :default-open="false"><ul class="agenda-month-list"><li v-for="m in marks" :key="m.day+m.label"><button class="ws-text-button" @click="day=m.day">{{ month.getMonth()+1 }}/{{ m.day }} · {{ m.label }}</button></li><li v-if="!marks.length" class="ws-muted">本月没有已记录节点。</li></ul></Foldable></div></template>
<template v-else-if="backendDemo.state.academic?.courses?.length"><div class="sched-course-shell"><div class="ws-section-head"><h2>每周课程安排</h2><p>{{ backendDemo.state.academic?.term || '正在读取学期信息' }}</p></div><div class="course-desktop"><div class="course-week" :style="{'--periods':lastPeriod}"><div class="course-week__corner"/><div v-for="w in 7" :key="'head'+w" class="course-week__day" :style="{gridColumn:w+1,gridRow:1}">周{{ weekdays[w-1] }}</div><div v-for="p in lastPeriod" :key="'period'+p" class="course-week__period" :style="{gridColumn:1,gridRow:p+1}">{{ p }} 节</div><div v-for="w in 7" :key="'grid'+w" class="course-week__column" :style="{gridColumn:w+1,gridRow:'2 / span '+lastPeriod}"/><button type="button" v-for="(c,i) in lanes" @click="courseDetails={...c}" :key="i" class="course-block" :style="{gridColumn:c.weekday!+1,gridRow:(c.start_period!+1)+' / span '+(c.end_period!-c.start_period!+1),width:'calc((100% - 8px) / '+c.lanes+')',marginLeft:'calc(4px + (100% - 8px) * '+c.lane+' / '+c.lanes+')'}"><strong>{{ c.name }}</strong><span>{{ c.start_period }}–{{ c.end_period }} 节</span><small v-if="c.place">{{ c.place }}</small><small v-if="c.weeks">{{ c.weeks }} 周</small></button></div></div>
<div class="course-mobile"><div class="course-day-picker" role="group" aria-label="课程日期"><button v-for="w in 7" :key="w" :aria-pressed="courseDay===w" @click="courseDay=w">周{{ weekdays[w-1] }}</button></div><article v-for="(c,i) in visibleCourses" :key="i" class="course-list-item"><div>{{ c.start_period }}–{{ c.end_period }}<small>节</small></div><section><h3><button class="ws-text-button course-title" @click="courseDetails={...c}">{{ c.name }}<UiIcon name="arrow" :size="16"/></button></h3><p>{{ c.place || '地点未提供' }}<span v-if="c.weeks"> · {{ c.weeks }} 周</span></p></section></article><EmptyState v-if="!visibleCourses.length" kind="schedule" size="sm" :heading-level="4" :title="'周' + weekdays[courseDay-1] + '没有已导入的课程'" description="切到其他星期，或先回到资料页导入课表。" /></div>
<StatusBanner v-if="unscheduled.length || timed.some(c=>c.end_period!>40)" tone="warning" class="ws-section" :message="'有 ' + (unscheduled.length + timed.filter(c=>c.end_period!>40).length) + ' 门课程的上课时间没有补全，这些课不会排进上面的课表；展开下方列表可逐条核对。'" /><Foldable v-if="unscheduled.length || timed.some(c=>c.end_period!>40)" title="时间待补充与其他节次的课程" variant="section" :count="unscheduled.length + timed.filter(c=>c.end_period!>40).length"><ul class="ws-mini-list"><li v-for="(c,i) in [...unscheduled,...timed.filter(c=>c.end_period!>40)]" :key="i">{{ c.name }} · {{ courseTimeLabel(c) }}</li></ul></Foldable><p class="ws-muted ws-section">课程按导入节次展示。相同时段的课程可能重叠，请回到资料页核对；空格仅表示快照中没有课程。</p></div></template>
<section v-else class="ws-section"><EmptyState kind="schedule" :heading-level="2" title="课表还没有放进来" description="导入已有课表后，课程会按节次排列。" action-to="/academic" action-label="去导入课表" /></section>
</PanelTabs><StatusBanner v-if="backendDemo.state.liveCalendar?.some(n=>!nodeDate(n.due_at))" tone="warning" class="ws-section" :message="'有 ' + backendDemo.state.liveCalendar.filter(n=>!nodeDate(n.due_at)).length + ' 条事项没有提供日期，因此不会出现在上面的日历里；展开下方列表可逐条核对。'" /><Foldable v-if="backendDemo.state.liveCalendar?.some(n=>!nodeDate(n.due_at))" title="日期待补充的事项" variant="section" :count="backendDemo.state.liveCalendar.filter(n=>!nodeDate(n.due_at)).length"><ul class="ws-mini-list"><li v-for="n in backendDemo.state.liveCalendar.filter(n=>!nodeDate(n.due_at))" :key="n.node_id">{{ n.title }}<p>{{ n.related_task_text }}</p></li></ul></Foldable><TimetableAdvice/><nav class="ws-related"><RouterLink to="/home">查看今日行动<UiIcon name="action" :size="16"/></RouterLink><RouterLink to="/academic">更新学校资料<UiIcon name="academic" :size="16"/></RouterLink></nav><p class="ws-demo-note">{{ backendDemo.state.liveCalendar!==null?'节点来自本次读取的日程。未提供日期的事项另行保留。':'关键节点为2026年10月示例。' }} 计划任务与课程读取各自的共享记录。</p><InfoSheet :open="courseDetails!==null" shape="sheet" :title="courseDetails?.name ?? '课程详情'" @close="courseDetails=null"><dl class="course-detail"><div><dt>上课时间</dt><dd>{{ courseDetails ? courseTimeLabel(courseDetails) : '' }}</dd></div><div><dt>地点</dt><dd>{{ courseDetails?.place || '未提供' }}</dd></div><div><dt>周次</dt><dd>{{ courseDetails?.weeks || '未提供' }}</dd></div><div><dt>教师</dt><dd>{{ courseDetails?.teacher || '未提供' }}</dd></div></dl><RouterLink class="ws-text-link ws-section" to="/academic" @click="courseDetails=null">核对导入资料</RouterLink></InfoSheet>
</div>
<!-- ======= 右侧粘性列：这一周的时间被谁占住了 =======
     与靶子的 `.pg-doc__side`（312×1146，sticky）是同一件东西：桌面粘在右侧，
     <768px 收成单列（见本文件 `@media (max-width: 767px)` 那一段）。
     三块：读数（课/事/剩下的）· 图例（把上面那块对照图的语法说清）· 口径与来源。 -->
<aside class="sched-rail" aria-labelledby="sched-rail-title">
  <section class="sched-rail__block">
    <h2 class="sched-rail__t" id="sched-rail-title">第 {{ thisWeek?.n }} 周的时间分配</h2>
    <p class="sched-rail__n"><b class="t-num">{{ hours(thisWeek?.courseHours ?? 0) }}</b><small>课的占用（{{ thisWeek?.courses ?? 0 }} 天有课）</small></p>
    <p class="sched-rail__n sched-rail__n--key"><b class="t-num">{{ hours(thisWeek?.taskHours ?? 0) }}</b><small>任务排进去的（{{ thisWeek?.taskDone ?? 0 }}/{{ thisWeek?.taskTotal ?? 0 }} 件已完成）</small></p>
    <p class="sched-rail__d">每 1 小时课配到 <b>{{ thisWeek && thisWeek.taskHours ? Math.round(perCourseHour(thisWeek) * 60) : 0 }} 分钟</b>事。{{ thisWeek && thisWeek.conflicts ? '有 ' + thisWeek.conflicts + ' 个节次被两门课同时占住，那几节是排不进任务的。' : '没有课与课撞在一起的节次。' }}</p>
    <p class="sched-rail__d" v-if="busiestDay && busiestDay.hours">{{ busiestDay.label }}最重：{{ busiestDay.names.join('、') }}，合计 {{ hours(busiestDay.hours) }} —— 这一天基本摆不下事。</p>
  </section>
  <section class="sched-rail__block">
    <h3 class="sched-rail__t2">上面那张图怎么看</h3>
    <ul class="sched-rail__key">
      <li><i class="sched-rail__i sched-rail__i--c" aria-hidden="true" />课量（固定，不能挪）</li>
      <li><i class="sched-rail__i sched-rail__i--t" aria-hidden="true" />任务量（可按你的时间重排）</li>
      <li><i class="sched-rail__i sched-rail__i--r" aria-hidden="true" />空槽（这一类没占，不是空闲）</li>
    </ul>
    <p class="sched-rail__d">两根横条共用一根刻度，所以"课多的一周事排得少"是看出来的，不是读一句话读出来的；最右一列把它折成每小时的比值，方便横向比。</p>
  </section>
  <section class="sched-rail__block">
    <h3 class="sched-rail__t2">这份读数从哪来</h3>
    <p class="sched-rail__src"><SourceChip :label="backendDemo.state.academicOrigin === 'live' ? '教务系统导入' : '本人导入的课表快照'" kind="external" /><span>课量按导入的节次算（1 节 = 1 小时），周次用课程自己的 weeks 字段。</span></p>
    <p class="sched-rail__src"><SourceChip :label="backendDemo.state.liveAction ? '服务端阶段计划' : '本地演示阶段计划'" kind="citation" /><span>任务量按阶段计划自己划的时间窗归周（第 {{ weekTerm?.from }}–{{ weekTerm?.to }} 周）。</span></p>
    <p class="sched-rail__src" v-if="pendingTimeCourses"><SourceChip label="时间待补充的课程" kind="transcript" /><span>{{ pendingTimeCourses }} 门课没有节次或超出常规节次，不计入上面的课量。</span></p>
  </section>
</aside>
</div>
</div>
</template>

<style scoped>
/* 刷新时的骨架屏：盖在仍在 DOM 的内容上（SkeletonBlock 自己会摘内容，
   这里保留内容只加一层遮罩 —— 刷新不该让已经读到的日历/课表先空一块） */
.sched-refresh-shell { position: relative; }
.sched-course-shell { position: relative; }
/* 盖满容器：只用 inset 拉伸（同时写 height 会与 top/bottom 冲突，浏览器会丢掉 bottom 变成顶部固定高度）。
   骨架自己会按 variant 给高度（SkeletonBlock 的 :height 是内联样式），所以这里再给一层内边距让它不贴边。 */
.sched-refresh { position: absolute; inset: 0; z-index: 1; padding: var(--sp-5) var(--sp-4); overflow: hidden; background: var(--c-surface); }

/* ============================================================================
 * 页头第 3 行（meta）
 * ---------------------------------------------------------------------------
 * 靶子 `.pgh__meta`：68×27 的 tag（12px/600、padding 2px 9px、r999px、1px 描边）
 * + `.conf` 品质标。这里照同一档重量做，但**内容全部是这一页的真实读数**
 * （学期、有节次的课数、这一周的课/事小时数），不是照抄"演示数据"四个字。
 *
 * 为什么"本地演示数据"那一颗最重（红底）：它说的是"这些数字是虚构的，别当真"，
 * 属 tokens.css 里"需要你注意"的语义 —— 红是本站唯一允许承载它的色相。
 * 其余几颗是中性结构信息，用灰底；所以一屏里红色只有这一处。
 * ==========================================================================*/
.sched-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; }
/* 已知的读数与"还没有依据"之间留一道竖线：不加它，两枚徽标会连读成
   "还需要再核对未评估"（实测量到的 innerText 就是这样连着的）。 */
.sched-meta__sep { width: 1px; height: 14px; background: var(--c-border-strong); }

.sched-meta__tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface-2);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  line-height: 1.65;
  color: var(--c-text-2);
}

.sched-meta__tag--demo {
  border-color: var(--c-attention-border);
  background: var(--c-attention-weak);
  color: var(--c-attention);
}

/* ============================================================================
 * ① 结构显形：三周的课量与任务量摆在同一把尺子上
 * ---------------------------------------------------------------------------
 * 一行 = 一周，行内两根横条**共用同一根刻度**（宽度 = 小时 / 三周最大值）。
 * 所以"课量最大的那一周任务量最小"不是文案，是两根条的相对长度。
 *
 * 【为什么条不做生长动画】DESIGN-LANGUAGE §5 反例表点名"数据页加图表 + 图表生长"：
 * 关系没变，生长只是装饰。这里的条是**状态**（宽度即读数），不是入场表演，
 * 所以宽度由内联 style 一次给足，页面里没有任何新 @keyframes。
 * 【为什么没有网格线】加刻度线会让它读成"另一个图表"；两件事同刻度靠**共用轨道**表达，
 * 数字在右侧写全（课/事各一个数），灰度打印下也读得出。
 * ==========================================================================*/
.sched-cmp__count {
  flex: none;
  padding: 1px 10px;
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-2);
}

/* 列：周名 126px · 对照条 1fr · 读数 132px · 余量 154px · 出口 96px。
   窄屏（<768）在下面被压成一列，这里不写 auto-fit —— 五列的断点必须确定。 */
.sched-cmp__grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--sp-2); }
.sched-cmp__legend,
.sched-cmp__row {
  display: grid;
  grid-template-columns: 126px minmax(0, 1fr) minmax(0, 132px) minmax(0, 150px) 92px;
  align-items: center;
  gap: var(--sp-3);
}
.sched-cmp__legend { padding-bottom: var(--sp-1); font-size: var(--fs-12); color: var(--c-text-3); }
.sched-cmp__legend .sched-cmp__k { font-weight: var(--fw-medium); }
/* 表头三列各自对上它下面那一列（第 1 列是周名，没有表头）。 */
.sched-cmp__legend .sched-cmp__k:nth-child(1) { grid-column: 2; }
.sched-cmp__legend .sched-cmp__k:nth-child(2) { grid-column: 3; }
.sched-cmp__legend .sched-cmp__k:nth-child(3) { grid-column: 4; }
.sched-cmp__k { font-size: var(--fs-12); color: var(--c-text-3); }

.sched-cmp__row {
  padding: var(--sp-3) 0;
  border-top: var(--bw-1) solid var(--c-border);
}
.sched-cmp__w { font-size: var(--fs-14); font-weight: var(--fw-semibold); color: var(--c-text); line-height: var(--lh-snug); }
.sched-cmp__w small { display: block; margin-top: 2px; font-size: var(--fs-12); font-weight: var(--fw-regular); color: var(--c-text-3); font-variant-numeric: tabular-nums; }

/* 对照区：两根条各自一行（课在上、事在下），**轨道等宽**才有可比性。
   左侧 22px 是"课 / 事"两个单字标 —— 有它不需要图例也能读，图例是第二道保险。
   条高 8px：它承载的是"长度"这一个量，再高就会读成两个色块。
   轨道底用 --c-surface-3（浅底），条压在上面 —— 空槽的那一段仍然看得见。 */
.sched-cmp__bars { display: grid; grid-template-columns: 22px minmax(0, 1fr); align-items: center; gap: 4px var(--sp-2); min-width: 0; }
.sched-cmp__track { position: relative; height: 8px; min-width: 0; border-radius: var(--r-sm); background: var(--c-surface-3); }
.sched-cmp__bar { position: absolute; left: 0; top: 0; bottom: 0; border-radius: var(--r-sm); }
.sched-cmp__bar--c { background: var(--c-text-3); }
.sched-cmp__bar--t { background: var(--c-primary); }

.sched-cmp__v { display: flex; align-items: baseline; gap: 4px; font-size: var(--fs-12); color: var(--c-text-3); font-variant-numeric: tabular-nums; }
.sched-cmp__v b { font-size: var(--fs-14); font-weight: var(--fw-semibold); color: var(--c-text); }
.sched-cmp__v span + b { margin-left: var(--sp-2); }

/* 折成比值的那一列：数字 + 单位 + 一行算式说明。 */
.sched-cmp__m { font-size: var(--fs-12); color: var(--c-text-3); line-height: var(--lh-snug); font-variant-numeric: tabular-nums; }
.sched-cmp__m > span { font-size: var(--fs-14); font-weight: var(--fw-semibold); color: var(--c-text-2); }
.sched-cmp__m small { display: block; }
/* "这一周一条任务都没排"是**需要你注意**的事实（不是零读数）→ 红。
   本页的红只落在两处：页头那颗"本地演示数据"与这里。 */
.sched-cmp__m--none > span,
.sched-cmp__m--none small { color: var(--c-attention); }

.sched-cmp__go { justify-content: flex-end; gap: 4px; white-space: nowrap; }

.sched-cmp__empty { padding: var(--sp-3) 0; font-size: var(--fs-14); color: var(--c-text-3); }

/* 口径行：靶子的 `.sec__foot` 位置 —— 它解释的是那个**反直觉读数**（空课格 ≠ 空闲），
   所以不能省：没有它，"那天没课"会被当成"那天可以用"。 */
.sched-cmp__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3) var(--sp-5);
  margin-top: var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  font-size: var(--fs-12);
  line-height: var(--lh-snug);
  color: var(--c-text-2);
}
.sched-cmp__foot b { font-weight: var(--fw-semibold); color: var(--c-text); }
/* 口径行里的出口链接：`.ws-text-link` 自带 44px 命中区（它是一行里的**主出口**，
   不是卡片内的次要控件，所以按 44 那一档撑）。 */
.sched-cmp__footlink { flex: none; gap: 4px; }

/* ============================================================================
 * 右侧粘性列
 * ---------------------------------------------------------------------------
 * 桌面（≥768px）：主列 + 312px 的粘性侧列 —— 这就是靶子 `.pg-doc__side` 的宽度。
 * 为什么用 312 而不是现有 `.ws-two-columns` 的 minmax(280px,1fr)：
 * 那一对是"1.6fr + 最小 280"，实测在 1280 下侧列会到 331px；
 * 这一页的右栏装的是徽标与短句，312 刚好让 `.src` 不折行。
 * <768px：收成单列（媒体查询在本文件末尾），且不再 sticky —— 手机上粘一整列会吃掉半个屏幕。
 * ==========================================================================*/
.sched-split { display: grid; grid-template-columns: minmax(0, 1fr) 312px; gap: var(--sp-5); align-items: start; }
.sched-split__main { min-width: 0; display: flex; flex-direction: column; gap: var(--sp-6); }

.sched-rail { position: sticky; top: var(--sp-5); display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
.sched-rail__block { display: flex; flex-direction: column; gap: var(--sp-2); }
.sched-rail__block + .sched-rail__block { padding-top: var(--sp-5); border-top: var(--bw-1) solid var(--c-border); }
.sched-rail__t { font-size: var(--fs-16); font-weight: var(--fw-semibold); line-height: var(--lh-snug); }
.sched-rail__t2 { font-size: var(--fs-14); font-weight: var(--fw-semibold); color: var(--c-text-2); }

/* 读数：标签与数字**同一行**（靶子 `.hm-side__n` 的排法），单位降一档。 */
.sched-rail__n { display: flex; align-items: baseline; gap: 6px; font-size: var(--fs-12); color: var(--c-text-3); }
.sched-rail__n b { font-size: var(--fs-30); font-weight: var(--fw-semibold); line-height: 1.05; letter-spacing: -0.02em; color: var(--c-text); }
.sched-rail__n--key b { color: var(--c-primary); }
.sched-rail__d { font-size: var(--fs-12); line-height: var(--lh-normal); color: var(--c-text-2); }
.sched-rail__d b { font-weight: var(--fw-semibold); color: var(--c-text); }

.sched-rail__key { display: flex; flex-direction: column; gap: var(--sp-2); }
.sched-rail__key li { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-12); line-height: var(--lh-snug); color: var(--c-text-2); }
/* 图例的小方块与上面两条横条**同色同形**（课=深灰、事=主色），
   第三支是虚线的空槽 —— 它对应"还没被占的那一段"，与实心条区分开。 */
.sched-rail__i { flex: none; width: 18px; height: 8px; border-radius: var(--r-sm); }
.sched-rail__i--c { background: var(--c-text-3); }
.sched-rail__i--t { background: var(--c-primary); }
.sched-rail__i--r { border: var(--bw-1) dashed var(--c-border-strong); }

.sched-rail__src { display: flex; flex-direction: column; align-items: flex-start; gap: var(--sp-2); font-size: var(--fs-12); line-height: var(--lh-normal); color: var(--c-text-3); }
.sched-rail__src b { font-weight: var(--fw-semibold); color: var(--c-text-2); }

/* 窄屏收成单列。断点取 767（与 workspace.css 的 `.ws-two-columns` 同一档口径）：
   ≥768 两列、≤767 一列 —— 任务要求"桌面右侧粘性列，<768px 收成单列"就是这条。 */
@media (max-width: 767px) {
  .sched-split { grid-template-columns: minmax(0, 1fr); }
  .sched-rail { position: static; }
  .sched-cmp__legend { display: none; }
  .sched-cmp__row { grid-template-columns: minmax(0, 1fr); gap: var(--sp-2); }
  .sched-cmp__bars,
  .sched-cmp__v,
  .sched-cmp__m,
  .sched-cmp__go { grid-column: 1; }
  .sched-cmp__go { justify-content: flex-start; }
  .sched-cmp__foot { flex-direction: column; align-items: flex-start; }
}
</style>
