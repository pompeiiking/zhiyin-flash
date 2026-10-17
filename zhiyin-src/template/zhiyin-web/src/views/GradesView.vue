<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { backendClient } from '../api/backend-client'
import type { PortraitAnalysis } from '../api/ai-types'
import type { AcademicGradeView } from '../api/backend-types'
import AcademicImportSheet from '../components/AcademicImportSheet.vue'
import AiResultMeta from '../components/AiResultMeta.vue'
import AiStatus from '../components/AiStatus.vue'
import EmptyState from '../components/EmptyState.vue'
import InfoSheet from '../components/InfoSheet.vue'
import PageHeading from '../components/PageHeading.vue'
import ReadableText from '../components/ReadableText.vue'
import StatusBanner from '../components/StatusBanner.vue'
import UiIcon from '../components/UiIcon.vue'
import DetailPopover from '../components/DetailPopover.vue'
import { backendDemo } from '../lib/backend-demo'
import { useAiTask } from '../lib/use-ai-task'

type GradeGroup = { term: string; rows: AcademicGradeView[] }
type ChartMetric = 'score' | 'point'
type AnalysisView = 'trend' | 'courses'

const academic = computed(() => backendDemo.state.academic)
const grades = computed(() => academic.value?.grades ?? [])
const importOpen = ref(false)
const revokeOpen = ref(false)
const loading = ref(false)
const status = ref('')
const error = ref('')
const selectedTerm = ref('all')
const analysisTerm = ref('all')
const analysisKind = ref('all')
const analysisMetric = ref<ChartMetric>('score')
const analysisView = ref<AnalysisView>('trend')
const learningAnalysis = useAiTask<PortraitAnalysis>()
const analysisSerial = ref(-1)
const analysisStale = computed(() => !!learningAnalysis.result.value && analysisSerial.value !== backendDemo.state.profileEditSerial)
let analysisScrollTop: number | null = null

function analysisScroller() {
  return document.querySelector<HTMLElement>('.app__main')
}

function rememberAnalysisScroll() {
  const scroller = analysisScroller()
  if (scroller) analysisScrollTop = scroller.scrollTop
}

function restoreAnalysisScroll() {
  const top = analysisScrollTop
  analysisScrollTop = null
  if (top === null) return
  void nextTick(() => {
    requestAnimationFrame(() => {
      const scroller = analysisScroller()
      if (scroller) scroller.scrollTop = top
    })
  })
}

function selectAnalysisMetric(metric: ChartMetric) {
  analysisMetric.value = metric
  restoreAnalysisScroll()
}

