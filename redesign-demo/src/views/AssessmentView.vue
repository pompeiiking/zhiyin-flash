<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { DIRECTION_PLANS, REPORT_SECTIONS, REPORT_SUMMARY, REPORT_VERSIONS, SELF_RADAR, THRESHOLD_COMPARE } from '../data/student'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import RadarChart from '../components/charts/RadarChart.vue'
import MeterRow from '../components/charts/MeterRow.vue'
import QuadrantChart from '../components/charts/QuadrantChart.vue'
import TrendLine from '../components/charts/TrendLine.vue'
import { backendDemo } from '../lib/backend-demo'
import PanelTabs from '../components/PanelTabs.vue'
import DirectionCompare from '../components/DirectionCompare.vue'
const route = useRoute()
const router = useRouter()
const view = ref('summary')
const printing = ref(false)
const comparison = ref('overview')
const version = computed(() => REPORT_VERSIONS.find((v) => v.id === demo.state.reportVersion) ?? REPORT_VERSIONS[0])
const selected = computed(() => demo.use.selectedDirection.value)
const previous = computed(() => demo.use.previousDirection.value)
const available = computed(() => view.value === 'directions' ? backendDemo.state.directionsAvailable : backendDemo.state.reportAvailable)
watch(() => [route.path, route.query.focus], () => { view.value = route.path === '/directions' || route.query.focus === 'choose' ? 'directions' : route.query.focus === 'versions' ? 'versions' : 'summary' }, { immediate: true })
function changeView(next: string) {
  const query = { ...route.query }
  if (next === 'versions') query.focus = 'versions'
  else delete query.focus
  router.replace({ path: next === 'directions' ? '/directions' : '/report', query })
}
const quadrants = DIRECTION_PLANS.map((d, i) => ({ id: d.id, label: d.title, role: d.role, x: [72, 84, 40][i], y: [58, 44, 76][i] }))
const trend = REPORT_VERSIONS.slice().reverse().map((v) => ({ label: v.label.replace('（当前）', ''), value: v.fit }))
async function printReport() { printing.value = true; await nextTick(); window.print(); printing.value = false }
function beforePrint() { printing.value = true }
function afterPrint() { printing.value = false }
onMounted(() => { window.addEventListener('beforeprint', beforePrint); window.addEventListener('afterprint', afterPrint) })
onUnmounted(() => { window.removeEventListener('beforeprint', beforePrint); window.removeEventListener('afterprint', afterPrint) })
</script>
<template>
  <div class="ws-page" :class="{ 'journey-page': view === 'directions' }">
    <PageHeading :title="view === 'directions' ? '方向方案' : '诊断报告'" :description="view === 'directions' ? '比较各方向的匹配依据、能力差距与主要风险。' : '查看诊断结果、支持依据及报告版本。'">
      <label v-if="view !== 'directions' && available" class="ws-version-select"><span class="sr-only">报告版本</span><select :value="view === 'versions' ? demo.state.reportVersion : 'v3'" @change="demo.setReportVersion(($event.target as HTMLSelectElement).value); changeView('versions')"><option v-for="v in REPORT_VERSIONS" :key="v.id" :value="v.id">{{ v.label }}</option></select></label>
      <button v-if="available" class="btn" @click="printReport">打印 / 保存 PDF</button>
    </PageHeading>
    <nav v-if="view !== 'directions' && available" class="ws-subnav" aria-label="诊断报告视图"><RouterLink to="/report" :aria-current="view === 'summary' ? 'page' : undefined" @click.prevent="changeView('summary')">诊断结果</RouterLink><RouterLink to="/report?focus=versions" :aria-current="view === 'versions' ? 'page' : undefined" @click.prevent="changeView('versions')">版本记录</RouterLink></nav>
    <template v-if="!available">
      <section class="ws-paper"><div class="ws-empty"><h2 class="ws-section-title">{{ view === 'directions' ? '方向方案还没有形成' : '报告还没有生成' }}</h2><p>完成咨询并补充必要信息后，可生成相应内容。当前未生成个人报告。</p><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><div><button class="ws-text-button" @click="backendDemo.loadAssessmentSample()">查看{{ view === 'directions' ? '方向' : '报告' }}示例</button></div></div></section>
    </template>
    <template v-else>
      <section v-if="view === 'summary'">
        <div class="ws-paper ws-report-lead"><div><h2>优先提升经历表达能力</h2><p>示例诊断显示，专业与目标方向基本匹配，当前主要差距为经历表达能力。建议先完善简历，再制定投递计划。</p><div class="ws-inline-actions"><RouterLink class="btn btn--primary" to="/home">查看行动计划<UiIcon name="arrow" :size="16" /></RouterLink><button class="ws-text-button" @click="changeView('directions')">比较三个方向</button></div></div><div class="ws-report-score"><strong>4 <small>分</small></strong><p>呈现能力距离<br />主攻方向门槛的差距</p></div></div>
        <section class="ws-paper ws-section">
          <div class="ws-section-head"><div><h2>诊断依据</h2><p>从个人情况、外部环境和决策条件三个方面提供支持依据。</p></div></div>
          <div class="ws-report-sections"><details v-for="s in REPORT_SECTIONS" :key="s.key" :open="printing"><summary>{{ s.title }}<UiIcon name="chevron" :size="20" /></summary><article v-for="d in s.dimensions" :key="d.key" class="ws-dimension"><div class="ws-dimension__label"><span>{{ d.label }}</span><ConfidenceBadge :value="d.confidence" /></div><p>{{ d.conclusion }}</p><p v-if="d.threshold" class="ws-dimension__threshold">{{ d.threshold }}</p><details class="ws-fold" :open="printing"><summary>查看分值与依据<UiIcon name="chevron" :size="16" /></summary><div class="ws-fold__body"><MeterRow v-if="d.score != null" :label="d.label" :score="d.score" :requirement="d.key === 'present' ? 50 : undefined" /><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul></div></details></article></details></div>
          <details class="ws-fold" :open="printing"><summary>查看能力画像与门槛对照<UiIcon name="chevron" :size="18" /></summary><div class="ws-fold__body"><div class="ws-chart-grid"><div><RadarChart :axes="SELF_RADAR" :size="300" :baseline="50" /><p class="ws-muted">预置自评数据；虚线表示 50 分要求线。</p></div><div class="ws-stack"><MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :score="d.mine" :requirement="d.requirement" /></div></div></div></details>
          <details class="ws-fold" :open="printing"><summary>阅读完整结论<UiIcon name="chevron" :size="18" /></summary><p class="ws-fold__body">{{ REPORT_SUMMARY }}</p></details>
        </section>
      </section>
      <section v-if="view === 'directions'">
        <div class="journey-decision-lead"><span class="journey-decision-lead__icon"><UiIcon name="directions" :size="36" /></span><div class="journey-decision-lead__copy"><h2>{{ selected ? '你的选择，已经有了落点' : '看清几条路，再选适合自己的' }}</h2><p>{{ selected ? '当前方向：' + selected.title : '结合匹配依据与主要风险，比较主攻、平行和保底三条方向。' }}</p></div><span class="journey-decision-lead__note"><UiIcon name="review" :size="16" />选择后仍可调整</span></div>
        <div class="ws-paper journey-options">
