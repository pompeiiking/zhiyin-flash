<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { backendClient, BackendError } from '../api/backend-client'
import { downloadExport } from '../api/student-capabilities'
import { backendDemo } from '../lib/backend-demo'
import type { ReportFullTextView, AssetVersionView, WorkspacePageView } from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import ActionMenu from '../components/ActionMenu.vue'
import FullReportBody from '../components/FullReportBody.vue'
import ReportHistory from '../components/ReportHistory.vue'
import AssetNotice from '../components/AssetNotice.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { studentVoice } from '../lib/student-voice'
import { formatDateTime } from '../lib/format'

const regenerateTarget = {path: '/chat', query: {ask: '请根据我最新的资料重新生成诊断报告。先给我看新版，等我确认后再替换当前报告，并保留历史版本。'}}
const route = useRoute()
const router = useRouter()
const busy = ref(false)
const error = ref('')
const history = computed(() => route.query.focus === 'versions' || route.query.view === 'versions')
function setHistory(open: boolean) { const query = {...route.query}; delete query.focus; if(open) query.view='versions'; else delete query.view; void router.replace({query}) }
const viewedReport = ref<ReportFullTextView | null>(null)
const viewedMetadata = ref<AssetVersionView | null>(null)
const profileError = ref('')
const versionError = ref('')
const report = computed(() => viewedReport.value)
const workspace = ref<WorkspacePageView | null>(null)
const reportItems = computed(() => report.value?.sections?.flatMap((section) => section.items ?? []) ?? [])
const pendingCount = computed(() => reportItems.value.filter((item) => !item.evidence?.trim() || /待|缺|不足|未知/.test(item.tag || '')).length)
/**
 * 【#14】产品承诺最多 15 个分析维度，但有证据的维度才展开，提示词明确禁止"凑满 15 维"。
 * 所以这里如实展示覆盖度：有证据的维度 / 15（其余待补充），不再承诺"15 项判断"。
 * 如果后端 full-text 已经把目录列到 15 个节点，就按"目录节点里有内容可读的"计数。
 */
const promisedDimensionTotal = computed(() => Math.max(15, report.value?.toc?.length ?? 0))
const evidencedDimensionCount = computed(() => {
  const items = reportItems.value
  const toc = report.value?.toc ?? []
  if (toc.length >= 15) {
    const titled = new Set(
      [...(report.value?.sections ?? []).map((section) => section.title), ...items.map((item) => item.name)]
        .filter(Boolean)
        .map((value) => String(value).trim()),
    )
    const covered = toc.filter((node) => titled.has(String(node.title ?? '').trim())).length
    return covered || items.length
  }
  return items.length
})
const pendingDimensionCount = computed(() => Math.max(0, promisedDimensionTotal.value - evidencedDimensionCount.value))
const exportStatus = ref('')
const latestVersion = computed(() => backendDemo.state.liveReport?.version ?? null)
const historicalView = computed(() => !!report.value && latestVersion.value !== null && report.value.version !== latestVersion.value)
const reportState = computed(() => {
  if (historicalView.value) return '历史版本'
  if (!viewedMetadata.value) return '更新状态未知'
  return viewedMetadata.value.needs_recompute ? '待重新核对' : '当前版本'
})

function reportText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(reportText).filter(Boolean).join('；')
  if (typeof value === 'object') return Object.values(value).map(reportText).filter(Boolean).join('；')
  return String(value)
}
const reportDate = (value: string) => formatDateTime(value) || '未记录时间'

