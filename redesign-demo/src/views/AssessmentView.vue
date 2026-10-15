<script setup lang="ts">
import DetailPopover from '../components/DetailPopover.vue'
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
import InfoSheet from '../components/InfoSheet.vue'
const reportBasisOpen=ref(false)
const reportDetails=ref(false), chartDetails=ref(false), activeChapter=ref('')
import DirectionCompare from '../components/WeightedDirectionCompare.vue'
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
const evidenceSection = ref('')
const reportVerdicts = [
  { key: 'expression', title: '优先完善项目经历的表达与证据', detail: '呈现能力 46 分，目标要求 50 分；项目和实习经历是目前需要补齐的证据。', depends: ['present', 'threshold', 'compete'] },
  { key: 'supply', title: '岗位供给信息仍需核实', detail: '岗位供给来自本版统计，实际趋势仍需核对最新来源；这条不确定性会影响方向与时间取舍。', depends: ['demand', 'time'] },
  { key: 'conditions', title: '结合家庭期待与目标城市评估选择', detail: '家庭期待、城市与预算都参与同一个决定。已有信息和仍需核对的条件，不能混成一条确定结论。', depends: ['family', 'city'] },
]
function chooseEvidence(key: string) { evidenceSection.value=key;activeChapter.value='';reportDetails.value=true }
function evidenceHit(key: string) { return reportVerdicts.find(s => s.key === evidenceSection.value)?.depends.includes(key) ?? false }
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
/* ============================================================================
 * toc 跳转：**为什么不能只靠「点一下 `<a href="#x">`」**
 * ---------------------------------------------------------------------------
 * 这是一页 hash 路由（`createWebHashHistory`）—— 地址栏的 fragment 就是路由本身，
 * 页内锚点和路由抢的是同一个位置。实测三种写法，全都不成立：
 *   · `<a href="#report-market">` 直接点（上一轮就是这一类）：浏览器先把 fragment
 *     改成 `#report-market`，vue-router 的 hash 监听随即把它当**路由**解析 ——
 *     `#report-market` 不是任何一条 route，于是走兜底、整页跳到 404，
 *     实测点完 `.report-toc a` 直接消失（元素没了）。
 *   · 上一轮真正写的是 `'#'+$route.fullPath+'#report-'+key`
 *     （`#/report?as=mid#report-self`）：连"短暂正确"都没有过，一个条目都不动。
 *   · `location.hash = id`：与第一条同因 —— 路由接走 → 404（实测）。
 *
 * 【成立的写法】把"滚动"和"地址栏"分开，而且**两者都不许惊动路由**：
 *   ① 滚动：`scrollIntoView`。滚动容器是谁、`scroll-margin-top` 多少，全归浏览器管，
 *      与"把地址贴给别人"时用的是同一条规则。
 *   ② 地址栏：`history.replaceState`，把锚点**追加在路由 fragment 后面**
 *      （`#/report?as=mid` → `#/report?as=mid#report-market`）。
 *      这一条同时满足三件事，逐条都实测过：
 *        · replaceState **不派发 popstate / hashchange** → vue-router 不知道这件事、
 *          不会把锚点当路由去解析（实测：12 次点击，`router.afterEach` 一次都没触发，
 *          页面始终停在 /report）；
 *        · `location.hash` 里看得见锚点（`hash.includes('report-market')` 为真）；
 *        · **路由还在 URL 里**，所以刷新后按 `#/report?as=mid#report-market` 打开
 *          能正确回到报告页（实测 hasToc=true、四个分组 id 都在）。
 *          只写 `#report-market` 的那种方案刷新会掉进 404（实测 urlB 的 h1 是
 *          「这个地址不存在」）—— 这是这一步唯一必须"多拼一截"的理由。
 *      为什么先剥掉已有的第二段 `#`：连点两条 toc 时不能再叠一层。
 * ==========================================================================*/
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
async function printReport() {
  printing.value = true
  await nextTick()
  window.print()
  /* 【2026-10-14 · wave4】"还原"这一步必须留在这里，不能只靠事件。
     实测：`emulateMedia({media:'print'})` 下 beforeprint/afterprint **一次都不派发**，
     真机上也有浏览器（老 WebKit）在"用户取消打印"时不派发 afterprint。
     那条路径上 `printing` 会一直停在 true（`Foldable :force-open` 把折叠全撑开），
     屏幕状态就被打印弄乱了。所以这里同步落一次 printMedia —— 它是唯一真相源，
     `printing` 由 watch(printMedia) 派生；afterprint 到了也只是把同一格再写一遍。 */
  printMedia.value = window.matchMedia('print').matches
  printing.value = false
}
/* 【2026-10-14 · wave4】原来的 `beforePrint` / `afterPrint` 两个函数已经并进
   `printMedia` 那一套（见下面"打印必须按默认轴"段）：`printing` 由 `watch(printMedia)`
   派生，不再有两处各自写 `printing` 的状态 —— 两份状态一定会漂。 */
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
const printMedia = ref(false)
let printQuery: MediaQueryList | null = null
function onPrintMediaChange(event: MediaQueryListEvent) { printMedia.value = event.matches }
function onBeforePrintMedia() { printMedia.value = true }
function onAfterPrintMedia() { printMedia.value = false }
onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  printQuery = window.matchMedia('print')
  printMedia.value = printQuery.matches
  printQuery.addEventListener('change', onPrintMediaChange)
  window.addEventListener('beforeprint', onBeforePrintMedia)
  window.addEventListener('afterprint', onAfterPrintMedia)
})
onUnmounted(() => {
  printQuery?.removeEventListener('change', onPrintMediaChange)
  window.removeEventListener('beforeprint', onBeforePrintMedia)
  window.removeEventListener('afterprint', onAfterPrintMedia)
  printQuery = null
})
const printAxis = computed(() => 'section')

