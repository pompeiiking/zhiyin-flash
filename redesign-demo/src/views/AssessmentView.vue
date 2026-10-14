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
import type { ReportDimension } from '../data/types'
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

/* ============================================================================
 * 落点②组织权 —— 报告的三个"看角"
 * ---------------------------------------------------------------------------
 * 【病灶】这一页原来只有一个 `<select>`，它切的是**版本**（第 3 版 / 第 2 版 / 第 1 版），
 * 不是视角：同一批 9 个维度只有一种组织方式（按章节），用户改不了它。
 * 门禁实测 `orgKinds {tabs:0, pressed:0, selects:1}` —— "组织权"这一落点等于没显形。
 *
 * 【判据】三个轴都是**真的换分组轴**，不是"换一个列表内容"：条目会被搬到别的组里，
 * 分组头的条数跟着变。9 个维度的实测分布：
 *   按章节看  3 组 · 3 / 3 / 3
 *   按把握看  3 组 · 依据充分 4 / 待验证 4 / 信息不足 1
 *   按分值看  3 组 · 低于 55 分 3 / 55–65 分 4 / 高于 65 分 2
 * 同一批条目在这三个轴下的**相邻关系完全不同**（例如「兴趣方向」在按章节看里与
 * 「做事方式」相邻，在按把握看里与「岗位供给」相邻，在按分值看里与「家里的期待」相邻）
 * —— 这就是"重排"的可核对证据，而不是换个标题。
 *
 * 控件用 PanelTabs（reka-ui）：role=tablist / role=tab / aria-selected / 左右方向键
 * 都是它内建的，44px 触控高度由全局 .exp-tabs__trigger 保证。键盘与读屏不用另写。
 * ==========================================================================*/
const PERSPECTIVES = [
  { key: 'section', label: '按章节看' },
  { key: 'confidence', label: '按把握看' },
  { key: 'score', label: '按分值看' },
]
/* 类型不写死成联合类型：PanelTabs 的 v-model 走的是 string（它 emit 的是 String(value)），
   写成 'section'|'confidence'|'score' 会让 vue-tsc 在模板里报"string 不能赋给它"。 */
const perspective = ref('section')

type ReportItem = ReportDimension & { sectionKey: string; sectionTitle: string }

/** 9 个维度摊平，每条带上它原来的分区 —— 换轴之后仍然要能说清"它原来在哪" */
const allDimensions = computed<ReportItem[]>(() =>
  REPORT_SECTIONS.flatMap((s) => s.dimensions.map((d) => ({ ...d, sectionKey: s.key, sectionTitle: s.title }))),
)

/** 把握度三档。组名与 data/student.ts 里逐条的 `Confidence.label` 同一口径，只是这里按组归纳。 */
const CONFIDENCE_BANDS = [
  { key: 'high', title: '依据充分', note: '这一组的结论有三条以上可核对的依据，可以直接拿去用。' },
  { key: 'mid', title: '待验证', note: '有依据但还不够硬：下面写清还缺什么，补上再当结论。' },
  { key: 'low', title: '信息不足', note: '只有一条依据，先当线索看，不要当结论。' },
] as const

/** 分值三档。55 / 65 是这一组示例数据（46–72 分）的自然断点，不是通用阈值 —— 所以它写在这一页，不写进令牌。 */
const SCORE_BANDS = [
  { key: 'gap', title: '还比较薄（低于 55 分）', note: '和门槛的差距主要落在这几项上。' },
  { key: 'mid', title: '中间一段（55–65 分）', note: '不拖后腿，但也没有余量。' },
  { key: 'edge', title: '相对有底（高于 65 分）', note: '这几项是当前能拿出去的底子。' },
] as const

function inScoreBand(score: number | undefined, band: 'gap' | 'mid' | 'edge'): boolean {
  if (score == null) return false
  if (band === 'gap') return score < 55
  if (band === 'mid') return score >= 55 && score <= 65
  return score > 65
}

