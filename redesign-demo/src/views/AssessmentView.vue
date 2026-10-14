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
import FullReportBody from '../components/FullReportBody.vue'
import DirectionDetails from '../components/LiveDirectionCompare.vue'
import ReportHistory from '../components/ReportHistory.vue'
import AssetNotice from '../components/AssetNotice.vue'
import Foldable from '../components/Foldable.vue'
import StatTile from '../components/StatTile.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { formatScore01 } from '../components/charts/MeterRow.vue'
import { backendClient } from '../api/backend-client'
import type { ReportFullTextView, AssetVersionView } from '../api/backend-types'
const route = useRoute()
const router = useRouter()
const view = ref('summary')
const printing = ref(false)
const comparison = ref('overview')
const candidate = ref(demo.state.selectedDirectionId ?? '')
const fullReport = computed(() => backendDemo.state.liveReport)
const reportMetadata = computed(() => backendDemo.state.reportMetadata)
const reportLoading = ref(false), reportError = ref('')
const latestDirections = computed(() => backendDemo.state.liveDirections)
const directionLoading=ref(false), directionSaving=ref(false), directionError=ref('')
async function loadDirections() {
  if (directionLoading.value || directionSaving.value) return
  directionError.value='';directionLoading.value=true
  try { const data=await backendClient.directions();if(!data||!Array.isArray(data.plans))throw new Error('Incomplete directions response');backendDemo.setLiveDirections(data) }
  catch { directionError.value='暂时没有取得最新方案。可以重试，当前内容仍然保留。' }
  finally { directionLoading.value=false }
}
async function selectLatest(id:string) {
  if(directionLoading.value || directionSaving.value)return
  directionSaving.value=true;directionError.value=''
  try { const result=await backendClient.selectDirection(id);if(!result||!Array.isArray(result.plans))throw new Error('Incomplete selection response');backendDemo.setLiveDirections(result);backendDemo.markDirectionChange() }
  catch { directionError.value='这次选择没有保存成功，请重试。原方案仍然保留。' }
  finally { directionSaving.value=false }
}
async function loadFullReport() {
  reportError.value = ''; reportLoading.value = true
  try {
    const document = await backendClient.report()
    if (!document || typeof document.version !== 'number' || typeof document.report_id !== 'string' || typeof document.generated_at !== 'string') throw new Error('Incomplete report response')
    backendDemo.setReport(document);backendDemo.setReportMetadata(null);changeView('summary')
    try { const versions=await backendClient.versions('report');backendDemo.setReportMetadata(versions.find(v=>v.version===document.version)??null) } catch { /* The document is usable; status stays explicitly unknown. */ }
  }
  catch { reportError.value = '暂时没有取得完整报告。可以重试，当前内容仍然保留。' }
  finally { reportLoading.value = false }
}
const pendingDirection = computed(() => DIRECTION_PLANS.find(d => d.id === candidate.value))
function jumpTo(id: string) { document.getElementById(id)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }) }
const version = computed(() => REPORT_VERSIONS.find((v) => v.id === demo.state.reportVersion) ?? REPORT_VERSIONS[0])
const selected = computed(() => demo.use.selectedDirection.value)
const previous = computed(() => demo.use.previousDirection.value)
const available = computed(() => view.value === 'directions' ? !!latestDirections.value || backendDemo.state.directionsAvailable : !!fullReport.value || backendDemo.state.reportAvailable)
function openHistorical(document: ReportFullTextView, metadata: AssetVersionView | null) { backendDemo.setReport(document);backendDemo.setReportMetadata(metadata);changeView('summary') }
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
/* ---- 读数与状态：三个"同一字段多种印法"的收敛点 ----
 * 1. `format`：MeterRow / StatTile 只接受 0–1，且**不把 0–1 直接印成人话**
 *    （MeterRow.vue:26-34）。报告页的口径是"整分"（页首 `report-gap` 已经是
 *    「46 / 50」裸数字），所以必须显式给 `formatScore01`，否则同屏出现 46% 与 46 分两把尺。
 * 2. `recomputeState`：`needs_recompute` 在本页原来是中性发丝线（`.asset-notice`），
 *    在 ReportHistory 是红字、在画像页又是红底块 —— 收敛成 StatTile 的 recompute 态。
 *    三态必须分开：需要重算 / 确认无需重算 / **状态尚未取得**（unknown 不是 done）。
 * 3. `dimensionCount`：每个维度的依据条数，给静态段的计数徽标。 */
