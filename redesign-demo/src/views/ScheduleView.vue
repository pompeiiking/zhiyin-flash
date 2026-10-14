<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { demo } from '../store'
import { CALENDAR_MARKS } from '../data/student'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
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
</script>
<template>
<div class="ws-page schedule-page"><PageHeading title="日历与课表" description="关键节点、今日任务和学校课程，各自保留来源。"><button class="btn" :disabled="calendarBusy" @click="loadCalendar">{{ calendarBusy?'正在读取…':(readOnce?'更新最新日程':'读取最新日程') }}</button><RouterLink class="btn" to="/academic"><UiIcon name="upload" :size="16" />管理导入资料</RouterLink></PageHeading>
<p v-if="calendarError" class="ws-field-error" role="alert">{{ calendarError }}</p><PanelTabs v-model="tab" label="日程视图" :items="[{key:'calendar',label:'关键日历'},{key:'courses',label:'一周课表'}]">
<template v-if="tab==='calendar'"><div class="sched-refresh-shell" :aria-busy="refreshing"><div v-if="refreshing" class="sched-refresh"><SkeletonBlock variant="chart" :columns="7" /></div><p v-if="refreshing" class="sr-only" role="status">正在读取最新日程，日历内容保留。</p><header class="calendar-toolbar"><h2>{{ title }}</h2><div class="calendar-toolbar__actions"><button class="ws-icon-button" :aria-label="mode==='week'?'上一周':'上个月'" @click="move(-1)"><UiIcon name="back" /></button><button class="btn" @click="resetDate">今天</button><button class="ws-icon-button" :aria-label="mode==='week'?'下一周':'下个月'" @click="move(1)"><UiIcon name="arrow" /></button><label class="calendar-view">视图<select v-model="mode" aria-label="日历显示方式"><option value="month">月历</option><option value="week">周视图</option><option value="agenda">议程</option></select></label></div></header>
<div v-if="mode==='week'" class="calendar-week-events" aria-label="本周事项"><button v-for="date in weekDates" :key="date.toISOString()" :aria-pressed="date.getDate()===day && date.getMonth()===month.getMonth()" @click="selectDate(date)"><strong>周{{ weekdays[(date.getDay()+6)%7] }} · {{ date.getMonth()+1 }}/{{ date.getDate() }}</strong><span v-for="label in weekItems(date)" :key="label">{{ label }}</span><small v-if="!weekItems(date).length">没有已记录的事项</small></button></div><div class="calendar-layout"><div v-if="mode==='month'" class="calendar-month"><div class="ws-calendar"><span v-for="w in weekdays" :key="w" class="ws-calendar__weekday">{{ w }}</span><span v-for="n in offset" :key="'empty'+n"/><button v-for="d in length" :key="d" class="ws-calendar__day" :class="{'ws-calendar__day--selected':day===d,'ws-calendar__day--marked':marks.some(m=>m.day===d)}" :aria-label="(month.getMonth()+1)+'月'+d+'日'" :aria-pressed="day===d" @click="day=d;advice=false"><span>{{ d }}</span><small v-for="m in marks.filter(m=>m.day===d)" :key="m.label" :title="m.label">{{ m.label }}</small><small v-if="d===today.getDate() && month.getMonth()===today.getMonth() && month.getFullYear()===today.getFullYear() && !backendDemo.state.liveAction && demo.use.now.value.length">{{ demo.use.now.value.length }} 件待执行</small></button></div></div>
<section class="calendar-agenda"><div class="ws-section-head"><h3>{{ month.getMonth()+1 }} 月 {{ day }} 日</h3><span class="ws-muted">当日议程</span></div><label v-if="mode==='agenda'" class="ws-field">选择日期<select v-model.number="day"><option v-for="d in length" :key="d" :value="d">{{ month.getMonth()+1 }} 月 {{ d }} 日</option></select></label><article v-for="m in selectedMarks" :key="m.label" class="agenda-item"><UiIcon name="calendar" :size="18"/><div><h4>{{ m.label }}</h4><p>{{ backendDemo.state.liveCalendar!==null ? '已读取的日程节点' : '预置'+(m.kind==='deadline'?'截止节点':m.kind==='review'?'复盘安排':'行动节点') }}</p></div></article><article v-for="t in selectedTasks" :key="t.id" class="agenda-item"><UiIcon name="action" :size="18"/><div><h4>{{ t.title }}</h4><p>计划任务<span v-if="t.minutes!==null"> · 约 {{ t.minutes }} 分钟</span></p><RouterLink class="ws-text-link" to="/home">查看并执行</RouterLink></div></article><p v-if="!selectedMarks.length&&!selectedTasks.length" class="ws-muted ws-section">这天没有已记录的安排。</p><button class="ws-text-button" @click="advice=true">查看当日建议<UiIcon name="arrow" :size="16"/></button><DayAdvicePanel v-if="advice" :date="selectedDate"/></section></div>
<Foldable title="本月关键节点" variant="section" :count="marks.length" :default-open="false"><ul class="agenda-month-list"><li v-for="m in marks" :key="m.day+m.label"><button class="ws-text-button" @click="day=m.day">{{ month.getMonth()+1 }}/{{ m.day }} · {{ m.label }}</button></li><li v-if="!marks.length" class="ws-muted">本月没有已记录节点。</li></ul></Foldable></div></template>
<template v-else-if="backendDemo.state.academic?.courses?.length"><div class="sched-course-shell"><div class="ws-section-head"><h2>每周课程安排</h2><p>{{ backendDemo.state.academic?.term || '正在读取学期信息' }}</p></div><div class="course-desktop"><div class="course-week" :style="{'--periods':lastPeriod}"><div class="course-week__corner"/><div v-for="w in 7" :key="'head'+w" class="course-week__day" :style="{gridColumn:w+1,gridRow:1}">周{{ weekdays[w-1] }}</div><div v-for="p in lastPeriod" :key="'period'+p" class="course-week__period" :style="{gridColumn:1,gridRow:p+1}">{{ p }} 节</div><div v-for="w in 7" :key="'grid'+w" class="course-week__column" :style="{gridColumn:w+1,gridRow:'2 / span '+lastPeriod}"/><button type="button" v-for="(c,i) in lanes" @click="courseDetails={...c}" :key="i" class="course-block" :style="{gridColumn:c.weekday!+1,gridRow:(c.start_period!+1)+' / span '+(c.end_period!-c.start_period!+1),width:'calc((100% - 8px) / '+c.lanes+')',marginLeft:'calc(4px + (100% - 8px) * '+c.lane+' / '+c.lanes+')'}"><strong>{{ c.name }}</strong><span>{{ c.start_period }}–{{ c.end_period }} 节</span><small v-if="c.place">{{ c.place }}</small><small v-if="c.weeks">{{ c.weeks }} 周</small></button></div></div>
<div class="course-mobile"><div class="course-day-picker" role="group" aria-label="课程日期"><button v-for="w in 7" :key="w" :aria-pressed="courseDay===w" @click="courseDay=w">周{{ weekdays[w-1] }}</button></div><article v-for="(c,i) in visibleCourses" :key="i" class="course-list-item"><div>{{ c.start_period }}–{{ c.end_period }}<small>节</small></div><section><h3><button class="ws-text-button course-title" @click="courseDetails={...c}">{{ c.name }}<UiIcon name="arrow" :size="16"/></button></h3><p>{{ c.place || '地点未提供' }}<span v-if="c.weeks"> · {{ c.weeks }} 周</span></p></section></article><EmptyState v-if="!visibleCourses.length" kind="schedule" size="sm" :heading-level="4" :title="'周' + weekdays[courseDay-1] + '没有已导入的课程'" description="切到其他星期，或先回到资料页导入课表。" /></div>
<StatusBanner v-if="unscheduled.length || timed.some(c=>c.end_period!>40)" tone="warning" class="ws-section" :message="'有 ' + (unscheduled.length + timed.filter(c=>c.end_period!>40).length) + ' 门课程的上课时间没有补全，这些课不会排进上面的课表；展开下方列表可逐条核对。'" /><Foldable v-if="unscheduled.length || timed.some(c=>c.end_period!>40)" title="时间待补充与其他节次的课程" variant="section" :count="unscheduled.length + timed.filter(c=>c.end_period!>40).length"><ul class="ws-mini-list"><li v-for="(c,i) in [...unscheduled,...timed.filter(c=>c.end_period!>40)]" :key="i">{{ c.name }} · {{ courseTimeLabel(c) }}</li></ul></Foldable><p class="ws-muted ws-section">课程按导入节次展示。相同时段的课程可能重叠，请回到资料页核对；空格仅表示快照中没有课程。</p></div></template>
<section v-else class="ws-section"><EmptyState kind="schedule" :heading-level="2" title="课表还没有放进来" description="导入已有课表后，课程会按节次排列。" action-to="/academic" action-label="去导入课表" /></section>
</PanelTabs><StatusBanner v-if="backendDemo.state.liveCalendar?.some(n=>!nodeDate(n.due_at))" tone="warning" class="ws-section" :message="'有 ' + backendDemo.state.liveCalendar.filter(n=>!nodeDate(n.due_at)).length + ' 条事项没有提供日期，因此不会出现在上面的日历里；展开下方列表可逐条核对。'" /><Foldable v-if="backendDemo.state.liveCalendar?.some(n=>!nodeDate(n.due_at))" title="日期待补充的事项" variant="section" :count="backendDemo.state.liveCalendar.filter(n=>!nodeDate(n.due_at)).length"><ul class="ws-mini-list"><li v-for="n in backendDemo.state.liveCalendar.filter(n=>!nodeDate(n.due_at))" :key="n.node_id">{{ n.title }}<p>{{ n.related_task_text }}</p></li></ul></Foldable><TimetableAdvice/><nav class="ws-related"><RouterLink to="/home">查看今日行动<UiIcon name="action" :size="16"/></RouterLink><RouterLink to="/academic">更新学校资料<UiIcon name="academic" :size="16"/></RouterLink></nav><p class="ws-demo-note">{{ backendDemo.state.liveCalendar!==null?'节点来自本次读取的日程。未提供日期的事项另行保留。':'关键节点为2026年10月示例。' }} 计划任务与课程读取各自的共享记录。</p><InfoSheet :open="courseDetails!==null" shape="sheet" :title="courseDetails?.name ?? '课程详情'" @close="courseDetails=null"><dl class="course-detail"><div><dt>上课时间</dt><dd>{{ courseDetails ? courseTimeLabel(courseDetails) : '' }}</dd></div><div><dt>地点</dt><dd>{{ courseDetails?.place || '未提供' }}</dd></div><div><dt>周次</dt><dd>{{ courseDetails?.weeks || '未提供' }}</dd></div><div><dt>教师</dt><dd>{{ courseDetails?.teacher || '未提供' }}</dd></div></dl><RouterLink class="ws-text-link ws-section" to="/academic" @click="courseDetails=null">核对导入资料</RouterLink></InfoSheet></div>
</template>

<style scoped>
/* 刷新时的骨架屏：盖在仍在 DOM 的内容上（SkeletonBlock 自己会摘内容，
   这里保留内容只加一层遮罩 —— 刷新不该让已经读到的日历/课表先空一块） */
.sched-refresh-shell { position: relative; }
.sched-course-shell { position: relative; }
/* 盖满容器：只用 inset 拉伸（同时写 height 会与 top/bottom 冲突，浏览器会丢掉 bottom 变成顶部固定高度）。
   骨架自己会按 variant 给高度（SkeletonBlock 的 :height 是内联样式），所以这里再给一层内边距让它不贴边。 */
.sched-refresh { position: absolute; inset: 0; z-index: 1; padding: var(--sp-5) var(--sp-4); overflow: hidden; background: var(--c-surface); }
</style>