let loadSerial = 0
async function load() {
  if (busy.value) return
  const serial = ++loadSerial
  busy.value = true
  error.value = ''
  profileError.value = ''
  versionError.value = ''
  try {
    // Report body and version metadata are independent reads. A version-list
    // failure must not discard a report that already loaded successfully.
    const [reportResult, versionsResult, workspaceResult] = await Promise.allSettled([
      backendClient.report(),
      backendClient.versions('report'),
      backendClient.workspace(),
    ])
    if (serial !== loadSerial) return
    if (workspaceResult.status === 'fulfilled') {
      backendDemo.setWorkspace(workspaceResult.value); workspace.value = workspaceResult.value
    } else if (!workspace.value) {
      profileError.value = '个人档案暂时没有读取到，诊断正文仍可继续查看。'
    }
    if (reportResult.status === 'rejected') {
      const caught = reportResult.reason
      if (!(caught instanceof BackendError && caught.code === 1002)) error.value = (caught as Error).message
      viewedReport.value = null
      viewedMetadata.value = null
      backendDemo.setReportMetadata(null)
      return
    }
    const current = reportResult.value
    let metadata: AssetVersionView | null = null
    if (versionsResult.status === 'fulfilled' && Array.isArray(versionsResult.value)) {
      metadata = versionsResult.value.find((item) => item.version === current.version) ?? null
      if (!metadata && current.version > 0) {
        versionError.value = '版本记录里没有这份报告的状态，暂时无法判断是否需要重新核对。'
      }
    } else {
      versionError.value = '版本状态暂时没有读取到；报告正文仍可查看，但无法确认它是否已过期。'
    }
    backendDemo.setReport(current)
    backendDemo.setReportMetadata(metadata)
    viewedReport.value = current.version > 0 || metadata ? current : null
    viewedMetadata.value = metadata
  } finally { if (serial === loadSerial) busy.value = false }
}
function printReport() { window.print() }
const exporting = ref(false)
const moreActions = computed(() => [
  { id: 'refresh', label: historicalView.value ? '回到最新版' : '刷新报告', disabled: busy.value },
  { id: 'export', label: '导出 PDF', disabled: busy.value || exporting.value || !report.value },
  { id: 'print', label: '打印报告' },
])
function selectMore(id: string) {
  if (id === 'refresh') void load()
  else if (id === 'export') void exportReport()
  else if (id === 'print') printReport()
}
/**
 * 报告导出走服务端文档生成（PDF），与「个人画像」「单项成果」同一条链路。
 * 此前这里是浏览器端拼 JSON：普通用户拿到的是接口数据，且导出入口与功能开关
 * 各说各话（开关关着时其它入口 403，这个入口却照样下载）。
 */
async function exportReport() {
  const current = report.value
  if (!current) { exportStatus.value = '先生成报告后才能导出。'; return }
  if (exporting.value) return
  exporting.value = true
  exportStatus.value = ''
  try {
    const result = await backendClient.exportAsset('report', 'pdf')
    if (!result.available || !result.object_key) {
      throw new Error(result.message || '导出暂时不可用，请稍后重试。')
    }
    await downloadExport(result.object_key, `职引-诊断报告-第${current.version}版.pdf`)
    exportStatus.value = `报告已导出为 PDF（第 ${current.version} 版）。`
  } catch (error) {
    exportStatus.value = error instanceof Error ? error.message : '导出失败，请稍后重试。'
  } finally {
    exporting.value = false
  }
}
function historical(document: ReportFullTextView, metadata: AssetVersionView | null) { viewedReport.value = document; viewedMetadata.value = metadata; setHistory(false) }
onMounted(load)
</script>

