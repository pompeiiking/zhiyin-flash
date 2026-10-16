<script setup lang="ts">
import type { ProfileFieldView, ReportDimensionItemView, ReportFullTextView, ReportSectionView, WorkspacePageView } from '../api/backend-types'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PROFILE_TOPICS } from '../lib/profile-organization'
import { profileLabel } from '../lib/server-copy'
import { useAiTask } from '../lib/use-ai-task'
import AiResultMeta from './AiResultMeta.vue'
import AiStatus from './AiStatus.vue'
import DetailPopover from './DetailPopover.vue'
import InfoSheet from './InfoSheet.vue'

type ReportReading = { headline: string; paragraphs: string[]; moves: { label: string; why: string }[] }
type ProfileSection = { key: string; title: string; fields: ProfileFieldView[] }
type TocItem = { id: string; title: string; level: 'section' | 'item' }

const props = withDefaults(defineProps<{
  report: ReportFullTextView
  workspace?: WorkspacePageView | null
  profileError?: string
  allowAiSummary?: boolean
}>(), { allowAiSummary: false })

const route = useRoute()
const router = useRouter()
const ai = useAiTask<ReportReading>()
const appendix = ref(false)
const profileSheet = ref(false)
const tocOpen = ref(false)
const activeSection = ref('overview')
const all = computed(() => props.report.sections?.flatMap((section) => section.items ?? []) ?? [])
const pendingItems = computed(() => all.value.filter(isPending))
const supportedCount = computed(() => all.value.filter((item) => !isPending(item)).length)
const profileFields = computed(() => props.workspace?.profile_panel?.fields ?? [])
const profileGaps = computed(() => props.workspace?.profile_panel?.gaps ?? [])
const academic = computed(() => props.workspace?.academic_panel ?? null)
const executiveFindings = computed(() => {
  const sections = props.report.sections ?? []
  const selfItem = sections[0]?.items?.[0]
  const directionItem = sections[1]?.items?.find((item) => /主要方向|目标方向/.test(item.name)) ?? sections[1]?.items?.[0]
  const decisionItem = sections[2]?.items?.find(isPending) ?? sections[2]?.items?.[0]
  const picks = [
    sections[0] && selfItem ? { section: sections[0], item: selfItem } : null,
    sections[1] && directionItem ? { section: sections[1], item: directionItem } : null,
    sections[2] && decisionItem ? { section: sections[2], item: decisionItem } : null,
  ]
  return picks.filter((value): value is { section: ReportSectionView; item: ReportDimensionItemView } => !!value?.item)
})

const profileSections = computed<ProfileSection[]>(() => {
  const known = new Set(PROFILE_TOPICS.flatMap((topic) => topic.keys))
  const sections = PROFILE_TOPICS
    .map((topic) => ({ key: topic.key, title: topic.title, fields: profileFields.value.filter((field) => topic.keys.includes(field.key)) }))
    .filter((topic) => topic.fields.length)
  const other = profileFields.value.filter((field) => !known.has(field.key))
  if (other.length) sections.push({ key: 'other', title: '其他个人信息', fields: other })
  return sections
})

const tocGroups = computed(() => (props.report.sections ?? []).map((section) => ({
  id: section.id,
  title: sectionTitle(section),
  items: (section.items ?? []).map((item) => ({ id: itemId(item), title: item.name, level: 'item' as const })),
})))
const tocItems = computed<TocItem[]>(() => [
  { id: 'overview', title: '执行摘要', level: 'section' },
  { id: 'diagnosis', title: '综合诊断', level: 'section' },
  ...tocGroups.value.flatMap((group) => [
    { id: group.id, title: group.title, level: 'section' as const },
    ...group.items,
  ]),
  ...(pendingItems.value.length ? [{ id: 'actions', title: '下一步验证', level: 'section' as const }] : []),
  { id: 'references', title: '资料与方法', level: 'section' },
])

const sourceNames: Record<string, string> = {
  resume: '简历材料', conversation: '咨询对话', assessment: '综合分析', behavior_inference: '行为记录', mentor: '导师记录', record: '学校记录', user_edit: '本人填写',
}
const labels: Record<string, string> = {
  strengths: '优势', weaknesses: '短板', opportunities: '机会', threats: '风险',
  strength: '优势', weakness: '短板', opportunity: '机会', risk: '风险', threat: '风险',
}

let observer: IntersectionObserver | null = null

