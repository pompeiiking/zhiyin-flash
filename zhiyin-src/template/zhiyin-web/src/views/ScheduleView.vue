<script setup lang="ts">
import { onMounted } from 'vue'
import DetailPopover from '../components/DetailPopover.vue'
import OverviewMetric from '../components/OverviewMetric.vue'
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { demo } from '../store'


import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'


import { hasCourseTime, courseTimeLabel } from '../lib/academic'
import InfoSheet from '../components/InfoSheet.vue'
import DayAdvicePanel from '../components/DayAdvicePanel.vue'
import ScheduleCapacity from '../components/ScheduleCapacity.vue'
import ScheduleLoad from '../components/ScheduleLoad.vue'
import { backendClient } from '../api/backend-client'
import TimetableAdvice from '../components/TimetableAdvice.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusBanner from '../components/StatusBanner.vue'
import type { AcademicCourseView } from '../api/backend-types'
import AcademicImportSheet from '../components/AcademicImportSheet.vue'
const courseDetails = ref<AcademicCourseView | null>(null)
const coursesOpen=ref(false)
const courseImportOpen=ref(false),courseRevokeOpen=ref(false),academicStatus=ref(''),academicError=ref('')
const mode = ref(window.matchMedia('(max-width:760px)').matches ? 'agenda' : 'month')
const today = new Date(), month = ref(new Date(today.getFullYear(), today.getMonth(), 1)), day = ref(today.getDate())
const selectedDate = computed(() => month.value.getFullYear()+'-'+String(month.value.getMonth()+1).padStart(2,'0')+'-'+String(day.value).padStart(2,'0'))
const weekDates = computed(() => { const start=new Date(month.value.getFullYear(),month.value.getMonth(),day.value);start.setDate(start.getDate()-(start.getDay()+6)%7);return Array.from({length:7},(_,i)=>new Date(start.getFullYear(),start.getMonth(),start.getDate()+i)) })
const title = computed(() => mode.value==='week' ? (weekDates.value[0].getMonth()+1)+'月'+weekDates.value[0].getDate()+'日 — '+(weekDates.value[6].getMonth()+1)+'月'+weekDates.value[6].getDate()+'日' : month.value.getFullYear() + ' 年 ' + (month.value.getMonth()+1) + ' 月')
function selectDate(date:Date){month.value=new Date(date.getFullYear(),date.getMonth(),1);day.value=date.getDate();advice.value=false}
const calendarEntries=computed(()=>{
 const nodes=[...(backendDemo.state.liveCalendar??[])];
 for(const phase of backendDemo.state.liveAction?.phases??[])for(const task of phase.tasks??[]){const when=task.scheduled_at||task.due_date;if(when&&!nodes.some(n=>n.related_task_text===task.text&&nodeDate(n.due_at)===nodeDate(when)))nodes.push({node_id:'task-'+task.task_id,title:task.text,due_at:when,source:'manual',related_task_text:task.text})}
 return nodes
})
function weekItems(date:Date){const key=date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0');return backendDemo.state.liveCalendar!==null ? calendarEntries.value.filter(n=>nodeDate(n.due_at)===key).map(n=>n.title) : [] }
const offset = computed(() => (month.value.getDay()+6)%7)
const length = computed(() => new Date(month.value.getFullYear(),month.value.getMonth()+1,0).getDate())

const calendarBusy=ref(false),calendarError=ref(''),refreshing=ref(false),readOnce=ref(false)
/* 刷新 = "页面上已经有内容，这次是再读一遍"。没有内容时是首次加载：
   这时用按钮自身的"正在读取…"，不要拿骨架屏盖住空日历（那会把"还没有"说成"正在有"）。 */
async function loadCalendar(){if(calendarBusy.value)return;calendarBusy.value=true;calendarError.value='';if(readOnce.value)refreshing.value=true;try{const [data,plan,workspace]=await Promise.all([backendClient.calendar(),backendClient.action(),backendClient.workspace()]);backendDemo.setAction(plan);backendDemo.setWorkspace(workspace);if(!Array.isArray(data))throw new Error('Incomplete calendar');backendDemo.setCalendar(data);readOnce.value=true}catch{calendarError.value='最新日程没有取得，请重试。当前日期和内容仍保留。'}finally{calendarBusy.value=false;refreshing.value=false}}
function nodeDate(value?:string|null){if(!value)return '';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;const date=new Date(value);return Number.isNaN(date.getTime())?'':date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0')}
const marks = computed(() => backendDemo.state.liveCalendar!==null ? calendarEntries.value.filter(n=>{const d=nodeDate(n.due_at);return d.startsWith(month.value.getFullYear()+'-'+String(month.value.getMonth()+1).padStart(2,'0')+'-')}).map(n=>({day:Number(nodeDate(n.due_at).slice(-2)),label:n.title,kind:'action',source:n.source,detail:n.related_task_text})) : [])
const selectedMarks = computed(() => marks.value.filter(m => m.day === day.value && !(m.source==='manual'&&selectedTasks.value.some(t=>t.title===m.label))))
const selectedTasks = computed(() => backendDemo.state.liveAction ? (backendDemo.state.liveAction.phases?.flatMap(p=>p.tasks??[])??[]).filter(t=>!t.done&&nodeDate(t.scheduled_at||t.due_date)===selectedDate.value).map(t=>({id:t.task_id,title:t.text,minutes:t.estimated_minutes??null})) : month.value.getFullYear()===today.getFullYear() && month.value.getMonth()===today.getMonth() && day.value===today.getDate() ? demo.use.now.value : [])
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

const pendingTimeCourses = computed(() => timed.value.filter(c=>c.end_period!>40).length + unscheduled.value.length)
const undatedTasks=computed(()=>demo.use.now.value.filter(task=>!task.due))
const scheduleDetailsOpen=ref(false)
async function courseImported(message:string){courseImportOpen.value=false;await loadCalendar();academicStatus.value=message;coursesOpen.value=true}
async function revokeCourses(){if(calendarBusy.value)return;calendarBusy.value=true;academicError.value='';try{const result=await backendClient.revokeAcademicCourses();if(!result.revoked)throw new Error('Not confirmed');backendDemo.revokeAcademicCourses();courseRevokeOpen.value=false;coursesOpen.value=false;academicStatus.value='已撤回课表，成绩记录保持不变。';backendDemo.setWorkspace(await backendClient.workspace())}catch{academicError.value='撤回结果暂时没有确认，请重新读取后再试。'}finally{calendarBusy.value=false}}
onMounted(()=>{ void loadCalendar() })
</script>
<template>
<div class="ws-page schedule-page"><PageHeading title="日历与课表" description="关键节点、今日任务和学校课程，各自保留来源。"><template #meta><div class="sched-meta"><span>{{backendDemo.state.academic?.term || '学期未导入'}}</span><span>{{timed.length}} 门课程有节次</span><span v-if="pendingTimeCourses">{{pendingTimeCourses}} 门待补充时间</span></div></template><button class="btn" :disabled="calendarBusy" @click="loadCalendar">{{ calendarBusy?'正在读取…':(readOnce?'更新最新日程':'读取最新日程') }}</button><button class="btn" @click="courseImportOpen=true"><UiIcon name="upload" :size="16" />{{backendDemo.state.academic?.courses?.length?'更新课表':'导入课表'}}</button></PageHeading>
<p v-if="calendarError" class="ws-field-error" role="alert">{{ calendarError }}</p>
<StatusBanner v-if="academicStatus" tone="success" size="sm" :message="academicStatus" @dismiss="academicStatus=''"/>
<StatusBanner v-if="academicError" tone="error" size="sm" :message="academicError" @dismiss="academicError=''"/>
<ScheduleCapacity :date="selectedDate"/><ScheduleLoad :date="selectedDate" @select="selectDate($event);mode='week'"/>
<div class="sched-split">
<div class="sched-split__main">
 <section class="c2-profile-stats" aria-label="已保存的日程与课程"><OverviewMetric label="本月节点"><template #value><strong>{{marks.length}}</strong></template></OverviewMetric><OverviewMetric label="有节次的课程"><template #value><strong>{{timed.length}}</strong></template></OverviewMetric><OverviewMetric label="待执行任务"><template #value><strong>{{demo.use.now.value.length}}</strong></template></OverviewMetric></section>

<div class="schedule-reading-actions"><button class="ws-text-button" @click="scheduleDetailsOpen=true">时间依据<UiIcon name="info" :size="16"/></button><button class="btn" @click="coursesOpen=true">查看一周课表<UiIcon name="academic" :size="16"/></button></div><div class="sched-refresh-shell" :aria-busy="refreshing"><div v-if="refreshing" class="sched-refresh"><SkeletonBlock variant="chart" :columns="7" /></div><p v-if="refreshing" class="sr-only" role="status">正在读取最新日程，日历内容保留。</p><header class="calendar-toolbar"><h2>{{ title }}</h2><div class="calendar-toolbar__actions"><button class="ws-icon-button" :aria-label="mode==='week'?'上一周':'上个月'" @click="move(-1)"><UiIcon name="back" /></button><button class="btn" @click="resetDate">今天</button><button class="ws-icon-button" :aria-label="mode==='week'?'下一周':'下个月'" @click="move(1)"><UiIcon name="arrow" /></button><DetailPopover title="日历显示方式" label="选择日历显示方式"><template #trigger>{{ mode==='month'?'月历':mode==='week'?'周视图':'议程' }}<UiIcon name="settings" :size="16"/></template><fieldset class="ws-field"><legend>日历显示方式</legend><label v-for="option in [{key:'month',label:'月历'},{key:'week',label:'周视图'},{key:'agenda',label:'议程'}]" :key="option.key" class="direction-radio"><input v-model="mode" type="radio" name="calendar-mode" :value="option.key"/>{{ option.label }}</label></fieldset></DetailPopover></div></header>
<div v-if="mode==='week'" class="calendar-week-events" aria-label="本周事项"><button v-for="date in weekDates" :key="date.toISOString()" :aria-pressed="date.getDate()===day && date.getMonth()===month.getMonth()" @click="selectDate(date)"><strong>周{{ weekdays[(date.getDay()+6)%7] }} · {{ date.getMonth()+1 }}/{{ date.getDate() }}</strong><span v-for="label in weekItems(date)" :key="label">{{ label }}</span><small v-if="!weekItems(date).length">没有已记录的事项</small></button></div><div class="calendar-layout"><div v-if="mode==='month'" class="calendar-month"><div class="ws-calendar"><span v-for="w in weekdays" :key="w" class="ws-calendar__weekday">{{ w }}</span><span v-for="n in offset" :key="'empty'+n"/><button v-for="d in length" :key="d" class="ws-calendar__day" :class="{'ws-calendar__day--selected':day===d,'ws-calendar__day--marked':marks.some(m=>m.day===d)}" :aria-label="(month.getMonth()+1)+'月'+d+'日'" :aria-pressed="day===d" @click="day=d;advice=false"><span>{{ d }}</span><small v-for="m in marks.filter(m=>m.day===d)" :key="m.label" :title="m.label">{{ m.label }}</small><small v-if="d===today.getDate() && month.getMonth()===today.getMonth() && month.getFullYear()===today.getFullYear() && !backendDemo.state.liveAction && demo.use.now.value.length">{{ demo.use.now.value.length }} 件待执行</small></button></div></div>
<section class="calendar-agenda"><div class="ws-section-head"><h3>{{ month.getMonth()+1 }} 月 {{ day }} 日</h3><span class="ws-muted">当日议程</span></div><label v-if="mode==='agenda'" class="ws-field">选择日期<input type="date" :value="selectedDate" @change="($event.target as HTMLInputElement).value && selectDate(new Date(($event.target as HTMLInputElement).value+'T12:00:00'))"/></label><article v-for="m in selectedMarks" :key="m.label" class="agenda-item"><UiIcon name="calendar" :size="18"/><div><h4>{{ m.label }}</h4><p>{{ backendDemo.state.liveCalendar!==null ? '已读取的日程节点' : '预置'+(m.kind==='deadline'?'截止节点':m.kind==='review'?'复盘安排':'行动节点') }}</p></div></article><article v-for="t in selectedTasks" :key="t.id" class="agenda-item"><UiIcon name="action" :size="18"/><div><h4>{{ t.title }}</h4><p>计划任务<span v-if="t.minutes!==null"> · 约 {{ t.minutes }} 分钟</span></p><RouterLink class="ws-text-link" to="/home">查看并执行</RouterLink></div></article><p v-if="!selectedMarks.length&&!selectedTasks.length" class="ws-muted ws-section">这天没有已记录的安排。</p><button class="ws-text-button" @click="advice=true">查看当日建议<UiIcon name="arrow" :size="16"/></button><DayAdvicePanel v-if="advice" :date="selectedDate"/></section></div>
<Foldable title="本月关键节点" variant="section" :count="marks.length" :default-open="false"><ul class="agenda-month-list"><li v-for="m in marks" :key="m.day+m.label"><button class="ws-text-button" @click="day=m.day">{{ month.getMonth()+1 }}/{{ m.day }} · {{ m.label }}</button></li><li v-if="!marks.length" class="ws-muted">本月没有已记录节点。</li></ul></Foldable></div>
<InfoSheet :open="coursesOpen" shape="panel" title="一周课表" @close="coursesOpen=false"><template v-if="backendDemo.state.academic?.courses?.length"><div class="sched-course-shell"><div class="ws-section-head"><h2>每周课程安排</h2><p>{{ backendDemo.state.academic?.term || '正在读取学期信息' }}</p></div><div class="course-desktop"><div class="course-week" :style="{'--periods':lastPeriod}"><div class="course-week__corner"/><div v-for="w in 7" :key="'head'+w" class="course-week__day" :style="{gridColumn:w+1,gridRow:1}">周{{ weekdays[w-1] }}</div><div v-for="p in lastPeriod" :key="'period'+p" class="course-week__period" :style="{gridColumn:1,gridRow:p+1}">{{ p }} 节</div><div v-for="w in 7" :key="'grid'+w" class="course-week__column" :style="{gridColumn:w+1,gridRow:'2 / span '+lastPeriod}"/><button type="button" v-for="(c,i) in lanes" @click="courseDetails={...c}" :key="i" class="course-block" :style="{gridColumn:c.weekday!+1,gridRow:(c.start_period!+1)+' / span '+(c.end_period!-c.start_period!+1),width:'calc((100% - 8px) / '+c.lanes+')',marginLeft:'calc(4px + (100% - 8px) * '+c.lane+' / '+c.lanes+')'}"><strong>{{ c.name }}</strong><span>{{ c.start_period }}–{{ c.end_period }} 节</span><small v-if="c.place">{{ c.place }}</small><small v-if="c.weeks">{{ c.weeks }} 周</small></button></div></div>
<div class="course-mobile"><div class="course-day-picker" role="group" aria-label="课程日期"><button v-for="w in 7" :key="w" :aria-pressed="courseDay===w" @click="courseDay=w">周{{ weekdays[w-1] }}</button></div><article v-for="(c,i) in visibleCourses" :key="i" class="course-list-item"><div>{{ c.start_period }}–{{ c.end_period }}<small>节</small></div><section><h3><button class="ws-text-button course-title" @click="courseDetails={...c}">{{ c.name }}<UiIcon name="arrow" :size="16"/></button></h3><p>{{ c.place || '地点未提供' }}<span v-if="c.weeks"> · {{ c.weeks }} 周</span></p></section></article><EmptyState v-if="!visibleCourses.length" kind="schedule" size="sm" :heading-level="4" :title="'周' + weekdays[courseDay-1] + '没有已导入的课程'" description="切到其他星期，或在本页更新课表。" /></div>
<StatusBanner v-if="unscheduled.length || timed.some(c=>c.end_period!>40)" tone="warning" class="ws-section" :message="'有 ' + (unscheduled.length + timed.filter(c=>c.end_period!>40).length) + ' 门课程的上课时间没有补全，这些课不会排进上面的课表；展开下方列表可逐条核对。'" /><Foldable v-if="unscheduled.length || timed.some(c=>c.end_period!>40)" title="时间待补充与其他节次的课程" variant="section" :count="unscheduled.length + timed.filter(c=>c.end_period!>40).length"><ul class="ws-mini-list"><li v-for="(c,i) in [...unscheduled,...timed.filter(c=>c.end_period!>40)]" :key="i">{{ c.name }} · {{ courseTimeLabel(c) }}</li></ul></Foldable><p class="ws-muted ws-section">课程按导入节次展示。相同时段的课程可能重叠；空格仅表示快照中没有课程。</p><div class="ws-inline-actions"><button class="btn" @click="courseImportOpen=true">更新课表</button><button class="btn btn--danger" @click="courseRevokeOpen=true">撤回课表</button></div></div></template>
<section v-else class="ws-section"><EmptyState kind="schedule" :heading-level="2" title="课表还没有放进来" description="导入已有课表后，课程会按节次排列。" action-label="导入课表" @action="courseImportOpen=true" /></section>
</InfoSheet><StatusBanner v-if="backendDemo.state.liveCalendar?.some(n=>!nodeDate(n.due_at))" tone="warning" class="ws-section" :message="'有 ' + calendarEntries.filter(n=>!nodeDate(n.due_at)).length + ' 条事项没有提供日期，因此不会出现在上面的日历里；展开下方列表可逐条核对。'" /><Foldable v-if="backendDemo.state.liveCalendar?.some(n=>!nodeDate(n.due_at))" title="日期待补充的事项" variant="section" :count="calendarEntries.filter(n=>!nodeDate(n.due_at)).length"><ul class="ws-mini-list"><li v-for="n in calendarEntries.filter(n=>!nodeDate(n.due_at))" :key="n.node_id">{{ n.title }}<p>{{ n.related_task_text }}</p></li></ul></Foldable><TimetableAdvice/><nav class="ws-related"><RouterLink to="/home">查看今日行动<UiIcon name="action" :size="16"/></RouterLink><RouterLink to="/grades">查看我的成绩<UiIcon name="academic" :size="16"/></RouterLink></nav><p class="ws-demo-note">{{ backendDemo.state.liveCalendar!==null?'节点来自本次读取的日程。未提供日期的事项另行保留。':'关键节点来自2026年10月计划。' }} 计划任务与课程读取各自的共享记录。</p><InfoSheet :open="courseDetails!==null" shape="sheet" :title="courseDetails?.name ?? '课程详情'" @close="courseDetails=null"><dl class="course-detail"><div><dt>上课时间</dt><dd>{{ courseDetails ? courseTimeLabel(courseDetails) : '' }}</dd></div><div><dt>地点</dt><dd>{{ courseDetails?.place || '未提供' }}</dd></div><div><dt>周次</dt><dd>{{ courseDetails?.weeks || '未提供' }}</dd></div><div><dt>教师</dt><dd>{{ courseDetails?.teacher || '未提供' }}</dd></div></dl><button class="ws-text-button ws-section" @click="courseDetails=null;courseImportOpen=true">更新课表资料</button></InfoSheet>
</div>
<!-- ======= 右侧粘性列：这一周的时间被谁占住了 =======
     与靶子的 `.pg-doc__side`（312×1146，sticky）是同一件东西：桌面粘在右侧，
     <768px 收成单列（见本文件 `@media (max-width: 767px)` 那一段）。
     三块：读数（课/事/剩下的）· 图例（把上面那块对照图的语法说清）· 口径与来源。 -->
<InfoSheet :open="scheduleDetailsOpen" shape="panel" title="课程与任务时间依据" @close="scheduleDetailsOpen=false"><aside class="sched-rail" aria-labelledby="sched-rail-title">
  <section class="sched-rail__block c2-undated-tasks"><h2>还没有具体日期的任务</h2><article v-for="task in undatedTasks" :key="task.id" class="c2-calendar-node"><h3>{{ task.title }}</h3><p>仍保留在计划里，尚未排到具体日期</p><RouterLink class="ws-text-link" to="/home">回到行动计划 →</RouterLink></article><p v-if="!undatedTasks.length">当前待执行任务都有日期标记。</p></section>
  <section class="sched-rail__block"><h2 id="sched-rail-title">时间来源</h2><p>课程按导入的星期、节次和周次展示；截止日期来自已保存的行动计划。学期起始日期和每节课时长尚未提供，因此不估算每周空闲时间。</p></section>
</aside></InfoSheet>
<AcademicImportSheet :open="courseImportOpen" kind="courses" :has-rows="!!backendDemo.state.academic?.courses?.length" :school="backendDemo.state.academic?.school" :term="backendDemo.state.academic?.term" @close="courseImportOpen=false" @saved="courseImported" />
<InfoSheet :open="courseRevokeOpen" shape="dialog" title="撤回课表" @close="courseRevokeOpen=false"><p>将删除当前保存的课程和排课信息。成绩、学籍与行动记录不会受影响。</p><div class="ws-inline-actions"><button class="btn btn--danger" :disabled="calendarBusy" @click="revokeCourses">{{calendarBusy?'正在撤回…':'确认撤回课表'}}</button><button class="btn" :disabled="calendarBusy" @click="courseRevokeOpen=false">取消</button></div></InfoSheet>
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
 * 为什么"本地资料"那一颗最重（红底）：它说的是"这些数字是虚构的，别当真"，
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
 * ① 结构显形：三周的课程与任务用时对比
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
   本页的红只落在两处：页头那颗"本地资料"与这里。 */
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