<PanelTabs v-model="comparison" label="方向比较视图" :items="[{ key: 'overview', label: '方案概览' }, { key: 'matrix', label: '逐项对照' }]"><div v-if="comparison === 'overview'" class="ws-directions"><article v-for="d in DIRECTION_PLANS" :key="d.id" class="ws-direction" :class="{ 'ws-direction--selected': selected?.id === d.id }"><div class="ws-direction__role"><span>{{ d.role }}</span><ConfidenceBadge :value="d.fit" /></div><h2>{{ d.title }}</h2><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul><p class="ws-direction__risk"><span><UiIcon name="info" :size="14" />需要留意</span>{{ d.risk }}</p><button class="btn" :class="selected?.id === d.id ? '' : 'btn--primary'" :disabled="selected?.id === d.id" @click="demo.chooseDirection(d.id)"><UiIcon v-if="selected?.id === d.id" name="check" :size="17" />{{ selected?.id === d.id ? '已选择此方向' : '选择这个方向' }}<UiIcon v-if="selected?.id !== d.id" name="arrow" :size="17" /></button></article></div><DirectionCompare v-else :items="DIRECTION_PLANS" :selected-id="selected?.id" @pick="demo.chooseDirection" />
          </PanelTabs>
          <details class="ws-fold" :open="printing"><summary>机会与门槛对比<UiIcon name="chevron" :size="18" /></summary><div class="ws-fold__body"><QuadrantChart :items="quadrants" :selected-id="selected?.id" @pick="demo.chooseDirection" /></div></details>
        </div>
        <section v-if="selected" class="ws-paper ws-section journey-decision-impact"><div class="ws-impact"><div><h2>{{ previous ? '方向选择已更新' : '当前选择' }}</h2><p>{{ previous ? '从「' + previous.title + '」改选为「' + selected.title + '」。' : selected.title }}</p><p style="margin-top: var(--sp-3)">这会关联 {{ selected.ripple }} 处内容。当前示例展示影响范围，真实报告与计划尚未接入自动重算。</p><RouterLink class="ws-text-link" to="/plan">查看阶段计划<UiIcon name="arrow" :size="16" /></RouterLink></div><div><h2>关联内容</h2><ul v-if="demo.state.rippleOpen || printing"><li v-for="p in selected.ripplePoints" :key="p">{{ p }}</li></ul><button v-if="demo.state.rippleOpen" class="ws-text-button" @click="demo.closeRipple()">收起变更说明</button><button v-else class="ws-text-button" @click="demo.openRipple()">展开影响范围</button></div></div></section>
      </section>
      <section v-if="view === 'versions'" class="ws-paper">
        <div class="ws-section-head"><div><h2>{{ version.label }} · {{ version.at }}</h2><p>本次更新：{{ version.change }}</p></div></div>
        <div class="ws-chart-grid"><div><TrendLine :points="trend" :highlight-index="REPORT_VERSIONS.length - 1 - REPORT_VERSIONS.findIndex((v) => v.id === version.id)" /><p class="ws-muted">第 1–3 版匹配度的预置快照。</p></div><div><p>每一次补充与核验，都留下一版记录。旧版保留，变化可以对照。</p><p class="ws-muted" style="margin-top: var(--sp-4)">当前页面的详细分值使用第 3 版示例。</p></div></div>
        <div class="ws-versions"><article v-for="v in REPORT_VERSIONS" :key="v.id" class="ws-version-row"><strong>{{ v.label }}</strong><p>{{ v.change }}</p><span class="ws-muted">{{ v.at }}</span></article></div>
      </section>
    </template>
    <div v-if="!demo.state.guidesClosed.report" class="ws-guide"><UiIcon name="info" :size="18" /><p>{{ view === 'directions' ? '比较匹配依据与主要风险后选择方向。改选会展示关联内容，已有执行记录保留。' : '报告默认展示诊断结果，可展开查看分值与依据。方向方案通过侧栏独立访问。' }}</p><button @click="demo.closeGuide('report')">收起</button></div>
    <p class="ws-demo-note">这是一份预置示例，尚未基于你的真实情况生成。</p>
  </div>
</template>