function content(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(content).filter(Boolean).join('；')
  if (typeof value === 'object') return Object.values(value).map(content).filter(Boolean).join('；')
  return String(value)
}
function profileValue(field: ProfileFieldView): string {
  if (field.key === 'courses' && academic.value?.courses?.length) return `已记录 ${academic.value.courses.length} 门课程`
  if (field.key === 'scores' && academic.value?.grades?.length) return `已记录 ${academic.value.grades.length} 条成绩`
  return content(field.value) || '尚待补充'
}
function fieldDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '未记录时间' : date.toLocaleDateString('zh-CN')
}
function reportDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '未记录时间' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(date)
}
function sectionTitle(section: ReportSectionView) {
  if (/self|portrait|自我|画像/i.test(section.id + section.title)) return '你是什么样的人'
  if (/job|market|职业|环境/i.test(section.id + section.title)) return '外面是什么情况'
  if (/decision|risk|决策|风险/i.test(section.id + section.title)) return '你要做哪些取舍'
  return section.title
}
function sectionLead(section: ReportSectionView) {
  const title = sectionTitle(section)
  if (title === '你是什么样的人') return '这一章不急着给你贴标签，而是把兴趣、能力、价值取向和现实基础放到一起，看看哪些特征已经稳定，哪些仍只是线索。'
  if (title === '外面是什么情况') return '个人特点只有放进真实环境里才有意义。这里关注目标方向的要求、机会、竞争和变化，判断“想去”与“能够到达”之间还有多远。'
  if (title === '你要做哪些取舍') return '方向选择不是把所有可能性排成名次，而是明确什么值得投入、什么需要验证，以及哪些风险不能只靠想象来回答。'
  return '下面把已有资料串成连续判断，结论中的蓝色文字可以打开依据。'
}
function chapterLabel(index: number) { return ['第一章', '第二章', '第三章', '第四章'][index] ?? `第 ${index + 1} 章` }
function itemId(item: ReportDimensionItemView) { return `finding-${item.index}` }
function isPending(item: ReportDimensionItemView) { return !item.evidence?.trim() || /待|缺|不足|未知/.test(item.tag || '') }
function evidenceText(value?: string | null) { return (value || '').replace(/\b[a-z]+(?:_[a-z]+)+\b/g, key => profileLabel(key, key)) }
function confidenceText(item: ReportDimensionItemView) { return isPending(item) ? '仍需验证' : '已附依据 · 待核对' }
function sectionDomId(id: string) { return `report-section-${id.replace(/[^a-zA-Z0-9_-]/g, '-')}` }
function askLink(item: ReportDimensionItemView) {
  return '/chat?question=' + encodeURIComponent(`我想核对第${props.report.version}版报告中的「${item.name}」：${item.conclusion}${item.evidence ? `；依据：${item.evidence}` : '；目前没有提供依据'}`)
}
function weekday(value?: number | null) {
  return value ? `周${['一', '二', '三', '四', '五', '六', '日'][value - 1]}` : '时间待补充'
}