function parseNumber(value?: string) {
  if (!value?.trim()) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function termSortKey(term: string) {
  const years = term.match(/(20\d{2}).*?(20\d{2})/)
  const firstYear = Number(years?.[1] ?? term.match(/20\d{2}/)?.[0] ?? 0)
  const semester = Number(term.match(/(?:-|第)?([12])(?:学期)?\s*$/)?.[1] ?? 0)
  return firstYear * 10 + semester
}

function gradeTerm(row: AcademicGradeView) {
  return row.term?.trim() || academic.value?.term?.trim() || '未标注学期'
}

function courseKind(row: AcademicGradeView) {
  const labels = [row.kind?.trim(), row.category?.trim()].filter((label): label is string => !!label)
  return [...new Set(labels)].join(' · ') || '未标注'
}

function formatTerm(term: string) {
  const parsed = term.match(/(20\d{2})\s*[-—至/]\s*(20\d{2}).*?([12])\s*$/)
  if (!parsed) return term
  return `${parsed[1]}-${parsed[2]}学年 · ${parsed[3] === '1' ? '秋学期' : '春学期'}`
}

function shortTerm(term: string) {
  const parsed = term.match(/(20\d{2})\s*[-—至/]\s*(20\d{2}).*?([12])\s*$/)
  if (!parsed) return term.length > 10 ? `${term.slice(0, 9)}…` : term
  return `${parsed[1]}–${parsed[2].slice(2)} ${parsed[3] === '1' ? '秋' : '春'}`
}

const grouped = computed<GradeGroup[]>(() => {
  const map = new Map<string, AcademicGradeView[]>()
  for (const grade of grades.value) {
    const term = gradeTerm(grade)
    map.set(term, [...(map.get(term) ?? []), grade])
  }
  return [...map.entries()]
    .map(([term, rows]) => ({ term, rows }))
    .sort((a, b) => termSortKey(b.term) - termSortKey(a.term) || b.term.localeCompare(a.term, 'zh-CN'))
})

const filteredGroups = computed(() => grouped.value.filter(group => selectedTerm.value === 'all' || group.term === selectedTerm.value))
const filteredCount = computed(() => filteredGroups.value.reduce((sum, group) => sum + group.rows.length, 0))

const termScopedRows = computed(() => grades.value.filter(row => analysisTerm.value === 'all' || gradeTerm(row) === analysisTerm.value))
const courseKindOptions = computed(() => [...new Set(termScopedRows.value.map(courseKind))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
watch([analysisTerm, courseKindOptions], () => {
  if (analysisKind.value !== 'all' && !courseKindOptions.value.includes(analysisKind.value)) analysisKind.value = 'all'
})
const analysisRows = computed(() => termScopedRows.value.filter(row => analysisKind.value === 'all' || courseKind(row) === analysisKind.value))
const analysisRangeLabel = computed(() => analysisTerm.value === 'all' ? `全部 ${grouped.value.length} 个学期` : formatTerm(analysisTerm.value))

function averagePointOf(rows: AcademicGradeView[]) {
  const points = rows.map(row => ({ point: parseNumber(row.point), credit: parseNumber(row.credit) })).filter((item): item is { point: number; credit: number | null } => item.point !== null)
  const weighted = points.length > 0 && points.every(item => item.credit !== null && item.credit > 0)
  const creditSum = weighted ? points.reduce((sum, item) => sum + item.credit!, 0) : 0
  const value = !points.length
    ? null
    : weighted
      ? points.reduce((sum, item) => sum + item.point * item.credit!, 0) / creditSum
      : points.reduce((sum, item) => sum + item.point, 0) / points.length
  return { value, weighted }
}

const totalCredits = computed(() => {
  const values = analysisRows.value.map(row => parseNumber(row.credit)).filter((value): value is number => value !== null)
  return values.length ? values.reduce((sum, value) => sum + value, 0).toFixed(1).replace(/\.0$/, '') : ''
})

const scoreBands = computed(() => {
  const numeric = analysisRows.value.map(row => parseNumber(row.score)).filter((value): value is number => value !== null)
  const total = analysisRows.value.length || 1
  return [
    { key: 'excellent', label: '85 分及以上', count: numeric.filter(value => value >= 85).length },
    { key: 'steady', label: '60–84 分', count: numeric.filter(value => value >= 60 && value < 85).length },
    { key: 'attention', label: '60 分以下', count: numeric.filter(value => value < 60).length },
    { key: 'level', label: '等级制 / 未录入', count: analysisRows.value.length - numeric.length },
  ].map(item => ({ ...item, width: `${item.count / total * 100}%` }))
})

const scoreSummary = computed(() => scoreBands.value.filter(item => item.count).map(item => `${item.label} ${item.count} 门`).join('，'))
const termAnalytics = computed(() => {
  const map = new Map<string, AcademicGradeView[]>()
  for (const row of analysisRows.value) {
    const term = gradeTerm(row)
    map.set(term, [...(map.get(term) ?? []), row])
  }
  return [...map.entries()].map(([term, rows]) => {
    const scores = rows.map(row => parseNumber(row.score)).filter((value): value is number => value !== null)
    const pointAverage = averagePointOf(rows)
    return {
      term,
      averageScore: scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null,
      averagePoint: pointAverage.value,
      pointWeighted: pointAverage.weighted,
      courses: rows.length,
    }
  }).filter(item => item.averageScore !== null || item.averagePoint !== null).sort((a, b) => termSortKey(a.term) - termSortKey(b.term))
})

const trendSeries = computed(() => termAnalytics.value.map(item => ({
  ...item,
  value: analysisMetric.value === 'score' ? item.averageScore : item.averagePoint,
})).filter((item): item is typeof item & { value: number } => item.value !== null))

const chartFloor = computed(() => {
  const lowest = Math.min(...trendSeries.value.map(item => item.value))
  if (!Number.isFinite(lowest)) return 0
  return analysisMetric.value === 'score'
    ? Math.max(0, Math.floor((lowest - 10) / 20) * 20)
    : Math.max(0, Math.floor((lowest - .5) * 2) / 2)
})
const chartCeiling = computed(() => {
  if (analysisMetric.value === 'score') return 100
  const highest = Math.max(...trendSeries.value.map(item => item.value))
  return Number.isFinite(highest) ? Math.max(4, Math.ceil(highest * 2) / 2) : 4
})
const chartTicks = computed(() => {
  if (analysisMetric.value === 'score') {
    const ticks: number[] = []
    for (let value = chartCeiling.value; value >= chartFloor.value; value -= 20) ticks.push(value)
    if (ticks.at(-1) !== chartFloor.value) ticks.push(chartFloor.value)
    return ticks
  }
  return [chartCeiling.value, (chartCeiling.value + chartFloor.value) / 2, chartFloor.value]
})
function chartY(value: number) {
  return 18 + (chartCeiling.value - value) / Math.max(.5, chartCeiling.value - chartFloor.value) * 150
}
function formatTrendValue(value: number) {
  return analysisMetric.value === 'score' ? value.toFixed(1) : value.toFixed(2)
}

const trendPoints = computed(() => trendSeries.value.map((item, index, points) => ({
  ...item,
  x: points.length === 1 ? 330 : 48 + index * (566 / (points.length - 1)),
  y: chartY(item.value),
})))
const trendPath = computed(() => trendPoints.value.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' '))
const latestTrendPoint = computed(() => trendPoints.value.at(-1))
const trendDelta = computed(() => trendPoints.value.length > 1 ? trendPoints.value.at(-1)!.value - trendPoints.value.at(-2)!.value : null)
const analysisSummary = computed(() => {
  const scores = analysisRows.value.map(row => parseNumber(row.score)).filter((value): value is number => value !== null)
  const pointAverage = averagePointOf(analysisRows.value)
  return {
    averageScore: scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null,
    averagePoint: pointAverage.value,
    pointWeighted: pointAverage.weighted,
  }
})
const highestCourse = computed(() => analysisRows.value.map(row => ({ row, score: parseNumber(row.score) })).filter(item => item.score !== null).sort((a, b) => b.score! - a.score!)[0])
const attentionCount = computed(() => analysisRows.value.filter(row => (parseNumber(row.score) ?? 60) < 60).length)

const courseRows = computed(() => analysisRows.value.map(row => ({
  row,
  term: gradeTerm(row),
  kind: courseKind(row),
  value: parseNumber(analysisMetric.value === 'score' ? row.score : row.point),
})).filter(item => item.value !== null).sort((a, b) => b.value! - a.value!))
const visibleCourseRows = computed(() => courseRows.value.slice(0, 12))
const courseHiddenCount = computed(() => Math.max(0, courseRows.value.length - visibleCourseRows.value.length))
const courseMetricMax = computed(() => {
  if (analysisMetric.value === 'score') return 100
  const highest = Math.max(...courseRows.value.map(item => item.value as number))
  return Number.isFinite(highest) ? Math.max(4, Math.ceil(highest * 2) / 2) : 4
})
const courseMetricMid = computed(() => courseMetricMax.value / 2)
const courseMissingCount = computed(() => analysisRows.value.filter(row => parseNumber(analysisMetric.value === 'score' ? row.score : row.point) === null).length)
function formatCourseValue(value: number) {
  return analysisMetric.value === 'score' ? value.toFixed(0) : value.toFixed(1)
}

const importedAt = computed(() => {
  const raw = academic.value?.imported_at
  if (!raw) return '尚未记录更新时间'
  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? raw : `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日更新`
})

function scoreTone(score = '') {
  const value = parseNumber(score)
  if (value === null) return 'is-level'
  if (value < 60) return 'is-low'
  if (value >= 85) return 'is-high'
  return ''
}

async function analyzeLearning() {
  const revision = backendDemo.state.profileEditSerial
  const result = await learningAnalysis.run('portraitAnalysis')
  if (result) analysisSerial.value = revision
}

async function loadGrades(notify = false) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    backendDemo.setWorkspace(await backendClient.workspace())
    if (notify) status.value = '已读取最新成绩记录。'
  } catch {
    error.value = '最新成绩暂时没有读取成功，当前内容仍保留。'
  } finally {
    loading.value = false
  }
}

