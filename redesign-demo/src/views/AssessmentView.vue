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
const route = useRoute()
const router = useRouter()
const view = ref('summary')
const printing = ref(false)
const version = computed(() => REPORT_VERSIONS.find((v) => v.id === demo.state.reportVersion) ?? REPORT_VERSIONS[0])
const selected = computed(() => demo.use.selectedDirection.value)
const previous = computed(() => demo.use.previousDirection.value)
const progress = computed(() => demo.use.profileProgress.value)
watch(() => route.query.focus, (focus) => { view.value = focus === 'choose' ? 'directions' : focus === 'versions' ? 'versions' : 'summary' }, { immediate: true })
function changeView(next: string) {
  const query = { ...route.query }
  if (next === 'directions') query.focus = 'choose'
  else if (next === 'versions') query.focus = 'versions'
  else delete query.focus
  router.replace({ path: '/report', query })
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
  <div class="ws-page">
    <PageHeading title="评估报告" description="先看结论，再看依据。方向的选择，始终在你手上。">
      <label class="ws-version-select"><span class="sr-only">报告版本</span><select :value="demo.state.reportVersion" @change="demo.setReportVersion(($event.target as HTMLSelectElement).value)"><option v-for="v in REPORT_VERSIONS" :key="v.id" :value="v.id">{{ v.label }}</option></select></label>
      <button class="btn" @click="printReport">打印 / 存成 PDF</button>
    </PageHeading>
    <nav class="ws-subnav" aria-label="报告内容"><RouterLink to="/report" :aria-current="view === 'summary' ? 'page' : undefined" @click.prevent="changeView('summary')">结论与差距</RouterLink><RouterLink to="/report?focus=choose" :aria-current="view === 'directions' ? 'page' : undefined" @click.prevent="changeView('directions')">方向对比</RouterLink><RouterLink to="/report?focus=versions" :aria-current="view === 'versions' ? 'page' : undefined" @click.prevent="changeView('versions')">版本与变化</RouterLink></nav>
    <template v-if="demo.state.account === 'fresh' && progress.known < 4">
      <section class="ws-paper"><div class="ws-empty"><h2 class="ws-section-title">先了解你，报告才有依据</h2><p>聊几个问题之后，再来看看方向与差距。不会把预置结论当成你的报告。</p><RouterLink class="btn btn--primary" to="/chat">继续对话</RouterLink></div></section>
    </template>
    <template v-else>
      <section v-if="view === 'summary' || printing">
        <div class="ws-paper ws-report-lead"><div><h2>先补呈现能力，<br />再谈投多少家。</h2><p>专业和兴趣已有对得上的方向。眼前最值得先补的是，把已有经历讲成别人听得懂的话。</p><div class="ws-inline-actions"><RouterLink class="btn btn--primary" to="/home">看看今天能做的<UiIcon name="arrow" :size="16" /></RouterLink><button class="ws-text-button" @click="changeView('directions')">比较三个方向</button></div></div><div class="ws-report-score"><strong>4 <small>分</small></strong><p>呈现能力距离<br />主攻方向门槛的差距</p></div></div>
        <section class="ws-paper ws-section">
          <div class="ws-section-head"><div><h2>判断是怎么来的</h2><p>三个角度，各自说明结论、把握和依据。</p></div></div>
          <div class="ws-report-sections"><details v-for="s in REPORT_SECTIONS" :key="s.key" :open="printing"><summary>{{ s.title }}<UiIcon name="chevron" :size="20" /></summary><article v-for="d in s.dimensions" :key="d.key" class="ws-dimension"><div class="ws-dimension__label"><span>{{ d.label }}</span><ConfidenceBadge :value="d.confidence" /></div><p>{{ d.conclusion }}</p><p v-if="d.threshold" class="ws-dimension__threshold">{{ d.threshold }}</p><details class="ws-fold" :open="printing"><summary>看分值与依据<UiIcon name="chevron" :size="16" /></summary><div class="ws-fold__body"><MeterRow v-if="d.score != null" :label="d.label" :score="d.score" :requirement="d.key === 'present' ? 50 : undefined" /><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul></div></details></article></details></div>
          <details class="ws-fold" :open="printing"><summary>查看能力画像与门槛对照<UiIcon name="chevron" :size="18" /></summary><div class="ws-fold__body"><div class="ws-chart-grid"><div><RadarChart :axes="SELF_RADAR" :size="300" :baseline="50" /><p class="ws-muted">预置自评数据；虚线表示 50 分要求线。</p></div><div class="ws-stack"><MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :score="d.mine" :requirement="d.requirement" /></div></div></div></details>
          <details class="ws-fold" :open="printing"><summary>阅读完整结论<UiIcon name="chevron" :size="18" /></summary><p class="ws-fold__body">{{ REPORT_SUMMARY }}</p></details>
        </section>
      </section>
      <section v-if="view === 'directions' || printing">
        <div class="ws-paper">
          <div class="ws-section-head"><div><h2>三条路，先看各自的代价</h2><p>主攻、平行、保底是方案的角色。你可以选择，也可以先放着。</p></div></div>
          <div class="ws-directions"><article v-for="d in DIRECTION_PLANS" :key="d.id" class="ws-direction" :class="{ 'ws-direction--selected': selected?.id === d.id }"><div class="ws-direction__role"><span>{{ d.role }}</span><ConfidenceBadge :value="d.fit" /></div><h2>{{ d.title }}</h2><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul><p class="ws-direction__risk">要留意：{{ d.risk }}</p><button class="btn" :class="selected?.id === d.id ? '' : 'btn--primary'" :disabled="selected?.id === d.id" @click="demo.chooseDirection(d.id)">{{ selected?.id === d.id ? '已选择这一方向' : '选择这个方向' }}</button></article></div>
          <details class="ws-fold" :open="printing"><summary>用机会与门槛比较一下<UiIcon name="chevron" :size="18" /></summary><div class="ws-fold__body"><QuadrantChart :items="quadrants" :selected-id="selected?.id" @pick="demo.chooseDirection" /></div></details>
        </div>
        <section v-if="selected" class="ws-paper ws-section"><div class="ws-impact"><div><h2>{{ previous ? '你的选择已更新' : '已选定这一方向' }}</h2><p>{{ previous ? '从「' + previous.title + '」改选为「' + selected.title + '」。' : selected.title }}</p><p style="margin-top: var(--sp-3)">这会关联 {{ selected.ripple }} 处内容。当前示例展示影响范围，真实报告与计划尚未接入自动重算。</p><RouterLink class="ws-text-link" to="/plan">接下来看看计划<UiIcon name="arrow" :size="16" /></RouterLink></div><div><h2>跟着动的地方</h2><ul v-if="demo.state.rippleOpen || printing"><li v-for="p in selected.ripplePoints" :key="p">{{ p }}</li></ul><button v-if="demo.state.rippleOpen" class="ws-text-button" @click="demo.closeRipple()">收起变更说明</button><button v-else class="ws-text-button" @click="demo.openRipple()">展开影响范围</button></div></div></section>
      </section>
      <section v-if="view === 'versions' || printing" class="ws-paper">
        <div class="ws-section-head"><div><h2>{{ version.label }} · {{ version.at }}</h2><p>这次补上了：{{ version.change }}</p></div></div>
        <div class="ws-chart-grid"><div><TrendLine :points="trend" :highlight-index="REPORT_VERSIONS.length - 1 - REPORT_VERSIONS.findIndex((v) => v.id === version.id)" /><p class="ws-muted">第 1–3 版匹配度的预置快照。</p></div><div><p>每一次补充与核验，都留下一版记录。旧版保留，变化可以对照。</p><p class="ws-muted" style="margin-top: var(--sp-4)">当前页面的详细分值使用第 3 版示例。</p></div></div>
        <div class="ws-versions"><article v-for="v in REPORT_VERSIONS" :key="v.id" class="ws-version-row"><strong>{{ v.label }}</strong><p>{{ v.change }}</p><span class="ws-muted">{{ v.at }}</span></article></div>
      </section>
    </template>
    <div v-if="!demo.state.guidesClosed.report" class="ws-guide"><UiIcon name="info" :size="18" /><p>默认先给结论。想核对时，再展开分值和依据；方向对比与版本记录可单独查看。</p><button @click="demo.closeGuide('report')">收起</button></div>
    <p class="ws-demo-note">这是一份预置示例，尚未基于你的真实情况生成。</p>
  </div>
</template>