async function scrollToSection(id: string, updateRoute = true) {
  activeSection.value = id
  tocOpen.value = false
  if (updateRoute) {
    const query: Record<string, string | string[] | null | undefined> = { ...route.query, section: id }
    for (const key of ['q', 'group', 'tag', 'page']) delete query[key]
    await router.replace({ query })
  }
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const target = id === 'overview' ? document.querySelector<HTMLElement>('.report-masthead') : document.getElementById(sectionDomId(id))
    target?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  }))
}
function observeSections() {
  observer?.disconnect()
  if (typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
    const id = (visible[0]?.target as HTMLElement | undefined)?.dataset.sectionId
    if (id) activeSection.value = id
  }, { rootMargin: '-12% 0px -72% 0px', threshold: 0 })
  document.querySelectorAll<HTMLElement>('[data-report-section]').forEach((section) => observer?.observe(section))
}
async function prepareDocument() {
  await nextTick()
  observeSections()
  const requested = typeof route.query.section === 'string' ? route.query.section : ''
  if (requested && tocItems.value.some((section) => section.id === requested)) void scrollToSection(requested, false)
  else {
    activeSection.value = 'overview'
    if (requested) { const query = { ...route.query }; delete query.section; void router.replace({ query }) }
  }
}
function requestAiReading() {
  if (props.allowAiSummary && !ai.busy.value && !ai.result.value) void ai.run('reportSummary')
}
onMounted(() => { void prepareDocument(); requestAiReading() })
watch([() => props.report.version, () => props.workspace?.profile_panel?.updated_at], prepareDocument)
watch(() => props.allowAiSummary, requestAiReading)
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <article class="full-report report-document">
    <div class="report-document__grid">
      <div class="report-paper">
        <p v-if="profileError" class="report-profile-error" role="status">{{ profileError }}</p>

        <section :id="sectionDomId('overview')" class="report-overview article-section" data-section-id="overview" data-report-section>
          <header class="article-heading">
            <p>执行摘要</p>
            <h2>{{ ai.result.value?.data.headline || '把零散的个人信息，读成一个可以行动的判断' }}</h2>
          </header>
          <div v-if="ai.result.value" class="article-prose article-prose--lead">
            <p v-for="paragraph in ai.result.value.data.paragraphs" :key="paragraph">{{ paragraph }}</p>
          </div>
          <div v-else class="article-prose article-prose--lead">
            <p>这不是一份资料清单，而是对你当前状态的一次解释：系统把个人画像、咨询记录、学业资料和已经形成的诊断结论放到同一个语境里，寻找稳定优势、现实差距与最值得验证的假设。</p>
            <p v-if="report.sections?.[0]?.items?.[0]">目前最先浮现的线索，是关于<strong>{{ report.sections[0].items[0].name }}</strong>的判断：{{ report.sections[0].items[0].conclusion }}</p>
            <p>全文共形成 {{ all.length }} 项判断，其中 {{ supportedCount }} 项附有依据说明，{{ pendingItems.length }} 项仍需要新的行动或资料来验证。没有依据的部分会明确保留为假设，不会写成定论。</p>
          </div>
          <div v-if="executiveFindings.length" class="executive-findings" aria-label="报告核心结论">
            <p class="executive-findings__title">核心结论</p>
            <article v-for="(finding, index) in executiveFindings" :key="finding.item.index">
              <span aria-hidden="true">0{{ index + 1 }}</span>
              <p><DetailPopover :title="finding.item.name + ' · 判断依据'" :label="'查看“' + finding.item.name + '”的判断依据'" side="right" class="article-evidence-link article-evidence-link--summary"><template #trigger>{{ finding.item.name }}</template><p class="evidence-popover__label">{{ finding.item.evidence?.trim() ? '支撑这项判断的记录' : '当前还缺少什么' }}</p><p class="evidence-popover__quote">{{ evidenceText(finding.item.evidence) || '这项判断暂时没有可核对的记录，因此只能作为待验证假设。' }}</p><dl class="evidence-popover__facts"><div><dt>判断状态</dt><dd>{{ confidenceText(finding.item) }}</dd></div><div><dt>所在章节</dt><dd>{{ sectionTitle(finding.section) }}</dd></div><div><dt>报告版本</dt><dd>第 {{ report.version }} 版 · {{ reportDate(report.generated_at) }}</dd></div></dl><RouterLink class="btn btn--primary evidence-popover__action" :to="askLink(finding.item)">带着这条去核对</RouterLink></DetailPopover><strong>{{ finding.item.conclusion }}</strong></p>
            </article>
          </div>
          <AiStatus :busy="ai.busy.value" :error="ai.error.value" :progress="ai.progress.value" @cancel="ai.cancel" @retry="ai.run('reportSummary')" />
          <p class="article-reading-note">蓝色文字是可以核对的判断节点。点击后会在原处打开依据卡片，不必离开当前阅读位置。<button type="button" @click="profileSheet = true">查看本报告使用的全部个人资料</button></p>
          <DetailPopover v-if="ai.result.value" title="这段 AI 解读使用了什么" label="查看 AI 解读依据" side="right" class="article-meta-link">
            <template #trigger>查看 AI 解读依据</template>
            <AiResultMeta :result="ai.result.value" />
          </DetailPopover>
        </section>

        <section :id="sectionDomId('diagnosis')" class="article-section report-diagnosis" data-section-id="diagnosis" data-report-section>
          <header class="article-heading"><p>综合诊断</p><h2>你现在的优势，只有穿过短板与风险，才会变成真正的选择</h2></header>
          <div class="article-prose">
            <p>从现有资料看，这份报告并不支持用单一标签概括你。更准确的读法，是同时看见你已经具备的资源、仍然薄弱的环节，以及外部环境为你留下的窗口。</p>
            <template v-for="(value, key) in report.swot" :key="key">
              <h3>{{ labels[key] ?? '补充判断' }}</h3>
              <p>{{ content(value) || '本版还没有形成足够具体的判断，需要在后续咨询和行动中继续补充。' }}</p>
            </template>
          </div>
          <blockquote v-if="pendingItems.length">真正决定下一步的，不是再收集更多泛泛的信息，而是把 {{ pendingItems.map((item) => item.name).slice(0, 3).join('、') }} 这些尚不确定的部分变成可观察的结果。</blockquote>
        </section>

        <section v-for="(section, sectionIndex) in report.sections" :id="sectionDomId(section.id)" :key="section.id" class="report-chapter article-section" :data-section-id="section.id" data-report-section>
          <header class="article-heading article-heading--chapter">
            <p>{{ chapterLabel(sectionIndex) }} · {{ section.items?.length ?? 0 }} 项判断</p>
            <h2>{{ sectionTitle(section) }}</h2>
            <span>{{ sectionLead(section) }}</span>
          </header>
          <div class="article-prose">
            <article v-for="(item, index) in section.items" :id="sectionDomId(itemId(item))" :key="item.index + '-' + item.name" class="article-finding" :data-section-id="itemId(item)" data-report-section>
              <header class="article-finding__heading">
                <span>{{ sectionIndex + 1 }}.{{ index + 1 }}</span>
                <h3>
                <DetailPopover :title="item.name + ' · 判断依据'" :label="'查看“' + item.name + '”的判断依据'" side="right" class="article-evidence-link">
                  <template #trigger>{{ item.name }}</template>
                  <p class="evidence-popover__label">{{ item.evidence?.trim() ? '支撑这项判断的记录' : '当前还缺少什么' }}</p>
                  <p class="evidence-popover__quote">{{ evidenceText(item.evidence) || '这项判断暂时没有可核对的记录，因此只能作为待验证假设。' }}</p>
                  <dl class="evidence-popover__facts"><div><dt>判断状态</dt><dd>{{ confidenceText(item) }}</dd></div><div><dt>所在章节</dt><dd>{{ sectionTitle(section) }}</dd></div><div><dt>报告版本</dt><dd>第 {{ report.version }} 版 · {{ reportDate(report.generated_at) }}</dd></div></dl>
                  <RouterLink class="btn btn--primary evidence-popover__action" :to="askLink(item)">带着这条去核对</RouterLink>
                </DetailPopover>
                </h3>
                <em :class="{ 'is-pending': isPending(item) }">{{ confidenceText(item) }}</em>
              </header>
              <p class="article-finding__conclusion">{{ item.conclusion }}</p>
              <p class="article-finding__reading"><template v-if="isPending(item)">这项内容目前仍是待验证假设，不能据此形成最终选择。下一步应当用一次可观察的行动补足证据。</template><template v-else-if="sectionIndex === 0">它描述的是你当前较稳定的个人线索，将影响任务选择与学习方式，但不构成永久的人格定义。</template><template v-else-if="sectionIndex === 1">这项判断连接了个人条件与外部要求，后续需要通过真实任务或反馈继续校准。</template><template v-else>它的意义在于明确选择边界：保留调整空间，同时避免在证据不足时扩大投入。</template></p>
            </article>
            <p v-if="section.method" class="article-method">这一章的判断采用了<DetailPopover :title="sectionTitle(section) + ' · 判断方式'" :label="'查看' + sectionTitle(section) + '的判断方式'" side="right" class="article-evidence-link"><template #trigger>这一分析方法</template><p>{{ section.method }}</p><p class="evidence-popover__meta">方法用于组织证据和形成问题，不等于给你下最终定义。</p></DetailPopover>。它帮助把分散信息组织起来，但每一项结论仍应回到具体经历中核对。</p>
          </div>
        </section>

        <section v-if="pendingItems.length || ai.result.value?.data.moves?.length" :id="sectionDomId('actions')" class="article-section report-actions" data-section-id="actions" data-report-section>
          <header class="article-heading"><p>行动结语</p><h2>下一步不是继续猜，而是把关键问题做成验证</h2></header>
          <div class="article-prose">
            <p>一份诊断报告的价值，不在于把你描述得多么完整，而在于让下一次选择比上一次更有依据。下面这些动作应当优先服务于“减少不确定性”。</p>
            <ol class="action-list">
              <li v-for="move in ai.result.value?.data.moves ?? []" :key="move.label"><strong>{{ move.label }}</strong><span>{{ move.why }}</span></li>
              <li v-for="item in pendingItems" :key="item.index"><strong>验证{{ item.name }}</strong><span>{{ item.conclusion }} 可以通过一次具体项目、访谈、课程任务或真实投递来验证；完成后再回到报告更新判断。</span></li>
            </ol>
          </div>
        </section>

        <section :id="sectionDomId('references')" class="article-section report-references" data-section-id="references" data-report-section>
          <header class="article-heading"><p>附记</p><h2>资料与方法，不打断正文，但始终可以追溯</h2></header>
          <div class="article-prose"><p>这份报告允许使用系统中已经收集的全部用户信息，但“使用”不等于“全部堆进正文”。正文只保留能解释现状、差距、风险和行动的问题；原始画像、课程、成绩、资料来源与分析方法则放在附录中，供你随时核对。</p></div>
          <p class="reference-links"><button type="button" @click="profileSheet = true">阅读完整个人资料</button><button v-if="report.swot || report.methodologies?.length || report.sources?.length" type="button" @click="appendix = true">查看分析方法与来源</button></p>
        </section>
        <slot />
      </div>

      <aside class="report-toc-rail" :class="{ 'is-open': tocOpen }">
        <nav class="report-toc" aria-label="报告章节目录">
          <button class="report-toc__handle" :aria-expanded="tocOpen" aria-label="展开报告章节目录" @click="tocOpen = !tocOpen"><span class="report-toc__line" aria-hidden="true" /><span class="report-toc__ticks" aria-hidden="true"><i v-for="item in tocItems" :key="item.id" :class="{ 'is-active': activeSection === item.id, 'is-child': item.level === 'item' }" /></span></button>
          <div class="report-toc__panel">
            <p>报告目录 · {{ tocItems.length }} 个节点</p>
            <button v-for="item in tocItems" :key="item.id" :class="[{ 'is-active': activeSection === item.id }, item.level === 'section' ? 'report-toc__section' : 'report-toc__item']" @click="scrollToSection(item.id)"><span>{{ item.title }}</span></button>
          </div>
        </nav>
      </aside>
    </div>

    <InfoSheet :open="profileSheet" shape="panel" title="本报告使用的个人资料" @close="profileSheet = false">
      <p class="sheet-intro">这里汇总账号中已经保存的个人画像、课程和成绩。它们都是报告可以使用的输入；没有记录的部分不会被 AI 自行补写。</p>
      <p v-if="profileError" class="report-profile-error" role="status">{{ profileError }}</p>
      <section v-for="section in profileSections" :key="section.key" class="profile-sheet-section">
        <h2>{{ section.title }}</h2>
        <article v-for="field in section.fields" :key="field.key" class="profile-sheet-field"><header><strong>{{ profileLabel(field.key, field.label || field.key) }}</strong><span>{{ sourceNames[field.source] || field.source }}</span></header><p>{{ profileValue(field) }}</p><small><span v-if="field.confidence !== undefined">可信度 {{ Math.round(field.confidence * 100) }}% · </span>更新于 {{ fieldDate(field.updated_at) }}</small><ul v-if="field.evidence?.length"><li v-for="evidence in field.evidence" :key="evidence">{{ evidence }}</li></ul></article>
      </section>
      <section v-if="academic?.courses?.length" class="profile-sheet-section"><h2>课程记录 · {{ academic.courses.length }} 门</h2><div class="academic-prose"><article v-for="course in academic.courses" :key="course.name + '-' + course.weekday + '-' + course.start_period"><h3>{{ course.name }}</h3><p>{{ weekday(course.weekday) }}<template v-if="course.start_period">，第 {{ course.start_period }}–{{ course.end_period ?? course.start_period }} 节</template><template v-if="course.place">，上课地点为 {{ course.place }}</template><template v-if="course.teacher">，任课教师为 {{ course.teacher }}</template>。</p></article></div></section>
      <section v-if="academic?.grades?.length" class="profile-sheet-section"><h2>成绩记录 · {{ academic.grades.length }} 条</h2><div class="academic-prose"><article v-for="grade in academic.grades" :key="grade.name + '-' + grade.term"><h3>{{ grade.name }}</h3><p>{{ grade.term || '未注明学期' }}的记录中，成绩为 {{ grade.score || '未提供' }}<template v-if="grade.credit">，课程学分为 {{ grade.credit }}</template>。</p></article></div></section>
      <section v-if="profileGaps.length" class="profile-sheet-section"><h2>还缺的资料</h2><article v-for="gap in profileGaps" :key="gap.key" class="profile-sheet-field is-gap"><header><strong>{{ gap.label || profileLabel(gap.key, gap.key) }}</strong></header><p>{{ gap.reason }}</p><small v-if="gap.suggested_next_action">下一步：{{ gap.suggested_next_action }}</small></article></section>
      <p v-if="!profileSections.length && !academic?.courses?.length && !academic?.grades?.length" class="ws-muted">当前没有读取到个人资料。</p>
    </InfoSheet>

    <InfoSheet :open="appendix" shape="panel" title="分析方式与资料来源" @close="appendix = false">
      <p class="sheet-intro">这些信息解释报告如何形成。它们不是装饰，也不替代对具体经历的核对。</p>
      <section v-if="report.swot && Object.keys(report.swot).length" class="appendix-section"><h2>优势、短板与外部条件</h2><article v-for="(value, key) in report.swot" :key="key"><h3>{{ labels[key] ?? '补充分析' }}</h3><p>{{ content(value) || '暂未提供' }}</p></article></section>
      <section v-if="report.sections?.some((section) => section.method)" class="appendix-section"><h2>各部分判断方式</h2><article v-for="section in report.sections.filter((value) => value.method)" :key="section.id"><h3>{{ sectionTitle(section) }}</h3><p>{{ section.method }}</p></article></section>
      <section v-if="report.methodologies?.length" class="appendix-section"><h2>方法依据</h2><ul><li v-for="method in report.methodologies" :key="method">{{ method }}</li></ul></section>
      <section v-if="report.sources?.length" class="appendix-section"><h2>资料来源</h2><ul><li v-for="source in report.sources" :key="source"><a v-if="/^https?:\/\//.test(source)" class="ws-text-link" :href="source" target="_blank" rel="noopener noreferrer">{{ source }}</a><span v-else>{{ source }}</span></li></ul></section>
    </InfoSheet>
  </article>