interface ReportGroup {
  key: string
  title: string
  /** 分组轴的解释。按章节看时是 null —— 分区的意思不需要再解释一遍。 */
  note: string | null
  items: ReportItem[]
}

const reportGroups = computed<ReportGroup[]>(() => {
  const all = allDimensions.value
  if (perspective.value === 'confidence') {
    return CONFIDENCE_BANDS.map((b) => ({
      key: b.key,
      title: b.title,
      note: b.note,
      items: all.filter((d) => d.confidence.level === b.key),
    }))
  }
  if (perspective.value === 'score') {
    return SCORE_BANDS.map((b) => ({
      key: b.key,
      title: b.title,
      note: b.note,
      items: all.filter((d) => inScoreBand(d.score, b.key)),
    }))
  }
  return REPORT_SECTIONS.map((s) => ({
    key: s.key,
    title: s.title,
    note: null,
    items: all.filter((d) => d.sectionKey === s.key),
  }))
})

const perspectiveNote = computed(() => {
  const total = allDimensions.value.length
  if (perspective.value === 'confidence') {
    return `按"这份结论有多结实"重新分组：条目从原来的分区里搬出来，同一档把握的排在一起（共 ${total} 项）。`
  }
  if (perspective.value === 'score') {
    return `按示例分值重新分组：46–72 分之间的自然断点落在 55 与 65（共 ${total} 项）。`
  }
  return `按报告原本的三个分区排：同一分区里的维度连在一起（共 ${total} 项）。下拉框切的是版本，这里切的是看角。`
})
onMounted(() => { window.addEventListener('beforeprint', beforePrint); window.addEventListener('afterprint', afterPrint) })
onUnmounted(() => { window.removeEventListener('beforeprint', beforePrint); window.removeEventListener('afterprint', afterPrint) })
</script>
<template>
<div class="ws-page assessment-page" :class="{'directions-page':view==='directions'}"><PageHeading :title="view==='directions'?'方向方案':'诊断报告'" :description="view==='directions'?'把支持依据和风险放在一起比较，再确认你的选择。':'先看关键判断，再逐项核对支持依据。'"><label v-if="view!=='directions'&&available&&!fullReport" class="ws-version-select"><span class="sr-only">报告版本</span><select :value="view==='versions'?demo.state.reportVersion:'v3'" @change="demo.setReportVersion(($event.target as HTMLSelectElement).value);changeView('versions')"><option v-for="v in REPORT_VERSIONS" :key="v.id" :value="v.id">{{ v.label }}</option></select></label><button v-if="view!=='directions'" class="btn" :disabled="reportLoading" @click="loadFullReport">{{ reportLoading?'正在读取…':'获取完整报告' }}</button><button v-if="view==='directions'" class="btn" :disabled="directionLoading||directionSaving" @click="loadDirections">{{ directionLoading?'正在读取…':'获取最新方案' }}</button><button v-if="available" class="btn" @click="printReport">打印 / 保存 PDF</button></PageHeading>
<nav v-if="view!=='directions'&&available" class="ws-subnav" aria-label="诊断报告视图"><RouterLink to="/report" :aria-current="view==='summary'?'page':undefined" @click.prevent="changeView('summary')">诊断结果</RouterLink><RouterLink to="/report?focus=versions" :aria-current="view==='versions'?'page':undefined" @click.prevent="changeView('versions')">版本记录</RouterLink></nav>
<AssetNotice v-if="!fullReport&&!reportMetadata"/><template v-if="fullReport"><div class="report-status"><StatTile :label="reportStatusLabel" :value="reportStatusValue" unit="版" :state="recomputeState(reportMetadata)"/><p class="ws-muted" :class="{ 'ws-attention': reportMetadata?.needs_recompute }">{{ reportStatusNote }}</p><StatusBanner v-if="reportMetadata?.needs_recompute" tone="warning" title="这版报告待更新" message="依据已有变化，当前正文仍是原版本。请核对新的个人信息后，通过咨询更新报告。" action-label="核对完整版本记录" @action="changeView('versions')"/><p v-else class="ws-muted">正文版本、生成时间和来源如下；可在版本记录中核对依赖与变化。</p></div></template><p v-if="directionError&&!latestDirections" class="ws-field-error" role="alert">{{ directionError }}</p><p v-if="reportError" class="ws-field-error" role="alert">{{ reportError }}</p><SkeletonBlock v-if="reportLoading&&!available" variant="text" :lines="6" /><EmptyState v-else-if="!available&&!reportLoading" kind="report" :heading-level="2" :title="view==='directions'?'方向方案还没有形成':'报告还没有生成'" description="完成咨询并补充必要信息后，再查看相应结果。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><button class="ws-text-button" @click="backendDemo.loadAssessmentSample()">查看{{ view==='directions'?'方向':'报告' }}示例</button></EmptyState>
<template v-else><FullReportBody v-if="view==='summary'&&fullReport" :report="fullReport"/><template v-else-if="view==='summary'"><section class="report-lead"><h2>优先提升经历表达能力</h2><p>示例诊断显示，专业与目标方向基本匹配，当前主要差距为经历表达能力。建议先完善简历，再制定投递计划。</p><p class="report-gap"><strong>46</strong><span>当前呈现能力</span><UiIcon name="arrow" :size="18"/><strong>50</strong><span>方向要求 · 差4分</span></p><div class="ws-inline-actions"><RouterLink class="btn btn--primary" to="/home">查看行动计划<UiIcon name="arrow" :size="16"/></RouterLink><button class="ws-text-button" @click="changeView('directions')">比较三个方向</button></div></section>
<section class="report-key-evidence"><h2>这个判断的关键依据</h2><ul><li>已有实践经历，但经历表达与简历组织仍需提升。</li><li>示例中的呈现能力46分，目标要求50分。</li><li>先补齐经历表达，再结合投递反馈调整方向与计划。</li></ul><p class="ws-muted">以上为第3版示例摘要；下方可核对每项原始依据。</p></section>
<section class="report-views"><div class="ws-section-head"><div><h2>换一个看角</h2><p>{{ perspectiveNote }}</p></div></div><PanelTabs v-model="perspective" label="报告的看角" :items="PERSPECTIVES"><nav v-if="perspective==='section'" class="report-toc" aria-label="报告章节"><a v-for="s in REPORT_SECTIONS" :key="s.key" :href="'#'+$route.fullPath+'#report-'+s.key" @click.prevent="jumpTo('report-'+s.key)">{{ s.title }}</a><a href="#report-full" @click.prevent="jumpTo('report-full')">完整结论</a></nav><section v-for="g in reportGroups" :key="g.key" :id="(perspective==='section'?'report-':'report-view-')+g.key" class="report-chapter"><h2>{{ g.title }}<span class="report-chapter__count">{{ g.items.length }} 项</span></h2><p v-if="g.note" class="report-chapter__note">{{ g.note }}</p><article v-for="d in g.items" :key="d.key" class="report-dimension"><div class="ws-section-head"><h3>{{ d.label }}</h3><ConfidenceBadge :value="d.confidence"/></div><p>{{ d.conclusion }}</p><p v-if="perspective!=='section'" class="report-dimension__from">原本在「{{ d.sectionTitle }}」</p><Foldable static title="分值与依据" :count="dimensionCount(d)"><p v-if="d.threshold">{{ d.threshold }}</p><MeterRow v-if="d.score!=null" :label="d.label" :value="d.score/100" :requirement="d.key==='present'?0.5:undefined" :format="formatScore01"/><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul></Foldable></article></section></PanelTabs></section>
<Foldable static :title-level="2" class="report-block" title="能力画像与门槛对照"><div class="ws-chart-grid"><div><RadarChart :axes="SELF_RADAR" :size="300" :baseline="50"/><p class="ws-muted">预置自评数据；虚线为50分示例要求。</p></div><div class="ws-stack"><MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :value="d.mine/100" :requirement="d.requirement/100" :format="formatScore01"/></div></div></Foldable><section id="report-full" class="report-chapter reading-prose"><h2>完整结论</h2><p>{{ REPORT_SUMMARY }}</p></section></template>
<template v-else-if="view==='directions'&&latestDirections"><DirectionDetails :plans="latestDirections" :saving="directionSaving||directionLoading" :error="directionError" @select="selectLatest"/></template><template v-else-if="view==='directions'"><p class="direction-current"><UiIcon name="directions" :size="20"/><span>{{ selected?'当前方向：'+selected.title:'还没有确认方向，可以先逐项比较。' }}</span><small>选择后仍可调整</small></p><PanelTabs v-model="comparison" label="方向比较视图" :items="[{key:'overview',label:'方案概览'},{key:'matrix',label:'逐项对照'}]"><div v-if="comparison==='overview'" class="direction-options"><article v-for="d in DIRECTION_PLANS" :key="d.id" class="direction-option" :class="{'direction-option--candidate':candidate===d.id}"><div class="ws-section-head"><span>{{ d.role }}</span><ConfidenceBadge :value="d.fit"/></div><h2>{{ d.title }}</h2><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul><p class="direction-risk"><UiIcon name="info" :size="16"/>{{ d.risk }}</p><label class="direction-radio"><input v-model="candidate" type="radio" name="direction-candidate" :value="d.id"/>{{ selected?.id===d.id?'当前方向':'将此方向作为候选' }}</label></article></div><DirectionCompare v-else :items="DIRECTION_PLANS" :selected-id="candidate" @pick="candidate=$event"/></PanelTabs>
<section class="direction-confirm"><div><h2>{{ pendingDirection ? pendingDirection.title : '比较后再确认' }}</h2><p>{{ candidate===selected?.id?'当前方向已确认，仍可选择其他方向。':pendingDirection?'确认后显示关联内容；已有执行记录保留。':'选择一个候选方向，确认后加入当前计划。' }}</p></div><button class="btn btn--primary" :disabled="!candidate||candidate===selected?.id" @click="demo.chooseDirection(candidate)">确认方向<UiIcon name="check" :size="16"/></button></section>
<Foldable title="机会与门槛示意" :force-open="printing"><p class="ws-muted">两轴坐标为预置示意，不代表真实岗位数量或计算结果。点选只改变候选方向。</p><QuadrantChart :items="quadrants" :selected-id="candidate" @pick="candidate=$event"/></Foldable>
<section v-if="selected" class="direction-impact" role="status"><h2>{{ previous?'方向选择已更新':'当前选择已确认' }}</h2><p>{{ previous?'从「'+previous.title+'」改选为「'+selected.title+'」。':selected.title }}</p><p>关联{{ selected.ripple }}处内容；当前示例展示影响范围，真实报告与计划尚未自动重算。</p><Foldable title="查看关联内容" variant="inline" :default-open="demo.state.rippleOpen" :force-open="printing"><ul><li v-for="p in selected.ripplePoints" :key="p">{{ p }}</li></ul></Foldable><RouterLink class="ws-text-link" to="/plan">查看阶段计划<UiIcon name="arrow" :size="16"/></RouterLink></section></template>
<section v-else class="report-versions"><ReportHistory @open="openHistorical"/><header class="ws-section-head"><h2>{{ version.label }} · {{ version.at }}</h2></header><p>{{ version.change }}</p><div class="ws-chart-grid ws-section"><TrendLine :points="trend" :highlight-index="REPORT_VERSIONS.length-1-REPORT_VERSIONS.findIndex(v=>v.id===version.id)"/><p class="ws-muted">第1–3版为预置匹配度快照。详细正文使用第3版，历史摘要不代表完整旧版报告。</p></div><article v-for="v in REPORT_VERSIONS" :key="v.id" class="ws-version-row"><strong>{{ v.label }}</strong><p>{{ v.change }}</p><time>{{ v.at }}</time></article></section></template><p v-if="!latestDirections&&!fullReport" class="ws-demo-note">本页为预置示例，不代表基于你的真实情况生成的结果。</p><p v-else class="ws-demo-note">当前内容来自本次读取的数据。版本、来源和选择均按返回结果展示；资料变化后请核对更新状态。</p></div>
</template>