type ReportItem = ReportDimension & { sectionKey: string; sectionTitle: string }

/** 9 个维度摊平，每条带上它原来的分区 —— 换轴之后仍然要能说清"它原来在哪" */
const allDimensions = computed<ReportItem[]>(() =>
  REPORT_SECTIONS.flatMap((s) => s.dimensions.map((d) => ({ ...d, sectionKey: s.key, sectionTitle: s.title }))),
)

const reportGroups = computed(() => REPORT_SECTIONS.map(section => ({ key: section.key, title: section.title, note: null, items: allDimensions.value.filter(item => item.sectionKey === section.key) })))

const axisPrefix = computed(() => (printAxis.value === 'section' ? 'report-' : `report-${printAxis.value}-`))
function anchorOf(key: string): string {
  return axisPrefix.value + key
}
/* `printing`（方向页的 Foldable `:force-open`）与 printMedia 同源：
   真机靠 beforeprint/afterprint，emulateMedia 靠 media 的 change。
   两处都写同一个 ref，不另开一份状态 —— 两份状态一定会漂。 */
watch(printMedia, (on) => { printing.value = on })
</script>
<template>
<div class="ws-page assessment-page" :class="{'directions-page':view==='directions', 'c2-report-layout':view==='summary'}"><PageHeading :title="view==='directions'?'方向方案':'诊断报告'" :description="view==='directions'?'把支持依据和风险放在一起比较，再确认你的选择。':'先看关键判断，再逐项核对支持依据。'"><button v-if="view!=='directions'" class="btn" :disabled="reportLoading" @click="loadFullReport">{{ reportLoading?'正在读取…':'获取完整报告' }}</button><button v-if="view==='directions'" class="btn" :disabled="directionLoading||directionSaving" @click="loadDirections">{{ directionLoading?'正在读取…':'获取最新方案' }}</button><button v-if="view!=='directions'&&available" class="btn" @click="changeView(view==='versions'?'summary':'versions')">{{ view==='versions'?'返回当前报告':'历史版本' }}</button><button v-if="available" class="btn" @click="printReport">打印 / 保存 PDF</button></PageHeading>