<template>
  <div class="ws-page report-page" :aria-busy="busy">
    <p class="sr-only" role="status" aria-live="polite">{{ busy ? '正在读取报告…' : '' }}</p>
    <PageHeading title="你的报告" description="先看判断、差距和下一步；需要时再点开依据与资料。">
      <RouterLink v-if="!history && report" class="btn btn--primary" :to="regenerateTarget">重新生成报告</RouterLink>
      <button v-if="history" class="btn" @click="setHistory(false)">返回报告</button>
      <template v-else-if="report">
        <button class="ws-text-button" @click="setHistory(true)">版本记录</button>
        <ActionMenu label="更多报告操作" :items="moreActions" @select="selectMore" />
      </template>
    </PageHeading>

    <AssetNotice />
    <p v-if="!history" class="ws-muted">{{ historicalView ? '重新生成会使用最新资料，当前查看的历史版本会保留。' : '在对话中生成新版，确认后再更新正式报告。' }}</p>
    <StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load" />
    <StatusBanner v-if="versionError" tone="info" :message="versionError" retry-label="重新读取版本" @retry="load" />
    <StatusBanner v-if="exportStatus" tone="info" :message="exportStatus" @dismiss="exportStatus = ''" />
    <SkeletonBlock v-if="busy" variant="list" :lines="4" />
    <ReportHistory v-if="history" asset-type="report" @open="historical" />

    <div v-else-if="report" class="report-article-shell">
      <div class="report-masthead-grid">
        <header class="report-masthead" :class="{ 'report-masthead--attention': viewedMetadata?.needs_recompute, 'report-masthead--historical': historicalView }">
          <div class="report-cover__topline"><span>职引 · 个人发展诊断</span><strong>{{ reportState }}</strong></div>
          <div class="report-cover__title">
            <div><p>Personal development assessment</p><h2>个人发展诊断报告</h2></div>
            <div class="report-cover__edition"><span>REPORT</span><strong>V{{ report.version }}</strong></div>
          </div>
          <p class="report-cover__verdict">{{ studentVoice(reportText(report.verdict)) || '本版暂未提供总体判断。' }}</p>
          <div class="report-cover__footer">
            <div><span>形成时间</span><time :datetime="report.generated_at">{{ reportDate(report.generated_at) }}</time></div>
            <div><span>诊断覆盖</span><strong>{{ evidencedDimensionCount }} / {{ promisedDimensionTotal }} 维</strong></div>
            <div><span>待验证</span><strong>{{ pendingCount }} 项</strong></div>
          </div>
        </header>
      </div>

      <FullReportBody :key="`report-${report.version}-${historicalView ? 'history' : 'latest'}`" :report="report" :workspace="workspace" :profile-error="profileError" :allow-ai-summary="!historicalView">
        <footer class="report-reading-footer">
          <section class="report-next-step">
            <h2>报告需要更新时</h2>
            <p>先核对个人资料，再带着发生的变化继续咨询。新版报告会另存为新版本，不覆盖这里的阅读记录。</p>
            <p v-if="pendingDimensionCount > 0" class="report-coverage-note">本次有证据的维度 {{ evidencedDimensionCount }} / {{ promisedDimensionTotal }}，其余 {{ pendingDimensionCount }} 维待补充。报告只展开有证据的维度，不为了凑满而编内容；补充资料或继续咨询后重新生成，新版会把新增的维度展开。</p>
            <div><RouterLink class="btn btn--primary" to="/chat?topic=更新报告">带着变化继续咨询</RouterLink><RouterLink class="ws-text-link" to="/profile">核对个人画像</RouterLink></div>
          </section>
        </footer>
      </FullReportBody>
    </div>

    <EmptyState v-else-if="!busy && !error" kind="report" :heading-level="2" title="尚未生成报告" description="根据已有资料生成报告草稿，确认后保存在这里。资料不足时会说明限制，不编造结论。">
      <template #body>
        <div class="report-empty-outline" aria-label="报告将包含的内容">
          <div><span>结论</span><strong>一句话判断与把握程度</strong></div>
          <div><span>15 个维度</span><strong>自我画像、职业环境、决策风险</strong></div>
          <div><span>依据</span><strong>每条判断都能回看资料</strong></div>
        </div>
      </template>
      <div class="report-empty-actions"><RouterLink class="btn btn--primary" :to="regenerateTarget">生成报告</RouterLink><RouterLink class="ws-text-link" to="/chat">继续咨询</RouterLink></div>
    </EmptyState>
  </div>
</template>

