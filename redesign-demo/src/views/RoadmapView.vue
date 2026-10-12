<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { CALENDAR_MARKS } from '../data/student'
import PageHeading from '../components/PageHeading.vue'
import TaskList from '../components/TaskList.vue'
import UiIcon from '../components/UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
const scenario = computed(() => demo.use.scenario.value)
const tab = ref('milestones')
const tabs = [{ key: 'milestones', label: '阶段里程碑' }, { key: 'week', label: '本周任务' }, { key: 'calendar', label: '关键日历' }, { key: 'sources', label: '任务来源' }]
const selectedDay = ref<number | null>(null)
const weekdays = ['一', '二', '三', '四', '五', '六', '日']
const cells = computed(() => {
  const lead = (new Date(2026, 9, 1).getDay() + 6) % 7
  return [...Array.from({ length: lead }, () => null), ...Array.from({ length: 31 }, (_, i) => i + 1)]
})
const events = computed(() => selectedDay.value ? CALENDAR_MARKS.filter((m) => m.day === selectedDay.value) : CALENDAR_MARKS)
const books = computed(() => ['计划拆下来的', '建议的', '自己写的', '关键节点'].map((label) => ({ label, tasks: demo.state.tasks.filter((t) => t.origin === label) })))
</script>
<template>
  <div class="ws-page">
    <PageHeading title="行动计划" :description="scenario.grade + '这一年，把重要的事放进合适的时间。'"><RouterLink class="btn btn--primary" to="/home">看看今天这一件<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="ws-subnav" aria-label="行动计划视图"><RouterLink to="/home">今日行动</RouterLink><RouterLink to="/plan" aria-current="page">阶段计划</RouterLink><RouterLink to="/schedule">关键日历</RouterLink></nav>
    <section v-if="!backendDemo.state.planAvailable" class="ws-paper"><div class="ws-empty"><h2 class="ws-section-title">阶段计划还没有形成</h2><p>先在对话里确定方向与下一步，计划才有依据。</p><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><div><button class="ws-text-button" @click="backendDemo.loadPlanSample()">查看阶段计划示例</button></div></div></section>
    <div v-else class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-tabs" aria-label="计划内容"><button v-for="t in tabs" :key="t.key" :aria-pressed="tab === t.key" @click="tab = t.key">{{ t.label }}</button></div>
        <section v-if="tab === 'milestones'" class="ws-section"><div class="ws-section-head"><h2>{{ scenario.focus }}</h2></div><div class="ws-milestones"><article v-for="m in scenario.milestones" :key="m.id" class="ws-milestone"><div class="ws-milestone__head"><div><h3>{{ m.title }}</h3><p>{{ m.window }}</p></div><strong>{{ Math.round(m.progress * 100) }}%</strong></div><div class="ws-progress"><span :style="{ '--value': m.progress }" /></div><p>{{ m.note }}</p></article></div></section>
        <section v-else-if="tab === 'week'" class="ws-section"><div class="ws-section-head"><h2>这一周能推进的事</h2></div><TaskList :items="[...demo.use.now.value, ...demo.use.waiting.value]" /><p class="ws-muted" style="margin-top: var(--sp-4)">已完成 {{ demo.use.done.value.length }} 件，完成记录在今日任务里。</p></section>
        <section v-else-if="tab === 'calendar'" class="ws-section"><div class="ws-section-head"><h2>2026 年 10 月</h2><button v-if="selectedDay" class="ws-text-button" @click="selectedDay = null">查看整月</button></div><p class="ws-muted">点有标记的日期，查看那天的重要事项。</p><div class="ws-calendar"><span v-for="w in weekdays" :key="w" class="ws-calendar__weekday">{{ w }}</span><template v-for="(d, i) in cells" :key="i"><button v-if="d" class="ws-calendar__day" :class="{ 'ws-calendar__day--marked': CALENDAR_MARKS.some((m) => m.day === d), 'ws-calendar__day--selected': d === selectedDay }" :aria-label="'10月' + d + '日' + (CALENDAR_MARKS.some((m) => m.day === d) ? '，有关键事项' : '')" :aria-pressed="d === selectedDay" @click="selectedDay = d === selectedDay ? null : d"><span>{{ d }}</span><small v-if="CALENDAR_MARKS.some((m) => m.day === d)">有事项</small></button><span v-else /></template></div><ul class="ws-calendar-events"><li v-for="e in events" :key="e.label"><strong>{{ e.label }}</strong><span>10 月 {{ e.day }} 日 · {{ e.kind === 'deadline' ? '截止日期' : e.kind === 'review' ? '复盘' : '行动' }}</span></li><li v-if="!events.length">这一天没有预置事项。</li></ul></section>
        <section v-else class="ws-section"><div class="ws-section-head"><div><h2>每件事是谁放进来的</h2><p>建议可以采纳，也可以说不适合。</p></div></div><details v-for="b in books" :key="b.label" class="ws-fold" :open="b.label === '计划拆下来的'"><summary>{{ b.label }} · {{ b.tasks.length }} 件<UiIcon name="chevron" :size="18" /></summary><TaskList :items="b.tasks" /></details></section>
      </section>
      <aside class="ws-aside"><section><h2>现在最好先做</h2><p>{{ scenario.nextStep }}</p><RouterLink class="ws-text-link" to="/home">回到今日任务<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>做不动的时候</h2><p>可以把任务拆小、换一种方法，或者重新看看方向。回退也是推进的一部分。</p><RouterLink class="ws-text-link" to="/review">一起复盘一下<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>方向有变化？</h2><p>先看看每条路的依据与代价，再调整选择。</p><RouterLink class="ws-text-link" to="/report?focus=choose">比较三个方向<UiIcon name="arrow" :size="16" /></RouterLink></section></aside>
    </div>
    <div v-if="!demo.state.guidesClosed.plan" class="ws-guide"><UiIcon name="info" :size="18" /><p>里程碑看这一年的目标，本周任务看眼前的推进。关键日历与任务来源可以单独查看。</p><button @click="demo.closeGuide('plan')">收起</button></div>
    <p class="ws-demo-note">里程碑与 2026 年 10 月日历为预置示例。</p>
  </div>
</template>