<AssetNotice v-if="!fullReport&&!reportMetadata"/><template v-if="fullReport"><div class="report-status"><StatTile :label="reportStatusLabel" :value="reportStatusValue" unit="版" :state="recomputeState(reportMetadata)"/><p class="ws-muted" :class="{ 'ws-attention': reportMetadata?.needs_recompute }">{{ reportStatusNote }}</p><StatusBanner v-if="reportMetadata?.needs_recompute" tone="warning" title="这版报告待更新" message="依据已有变化，当前正文仍是原版本。请核对新的个人信息后，通过咨询更新报告。" action-label="核对完整版本记录" @action="changeView('versions')"/><p v-else class="ws-muted">正文版本、生成时间和来源如下；可在版本记录中核对依赖与变化。</p></div></template><p v-if="directionError&&!latestDirections" class="ws-field-error" role="alert">{{ directionError }}</p><p v-if="reportError" class="ws-field-error" role="alert">{{ reportError }}</p><SkeletonBlock v-if="reportLoading&&!available" variant="text" :lines="6" /><EmptyState v-else-if="!available&&!reportLoading" kind="report" :heading-level="2" :title="view==='directions'?'方向方案还没有形成':'报告还没有生成'" description="完成咨询并补充必要信息后，再查看相应结果。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><button class="ws-text-button" @click="backendDemo.loadAssessmentSample()">查看{{ view==='directions'?'方向':'报告' }}示例</button></EmptyState>
<template v-else><FullReportBody v-if="view==='summary'&&fullReport" :report="fullReport"/><template v-else-if="view==='summary'">
<section class="c2-report-verdicts report-overview"><div class="ws-section-head"><h2>当前诊断</h2><DetailPopover title="完整诊断概述" label="查看完整诊断概述"><p>{{ REPORT_SUMMARY }}</p></DetailPopover></div>
<div class="diagnosis-visual"><div class="diagnosis-visual__message"><span class="diagnosis-visual__symbol"><UiIcon name="report" :size="28"/></span><h2>项目经历与表达<br/>仍需完善</h2><p>当前优先完善项目表达，补充实践证据。</p><RouterLink class="btn btn--primary" to="/home">查看建议行动<UiIcon name="arrow" :size="16"/></RouterLink></div><div class="diagnosis-visual__scores"><div class="diagnosis-key"><span><i/>当前评分</span><span><i/>方向要求</span></div><div v-for="item in THRESHOLD_COMPARE" :key="item.label" class="diagnosis-measure"><div><strong>{{ item.label }}</strong><span>{{ item.mine < item.requirement ? '待提升 '+(item.requirement-item.mine)+' 分' : '已达本版要求' }}</span></div><div class="diagnosis-track" :aria-label="item.label+'：当前'+item.mine+'分，方向要求'+item.requirement+'分'"><i :style="{width:item.mine+'%'}"/><b :style="{left:item.requirement+'%'}"/></div><small>当前 {{ item.mine }}<span>要求 {{ item.requirement }}</span></small></div></div></div>
<div class="diagnosis-findings"><button v-for="verdict in reportVerdicts" :key="verdict.key" class="diagnosis-finding" :class="'diagnosis-finding--'+verdict.key" @click="chooseEvidence(verdict.key)"><span class="diagnosis-finding__type">{{ verdict.key==='expression'?'优先行动':verdict.key==='supply'?'待核实':'选择条件' }}</span><span><strong>{{ verdict.title }}</strong><small>{{ verdict.detail }}</small></span><span class="diagnosis-finding__link">{{ verdict.key==='expression'?'核对能力差距':verdict.key==='supply'?'核对资讯来源':'查看决策条件' }}<UiIcon name="arrow" :size="16"/></span></button></div></section>
<section class="report-reading-index"><div class="ws-section-head"><h2>报告分析</h2><button class="ws-text-button" @click="chartDetails=true">能力与门槛对照<UiIcon name="arrow" :size="16"/></button></div><button v-for="g in reportGroups" :key="g.key" class="information-entry" @click="activeChapter=g.key;evidenceSection='';reportDetails=true"><span><strong>{{ g.title }}</strong><small>{{ g.items.length }} 项分析 · {{ g.items[0]?.label }}</small></span><UiIcon name="arrow" :size="18"/></button></section>
<InfoSheet :open="reportDetails" shape="panel" :title="activeChapter ? reportGroups.find(g=>g.key===activeChapter)?.title ?? '报告依据' : reportVerdicts.find(v=>v.key===evidenceSection)?.title ?? '报告依据'" @close="reportDetails=false"><section v-for="g in reportGroups.filter(group => !activeChapter || group.key === activeChapter)" :key="g.key" :id="anchorOf(g.key)" class="report-chapter"><h2>{{ g.title }}<span class="report-chapter__count">{{ g.items.length }} 项</span></h2><p v-if="g.note" class="report-chapter__note">{{ g.note }}</p><article v-for="d in g.items.filter(item => !evidenceSection || evidenceHit(item.key))" :key="d.key" class="report-dimension" :class="{'c2-dimension--active':evidenceHit(d.key),'c2-dimension--dim':evidenceSection && !evidenceHit(d.key)}"><div class="ws-section-head"><h3>{{ d.label }}</h3><ConfidenceBadge :value="d.confidence"/></div><p>{{ d.conclusion }}</p><p v-if="printAxis!=='section'" class="report-dimension__from">原本在「{{ d.sectionTitle }}」</p><DetailPopover :title="d.label + ' · 分值与依据'" :label="'查看' + d.label + '分值与依据'"><template #trigger>分值与依据 <span>{{ dimensionCount(d) }}</span><UiIcon name="info" :size="16"/></template><p v-if="d.threshold">{{ d.threshold }}</p><MeterRow v-if="d.score!=null" :label="d.label" :value="d.score/100" :requirement="d.key==='present'?0.5:undefined" :format="formatScore01"/><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul></DetailPopover></article></section></InfoSheet>
<InfoSheet :open="chartDetails" shape="panel" title="能力与门槛对照" @close="chartDetails=false"><Foldable static :title-level="2" class="report-block" title="能力画像与门槛对照"><div class="ws-chart-grid"><div><RadarChart :axes="SELF_RADAR" :size="300" :baseline="50"/><p class="ws-muted">自评与方向要求使用同一刻度；虚线为50分参考线。</p></div><div class="ws-stack"><MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :value="d.mine/100" :requirement="d.requirement/100" :format="formatScore01"/></div></div></Foldable></InfoSheet><div class="information-print-only"><section v-for="g in reportGroups" :key="g.key" :id="'print-'+anchorOf(g.key)" class="report-chapter"><h2>{{ g.title }}<span class="report-chapter__count">{{ g.items.length }} 项</span></h2><p v-if="g.note" class="report-chapter__note">{{ g.note }}</p><article v-for="d in g.items" :key="d.key" class="report-dimension" :class="{'c2-dimension--active':evidenceHit(d.key),'c2-dimension--dim':evidenceSection && !evidenceHit(d.key)}"><div class="ws-section-head"><h3>{{ d.label }}</h3><ConfidenceBadge :value="d.confidence"/></div><p>{{ d.conclusion }}</p><p v-if="printAxis!=='section'" class="report-dimension__from">原本在「{{ d.sectionTitle }}」</p><DetailPopover :title="d.label + ' · 分值与依据'" :label="'查看' + d.label + '分值与依据'"><template #trigger>分值与依据 <span>{{ dimensionCount(d) }}</span><UiIcon name="info" :size="16"/></template><p v-if="d.threshold">{{ d.threshold }}</p><MeterRow v-if="d.score!=null" :label="d.label" :value="d.score/100" :requirement="d.key==='present'?0.5:undefined" :format="formatScore01"/><ul><li v-for="e in d.evidence" :key="e">{{ e }}</li></ul></DetailPopover></article></section><Foldable static :title-level="2" class="report-block" title="能力画像与门槛对照"><div class="ws-chart-grid"><div><RadarChart :axes="SELF_RADAR" :size="300" :baseline="50"/><p class="ws-muted">自评与方向要求使用同一刻度；虚线为50分参考线。</p></div><div class="ws-stack"><MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :value="d.mine/100" :requirement="d.requirement/100" :format="formatScore01"/></div></div></Foldable></div><section id="report-full" class="report-chapter reading-prose information-print-only"><h2>完整结论</h2><p>{{ REPORT_SUMMARY }}</p></section></template>
<template v-else-if="view==='directions'&&latestDirections"><DirectionDetails :plans="latestDirections" :saving="directionSaving||directionLoading" :error="directionError" @select="selectLatest"/></template><template v-else-if="view==='directions'"><DirectionCompare :items="DIRECTION_PLANS" :selected-id="candidate" @pick="candidate=$event"/>
<section class="direction-confirm"><div><h2>{{ pendingDirection ? pendingDirection.title : '比较后再确认' }}</h2><p>{{ candidate===selected?.id?'当前方向已确认，仍可选择其他方向。':pendingDirection?'确认后显示关联内容；已有执行记录保留。':'选择一个候选方向，确认后加入当前计划。' }}</p></div><button class="btn btn--primary" :disabled="!candidate||candidate===selected?.id" @click="demo.chooseDirection(candidate)">确认方向<UiIcon name="check" :size="16"/></button></section>
<Foldable title="机会与门槛示意" :force-open="printing"><p class="ws-muted">两轴坐标为预置示意，不代表真实岗位数量或计算结果。点选只改变候选方向。</p><QuadrantChart :items="quadrants" :selected-id="candidate" @pick="candidate=$event"/></Foldable>
<section v-if="selected" class="direction-impact" role="status"><h2>{{ previous?'方向选择已更新':'当前选择已确认' }}</h2><p>{{ previous?'从「'+previous.title+'」改选为「'+selected.title+'」。':selected.title }}</p><p>关联{{ selected.ripple }}处内容；关联范围已列出，报告与计划需要补齐依据后再更新。</p><Foldable title="查看关联内容" variant="inline" :default-open="demo.state.rippleOpen" :force-open="printing"><ul><li v-for="p in selected.ripplePoints" :key="p">{{ p }}</li></ul></Foldable><RouterLink class="ws-text-link" to="/plan">查看阶段计划<UiIcon name="arrow" :size="16"/></RouterLink></section></template>
<section v-else class="report-versions"><ReportHistory @open="openHistorical"/><header class="ws-section-head"><h2>{{ version.label }} · {{ version.at }}</h2></header><p>{{ version.change }}</p><div class="ws-chart-grid ws-section"><TrendLine :points="trend" :highlight-index="REPORT_VERSIONS.length-1-REPORT_VERSIONS.findIndex(v=>v.id===version.id)"/><p class="ws-muted">第1–3版为预置匹配度快照。详细正文使用第3版，历史摘要不代表完整旧版报告。</p></div><article v-for="v in REPORT_VERSIONS" :key="v.id" class="ws-version-row"><button class="ws-text-button" :aria-pressed="demo.state.reportVersion===v.id" @click="demo.setReportVersion(v.id)">{{ v.label }} · 查看版本摘要</button><p>{{ v.change }}</p><time>{{ v.at }}</time></article></section></template><aside v-if="view==='summary' && available" class="c2-report-side report-next-rail" aria-label="诊断依据与下一步"><section><span class="report-next-symbol"><UiIcon name="action" :size="24"/></span><h2>接下来，完善经历</h2><p>补充具体行动、使用的方法与实际结果。</p><RouterLink class="btn" to="/chat?topic=实践经历">和顾问一起完善<UiIcon name="arrow" :size="16"/></RouterLink></section><section><h2>报告更新状态</h2><p>{{ reportMetadata ? reportMetadata.needs_recompute ? '依据已有变化，请核对最新资料。' : '已取得本版更新状态。' : '本版状态尚未取得，请核对来源与资料。' }}</p><button class="ws-text-button" @click="reportBasisOpen=true">报告依据与更新<UiIcon name="info" :size="16"/></button></section></aside><InfoSheet :open="reportBasisOpen" shape="panel" title="报告依据与更新" @close="reportBasisOpen=false"><section><h2>报告依据</h2><h3>办法</h3><p>把兴趣与经历交叉核对，再与目标岗位要求逐项比较。资料不足的地方保留待确认。</p><h3>来源</h3><p>咨询记录、学籍与资料、岗位要求笔记。每一项结论都能展开查看原始依据。</p><p class="c2-report-note">评分用于方向比较。资料变化后保留旧版依据，可通过页头读取最新报告。</p></section><section class="c2-report-recheck"><h2>{{ backendDemo.state.dataMode==='demo'?'有两条要核对最新来源':'核对报告更新状态' }}</h2><p>岗位供给和时间取舍仍使用本版的依据。原始判断与数字保留，不因点按钮自动变成新结果。</p><p v-if="backendDemo.state.reportReviewRequested" role="status">已标记为待更新。请通过咨询补齐资料，再核对最新报告。</p><button v-else class="btn" @click="backendDemo.requestReportReview()">标记为待更新</button><RouterLink class="ws-text-link" to="/chat?topic=核对报告依据">补齐依据并继续咨询 →</RouterLink></section><section><h2>建议优先补充</h2><p>补充经历中的具体行动和结果，核对它与目标岗位的关联。</p><RouterLink class="btn" to="/chat?topic=实践经历">和顾问聊聊</RouterLink><RouterLink class="ws-text-link" to="/profile">核对画像来源</RouterLink></section></InfoSheet><p v-if="view!=='summary'" class="ws-demo-note">当前内容来自本次读取的数据。版本、来源和选择均按返回结果展示；资料变化后请核对更新状态。</p></div>
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

/* toc 里那一格条数。toc 常驻之后，三条轴的分组名不一样、条数也不一样 ——
   把条数摆在条目上是"点进去之后会看到什么"的预告（与分组头的徽标同一门编号语言，
   但类名不同：这条是"toc 条目上的计数"，将来分开改时不该互相牵制）。
   toc 本体（.report-toc）在 redesign.css，是全局零件，这里不重新声明它。 */
.report-toc__count {
  margin-left: var(--sp-2);
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
}

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