function recomputeState(meta: { needs_recompute?: boolean } | null | undefined): 'recompute' | 'done' | 'none' {
  if (!meta) return 'none'
  return meta.needs_recompute ? 'recompute' : 'done'
}
const reportStatusLabel = computed(() => (reportMetadata.value ? '报告版本' : '本版状态未取得'))
const reportStatusValue = computed(() => reportMetadata.value?.version ?? null)
const reportStatusNote = computed(() => {
  const meta = reportMetadata.value
  if (!meta) return '还没有读到这一版的更新状态；正文仍可阅读。'
  return meta.needs_recompute
    ? '依据已有变化：正文与分值仍是原版本，请先核对最新个人信息。'
    : `生成于 ${new Date(meta.created_at).toLocaleString('zh-CN')}；依赖与差异可在版本记录中核对。`
})
function dimensionCount(d: { evidence?: string[] }): number {
  return d.evidence?.length ?? 0
}
onMounted(() => { window.addEventListener('beforeprint', beforePrint); window.addEventListener('afterprint', afterPrint) })
onUnmounted(() => { window.removeEventListener('beforeprint', beforePrint); window.removeEventListener('afterprint', afterPrint) })
</script>
<template>
<div class="ws-page assessment-page" :class="{'directions-page':view==='directions'}"><PageHeading :title="view==='directions'?'方向方案':'诊断报告'" :description="view==='directions'?'把支持依据和风险放在一起比较，再确认你的选择。':'先看关键判断，再逐项核对支持依据。'"><label v-if="view!=='directions'&&available&&!fullReport" class="ws-version-select"><span class="sr-only">报告版本</span><select :value="view==='versions'?demo.state.reportVersion:'v3'" @change="demo.setReportVersion(($event.target as HTMLSelectElement).value);changeView('versions')"><option v-for="v in REPORT_VERSIONS" :key="v.id" :value="v.id">{{ v.label }}</option></select></label><button v-if="view!=='directions'" class="btn" :disabled="reportLoading" @click="loadFullReport">{{ reportLoading?'正在读取…':'获取完整报告' }}</button><button v-if="view==='directions'" class="btn" :disabled="directionLoading||directionSaving" @click="loadDirections">{{ directionLoading?'正在读取…':'获取最新方案' }}</button><button v-if="available" class="btn" @click="printReport">打印 / 保存 PDF</button></PageHeading>
<nav v-if="view!=='directions'&&available" class="ws-subnav" aria-label="诊断报告视图"><RouterLink to="/report" :aria-current="view==='summary'?'page':undefined" @click.prevent="changeView('summary')">诊断结果</RouterLink><RouterLink to="/report?focus=versions" :aria-current="view==='versions'?'page':undefined" @click.prevent="changeView('versions')">版本记录</RouterLink></nav>
<AssetNotice v-if="!fullReport&&!reportMetadata"/><template v-if="fullReport"><div class="report-status"><StatTile :label="reportStatusLabel" :value="reportStatusValue" unit="版" :state="recomputeState(reportMetadata)"/><p class="ws-muted" :class="{ 'ws-attention': reportMetadata?.needs_recompute }">{{ reportStatusNote }}</p><StatusBanner v-if="reportMetadata?.needs_recompute" tone="warning" title="这版报告待更新" message="依据已有变化，当前正文仍是原版本。请核对新的个人信息后，通过咨询更新报告。" action-label="核对完整版本记录" @action="changeView('versions')"/><p v-else class="ws-muted">正文版本、生成时间和来源如下；可在版本记录中核对依赖与变化。</p></div></template><p v-if="directionError&&!latestDirections" class="ws-field-error" role="alert">{{ directionError }}</p><p v-if="reportError" class="ws-field-error" role="alert">{{ reportError }}</p><SkeletonBlock v-if="reportLoading&&!available" variant="text" :lines="6" /><EmptyState v-else-if="!available&&!reportLoading" kind="report" :heading-level="2" :title="view==='directions'?'方向方案还没有形成':'报告还没有生成'" description="完成咨询并补充必要信息后，再查看相应结果。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><button class="ws-text-button" @click="backendDemo.loadAssessmentSample()">查看{{ view==='directions'?'方向':'报告' }}示例</button></EmptyState>
<template v-else><FullReportBody v-if="view==='summary'&&fullReport" :report="fullReport"/><template v-else-if="view==='summary'"><section class="report-lead"><h2>优先提升经历表达能力</h2><p>示例诊断显示，专业与目标方向基本匹配，当前主要差距为经历表达能力。建议先完善简历，再制定投递计划。</p><p class="report-gap"><strong>46</strong><span>当前呈现能力</span><UiIcon name="arrow" :size="18"/><strong>50</strong><span>方向要求 · 差4分</span></p><div class="ws-inline-actions"><RouterLink class="btn btn--primary" to="/home">查看行动计划<UiIcon name="arrow" :size="16"/></RouterLink><button class="ws-text-button" @click="changeView('directions')">比较三个方向</button></div></section>
<section class="report-key-evidence"><h2>这个判断的关键依据</h2><ul><li>已有实践经历，但经历表达与简历组织仍需提升。</li><li>示例中的呈现能力46分，目标要求50分。</li><li>先补齐经历表达，再结合投递反馈调整方向与计划。</li></ul><p class="ws-muted">以上为第3版示例摘要；下方可核对每项原始依据。</p></section>
<nav class="report-toc" aria-label="报告章节"><a v-for="s in REPORT_SECTIONS" :key="s.key" :href="'#'+$route.fullPath+'#report-'+s.key" @click.prevent="jumpTo('report-'+s.key)">{{ s.title }}</a><a href="#report-full" @click.prevent="jumpTo('report-full')">完整结论</a></nav>
<section v-for="s in REPORT_SECTIONS" :key="s.key" :id="'report-'+s.key" class="report-chapter"><h2>{{ s.title }}</h2><article v-for="d in s.dimensions" :key="d.key" class="report-dimension"><div class="ws-section-head"><h3>{{ d.label }}</h3><ConfidenceBadge :value="d.confidence"/></div><p>{{ d.conclusion }}</p><Foldable static title="分值与依据" :count="dimensionCount(d)"><p v-if="d.threshold">{{ d.threshold }}</p><MeterRow v-if="d.score!=null" :label="d.label" :value="d.score/100" :requirement="d.key==='present'?0.5:undefined" :format="formatScore01"/><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul></Foldable></article></section>
<Foldable static title="能力画像与门槛对照"><template #title><h2>能力画像与门槛对照</h2></template><div class="ws-chart-grid"><div><RadarChart :axes="SELF_RADAR" :size="300" :baseline="50"/><p class="ws-muted">预置自评数据；虚线为50分示例要求。</p></div><div class="ws-stack"><MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :value="d.mine/100" :requirement="d.requirement/100" :format="formatScore01"/></div></div></Foldable><section id="report-full" class="report-chapter reading-prose"><h2>完整结论</h2><p>{{ REPORT_SUMMARY }}</p></section></template>
<template v-else-if="view==='directions'&&latestDirections"><DirectionDetails :plans="latestDirections" :saving="directionSaving||directionLoading" :error="directionError" @select="selectLatest"/></template><template v-else-if="view==='directions'"><p class="direction-current"><UiIcon name="directions" :size="20"/><span>{{ selected?'当前方向：'+selected.title:'还没有确认方向，可以先逐项比较。' }}</span><small>选择后仍可调整</small></p><PanelTabs v-model="comparison" label="方向比较视图" :items="[{key:'overview',label:'方案概览'},{key:'matrix',label:'逐项对照'}]"><div v-if="comparison==='overview'" class="direction-options"><article v-for="d in DIRECTION_PLANS" :key="d.id" class="direction-option" :class="{'direction-option--candidate':candidate===d.id}"><div class="ws-section-head"><span>{{ d.role }}</span><ConfidenceBadge :value="d.fit"/></div><h2>{{ d.title }}</h2><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul><p class="direction-risk"><UiIcon name="info" :size="16"/>{{ d.risk }}</p><label class="direction-radio"><input v-model="candidate" type="radio" name="direction-candidate" :value="d.id"/>{{ selected?.id===d.id?'当前方向':'将此方向作为候选' }}</label></article></div><DirectionCompare v-else :items="DIRECTION_PLANS" :selected-id="candidate" @pick="candidate=$event"/></PanelTabs>
<section class="direction-confirm"><div><h2>{{ pendingDirection ? pendingDirection.title : '比较后再确认' }}</h2><p>{{ candidate===selected?.id?'当前方向已确认，仍可选择其他方向。':pendingDirection?'确认后显示关联内容；已有执行记录保留。':'选择一个候选方向，确认后加入当前计划。' }}</p></div><button class="btn btn--primary" :disabled="!candidate||candidate===selected?.id" @click="demo.chooseDirection(candidate)">确认方向<UiIcon name="check" :size="16"/></button></section>
<Foldable title="机会与门槛示意" :force-open="printing"><p class="ws-muted">两轴坐标为预置示意，不代表真实岗位数量或计算结果。点选只改变候选方向。</p><QuadrantChart :items="quadrants" :selected-id="candidate" @pick="candidate=$event"/></Foldable>
<section v-if="selected" class="direction-impact" role="status"><h2>{{ previous?'方向选择已更新':'当前选择已确认' }}</h2><p>{{ previous?'从「'+previous.title+'」改选为「'+selected.title+'」。':selected.title }}</p><p>关联{{ selected.ripple }}处内容；当前示例展示影响范围，真实报告与计划尚未自动重算。</p><Foldable title="查看关联内容" variant="inline" :default-open="demo.state.rippleOpen" :force-open="printing"><ul><li v-for="p in selected.ripplePoints" :key="p">{{ p }}</li></ul></Foldable><RouterLink class="ws-text-link" to="/plan">查看阶段计划<UiIcon name="arrow" :size="16"/></RouterLink></section></template>
<section v-else class="report-versions"><ReportHistory @open="openHistorical"/><header class="ws-section-head"><h2>{{ version.label }} · {{ version.at }}</h2></header><p>{{ version.change }}</p><div class="ws-chart-grid ws-section"><TrendLine :points="trend" :highlight-index="REPORT_VERSIONS.length-1-REPORT_VERSIONS.findIndex(v=>v.id===version.id)"/><p class="ws-muted">第1–3版为预置匹配度快照。详细正文使用第3版，历史摘要不代表完整旧版报告。</p></div><article v-for="v in REPORT_VERSIONS" :key="v.id" class="ws-version-row"><strong>{{ v.label }}</strong><p>{{ v.change }}</p><time>{{ v.at }}</time></article></section></template><p v-if="!latestDirections&&!fullReport" class="ws-demo-note">本页为预置示例，不代表基于你的真实情况生成的结果。</p><p v-else class="ws-demo-note">当前内容来自本次读取的数据。版本、来源和选择均按返回结果展示；资料变化后请核对更新状态。</p></div>
</template>