</template>

<style scoped>
.report-document{width:100%}.report-document__grid{display:grid;grid-template-columns:minmax(0,760px) 44px;justify-content:center;gap:54px;align-items:start}.report-paper{min-width:0;padding:0 38px 34px;font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",STSong,serif}.article-section{padding:72px 0 82px;border-bottom:1px solid #dfe5ec;scroll-margin-top:28px}.report-overview{padding-top:54px}.article-heading{max-width:690px;margin-bottom:32px}.article-heading>p{margin-bottom:11px;color:#536172;font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:12px;font-weight:650;letter-spacing:.06em}.article-heading h2{font-size:clamp(28px,3.2vw,40px);font-weight:700;line-height:1.36;letter-spacing:-.025em}.article-heading>span{display:block;max-width:62ch;margin-top:17px;color:var(--c-text-2);font-size:16px;line-height:1.9}.article-heading--chapter{margin-bottom:42px}.article-prose{max-width:66ch}.article-prose p{margin:0 0 1.35em;font-size:17px;line-height:2.05;text-align:justify;text-justify:inter-ideograph}.article-prose--lead p:first-child{font-size:19px;line-height:2}.article-prose h3{margin:32px 0 9px;font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-15);line-height:1.5}.article-prose blockquote,.report-diagnosis blockquote{max-width:62ch;margin:34px 0 0;padding:7px 0 7px 24px;border-left:4px solid #0969da;color:var(--c-text-2);font-size:17px;line-height:1.95}.executive-findings{max-width:690px;margin:42px 0 8px;padding:24px 0 10px;border-top:2px solid #26384a;border-bottom:1px solid #b8c2cd}.executive-findings__title{margin-bottom:6px;color:#26384a;font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:13px;font-weight:700}.executive-findings article{display:grid;grid-template-columns:42px minmax(0,1fr);gap:16px;padding:18px 0;border-top:1px solid #dfe5ec}.executive-findings article>span{padding-top:2px;color:#8a97a5;font-family:ui-monospace,Consolas,monospace;font-size:12px}.executive-findings article>p{margin:0;font-size:16px;line-height:1.85}.executive-findings article strong{display:block;margin-top:5px;font-weight:500}.article-reading-note{max-width:64ch;margin-top:28px;padding-top:20px;border-top:1px solid var(--c-border);color:var(--c-text-3);font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-13);line-height:1.8}.article-reading-note button,.reference-links button{padding:0;border:0;background:transparent;color:#0969da;font:inherit;cursor:pointer}.article-reading-note button:hover,.reference-links button:hover{text-decoration:underline}:deep(.detail-trigger.article-meta-link),:deep(.detail-trigger.article-evidence-link){display:inline;min-width:0;min-height:0;padding:0;border:0;border-radius:0;background:transparent!important;color:#0969da!important;font:inherit;font-weight:700;line-height:inherit;text-decoration-line:underline;text-decoration-color:rgba(9,105,218,.62);text-decoration-thickness:1px;text-underline-offset:3px;vertical-align:baseline;cursor:pointer}:deep(.detail-trigger.article-meta-link){margin-top:13px;font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-13);font-weight:500;text-decoration-style:dashed}:deep(.detail-trigger.article-evidence-link):hover,:deep(.detail-trigger.article-evidence-link):focus-visible,:deep(.detail-trigger.article-meta-link):hover{background:transparent!important;text-decoration-color:#0969da;text-decoration-thickness:2px}:deep(.detail-trigger.article-evidence-link):focus-visible,:deep(.detail-trigger.article-meta-link):focus-visible{outline:2px solid #0969da;outline-offset:3px}:deep(.detail-trigger.article-evidence-link--summary){font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:14px}.article-finding{padding:26px 0 30px;border-top:1px solid #dfe5ec;scroll-margin-top:28px}.article-finding__heading{display:grid;grid-template-columns:42px minmax(0,1fr) auto;gap:16px;align-items:baseline;margin-bottom:12px;font-family:var(--font-sans,"Microsoft YaHei",sans-serif)}.article-finding__heading>span{color:#8a97a5;font-size:12px;font-variant-numeric:tabular-nums}.article-finding__heading h3{margin:0;font-size:17px;line-height:1.55}.article-finding__heading em{color:#617080;font-size:12px;font-style:normal;white-space:nowrap}.article-finding__heading em.is-pending{color:var(--c-attention-strong)}.article-finding__conclusion{margin:0 0 8px 58px!important;font-size:18px!important;font-weight:600;line-height:1.75!important;text-align:left!important}.article-finding__reading{margin:0 0 0 58px!important;color:var(--c-text-2);font-size:15px!important;line-height:1.9!important;text-align:left!important}.article-method{margin-top:34px!important;padding-top:20px;border-top:1px solid var(--c-border);color:var(--c-text-2);font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-14)!important}.evidence-popover__label{color:var(--c-text-3);font-size:var(--fs-12);font-weight:600}.evidence-popover__quote{margin-top:7px;padding:12px 14px;border-left:2px solid #0969da;background:var(--c-surface-2);font-size:var(--fs-14);line-height:1.8}.evidence-popover__meta{margin-top:10px;color:var(--c-text-3);font-size:var(--fs-12);line-height:1.7}.evidence-popover__facts{margin-top:16px;border-top:1px solid var(--c-border)}.evidence-popover__facts>div{display:grid;grid-template-columns:76px minmax(0,1fr);gap:12px;padding:9px 0;border-bottom:1px solid var(--c-border)}.evidence-popover__facts dt{color:var(--c-text-3);font-size:var(--fs-12)}.evidence-popover__facts dd{font-size:var(--fs-12)}.evidence-popover__action{width:100%;margin-top:16px}.action-list{margin:24px 0 0;padding:0;list-style:none;counter-reset:action}.action-list li{display:grid;grid-template-columns:30px minmax(0,1fr);gap:5px 14px;padding:17px 0;border-top:1px solid var(--c-border);counter-increment:action}.action-list li::before{grid-row:1 / 3;content:counter(action);color:#0969da;font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-13);font-variant-numeric:tabular-nums}.action-list strong{font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-15)}.action-list span{color:var(--c-text-2);font-size:var(--fs-14);line-height:1.8}.reference-links{display:flex;flex-wrap:wrap;gap:12px 24px;margin-top:22px;font-family:var(--font-sans,"Microsoft YaHei",sans-serif);font-size:var(--fs-14)}.report-profile-error{margin-bottom:24px;padding:13px 15px;border-left:3px solid var(--c-attention);background:var(--c-attention-weak);color:var(--c-attention-strong);font-size:var(--fs-13)}
.report-toc-rail{position:fixed;top:50%;right:max(42px,calc((100vw - 1074px)/2));z-index:38;width:44px;height:min(420px,calc(100vh - 112px));max-height:calc(100vh - 112px);transform:translateY(-50%)}.report-toc{position:absolute;top:0;right:0;width:44px;height:100%;min-height:0;border:1px solid rgba(191,202,214,.72);border-radius:14px;background:rgba(255,255,255,.56);box-shadow:0 12px 30px rgba(22,34,48,.08);backdrop-filter:blur(14px) saturate(135%);-webkit-backdrop-filter:blur(14px) saturate(135%);transition:width 150ms ease,background-color 150ms ease,border-color 150ms ease,box-shadow 150ms ease}.report-toc__handle{position:absolute;top:0;right:0;z-index:2;width:42px;height:100%;padding:0;border:0;background:transparent;cursor:pointer}.report-toc__line{position:absolute;top:18px;bottom:18px;left:20px;width:1px;background:var(--c-border-strong)}.report-toc__ticks{position:absolute;inset:15px 0;display:flex;flex-direction:column;justify-content:space-around;align-items:center}.report-toc__ticks i{display:block;width:7px;height:7px;border:2px solid rgba(255,255,255,.82);border-radius:50%;background:var(--c-border-strong);transition:transform 120ms ease,background-color 120ms ease}.report-toc__ticks i.is-child{width:5px;height:5px}.report-toc__ticks i.is-active{transform:scale(1.45);background:var(--c-primary)}.report-toc__panel{box-sizing:border-box;width:0;height:0;overflow:hidden;opacity:0;pointer-events:none;transition:width 150ms ease,opacity 100ms ease}.report-toc__panel>p{margin-bottom:8px;color:var(--c-text-3);font-size:var(--fs-12);font-weight:600}.report-toc__panel>button{display:block;width:100%;padding:8px;border:0;border-radius:7px;background:transparent;color:var(--c-text-2);font-size:var(--fs-13);text-align:left}.report-toc__panel>button:hover,.report-toc__panel>button.is-active{background:rgba(9,105,218,.09);color:var(--c-primary)}.report-toc__panel>button.report-toc__section{margin-top:7px;font-weight:600}.report-toc__panel>button.report-toc__item{padding:6px 8px 6px 20px;font-size:var(--fs-12)}.report-toc-rail:hover .report-toc,.report-toc-rail.is-open .report-toc,.report-toc:has(:focus-visible){width:286px;border-color:rgba(191,202,214,.86);background:rgba(255,255,255,.78);box-shadow:0 16px 40px rgba(22,34,48,.14)}.report-toc-rail:hover .report-toc__panel,.report-toc-rail.is-open .report-toc__panel,.report-toc:has(:focus-visible) .report-toc__panel{width:240px;height:100%;max-height:100%;overflow-y:auto;padding:16px 10px 16px 14px;opacity:1;pointer-events:auto}.report-toc__handle:focus-visible,.report-toc__panel>button:focus-visible{outline:2px solid var(--c-primary);outline-offset:2px}
.sheet-intro{margin-bottom:22px;color:var(--c-text-2);font-size:var(--fs-13);line-height:1.75}.profile-sheet-section,.appendix-section{padding:22px 0;border-top:1px solid var(--c-border)}.profile-sheet-section h2,.appendix-section h2{margin-bottom:10px;font-size:var(--fs-16)}.profile-sheet-field{padding:14px 0;border-bottom:1px solid var(--c-border)}.profile-sheet-field header{display:flex;justify-content:space-between;gap:14px}.profile-sheet-field header strong{font-size:var(--fs-14)}.profile-sheet-field header span,.profile-sheet-field small{color:var(--c-text-3);font-size:var(--fs-12)}.profile-sheet-field>p{margin-top:6px;color:var(--c-text-2);line-height:1.7}.profile-sheet-field>small{display:block;margin-top:5px}.profile-sheet-field ul,.appendix-section ul{margin-top:8px;padding-left:18px;color:var(--c-text-2);font-size:var(--fs-13);line-height:1.7}.profile-sheet-field.is-gap{padding-left:12px;border-left:2px solid var(--c-attention)}.academic-prose{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px}.academic-prose article,.appendix-section article{padding:12px 0;border-bottom:1px solid var(--c-border)}.academic-prose h3,.appendix-section h3{font-size:var(--fs-14)}.academic-prose p,.appendix-section article p{margin-top:5px;color:var(--c-text-2);font-size:var(--fs-13);line-height:1.75}
@media(max-width:980px){.report-document__grid{grid-template-columns:minmax(0,1fr) 44px;gap:20px}}
@media(max-width:767px){.report-document__grid{display:block}.report-paper{padding:0 20px 28px}.article-section{padding:52px 0 58px}.report-overview{padding-top:36px}.article-heading{margin-bottom:24px}.article-heading h2{font-size:28px}.article-heading>span{font-size:var(--fs-14)}.article-prose p{font-size:16px;line-height:1.92;text-align:left}.article-prose--lead p:first-child{font-size:18px}.executive-findings{margin-top:32px}.executive-findings article{grid-template-columns:30px minmax(0,1fr);gap:10px}.executive-findings article>p{font-size:15px}.article-finding{padding:22px 0 26px}.article-finding__heading{grid-template-columns:32px minmax(0,1fr);gap:10px}.article-finding__heading em{grid-column:2;margin-top:2px}.article-finding__conclusion,.article-finding__reading{margin-left:42px!important}.article-finding__conclusion{font-size:17px!important}.article-reading-note{margin-top:20px}.academic-prose{grid-template-columns:minmax(0,1fr)}.report-toc-rail{position:fixed;right:4px;bottom:86px;top:auto;z-index:40;width:38px;height:38px;max-height:none;transform:none}.report-toc{top:auto;bottom:0;width:38px;height:auto;min-height:38px;border-color:rgba(191,202,214,.8);background:rgba(255,255,255,.72);box-shadow:0 8px 24px rgba(22,34,48,.13)}.report-toc__handle{top:auto;bottom:0;width:36px;height:36px}.report-toc__line{top:7px;bottom:7px;left:17px}.report-toc__ticks{inset:7px 0}.report-toc__ticks i{display:none}.report-toc__ticks i.is-active{display:block;width:9px;height:9px}.report-toc-rail:hover .report-toc{width:38px}.report-toc-rail:hover .report-toc__panel{width:0;height:0;padding:0;opacity:0;pointer-events:none}.report-toc-rail.is-open .report-toc,.report-toc:has(:focus-visible){width:min(300px,calc(100vw - 12px))}.report-toc-rail.is-open .report-toc__panel,.report-toc:has(:focus-visible) .report-toc__panel{width:calc(min(300px,calc(100vw - 12px)) - 38px);height:auto;max-height:calc(100vh - 150px);overflow-y:auto;padding:14px 8px 14px 12px;opacity:1;pointer-events:auto}}
@media(prefers-reduced-motion:reduce){.report-toc,.report-toc__panel,.report-toc__ticks i{transition:none}}
@media print{.report-toc-rail,.article-meta-link,.article-reading-note button,.reference-links{display:none!important}.report-document__grid{display:block}.article-section{break-inside:avoid}:deep(.detail-trigger.article-evidence-link){color:inherit!important;text-decoration:none}}
</style>