async function imported(message: string) {
  importOpen.value = false
  await loadGrades()
  status.value = message
}

async function revokeGrades() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await backendClient.revokeAcademicGrades()
    if (!result.revoked) throw new Error('Not confirmed')
    backendDemo.revokeAcademicGrades()
    backendDemo.markProfileChange('scores')
    revokeOpen.value = false
    status.value = '已撤回成绩记录，课表保持不变。'
    await loadGrades()
  } catch {
    error.value = '撤回结果暂时没有确认，请重新读取后再试。'
  } finally {
    loading.value = false
  }
}

onMounted(() => { void loadGrades() })
</script>

<template>
  <div class="ws-page grades-page">
    <PageHeading title="我的成绩" description="先看成绩变化与学习建议，再按学年、学期核对课程明细。">
      <button v-if="grades.length" class="btn" :disabled="loading" @click="loadGrades(true)">{{ loading ? '正在读取…' : '刷新成绩' }}</button>
      <button v-if="grades.length" class="btn btn--primary" @click="importOpen = true"><UiIcon name="upload" :size="16" />更新成绩</button>
    </PageHeading>

    <StatusBanner v-if="status" tone="success" size="sm" :message="status" @dismiss="status=''" />
    <StatusBanner v-if="error" tone="error" size="sm" :message="error" retryable :retrying="loading" @retry="loadGrades(true)" @dismiss="error=''" />

    <template v-if="grades.length">
      <section class="grade-analysis" aria-labelledby="grade-analysis-title">
        <header class="section-intro">
          <div><p>成绩概览</p><h2 id="grade-analysis-title">成绩分析与趋势</h2></div>
          <span>{{ academic?.school || '学校待补充' }} · {{ importedAt }}</span>
        </header>

        <div
          class="analysis-filters"
          aria-label="成绩分析筛选"
          @pointerdown.capture="rememberAnalysisScroll"
          @focusin.capture="restoreAnalysisScroll"
          @change="restoreAnalysisScroll"
        >
          <label><span>图表类型</span><select v-model="analysisView"><option value="trend">学期趋势</option><option value="courses">课程对比</option></select></label>
          <label><span>学年学期</span><select v-model="analysisTerm"><option value="all">全部学年学期</option><option v-for="group in grouped" :key="group.term" :value="group.term">{{ formatTerm(group.term) }}</option></select></label>
          <label><span>课程性质</span><select v-model="analysisKind"><option value="all">全部性质</option><option v-for="kind in courseKindOptions" :key="kind" :value="kind">{{ kind }}</option></select></label>
          <div class="filter-group"><span>分析指标</span><div class="metric-switch" role="group" aria-label="分析指标"><button type="button" :class="{ 'is-active': analysisMetric === 'score' }" :aria-pressed="analysisMetric === 'score'" @click="selectAnalysisMetric('score')">成绩</button><button type="button" :class="{ 'is-active': analysisMetric === 'point' }" :aria-pressed="analysisMetric === 'point'" @click="selectAnalysisMetric('point')">绩点</button></div></div>
        </div>

        <div class="grade-analysis__grid">
          <article v-if="analysisView === 'trend'" class="trend-chart">
            <div class="trend-chart__head">
              <div>
                <h3>{{ analysisMetric === 'score' ? '学期平均分趋势' : '学期平均绩点趋势' }} <DetailPopover title="计算口径" label="查看计算口径"><p>{{ analysisMetric === 'score' ? '按筛选范围内每学期已录入的数值成绩计算。' : '学分完整时按学分加权；否则采用已录入绩点的算术平均。' }}</p></DetailPopover></h3>
              </div>
              <strong v-if="latestTrendPoint">{{ formatTrendValue(latestTrendPoint.value) }}<small>{{ analysisMetric === 'score' ? '分' : '绩点' }}</small></strong>
            </div>
            <svg v-if="trendPoints.length" viewBox="0 0 660 210" role="img" aria-labelledby="grade-trend-title grade-trend-desc">
              <title id="grade-trend-title">各学期{{ analysisMetric === 'score' ? '平均分' : '平均绩点' }}趋势</title>
              <desc id="grade-trend-desc">{{ trendPoints.map(point => `${formatTerm(point.term)}${analysisMetric === 'score' ? '平均分' : '平均绩点'}${formatTrendValue(point.value)}`).join('；') }}</desc>
              <g v-for="tick in chartTicks" :key="tick" class="chart-grid">
                <line x1="48" x2="614" :y1="chartY(tick)" :y2="chartY(tick)" />
                <text x="38" :y="chartY(tick) + 4">{{ analysisMetric === 'score' ? tick : tick.toFixed(1) }}</text>
              </g>
              <path v-if="trendPoints.length > 1" class="trend-chart__line" :d="trendPath" />
              <g v-for="point in trendPoints" :key="point.term" class="trend-chart__point">
                <circle :cx="point.x" :cy="point.y" r="5"><title>{{ formatTerm(point.term) }}，{{ analysisMetric === 'score' ? '平均分' : '平均绩点' }} {{ formatTrendValue(point.value) }}</title></circle>
                <text class="trend-chart__value" :x="point.x" :y="point.y - 12">{{ formatTrendValue(point.value) }}</text>
                <text class="trend-chart__label" :x="point.x" y="198">{{ shortTerm(point.term) }}</text>
              </g>
            </svg>
            <p v-else class="trend-empty">没有可用于这个指标的数值记录。</p>
            <p class="trend-note">
              <template v-if="trendDelta !== null">较上一学期{{ trendDelta >= 0 ? '上升' : '下降' }} {{ analysisMetric === 'score' ? Math.abs(trendDelta).toFixed(1) + ' 分' : Math.abs(trendDelta).toFixed(2) }}。</template>
              <template v-else-if="trendPoints.length === 1">目前只有一个可计算学期，作为基线展示；继续导入后会形成趋势线。</template>
            </p>
          </article>

          <article v-else class="course-comparison course-comparison--chart" aria-labelledby="course-comparison-title">
            <div class="course-comparison__head">
              <div><h3 id="course-comparison-title">课程表现对比</h3></div>
            </div>

            <ol v-if="visibleCourseRows.length" class="course-bars">
              <li v-for="item in visibleCourseRows" :key="`${item.term}-${item.row.name}`">
                <div class="course-bars__label"><strong>{{ item.row.name }}</strong><span><template v-if="analysisTerm === 'all'">{{ shortTerm(item.term) }} · </template>{{ item.kind }}<template v-if="item.row.credit"> · {{ item.row.credit }} 学分</template></span></div>
                <div class="course-bars__plot">
                  <div class="course-bars__track" role="img" :aria-label="`${item.row.name}${analysisMetric === 'score' ? '成绩' : '绩点'}${formatCourseValue(item.value!)}`"><i :style="{ width: `${Math.min(100, item.value! / courseMetricMax * 100)}%` }" /></div>
                </div>
                <strong class="course-bars__value">{{ formatCourseValue(item.value!) }}</strong>
              </li>
            </ol>
            <p v-else class="course-bars__empty">这个筛选下没有可用于{{ analysisMetric === 'score' ? '成绩' : '绩点' }}比较的课程。</p>
            <div v-if="visibleCourseRows.length" class="course-bars__axis" aria-hidden="true"><span>0</span><span>{{ formatCourseValue(courseMetricMid) }}</span><span>{{ formatCourseValue(courseMetricMax) }}</span></div>
            <p v-if="courseMissingCount || courseHiddenCount" class="course-bars__note"><template v-if="courseHiddenCount">图中显示当前指标最高的 12 门课程；其余 {{ courseHiddenCount }} 门可缩小学期范围后查看。</template><template v-if="courseHiddenCount && courseMissingCount"> </template><template v-if="courseMissingCount">另有 {{ courseMissingCount }} 门未录入{{ analysisMetric === 'score' ? '数值成绩' : '绩点' }}，未放入图中。</template></p>
          </article>

          <aside class="analysis-readout" aria-label="成绩分析摘要">
            <dl>
              <div><dt>筛选范围</dt><dd>{{ analysisRangeLabel }}</dd></div>
              <div><dt>平均成绩</dt><dd>{{ analysisSummary.averageScore !== null ? `${analysisSummary.averageScore.toFixed(1)} 分` : '暂无数值成绩' }}</dd></div>
              <div><dt>平均绩点</dt><dd>{{ analysisSummary.averagePoint !== null ? `${analysisSummary.averagePoint.toFixed(2)}${analysisSummary.pointWeighted ? '（学分加权）' : ''}` : '暂无绩点' }}</dd></div>
              <div><dt>最高成绩</dt><dd>{{ highestCourse ? `${highestCourse.row.name} · ${highestCourse.score} 分` : '暂无数值成绩' }}</dd></div>
              <div><dt>需留意</dt><dd>{{ attentionCount ? `${attentionCount} 门低于 60 分` : '暂无低于 60 分的课程' }}</dd></div>
              <div><dt>当前样本</dt><dd>{{ analysisRows.length }} 门课程<template v-if="totalCredits"> · {{ totalCredits }} 学分</template></dd></div>
            </dl>
            <div class="score-distribution">
              <div class="score-distribution__head"><h3>筛选范围成绩分布</h3><p>{{ scoreSummary || '暂无数值成绩' }}</p></div>
              <div class="score-distribution__track" role="img" :aria-label="`成绩分布：${scoreSummary}`"><i v-for="band in scoreBands" v-show="band.count" :key="band.key" :class="`is-${band.key}`" :style="{ width: band.width }" /></div>
              <ul><li v-for="band in scoreBands" v-show="band.count" :key="band.key"><i :class="`is-${band.key}`" />{{ band.label }}<strong>{{ band.count }}</strong></li></ul>
            </div>
          </aside>
        </div>

      </section>

      <section class="learning-analysis" aria-labelledby="learning-analysis-title">
        <div class="learning-analysis__lead">
          <div class="learning-analysis__icon" aria-hidden="true"><UiIcon name="trophy" :size="20" /></div>
          <div><p>结合成绩与已授权画像</p><h2 id="learning-analysis-title">AI 学习分析 <DetailPopover title="学习分析说明" label="查看学习分析说明"><p>识别优势、留意项和下一步；资料不足时保留待确认项，不替你推断。</p></DetailPopover></h2></div>
        </div>
        <button class="btn" :disabled="learningAnalysis.busy.value" @click="analyzeLearning">{{ learningAnalysis.result.value ? '更新学习分析' : '生成学习分析' }}</button>
        <AiStatus class="learning-analysis__status" :busy="learningAnalysis.busy.value" :error="learningAnalysis.error.value" :progress="learningAnalysis.progress.value" @cancel="learningAnalysis.cancel" @retry="analyzeLearning" />
        <StatusBanner v-if="analysisStale && learningAnalysis.result.value" class="learning-analysis__status" tone="warning" size="sm" message="成绩或个人资料已经变化，这份分析需要重新核对。" action-label="更新分析" @action="analyzeLearning" />
        <div v-if="learningAnalysis.result.value" class="learning-analysis__result">
          <h3>{{ learningAnalysis.result.value.data.headline }}</h3>
          <ReadableText :text="learningAnalysis.result.value.data.reading" />
          <div class="learning-analysis__columns">
            <section v-for="group in [{ title: '已有优势', items: learningAnalysis.result.value.data.strengths }, { title: '需要留意', items: learningAnalysis.result.value.data.watchouts }, { title: '下一步', items: learningAnalysis.result.value.data.next }]" :key="group.title">
              <h4>{{ group.title }}</h4>
              <ul><li v-for="item in group.items" :key="item.label"><strong>{{ item.label }}</strong><p>{{ item.why }}</p></li></ul>
            </section>
          </div>
          <AiResultMeta :result="learningAnalysis.result.value" />
        </div>
      </section>

      <section class="grade-query" aria-labelledby="grade-query-title">
        <header class="grade-query__head">
          <div><p>课程明细</p><h2 id="grade-query-title">学期成绩查询</h2><span>共找到 {{ filteredCount }} 门课程</span></div>
          <div class="grade-filters">
            <label><span>学年学期</span><select v-model="selectedTerm"><option value="all">全部学年学期</option><option v-for="group in grouped" :key="group.term" :value="group.term">{{ formatTerm(group.term) }}</option></select></label>
          </div>
        </header>

        <div v-if="filteredGroups.length" aria-live="polite">
          <section v-for="(group, groupIndex) in filteredGroups" :key="group.term" class="transcript" :aria-labelledby="`grade-term-${groupIndex}`">
            <header class="transcript__head"><div><span class="transcript__mark" aria-hidden="true" /><div><p>学期成绩单</p><h3 :id="`grade-term-${groupIndex}`">{{ formatTerm(group.term) }}</h3></div></div><span>{{ group.rows.length }} 门课程</span></header>
            <div class="transcript__table"><table><thead><tr><th>课程名称</th><th>课程性质</th><th>学分</th><th>绩点</th><th>成绩</th></tr></thead><tbody><tr v-for="(grade,index) in group.rows" :key="grade.name + index"><td><strong>{{ grade.name }}</strong><small v-if="grade.kind && grade.category">{{ grade.category }}</small></td><td>{{ grade.kind || grade.category || '—' }}</td><td>{{ grade.credit || '—' }}</td><td>{{ grade.point || '—' }}</td><td><span class="grade-score" :class="scoreTone(grade.score)">{{ grade.score || '—' }}</span></td></tr></tbody></table></div>
          </section>
        </div>
        <EmptyState v-else kind="search-empty" :heading-level="3" size="sm" title="这个筛选下没有成绩" description="换一个学年或学期查看。" :next="false" />
      </section>

      <section class="grade-notes"><DetailPopover title="成绩口径" label="查看成绩口径"><template #trigger>成绩口径</template><p>等级制成绩按原文保留，不自动换算；绩点以学校导出值为准。趋势仅使用已录入的数值成绩，不推算排名或综合绩点，避免混用不同学校的计算规则。</p></DetailPopover><button class="grade-revoke" @click="revokeOpen=true"><UiIcon name="trash" :size="16" />撤回成绩记录</button></section>
    </template>

    <EmptyState v-else kind="academic" :heading-level="2" title="还没有成绩记录" description="从教务系统复制带表头的成绩表，保存前可以先预览识别结果。" action-label="导入成绩" @action="importOpen=true" />

    <nav class="ws-related"><RouterLink to="/profile">查看学籍与个人画像<UiIcon name="profile" :size="16" /></RouterLink><RouterLink to="/schedule">查看日历与课表<UiIcon name="calendar" :size="16" /></RouterLink></nav>

    <AcademicImportSheet :open="importOpen" kind="grades" :has-rows="!!grades.length" :school="academic?.school" :term="academic?.term" @close="importOpen=false" @saved="imported" />
    <InfoSheet :open="revokeOpen" shape="dialog" title="撤回成绩记录" @close="revokeOpen=false"><p>将删除当前保存的全部成绩。课程表、学籍信息、行动记录不会受影响。</p><div class="ws-inline-actions"><button class="btn btn--danger" :disabled="loading" @click="revokeGrades">{{ loading ? '正在撤回…' : '确认撤回成绩' }}</button><button class="btn" :disabled="loading" @click="revokeOpen=false">取消</button></div></InfoSheet>
  </div>