<style scoped>
.report-article-shell{width:100%;max-width:860px;margin:20px auto 42px;border:1px solid var(--c-border-strong);border-top: 1px solid var(--c-primary);background:var(--c-surface);box-shadow:var(--e-2)}.report-masthead-grid{display:grid;grid-template-columns:minmax(0,760px) 44px;justify-content:center;gap:54px}.report-masthead{grid-column:1 / -1;position:relative;margin:0;padding:34px 38px 42px;border:0;border-bottom:1px solid var(--c-border);background:var(--c-surface);font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",STSong,"SimSun",serif}.report-masthead--attention{box-shadow:inset 4px 0 0 var(--c-attention)}.report-cover__topline{display:flex;align-items:center;justify-content:space-between;gap:18px;padding-bottom:16px;border-bottom:1px solid var(--c-border);color:var(--c-text-2);font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:12px}.report-cover__topline strong{color:var(--c-primary);font-weight:650}.report-masthead--attention .report-cover__topline strong{color:var(--c-attention-strong)}.report-masthead--historical .report-cover__topline strong{color:var(--c-text-2)}.report-cover__title{display:flex;align-items:end;justify-content:space-between;gap:26px;padding:44px 0 36px}.report-cover__title p{margin-bottom:8px;color:var(--c-text-3);font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-12);letter-spacing:.08em;text-transform:uppercase}.report-cover__title h2{font-size:clamp(36px,5vw,54px);font-weight:700;line-height:1.12;letter-spacing:.04em}.report-cover__edition{flex:none;width:92px;padding-left:18px;border-left:1px solid var(--c-border-strong);font-family:var(--font-sans,"Microsoft YaHei",sans-serif)}.report-cover__edition span{display:block;color:var(--c-text-3);font-size:var(--fs-12);letter-spacing:.08em}.report-cover__edition strong{display:block;margin-top:4px;color:var(--c-primary);font-size:26px;line-height:1}.report-cover__verdict{max-width:29em;margin:0 0 42px;padding-left:20px;border-left: 1px solid var(--c-primary);font-size:22px;font-weight:600;line-height:1.8}.report-cover__footer{display:grid;grid-template-columns:1.6fr .8fr .7fr;gap:0;border-top:1px solid var(--c-border-strong);font-family:var(--font-sans,"Microsoft YaHei",sans-serif)}.report-cover__footer>div{padding:16px 14px 0 0}.report-cover__footer>div+div{padding-left:14px;border-left:1px solid var(--c-border)}.report-cover__footer span{display:block;margin-bottom:5px;color:var(--c-text-3);font-size:var(--fs-12)}.report-cover__footer strong,.report-cover__footer time{display:block;color:var(--c-text);font-size:12px;font-weight:600;line-height:1.55}.report-reading-footer{padding:58px 0 20px;border-top:1px solid var(--c-border)}.report-reading-footer h2{margin-bottom:12px;font-size:var(--fs-18)}.report-next-step p{max-width:58ch;color:var(--c-text-2);font-size:var(--fs-14);line-height:1.8}.report-next-step>div{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin-top:18px}
.report-coverage-note{margin-top:12px;padding:12px 14px;border-left:1px solid var(--c-primary-border);border-radius:0 10px 10px 0;background:var(--c-primary-weak-2);color:var(--c-text-2);font-size:var(--fs-13)!important;line-height:1.75!important}
.report-empty-outline{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;width:min(680px,100%);margin:22px 0 18px;text-align:left}
.report-empty-outline>div{display:grid;gap:5px;padding:14px;border:1px solid var(--c-border);border-radius:12px;background:var(--c-surface-2)}
.report-empty-outline span{color:var(--c-text-3);font-size:var(--fs-12)}
.report-empty-outline strong{color:var(--c-text);font-size:var(--fs-14);line-height:1.6}
.report-empty-actions{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px 16px}
@media(max-width:640px){.report-empty-outline{grid-template-columns:minmax(0,1fr)}}
@media(max-width:980px){.report-masthead-grid{grid-template-columns:minmax(0,1fr) 44px;gap:20px}}
@media(max-width:767px){.report-article-shell{margin:12px auto 28px;border-right:0;border-left:0;box-shadow:none}.report-masthead-grid{display:block}.report-masthead{padding:24px 20px 30px}.report-cover__title{align-items:flex-start;padding:32px 0 26px}.report-cover__title h2{font-size:34px;letter-spacing:.02em}.report-cover__edition{width:66px;padding-left:12px}.report-cover__edition strong{font-size:21px}.report-cover__verdict{margin-bottom:30px;padding-left:14px;font-size:19px;line-height:1.75}.report-cover__footer{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 0}.report-cover__footer>div:nth-child(3){padding-left:0;border-left:0}.report-reading-footer{padding-top:42px}}
@media(max-width:480px){.report-cover__title{flex-direction:column;align-items:flex-start;gap:12px}.report-cover__edition{display:flex;align-items:baseline;gap:8px;width:auto;padding-left:0;border-left:0}.report-page :deep(.ws-heading__actions){display:flex;flex-wrap:wrap;align-items:center;gap:6px}.report-page :deep(.ws-heading__actions .btn),.report-page :deep(.ws-heading__actions .ws-text-button){flex:none;width:auto;justify-content:center;white-space:nowrap}}
@media(max-width:360px){
 .report-page :deep(.ws-heading__actions){display:grid;grid-template-columns:1fr auto;gap:8px}
 .report-page :deep(.ws-heading__actions)>:first-child{grid-column:1 / -1;width:100%;justify-content:center}
}
.report-cover__verdict{overflow-wrap:anywhere}
@media print{.report-page :deep(button),.report-page :deep(.direction-radio),.report-page :deep(select),.report-reading-footer{display:none!important}.report-masthead-grid{display:block}.report-masthead{padding-bottom:30px}}
</style>
