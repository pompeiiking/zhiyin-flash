<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { CALENDAR_MARKS } from '../data/student'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import { hasCourseTime, courseTimeLabel } from '../lib/academic'
const tab = ref('calendar')
const day = ref<number | null>(null)
const weekdays = ['一', '二', '三', '四', '五']
const timedCourses = computed(() => backendDemo.state.academic?.courses?.filter(hasCourseTime) ?? [])
const periods = computed(() => {
  const last = Math.max(10, ...timedCourses.value.map(c => c.end_period!))
  return Array.from({ length: Math.min(20, Math.ceil(last / 2)) }, (_, i) => ({ start: i * 2 + 1, end: i * 2 + 2, label: (i * 2 + 1) + '–' + (i * 2 + 2) + '节' }))
})
const marks = computed(() => day.value ? CALENDAR_MARKS.filter(m => m.day === day.value) : CALENDAR_MARKS)
const weekend = computed(() => timedCourses.value.filter(c => c.weekday! > 5 || c.end_period! > 40))
function courses(weekday: number, start: number, end: number) { return timedCourses.value.filter(c => c.weekday === weekday && c.start_period! <= end && c.end_period! >= start) }
const advice = ref(false)
</script>
<template>
  <div class="ws-page">
    <PageHeading title="日历与课表" description="把课程与重要日期放在一起，才知道时间能留给什么。"><RouterLink class="btn" to="/academic"><UiIcon name="upload" :size="16" />管理导入资料</RouterLink></PageHeading>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-tabs" aria-label="日程视图"><button :aria-pressed="tab === 'calendar'" @click="tab = 'calendar'">关键日历</button><button :aria-pressed="tab === 'courses'" @click="tab = 'courses'">一周课表</button></div>
        <template v-if="tab === 'calendar'"><div class="ws-section-head ws-section"><h2>2026 年 10 月</h2><button v-if="day" class="ws-text-button" @click="day = null; advice = false">查看整月</button></div><div class="ws-calendar"><span v-for="w in ['一','二','三','四','五','六','日']" :key="w" class="ws-calendar__weekday">{{ w }}</span><span v-for="n in 3" :key="'empty-' + n" /><button v-for="d in 31" :key="d" class="ws-calendar__day" :class="{ 'ws-calendar__day--marked': CALENDAR_MARKS.some(m => m.day === d), 'ws-calendar__day--selected': day === d }" :aria-label="'10月' + d + '日'" :aria-pressed="day === d" @click="day = d; advice = false"><span>{{ d }}</span><small v-if="CALENDAR_MARKS.some(m => m.day === d)">有事项</small></button></div><div class="desk-calendar-list"><article v-for="m in marks" :key="m.day + m.label" class="desk-calendar-row"><div class="desk-calendar-date">10 月<strong>{{ m.day }}</strong></div><div><h3>{{ m.label }}</h3><p>{{ m.kind === 'deadline' ? '截止节点' : m.kind === 'review' ? '复盘安排' : '行动任务' }} · 规划示例</p></div></article><p v-if="!marks.length" class="ws-empty ws-muted">这天没有预置的关键节点。仍可以从课表看看课程安排。</p></div><button v-if="day" class="ws-text-button" style="margin-top: var(--sp-4)" @click="advice = true">看看这一天的建议<UiIcon name="arrow" :size="16" /></button><p v-if="advice" class="desk-status" role="status">建议示例：先留好上课时间，再把一个最小动作放进空档。真实建议会由后端结合 {{ '2026-10-' + String(day).padStart(2, '0') }} 与你的时区生成。</p></template>
        <template v-else-if="backendDemo.state.academic?.courses?.length"><div class="ws-section-head ws-section"><div><h2>这一周，哪些时间已经有课</h2><p>{{ backendDemo.state.academic.term }} · 空白格只表示快照里没有课</p></div></div><div class="desk-time-grid"><span /><span v-for="w in weekdays" :key="w">周{{ w }}</span><template v-for="p in periods" :key="p.start"><span>{{ p.label }}</span><div v-for="w in 5" :key="w" class="desk-time-cell" :class="{ 'desk-time-cell--course': courses(w, p.start, p.end).length > 0 }"><div v-for="c in courses(w, p.start, p.end)" :key="c.name + c.start_period"><strong>{{ c.name }}</strong><small>{{ c.start_period }}–{{ c.end_period }}节{{ c.place ? ' · ' + c.place : '' }}</small></div></div></template></div><div v-if="weekend.length" class="ws-section"><h3 class="ws-section-title">其他时段课程</h3><ul class="ws-mini-list"><li v-for="c in weekend" :key="c.name">{{ c.name }} · {{ courseTimeLabel(c) }}</li></ul></div><p class="ws-muted ws-section">单节课与跨时段课程按实际节次显示，同一格可有多门课。未提供完整时间的课程可在资料页查看。</p></template>
        <div v-else class="ws-empty"><UiIcon name="academic" :size="40" /><h3 style="margin-top: var(--sp-4)">课表还没有放进来</h3><p>导入自己导出的课表，课程安排才会出现在这里。</p><RouterLink class="btn btn--primary" to="/academic">去导入课表</RouterLink></div>
      </section>
      <aside class="ws-aside"><section><h2>按时间看，也按事情看</h2><p>日历展示关键节点，行动计划展示阶段任务。两处看的是同一段推进。</p><RouterLink class="ws-text-link" to="/home">回到行动计划<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>课表不是所有日程</h2><p>空白不等于一定有空。兼职、社团和你自己的安排，仍要在对话里补充。</p></section><section><h2>资料有新变化？</h2><p>调课、选课或学期变化后，可以重新导入。快照显示读取的时间。</p><RouterLink class="ws-text-link" to="/academic">更新学校资料<UiIcon name="arrow" :size="16" /></RouterLink></section></aside>
    </div><p class="ws-demo-note">日历节点为预置示例；课表读取当前演示的导入快照。</p>
  </div>
</template>