</template>

<style scoped>
.grades-page {
  --grade-rule: var(--c-border);
  --grade-paper: #f7f9fc;
  --grade-blue-soft: #eaf3fb;
  --grade-blue-mid: #6e9fca;
}

.grade-analysis {
  margin: 10px 0 48px;
  padding: 26px 28px 28px;
  border: 1px solid #dbe4ec;
  border-radius: 18px;
  background: var(--c-surface);
  box-shadow: 0 12px 32px rgba(35, 58, 79, .06);
}

.section-intro,
.grade-query__head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
}

.section-intro p,
.grade-query__head > div:first-child > p,
.learning-analysis__lead p {
  color: var(--c-primary);
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
}

.section-intro h2,
.grade-query__head h2,
.learning-analysis__lead h2 {
  margin-top: 2px;
  font-size: var(--fs-22);
  font-weight: var(--fw-semibold);
  letter-spacing: -.01em;
}

.section-intro > span,
.grade-query__head > div:first-child > span {
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.analysis-filters {
  display: grid;
  grid-template-columns: minmax(126px, .75fr) minmax(210px, 1.4fr) minmax(122px, .8fr) auto;
  align-items: end;
  gap: 12px;
  margin-top: 20px;
}

.grade-analysis__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(260px, .8fr);
  gap: 28px;
  margin-top: 24px;
  padding-top: 22px;
  border-top: 1px solid var(--grade-rule);
}