<style scoped>
/* ============================================================================
 * 落点②组织权 · 报告的"看角"
 * ---------------------------------------------------------------------------
 * 分组头带**条数**：换轴时条目被搬动、条数跟着变，这是"真的重组"唯一可核对的证据。
 * 计数徽标的形状沿用 Foldable 的 .fold__count（同一门编号语言），但类名不同 ——
 * 它是"分组有几条"，不是"折叠里有几条"，将来要分开改的时候不该互相牵制。
 * ==========================================================================*/
.report-views { margin-top: var(--sp-7); }
.report-views .ws-section-head p { margin-top: var(--sp-2); }

.report-chapter__count {
  margin-left: var(--sp-3);
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
  vertical-align: 2px;
}

.report-chapter__note {
  margin-bottom: var(--sp-4);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

/* 换轴之后，"它原本在哪个分区"必须还在 —— 否则用户会以为分区被删了 */
.report-dimension__from {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* ============================================================================
 * 「能力画像与门槛对照」那个 24px —— 实测出来的**真实机制**，不是猜的
 * ---------------------------------------------------------------------------
 * 结论：它 24px **不是任何 CSS 规则设的**，而是**一条规则都没有**给它字号，
 * 于是浏览器 UA 的 `h2 { font-size: 1.5em }` 生效：1.5 × 父元素 .fold__static-head
 * 的 16px = 24px。实测证据（Chromium 内遍历 document.styleSheets，
 * 列出所有"影响 font-size 且提到 fold"的规则）：
 *   `.fold--section .fold__body h2/h3 → var(--fs-16)`  hit=false
 *   `.fold__static-head → var(--fs-16)`               hit=false（它是**父元素**的规则，不是这个 h2 的）
 *   命中数 = 0；computed 24px；父元素 computed 16px。
 * 为什么 base.css / Foldable.vue 那条 16px 管不到它：那条是
 * `.fold--section .fold__body h2, .fold--section .fold__body h3`，
 * 而这个 h2 是调用方塞进 Foldable `#title` **插槽**的，落在 `.fold__static-head`
 * 里面，**不在 `.fold__body` 里面**（Foldable.vue:174 vs :191）——
 * 父类 .fold--section 是对的，子类不是。
 *
 * 修法不是给字号打一个补丁，而是把插槽收回去：改用 `title-level="2"`，
 * 让 Foldable 直接把标题渲染成 `<h2 class="fold__static-head">`。
 * 顺带消掉原来那条 `<h3 class="fold__static-head"><h2>…</h2></h3>`（标题套标题，
 * 读屏会念两级）—— 也就是说，这条 24px 的成因和那条非法嵌套是同一件事。
 *
 * 档位取 20：它与 `.report-chapter > h2`（20px）、`#report-full > h2`（20px）是同级，
 * 共用一套章节标题。16px 是眉标档（`.report-key-evidence h2`），这一段不是眉标。
 * 选择器写到 `h2.fold__static-head`（特异度 0,2,1）是为了稳赢组件侧那条
 * `.fold__static-head[data-v-*]`（0,2,0），不靠样式加载顺序。
 * ==========================================================================*/
.report-block :deep(h2.fold__static-head) {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  /* base.css 的 :where(.fold__static-head){letter-spacing:0} 特异度为 0，这里盖得住；
     20px 用 -0.01em 是 CRAFT-BRIEF 4.1 允许的那一档。 */
  letter-spacing: -0.01em;
}
</style>