.trend-chart {
  min-width: 0;
  padding-right: 28px;
  border-right: 1px solid var(--grade-rule);
}

.trend-chart__head {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 18px;
}

.trend-chart__head h3,
.score-distribution__head h3 {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
}

.trend-chart__head p,
.score-distribution__head p {
  margin-top: 4px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
  line-height: 1.55;
}

.trend-chart__head > strong {
  color: var(--c-primary);
  font-size: 30px;
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
  letter-spacing: -.03em;
}

.trend-chart__head > strong small {
  margin-left: 4px;
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
}

.metric-switch {
  display: inline-flex;
  padding: 3px;
  border: 1px solid var(--grade-rule);
  border-radius: 9px;
  background: var(--c-surface);
}

.metric-switch button {
  min-height: 30px;
  padding: 5px 11px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.metric-switch button.is-active {
  background: var(--grade-blue-soft);
  color: var(--c-primary);
  font-weight: var(--fw-semibold);
}

.metric-switch button:focus-visible {
  outline: 2px solid var(--c-primary);
  outline-offset: 1px;
}

.trend-chart svg {
  display: block;
  width: 100%;
  margin-top: 12px;
  overflow: visible;
}

.chart-grid line {
  stroke: #e4e9ef;
  stroke-width: 1;
}

.chart-grid text {
  fill: var(--c-text-3);
  font-size: 12px;
  text-anchor: end;
}

.trend-chart__line {
  fill: none;
  stroke: var(--c-primary);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.trend-chart__point circle {
  fill: var(--c-surface);
  stroke: var(--c-primary);
  stroke-width: 3;
}

.trend-chart__value {
  fill: var(--c-text);
  font-size: 12px;
  font-weight: var(--fw-semibold);
  text-anchor: middle;
}

.trend-chart__label {
  fill: var(--c-text-3);
  font-size: 12px;
  text-anchor: middle;
}

.trend-note {
  margin-top: 2px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.trend-empty {
  display: grid;
  place-items: center;
  min-height: 210px;
  color: var(--c-text-3);
  font-size: var(--fs-13);
}

.analysis-readout dl {
  display: grid;
  gap: 0;
}

.analysis-readout dl > div {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid var(--grade-rule);
}

.analysis-readout dt {
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.analysis-readout dd {
  color: var(--c-text-2);
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
}

.score-distribution {
  padding-top: 18px;
}

.score-distribution__head {
  display: block;
}

.score-distribution__track {
  display: flex;
  gap: 3px;
  height: 8px;
  margin-top: 11px;
  overflow: hidden;
  border-radius: 999px;
  background: #e5eaf0;
}

.score-distribution__track i {
  display: block;
  min-width: 4px;
}

.score-distribution .is-excellent { background: var(--c-primary); }
.score-distribution .is-steady { background: var(--grade-blue-mid); }
.score-distribution .is-attention { background: var(--c-attention); }
.score-distribution .is-level { background: #aeb8c2; }

.score-distribution ul {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 14px;
  margin-top: 12px;
}

.score-distribution li {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.score-distribution li > i {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 2px;
}

.score-distribution li strong {
  margin-left: auto;
  color: var(--c-text-2);
  font-variant-numeric: tabular-nums;
}

.course-comparison {
  margin-top: 28px;
  padding-top: 26px;
  border-top: 1px solid var(--grade-rule);
}

.course-comparison--chart {
  min-width: 0;
  margin: 0;
  padding: 0 28px 0 0;
  border-top: 0;
  border-right: 1px solid var(--grade-rule);
}

.course-comparison__head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 28px;
}

.course-comparison__head h3 {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
}

.course-comparison__head > div:first-child p {
  margin-top: 4px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
  line-height: 1.55;
}

.analysis-filters label,
.filter-group {
  display: grid;
  gap: 5px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.analysis-filters select {
  width: 100%;
  min-height: 38px;
  padding: 0 32px 0 11px;
  border: 1px solid var(--grade-rule);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  color: var(--c-text);
  font: inherit;
  font-size: var(--fs-12);
}

.analysis-filters select:focus-visible {
  outline: 2px solid var(--c-primary);
  outline-offset: 2px;
}

.course-bars {
  display: grid;
  gap: 13px;
  margin-top: 24px;
}

.course-bars li {
  display: grid;
  grid-template-columns: minmax(150px, 220px) minmax(220px, 1fr) 48px;
  align-items: center;
  gap: 16px;
}

.course-comparison--chart .course-bars li {
  grid-template-columns: minmax(120px, 180px) minmax(120px, 1fr) 42px;
  gap: 12px;
}

.course-bars__label {
  min-width: 0;
}

.course-bars__label strong,
.course-bars__label span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-bars__label strong {
  color: var(--c-text-2);
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
}

.course-bars__label span {
  margin-top: 2px;
  color: var(--c-text-3);
  font-size: 12px;
}

.course-bars__plot {
  padding: 5px 0;
}

.course-bars__track {
  height: 11px;
  overflow: hidden;
  border-radius: 3px;
  background: #e8edf2;
}

.course-bars__track i {
  display: block;
  height: 100%;
  min-width: 3px;
  border-radius: inherit;
  background: var(--c-primary);
}

.course-bars__value {
  color: var(--c-text);
  font-size: var(--fs-14);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.course-bars__axis {
  display: flex;
  justify-content: space-between;
  margin: 7px 48px 0 236px;
  color: var(--c-text-3);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.course-comparison--chart .course-bars__axis {
  margin-right: 42px;
  margin-left: 192px;
}

.course-bars__empty {
  display: grid;
  place-items: center;
  min-height: 150px;
  margin-top: 20px;
  border: 1px dashed var(--grade-rule);
  border-radius: 10px;
  color: var(--c-text-3);
  font-size: var(--fs-13);
}

.course-bars__note {
  margin-top: 12px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.learning-analysis {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 18px 24px;
  margin: 0 0 54px;
  padding: 26px 28px;
  border: 1px solid var(--grade-rule);
  border-left: 4px solid var(--c-primary);
  border-radius: 0 16px 16px 0;
  background: var(--grade-paper);
}

.learning-analysis__lead {
  display: flex;
  align-items: center;
  gap: 14px;
}

.learning-analysis__icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  flex: none;
  border-radius: 12px;
  background: var(--grade-blue-soft);
  color: var(--c-primary);
}

.learning-analysis__lead span {
  display: block;
  max-width: 64ch;
  margin-top: 5px;
  color: var(--c-text-3);
  font-size: var(--fs-13);
  line-height: 1.6;
}

.learning-analysis > .btn {
  align-self: center;
}

.learning-analysis__status,
.learning-analysis__result {
  grid-column: 1 / -1;
}

.learning-analysis__result {
  padding-top: 20px;
  border-top: 1px solid var(--grade-rule);
}

.learning-analysis__result > h3 {
  margin-bottom: 8px;
  font-size: var(--fs-18);
  font-weight: var(--fw-semibold);
}

.learning-analysis__columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin: 24px 0;
}

.learning-analysis__columns section {
  padding-top: 13px;
  border-top: 2px solid #cad9e7;
}

.learning-analysis__columns h4 {
  font-size: var(--fs-13);
  font-weight: var(--fw-semibold);
}

.learning-analysis__columns ul {
  margin-top: 10px;
}

.learning-analysis__columns li + li {
  margin-top: 12px;
}

.learning-analysis__columns li strong,
.learning-analysis__columns li p {
  display: block;
  font-size: var(--fs-12);
  line-height: 1.6;
}

.learning-analysis__columns li p {
  margin-top: 2px;
  color: var(--c-text-3);
}

.grade-query {
  margin-top: 4px;
}

.grade-filters {
  display: flex;
  gap: 12px;
}

.grade-filters label {
  display: grid;
  gap: 5px;
  min-width: 152px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.grade-filters select {
  min-height: 40px;
  padding: 0 34px 0 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  color: var(--c-text);
  font: inherit;
  font-size: var(--fs-13);
}

.grade-filters select:focus-visible {
  outline: 2px solid var(--c-primary);
  outline-offset: 2px;
}

.transcript {
  margin-top: 30px;
}

.transcript__head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  padding: 0 2px 14px;
}

.transcript__head > div {
  display: flex;
  align-items: center;
  gap: 12px;
}

.transcript__mark {
  width: 4px;
  height: 42px;
  border-radius: 3px;
  background: var(--c-primary);
}

.transcript__head p {
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.transcript__head h3 {
  margin-top: 2px;
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
}

.transcript__head > span {
  padding-bottom: 2px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.transcript__table {
  overflow-x: auto;
  border: 1px solid var(--grade-rule);
  border-radius: 14px;
  background: var(--c-surface);
  box-shadow: 0 7px 20px rgba(35, 58, 79, .04);
}

.transcript table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.transcript th,
.transcript td {
  padding: 15px 18px;
  border-bottom: 1px solid var(--grade-rule);
  text-align: left;
}

.transcript th {
  background: var(--grade-paper);
  color: var(--c-text-3);
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
}

.transcript td {
  color: var(--c-text-2);
  font-size: var(--fs-14);
}

.transcript tbody tr:last-child td { border-bottom: 0; }
.transcript tbody tr { transition: background-color .16s ease; }
.transcript tbody tr:hover { background: #f9fbfd; }
.transcript th:last-child,
.transcript td:last-child { text-align: right; }

.transcript td strong {
  display: block;
  color: var(--c-text);
  font-weight: var(--fw-medium);
}

.transcript td small {
  display: block;
  margin-top: 3px;
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.grade-score {
  display: inline-grid;
  place-items: center;
  min-width: 48px;
  height: 34px;
  padding: 0 9px;
  border-radius: 9px;
  background: var(--c-surface-2);
  color: var(--c-text);
  font-size: var(--fs-18);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
}

.grade-score.is-high { background: var(--grade-blue-soft); color: var(--c-primary); }
.grade-score.is-low { background: var(--c-attention-weak); color: var(--c-attention-strong); }
.grade-score.is-level { font-size: var(--fs-14); }

.grade-notes {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 28px;
  margin-top: 42px;
  padding: 22px 2px 0;
  border-top: 1px solid var(--grade-rule);
}

.grade-notes h2 { font-size: var(--fs-14); font-weight: var(--fw-semibold); }
.grade-notes p { max-width: 78ch; margin-top: 5px; color: var(--c-text-3); font-size: var(--fs-13); line-height: 1.75; }

.grade-revoke {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 40px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--c-text-3);
  font-size: var(--fs-13);
  white-space: nowrap;
}

.grade-revoke:hover { border-color: var(--c-attention-border); background: var(--c-attention-weak); color: var(--c-attention-strong); }
.grade-revoke:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.ws-related { margin-top: 32px; }

@media (prefers-reduced-motion: reduce) {
  .transcript tbody tr { transition: none; }
}

@media (max-width: 820px) {
  .grade-analysis__grid { grid-template-columns: 1fr; }
  .trend-chart { padding: 0 0 24px; border-right: 0; border-bottom: 1px solid var(--grade-rule); }
  .course-comparison--chart { padding: 0 0 24px; border-right: 0; border-bottom: 1px solid var(--grade-rule); }
  .course-comparison__head { align-items: stretch; flex-direction: column; }
  .analysis-filters { display: grid; grid-template-columns: 1fr 1fr; }
  .filter-group { grid-column: 1 / -1; }
  .learning-analysis__columns { grid-template-columns: 1fr; }
}

@media (max-width: 700px) {
  .grade-analysis { padding: 22px 18px; }
  .section-intro,
  .grade-query__head { align-items: stretch; flex-direction: column; }
  .grade-filters { display: grid; grid-template-columns: 1fr; }
  .grade-filters label { min-width: 0; }
  .learning-analysis { grid-template-columns: 1fr; padding: 22px 18px; }
  .learning-analysis > .btn { width: 100%; }
  .learning-analysis__status,
  .learning-analysis__result { grid-column: 1; }
  .trend-chart__head { align-items: end; }
  .score-distribution ul { grid-template-columns: 1fr; }
  .analysis-filters { grid-template-columns: 1fr; }
  .filter-group { grid-column: 1; }
  .course-bars li { grid-template-columns: minmax(105px, 1fr) minmax(110px, 1.4fr) 38px; gap: 10px; }
  .course-bars__axis { margin-right: 38px; margin-left: calc(40% + 10px); }
  .transcript th,
  .transcript td { padding: 14px 12px; }
  .transcript th:nth-child(2),
  .transcript td:nth-child(2),
  .transcript th:nth-child(4),
  .transcript td:nth-child(4) { display: none; }
  .grade-notes { flex-direction: column; }
  .grade-revoke { width: 100%; justify-content: center; border-color: var(--c-border); }
}
</style>
