<script setup lang="ts">
import { studentVoice } from '../lib/student-voice'
import EvidenceState from '../components/EvidenceState.vue'
import {STUDY_YEAR_OPTIONS, studyYearLabel} from '../lib/study-year'
import { useRoute, useRouter } from 'vue-router'
/**
 * 个人画像 · v8
 * ---------------------------------------------------------------------------
 * 依据 docs/前端/历史设计/第六版重设计/活的设计语言.md：
 *   数据页的活 = 组织可见（第 3 节）。数据不动时，活来自三件事：
 *     把组织权交还用户（4.2 多视角重组 + FLIP）、结构与溯源显形（4.1 / 4.3）、
 *     状态与不确定性显形（4.4）。
 *
 * v7 相对 v6 的改动（都是把"平铺罗列"换成"有结构的组织"）：
 *   ① 分层：每条判断先给一句能扫完的话，完整句子、门槛解释与原始材料放进同一条目的第二层。
 *      每条信息行同理：值一行、来源与时间一行，折叠开关并进注脚行。
 *      1280 下整页 7534px → 4115px，靠的是分层，没有删掉任何一条信息。
 *   ② 判断与缺口不再各说一遍：A / B 两层只讲"已有的事实撑起了什么"，缺口只在 C 段讲全
 *      （缺什么 / 为什么重要 / 卡住哪几条判断 / 去哪补 / 现在能做什么）；B 段里虚线的那条
 *      依赖直接落到 C 段对应那张卡（带 C1/C2 编号），同一条缺口全页只出现一次完整表达。
 *   ③ A 段行的基线是固定的：标签列 78px、值一行、注脚一行；「支撑 N 条判断」与折叠开关
 *      都属于这条信息的注脚，跟着值走，值再长也不会把按钮挤到别的位置。
 *      （这两个东西在 v8 里不再是按钮，见 ⑥——基线不变，但命中区变成整行。）
 *   ④ 依赖关系优先消费契约里的 workspace.dependencies（DependencyEdgeView[]，
 *      含 via_profile_keys）；demo 才退回本地资料对应表，且**不混用**——
 *      用哪一套由"契约里有没有可匹配的边"一次性决定。
 *   ⑤ 可信度优先用后端的 overall_confidence / coverage；demo 没有时才自算，
 *      并明确标成资料对应关系。
 *
 * v8 相对 v7 的改动（只改行内交互的触控与可达性，不动信息本身）：
 *   ⑥ v7 为了行高，把行内动作压成了注脚尺寸（「支撑 N 条判断」22px、
 *      「原始依据与操作」20px、B 段「完整判断与依据」22px）。v8 不再放大这些小按钮——
 *      **整行就是命中区**：A 段的每一行、B 段的每一条判断各自是一个真正的
 *      <button>（Enter / Space 可开，带 aria-expanded / aria-controls），
 *      折叠外只留注脚大小的信息与状态指示，动作全部移进折叠内，
 *      在折叠内用 ≥44px 的行承载（含双向跳转：A↔B、B→C）。
 *      行高节奏因此不回退：折叠是用户发起的，默认态的行高与 v7 一致。
 *   ⑦ 依赖 chip（「靠 A 的 专业 / 兴趣 / …」）在折叠外只做**信息**（哪几条、缺哪几条、
 *      缺的落在 C 段第几张卡），可点的是折叠内的 44px 行——不再有 24px 的可点 chip。
 *   ⑧ 视角切换、子筛选、度量口径折叠、缺口动作、页头按钮统一补到 ≥44px。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { LayoutGroup, motion } from 'motion-v'
import { demo } from '../store'
import { COLLECT_ITEMS, STUDENT } from '../data/student'
import type { ProfileField } from '../data/types'
import DetailPopover from '../components/DetailPopover.vue'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import EmptyState from '../components/EmptyState.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import SourceChip from '../components/SourceChip.vue'
import StatTile from '../components/StatTile.vue'
import StatusBanner from '../components/StatusBanner.vue'
import ProfileInsights from '../components/ProfileInsights.vue'
import AcademicVerification from '../components/AcademicVerification.vue'
import FormConflict from '../components/FormConflict.vue'
import { backendDemo } from '../lib/backend-demo'
import { resolveDisplayName } from '../lib/display-name'
import { backendClient } from '../api/backend-client'
import { useProfileWorkspace } from '../lib/use-profile-workspace'
import { useProfileFields } from '../lib/use-profile-fields'
import { useProfileConclusions } from '../lib/use-profile-conclusions'
import { useProfileNavigation } from '../lib/use-profile-navigation'
import { useProfileCorrection } from '../lib/use-profile-correction'
import ProfileDossier from './profile/ProfileDossier.vue'
import EnrollmentCard from './profile/EnrollmentCard.vue'

const profileTab = ref<'facts' | 'judgments' | 'gaps' | 'sources'>('facts')
const profileRoute = useRoute()
const router = useRouter()
const verificationOpen = ref(false)
watch(() => profileRoute.query.tab, (tab) => {
  if (typeof tab === 'string' && ['facts','judgments','gaps','sources'].includes(tab)) profileTab.value = tab as typeof profileTab.value
}, { immediate: true })
watch(profileTab, (tab) => {
  // Keep the URL in sync so the same deep link can reopen the panel later.
  const desired = tab === 'facts' ? undefined : tab
  const current = typeof profileRoute.query.tab === 'string' ? profileRoute.query.tab : undefined
  if (current === desired) return
  const query = { ...profileRoute.query }
  if (desired) query.tab = desired
  else delete query.tab
  void router.replace({ query })
})
watch(() => profileRoute.query.section, async section => { if(section === 'enrollment') { await nextTick(); document.getElementById('enrollment-title')?.scrollIntoView({block:'start'}) } }, {immediate:true})
const insights = ref<InstanceType<typeof ProfileInsights> | null>(null)

/** 来源视角：把原来的「来源筛选」并进视角切换，不再两套并存 */
const SOURCE_GROUPS: { key: string; label: string; from: ProfileField['source'][] }[] = [
  { key: 'school', label: '学校档案', from: ['学校', '学信网', '教务系统', '客观记录'] },
  { key: 'talk', label: '咨询记录', from: ['对话'] },
  { key: 'material', label: '材料与分析', from: ['简历材料', '综合分析', '导师记录'] },
  { key: 'behavior', label: '行为记录', from: ['行为记录'] },
  { key: 'user', label: '本人填写', from: ['本人填写'] },
]

const workspace = useProfileWorkspace()
const { loading, serviceError, relatedError, live, livePanel, isVerified, progress, loadWorkspace } = workspace

const fields = useProfileFields({
  live: workspace.live,
  livePanel: workspace.livePanel,
  originalLive: workspace.originalLive,
  progress: workspace.progress,
  getFieldDeps: () => conclusions.fieldDeps.value,
  refreshRelated: workspace.loadWorkspace,
})
const { fieldValue, valueParts, known, statusLine, confBands, coverageNote, groups, clues, denyClue, conflicts, resolveConflict, profileActionError, profileActionsPending } = fields

const conclusions = useProfileConclusions({
  live: workspace.live,
  known: fields.known,
  rowsBase: fields.rowsBase,
  fieldLabels: fields.fieldLabels,
  missing: fields.missing,
})
const { depsSourceNote, depsMixed, conclusionMap, fieldDeps, reportFields, needsCheck, priorityConclusions, changedFields, recomputeIds, needsRecompute, gapRows, priorityGaps, gapIndex } = conclusions

const navigation = useProfileNavigation({
  profileTab,
  conclusionMap: conclusions.conclusionMap,
  fieldDeps: conclusions.fieldDeps,
  reduced: fields.reduced,
})
const { hoverField, hoverConclusion, openField, openConclusion, litFields, litConclusions, toggleConclusion, conclRowClick, toggleLingerConclusion, bindConclusion, flashId, jumpToConclusion, gapFlash, jumpToGap, jumpToField, fieldReading, readField, readAnalysis, stopJumpTimers } = navigation

const correctionState = useProfileCorrection({
  live: workspace.live,
  livePanel: workspace.livePanel,
  originalLive: workspace.originalLive,
  serviceError: workspace.serviceError,
  openField: navigation.openField,
  fieldValue: fields.fieldValue,
  inspect: (key, label) => { insights.value?.inspect(key, label) },
  refreshRelated: workspace.loadWorkspace,
})
const { correction, value, preferenceItems, multiple, correctionError, correctionLatest, correctionConflictRows, saveBusy, inspectField, edit, save, confirmCorrectionConflict, deleting, deleteBusy, deleteError, askDelete, closeDelete, confirmDelete } = correctionState

function changeTab(tab: 'facts' | 'judgments' | 'gaps' | 'sources') { profileTab.value = tab }

/** 画像里已有自述、但采集来源还不足以算「拿到」的字段：单独展示，不与完全缺失混在一起。 */
const unverifiedCollection = computed(() =>
  (backendDemo.state.liveWorkspace?.collection_panel?.items ?? []).filter(item => item.state === 'unverified'),
)
const confirmingKey = ref('')
const confirmError = ref('')
async function confirmCollection(item: { key: string; label: string }) {
  if (!live.value || confirmingKey.value) return
  const field = livePanel.value?.fields?.find(field => field.key === item.key)
  if (!field) return
  confirmingKey.value = item.key
  confirmError.value = ''
  try {
    await backendClient.correct(item.key, field.value as string | string[], field.updated_at ?? null, field.attributes ?? {})
    await loadWorkspace()
  } catch (error) {
    confirmError.value = error instanceof Error ? error.message : '确认没有保存成功，原记录仍然保留，请重试。'
  } finally {
    confirmingKey.value = ''
  }
}

const identity = computed(() => {
  const pick = (key: string) => known.value.find((row) => row.key === key)?.value
  const name = live.value ? pick('student_name') || pick('name') || resolveDisplayName() : STUDENT.name
  const school = live.value ? pick('school') : demo.state.profileEdits.school ?? STUDENT.school
  const grade = live.value ? pick('study_year') || pick('grade') : demo.state.profileEdits.grade ?? demo.use.scenario.value.grade
  if (!live.value && demo.state.account === 'fresh') return { name: '新用户', line: '学校与年级待补充' }
  return { name: name || '个人档案', line: [school, pick('major'), grade ? studyYearLabel(grade) : pick('degree_level')].filter(Boolean).join(' · ') || '学校与年级待补充' }
})
const profileSnapshot = computed(() => {
  const directions = backendDemo.state.liveDirections
  const selected = directions?.plans?.find(plan => plan.id === directions.selected_id || plan.selected)
  if (selected) return {
    label: '当前验证方向',
    title: selected.name,
    state: '已选择，继续验证',
    detail: selected.main_risk || '适合程度仍需结合具体经历与岗位要求核对。',
  }
  const first = priorityConclusions.value[0]
  if (!first) return {
    label: '画像状态',
    title: '资料正在形成',
    state: '需要补充',
    detail: known.value.some(row => row.entryType === 'experience' || row.entryType === 'interest')
      ? '已有经历或偏好可用于继续探索；可以查看整体分析，方向仍由你逐步比较和选择。'
      : '可以从一段真实经历或一个偏好开始，资料不齐也能继续交流。',
  }
  return {
    label: '当前重点判断',
    title: first.label,
    state: first.missingKeys.length ? `仍缺 ${first.missingKeys.length} 项资料` : '待继续验证',
    detail: `${studentVoice(first.brief || first.full)}。这是已有分析线索，尚不代表已选择该方向。`,
  }
})
const enrollmentRows = computed(() => {
  const pick = (...keys: string[]) => known.value.find((row) => keys.includes(row.key))
  return [
    { label: '学校', row: pick('school', 'university') },
    { label: '专业', row: pick('major', 'major_name') },
    { label: '当前学习阶段', row: pick('study_year', 'grade') },
    { label: '学历层次', row: pick('degree_level', 'education') },
    { label: '在读状态', row: pick('student_status', 'enrollment_status', 'study_status') },
  ].map(item => ({ ...item, value: item.row ? fieldValue(item.row) : '待补充' }))
})
function exportProfile(){
  if (loading.value || (live.value && !livePanel.value)) return
  const data = {schema_version: 1, exported_at: new Date().toISOString(), scope: 'current_profile_snapshot', history_included: false,
    profile: live.value ? livePanel.value : {fields: known.value}, collection: live.value ? backendDemo.state.liveWorkspace?.collection_panel : undefined}
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`职引-个人画像-${identity.value.name}-${new Date().toISOString().slice(0,10)}.json`;a.click();URL.revokeObjectURL(url)
}

/** 覆盖度环：进入页面从 0 生长到实际值；reduced-motion 直接给终值 */
onBeforeUnmount(() => {
  stopJumpTimers()
})

onMounted(()=>{ void loadWorkspace() })
</script>

<template>
  <div class="ws-page profile-page p7" :aria-busy="loading">
    <p class="sr-only" role="status" aria-live="polite">{{ loading ? '正在读取个人画像…' : '' }}</p>
    <PageHeading title="个人画像" description="把零散经历整理成可核对、可继续验证的个人画像。"><template #meta><div class="c2-page-meta"><span v-if="live">{{ livePanel ? '已读取的档案' : loading ? '正在读取档案' : '尚未读取档案' }}</span><span>{{ progress.known }} 条已知 · {{ progress.gap }} 条待补充</span></div></template>
      <RouterLink class="btn btn--primary" to="/chat">补充信息<UiIcon name="arrow" :size="16" /></RouterLink>
      <button class="btn" :disabled="loading || (live && !livePanel)" @click="exportProfile"><UiIcon name="download" :size="16"/>导出画像</button>
    </PageHeading>

    <StatusBanner
      v-if="serviceError"
      tone="error"
      size="sm"
      :message="serviceError"
      retry-label="重试读取"
      :retrying="loading"
      @retry="loadWorkspace"
    />
    <StatusBanner
      v-if="relatedError"
      tone="warning"
      size="sm"
      :message="relatedError"
      :dismissible="false"
    />


    <ProfileDossier
      :identity="identity"
      :progress="progress"
      :conf-bands="confBands"
      :loading="loading"
      :live-panel="livePanel"
      :service-error="serviceError"
      :profile-snapshot="profileSnapshot"
      :priority-conclusions="priorityConclusions"
      :priority-gaps="priorityGaps"
      :known="known"
      :needs-check="needsCheck"
      @tab="changeTab"
      @jump-conclusion="jumpToConclusion"
      @verify="verificationOpen = true"
    />

    <EnrollmentCard :enrollment-rows="enrollmentRows" :is-verified="isVerified" @verify="verificationOpen = true" />






    <!-- ═══ A · 我知道什么 ═══ -->
    <section class="p7-block" aria-labelledby="p7-a-title">
      <header class="profile-facts-head"><div><span class="profile-focus-kicker">资料底稿</span><h2 id="p7-a-title">组成这份画像的信息 <DetailPopover title="资料底稿说明" label="查看资料底稿说明"><p>点开一项可核对来源、可信度和关联判断。</p></DetailPopover></h2></div><button class="btn" type="button" @click="profileTab='sources'">资料来源<UiIcon name="arrow" :size="14"/></button></header>

      <!-- 全量资料按主题展开，不设置搜索、范围或组织方式筛选。 -->
      <LayoutGroup>
        <motion.div class="p7-groups" :layout="true" :layout-dependency="0" :transition="{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }">
          <StatusBanner v-if="profileActionError" tone="error" :message="profileActionError" retry-label="重试读取" :retrying="loading" @retry="async () => { await loadWorkspace(); if (!serviceError) profileActionError = '' }" />
          <!-- 系统理解与事实分开：线索必须能单独展示、单独否认。 -->
          <section v-if="clues.length" class="p7-group p7-clues" aria-labelledby="p7-clues-title">
            <header class="p7-group__head">
              <h3 id="p7-clues-title">系统基于证据的理解</h3>
              <span class="p7-group__hint">等待核对的线索，不是事实结论</span>
              <span class="p7-group__count">{{ clues.length }} 条</span>
            </header>
            <ul class="p7-rows">
              <li v-for="clue in clues" :key="clue.id" class="p7-row p7-clue">
                <div class="p7-clue__body">
                  <p class="p7-clue__text">{{ clue.text }}</p>
                  <details v-if="clue.evidence.length" class="p7-clue__evidence"><summary>查看依据（{{ clue.evidence.length }} 段用户原话）</summary><p v-for="(quote, index) in clue.evidence" :key="index">{{ quote }}</p></details>
                </div>
                <button class="ws-text-button" type="button" :disabled="profileActionsPending.includes('deny:' + clue.id)" @click="denyClue(clue.id)">{{ profileActionsPending.includes('deny:' + clue.id) ? '正在更新…' : '不是这样' }}</button>
              </li>
            </ul>
          </section>
          <!-- 冲突并存：当前值不改，另一种说法单独列出，由用户裁定。 -->
          <section v-if="conflicts.length" class="p7-group p7-conflicts" aria-labelledby="p7-conflicts-title">
            <header class="p7-group__head">
              <h3 id="p7-conflicts-title">有两种说法待核对</h3>
              <span class="p7-group__hint">当前记录没有改；选择以哪一版为准</span>
              <span class="p7-group__count">{{ conflicts.length }} 条</span>
            </header>
            <ul class="p7-rows">
              <li v-for="item in conflicts" :key="item.id" class="p7-row p7-conflict">
                <div class="p7-conflict__body">
                  <p class="p7-conflict__title">{{ item.label }}</p>
                  <p class="p7-conflict__line"><span>当前记录</span>{{ item.currentValue }}</p>
                  <p class="p7-conflict__line p7-conflict__line--new"><span>另一种说法</span>{{ item.value }}</p>
                  <p class="p7-conflict__reason">{{ item.reason }}</p>
                </div>
                <div class="p7-conflict__actions">
                  <button class="ws-text-button" type="button" :disabled="profileActionsPending.includes('resolve:' + item.id)" @click="resolveConflict(item.id, 'revision')">以新说法为准</button>
                  <button class="ws-text-button" type="button" :disabled="profileActionsPending.includes('resolve:' + item.id)" @click="resolveConflict(item.id, 'current')">保留当前记录</button>
                </div>
              </li>
            </ul>
          </section>
          <motion.section
            v-for="group in groups.filter(group=>group.rows.length)"
            :key="group.key"
            class="p7-group"
            :data-key="group.key"
            :layout="true"
            :layout-dependency="0"
            :transition="{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }"
          >
            <header class="p7-group__head">
              <h3>{{ group.title }}</h3>
              <span v-if="group.hint" class="p7-group__hint">{{ group.hint }}</span>
              <span class="p7-group__count">{{ group.rows.length }} 条</span>
            </header>
            <!-- 空态只有这一处是真正的"没有内容"：分组筛选之后这一类没有记录。
                 所以它用 EmptyState（`kind="search-empty"` 的语义就是"条件太窄"），
                 而不是一句 `.ws-muted` 灰字 —— 灰字与正文长得一样，看不出"这里空了"。 -->
            <EmptyState
              v-if="!group.rows.length"
              class="p7-group__empty"
              kind="search-empty"
              size="sm"
              :next="false"
              :heading-level="4"
              title="这一类暂时没有记录"
              description="换一个视角或清除「只看」的收窄条件，其余信息仍然在别的分组里。"
            />

            <motion.ul class="p7-rows" :layout="true" :layout-dependency="0" :transition="{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }">
              <motion.li
                v-for="row in group.rows"
                :key="row.key"
                class="p7-row"
                :class="{ 'p7-row--lit': litFields.has(row.key), 'p7-row--open': openField === row.key }"
                :data-key="row.key"
                :layout="true"
                :layout-dependency="0"
                :transition="{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }"
                @mouseenter="hoverField = row.key"
                @mouseleave="hoverField = null"
                @focusin="hoverField = row.key"
                @focusout="hoverField = null"
              >
                <div class="p7-row__wrap">
                <!-- 整行就是命中区：这一行的关系与来历都从这一下开始，注脚尺寸只留给信息本身 -->
                <DetailPopover class="profile-fact" :title="row.label" :label="row.label + '：' + fieldValue(row) + '，查看依据'" :model-value="openField === row.key" @update:model-value="(open: boolean) => openField = open ? row.key : null"><template #trigger>
                  <span class="p7-row__label">{{ row.label }}</span>
                  <span class="p7-row__main">
                    <span class="p7-row__value" :title="fieldValue(row)">{{ valueParts(row).head }}</span>
                    <span v-if="valueParts(row).hasHint" class="p7-row__hint">{{ valueParts(row).tail }}</span>
                    <span v-if="row.attributeSummary" class="p7-row__hint">{{ row.attributeSummary }}</span>
                    <span class="p7-row__meta">
                      <span class="p7-row__type">{{ row.typeLabel }}</span>
                      <span v-if="row.needsCheck" class="profile-needs-check">{{ row.verificationLabel }}</span><span class="p7-row__cue"><span class="sr-only">查看依据</span><UiIcon name="info" :size="16" /></span>
                    </span>
                  </span>
                </template><p class="profile-fact-value">{{fieldValue(row).slice(0,240)}}{{fieldValue(row).length>240?'…':''}}</p><div class="profile-fact-popover-meta"><SourceChip :source="row.src" :at="row.iso || null"/><span class="profile-fact-verification">{{ row.typeLabel }} · {{ row.verificationLabel }}</span></div><p class="profile-popover-meta">记录时间：{{ row.noted }}</p><p v-if="row.touched" class="profile-popover-meta">本人已更正<template v-if="row.prior">，原内容：{{ row.prior }}</template></p>
                  <div :id="`p7-more-${row.key}`" class="p7-row__more-body">
                    <p v-if="row.attributeSummary" class="profile-popover-meta">{{ row.attributeSummary }}</p>
                    <div class="p7-row__actions">
                      <button class="ws-text-button" type="button" @click="inspectField(row)">深入了解这项信息</button>
                      <button class="ws-text-button" type="button" @click="edit(row)">更正信息<UiIcon name="arrow" :size="14" /></button>
                      <button v-if="live" class="ws-text-button" type="button" @click="askDelete(row)">删除这条</button>
                    </div>
                    <template v-if="row.evidence.length">
                      <p class="p7-facts__title">原始证据</p>
                      <ul class="ws-mini-list p7-evidence">
                        <li v-for="item in row.evidence.slice(0,2)" :key="item">{{ item.slice(0,180) }}{{item.length>180?'…':''}}</li>
                      </ul>
                    </template>
                    <p v-else class="p7-evidence__none">这条没有附原始证据，只有来源与时间。</p>

                    <button v-if="row.evidence.length>2 || row.evidence.some(item=>item.length>180) || fieldValue(row).length>240" class="ws-text-button" @click="readField(row)">阅读完整资料与证据<UiIcon name="arrow" :size="14"/></button>
                    <!-- 关系本身在折叠内可点：跳到 B 段那条判断（≥44px 的行，不再是 24px 的 chip） -->
                    <p v-if="fieldDeps[row.key]?.length" class="p7-facts__title">关联判断 <span class="ws-muted">{{ fieldDeps[row.key]?.length || 0 }} 条</span></p>
                    <ul v-if="fieldDeps[row.key]?.length" class="p7-links">
                      <li v-for="key in fieldDeps[row.key].slice(0, 3)" :key="key">
                        <button class="p7-link" type="button" @click="jumpToConclusion(key)">
                          <span class="p7-link__label">{{ conclusionMap[key]?.label ?? key }}</span>
                          <span class="p7-link__value" :title="studentVoice(conclusionMap[key]?.brief)">{{ studentVoice(conclusionMap[key]?.brief) }}</span>
                          <span class="p7-link__go" aria-hidden="true"><UiIcon name="arrow" :size="14" /></span>
                        </button>
                      </li>
                    </ul>
                    <div v-else class="profile-association-note"><template v-if="reportFields.has(row.key)"><button class="ws-text-button" @click="readAnalysis">查看关联报告<UiIcon name="arrow" :size="14"/></button><p>这项资料关联整份报告，尚未明确对应哪些具体判断。</p></template><p v-else>尚未提供这项资料与具体判断的关联依据。</p></div><button v-if="fieldDeps[row.key]?.length > 3" class="ws-text-button" @click="jumpToConclusion(fieldDeps[row.key][0])">查看全部分析与判断<UiIcon name="arrow" :size="14" /></button>


                  </div>
                </DetailPopover>
                  <button class="p7-row__quick" type="button" :aria-label="'更正：' + row.label" @click="edit(row)">更正</button>
                </div>
              </motion.li>
            </motion.ul>
          </motion.section>
        </motion.div>
      </LayoutGroup>

      <!-- 刷新时的加载态：骨架**盖在仍在 DOM 的内容上**（`SkeletonBlock.vue:21-26`），不摘内容 ——
           原来只有页头按钮的文案从「读取最新档案」变成「正在读取…」，内容区在重新取数的
           整段时间里一动不动，看不出"这次读取正在进行"。
           骨架自己 `aria-hidden`，所以"正在读取"这句话由这里的 `role="status"` 说；
           两者必须是兄弟节点，骨架的 `inset: 0` 才对得上 `.p7-block`（它已 position: relative）。 -->
      <span v-if="loading" class="sr-only" role="status">正在读取最新档案，下面的内容仍然保留。</span>
      <SkeletonBlock v-if="loading" overlay variant="list" :lines="6" />

      <!-- 空态：`kind="profile"` 才画人像（缺省是 notes 的便签）。A 段整块被顶掉，
           所以标题层级显式提到 h2 —— 与它上面那个 <h2>「A 我知道什么」齐平。 -->
      <EmptyState v-if="!known.length && serviceError" kind="profile" :heading-level="2" title="个人信息暂时没有取得" description="这次读取失败，不能据此判断你还没有填写资料。请重新读取后再看。">
        <button class="btn" type="button" :disabled="loading" @click="loadWorkspace">{{ loading ? '正在读取…' : '重新读取' }}</button>
      </EmptyState>
      <EmptyState v-else-if="!known.length && !loading" kind="profile" :heading-level="2" title="暂无个人信息" description="可以从一次咨询开始，也可以导入已有的学校资料。">
        <RouterLink class="btn" to="/chat">开始咨询</RouterLink>
      </EmptyState>
    </section>

    <!-- ═══ B · 所以判断了什么 ═══ -->


    <!-- ═══ C · 还缺什么 ═══ -->


    <!-- 溯源总账。原来是 `.ws-context` 折叠 —— 正是 `DESIGN-LANGUAGE.md:102` 点名的
         「溯源做成一个折叠的『来源』」。这里不是"还有更多内容"，是"我为什么该这么理解"，
         所以用 Foldable 的 **static** 形态：标题照排，内容始终可见。
         改 static 之后本页的折叠层数：度量口径(static) + 行内(1 层) + 这里(static) = **1 层**。 -->





<InfoSheet :open="!!fieldReading" shape="panel" :title="fieldReading?.label || '完整资料'" @close="fieldReading=null"><template v-if="fieldReading"><p class="profile-fact-value">{{fieldValue(fieldReading)}}</p><p class="ws-muted">{{fieldReading.desc}} · {{fieldReading.noted}}</p><h3>原始证据</h3><ul class="ws-mini-list"><li v-for="item in fieldReading.evidence" :key="item">{{item}}</li></ul></template></InfoSheet>
<InfoSheet :open="profileTab === 'judgments'" shape="panel" title="分析与判断" keep-mounted @close="profileTab='facts'"><section><ProfileInsights ref="insights" /></section><section class="p7-block" aria-labelledby="p7-b-title">
      <header class="p7-block__head">
        <div>
          <h2 id="p7-b-title">资料支持的判断</h2>
          <p>查看判断与对应依据；资料不足或变化时，相关结论会保留提示。</p>
        </div>
        <!-- `needs_recompute` 在本页原来是最重的一处印法（红底 + 左红条 + 14/12px 两级字）。
             改成 `StatTile state="recompute"`：与 MeterRow / StatTile 同一把 0–1 的尺，
             状态与读数住在同一格（`StatTile.vue:14-16` 就是为这件事写的）。
             之所以现在**总是**出现（不只是需要重算时）：`state="done"` 那句
             「当前读数是最新的」也是这个字段要说的话 —— 缺了它，用户只能从"没有红条"猜。 -->
        <StatTile
          class="p7-recompute"
          :value="needsRecompute"
          unit="条"
          label="待更新的判断"
          :state="needsRecompute ? 'recompute' : 'done'"
          :trend="{ label: changedFields.size ? `本页更新了 ${changedFields.size} 条信息，相关判断需核对` : needsRecompute ? '服务已标记判断待更新' : '当前未发现待更新标记'  }"
        />
      </header>

      <p class="p7-deps-note"><strong>关系怎么来：</strong>{{ depsSourceNote }}<template v-if="depsMixed">部分关联尚未核实，已单独标注。</template></p>

      <ul class="p7-concls">
        <li
          v-for="item in Object.values(conclusionMap)"
          :key="item.key"
          :ref="(el) => bindConclusion(item.key, el as Element | null)"
          class="p7-concl"
          :class="{ 'p7-concl--lit': litConclusions.has(item.key), 'p7-concl--stale': recomputeIds.has(item.key), 'p7-concl--flash': flashId === item.key, 'p7-concl--plan': item.kind === 'direction', 'p7-concl--open': openConclusion === item.key }"
          :data-concl="item.key"
          @mouseenter="hoverConclusion = item.key"
          @mouseleave="hoverConclusion = null"
          @focusin="hoverConclusion = item.key"
          @focusout="hoverConclusion = null"
          @click="conclRowClick($event, item.key)"
        >
          <!-- 判断这一行就是命中区：展开后才是动作（原来那个 22px 的"完整判断与依据"折叠开关） -->
          <div class="p7-concl__row">
            <button
              class="p7-concl__hit"
              type="button"
              :aria-expanded="openConclusion === item.key"
              :aria-controls="`p7-concl-more-${item.key}`"
              :title="openConclusion === item.key ? `收起「${item.label}」的完整判断与依据` : `展开「${item.label}」的完整判断、原材料与逐条依赖`"
              @click.stop="toggleConclusion(item.key)"
            >
              <span class="p7-concl__label">
                <span class="p7-concl__kind">{{ item.kind === 'direction' ? '方向方案' : item.section }}</span>
                {{ item.label }}
              </span>
              <span class="p7-concl__brief">{{ studentVoice(item.brief) }}</span>
              <span class="p7-concl__side">
                <span class="p7-concl__conf">依据 {{ item.deps.length }} 条资料</span>
                <span v-if="recomputeIds.has(item.key)" class="chip chip--attention">需要重算</span>
                <span class="p7-concl__cue">{{ openConclusion === item.key ? '收起' : '完整判断与依据' }}<UiIcon name="chevron" :size="14" /></span>
              </span>
            </button>
          </div>

          <div class="p7-concl__deps">
            <span class="p7-concl__deps-label">关联资料</span>
            <!-- 折叠外只讲关系这一件事：哪几条、缺哪几条、缺的落在 C 段第几张卡。
                 可点的动作在下面的展开区（≥44px 行），所以这里不再有 24px 的可点 chip。 -->
            <ul class="p7-deps__list">
              <li
                v-for="dep in item.deps"
                :key="dep.key"
                class="p7-dep"
                :class="dep.present ? 'p7-dep--on' : 'p7-dep--missing'"
                :data-dep="dep.key"
                :title="dep.present ? `${dep.label}：${dep.value}` : `${dep.label}还没拿到 —— 展开这条判断可以直接跳到 C 段`"
                @mouseenter="hoverField = dep.key"
                @mouseleave="hoverField = null"
              >
                <i aria-hidden="true" />{{ dep.label }}<small v-if="!dep.present">缺</small><em v-if="!dep.present && gapIndex[dep.key]" class="p7-dep__where">C{{ gapIndex[dep.key] }}</em>
              </li>
              <li v-if="!item.deps.length" class="p7-dep p7-dep--none">逐项关联尚待核对</li>
            </ul>
            <span v-if="depsMixed && !item.depsFromContract" class="p7-concl__prov">资料对应表</span>
          </div>

          <div v-show="openConclusion === item.key" :id="`p7-concl-more-${item.key}`" class="p7-concl__more-body">
            <p class="p7-concl__more-label">这条判断的原话</p>
            <p class="p7-concl__full">{{ studentVoice(item.full) }}</p>
            <p v-if="item.note" class="p7-concl__note">门槛解释：{{ item.note }}</p>
            <p v-if="item.risk" class="p7-concl__note">风险：{{ item.risk }}</p>
            <p v-if="item.ripple" class="p7-concl__note">连带影响：{{ item.ripple }}</p>
            <template v-if="item.evidence.length">
              <p class="p7-concl__more-label">这条判断引用的原材料</p>
              <ul class="ws-mini-list p7-evidence">
                <li v-for="line in item.evidence" :key="line">{{ line }}</li>
              </ul>
            </template>

            <!-- 逐条依赖：这里才是可点的动作，每条一行 ≥44px；缺的直接落到 C 段那张卡 -->
            <p class="p7-concl__more-label">相关资料</p>
            <ul v-if="item.deps.length" class="p7-links">
              <li v-for="dep in item.deps" :key="dep.key">
                <button
                  class="p7-link"
                  :class="dep.present ? '' : 'p7-link--missing'"
                  type="button"
                  @click="dep.present ? jumpToField(dep.key) : jumpToGap(dep.key)"
                >
                  <i class="p7-link__dot" aria-hidden="true" />
                  <span class="p7-link__label">{{ dep.label }}</span>
                  <span class="p7-link__value" :title="dep.present ? dep.value : 'A 段还没有这条信息'">{{ dep.present ? dep.value : '还没拿到' }}</span>
                  <span class="p7-link__go">{{ dep.present ? '核对资料' : '补充信息' }}<UiIcon name="arrow" :size="14" /></span>
                </button>
              </li>
            </ul>
            <p v-else class="p7-evidence__none">尚未提供逐项关联记录，可结合判断原文与引用材料核对。</p>

            <button v-if="item.kind === 'direction'" class="ws-text-button" type="button" @click="toggleLingerConclusion(item.key)">
              看它用到哪几条<UiIcon name="arrow" :size="14" />
            </button>
            <button v-else class="ws-text-button" type="button" @click="insights?.inspectReport(item.full, item.label, item.evidence)">
              深入了解这条判断<UiIcon name="arrow" :size="14" />
            </button>
          </div>
        </li>
      </ul>
    </section></InfoSheet>
<InfoSheet :open="profileTab === 'gaps'" shape="panel" title="待补充信息" @close="profileTab='facts'"><section class="p7-block" aria-labelledby="p7-c-title">
      <header class="p7-block__head">
        <div>
          <h2 id="p7-c-title">建议补充的信息</h2>
          <p>优先完善会影响方向选择的信息。</p>
        </div>
        <span class="p7-block__count">{{ serviceError ? '暂时无法核对' : gapRows.length + ' 条待补充' }}</span>
      </header>
      <p v-if="serviceError" class="ws-field-error" role="alert">{{ serviceError }} <button class="ws-text-button" type="button" :disabled="loading" @click="loadWorkspace">重试</button></p>

      <section v-if="unverifiedCollection.length" class="p7-unverified" aria-labelledby="p7-unverified-title">
        <header class="p7-block__head">
          <div>
            <h3 id="p7-unverified-title">已有你的自述，待核实</h3>
            <p>这些信息已经在画像里，只是来源仍是本人自述；确认后就以「本人确认」记录。</p>
          </div>
          <span class="p7-block__count">{{ unverifiedCollection.length }} 条</span>
        </header>
        <p v-if="confirmError" class="ws-field-error" role="alert">{{ confirmError }}</p>
        <ul class="p7-gaps">
          <li v-for="item in unverifiedCollection" :key="item.key" class="p7-gap">
            <div class="p7-gap__head">
              <h3>{{ item.label }}</h3>
              <EvidenceState state="unverified" />
            </div>
            <p class="p7-gap__why"><span>已有</span>{{ Array.isArray(item.value) ? item.value.join('、') : item.value }}</p>
            <p class="p7-gap__where"><span>状态</span>{{ item.status_text || '画像里已有你的自述，还没有核实' }}</p>
            <div class="p7-gap__actions">
              <button class="btn btn--primary" type="button" :disabled="!!confirmingKey" @click="confirmCollection(item)">
                {{ confirmingKey === item.key ? '正在确认…' : '确认这个值' }}
              </button>
              <button class="ws-text-button" type="button" @click="profileTab = 'sources'; verificationOpen = true">
                去学信网核验<UiIcon name="shield" :size="14" />
              </button>
            </div>
          </li>
        </ul>
      </section>

      <ul v-if="gapRows.length" class="p7-gaps">
        <li
          v-for="(gap, index) in gapRows"
          :key="gap.key"
          class="p7-gap"
          :class="{ 'p7-gap--flash': gapFlash === gap.key, 'p7-gap--first': index === 0 }"
          :data-gap="gap.key"
        >
          <div class="p7-gap__head">
            <span class="p7-gap__index">C{{ index + 1 }}</span>
            <h3>{{ gap.label }}</h3>
            <EvidenceState state="missing" />
          </div>
          <p class="p7-gap__why"><span>为什么重要</span>{{ gap.why }}</p>
          <p class="p7-gap__blocked">
            <span>卡住了</span>
            <template v-if="gap.affects.length">
              <button v-for="affect in gap.affects" :key="affect.key" class="p7-affect" type="button" :title="studentVoice(affect.brief)" @click="jumpToConclusion(affect.key)">
                <i aria-hidden="true" />{{ affect.label }}
              </button>
            </template>
            <template v-else>暂时没有判断直接用到它</template>
          </p>
          <p class="p7-gap__where">
            <span>去哪补</span>{{ gap.origin }}<template v-if="gap.blocked"> · {{ gap.blocked }}</template>
            <template v-if="gap.next"><em class="p7-gap__next">下一步：{{ studentVoice(gap.next) }}</em></template>
          </p>
          <p v-if="gap.ask" class="p7-gap__ask"><span>可以直接回答</span>{{ gap.ask }}</p>
          <div class="p7-gap__actions">
            <RouterLink class="ws-text-link" :to="'/chat?gap=' + encodeURIComponent(gap.key) + '&label=' + encodeURIComponent(gap.label)">在咨询里补充<UiIcon name="arrow" :size="14" /></RouterLink>
            <button class="ws-text-button" type="button" @click="insights?.inspectGap(gap.key, gap.label, { why: gap.why, next: gap.next, ask: gap.ask })">看看需要补充什么</button>
          </div>
        </li>
      </ul>
      <p v-else-if="!serviceError" class="ws-muted p7-none">暂未发现缺口。已记录的信息会继续按来源与可信度核对。</p>
    </section></InfoSheet>
<InfoSheet :open="profileTab === 'sources'" shape="panel" title="资料管理" @close="profileTab='facts'"><Foldable class="p7-sources" static variant="section" title="资料来源与核验说明">
      <div class="ws-context__body">
        <section>
          <h3>可获取的信息</h3>
          <ul class="ws-mini-list">
            <li v-for="item in COLLECT_ITEMS" :key="item.label">
              <strong>{{ item.label }}</strong>
              <p>{{ item.fetchable ? '来自' + item.from : item.blockedBy }}</p>
            </li>
          </ul>
        </section>
        <section>
          <h3>学校资料</h3>
          <p>学籍核验只需在线验证码，不需要账号密码。课表和成绩分别在对应页面管理。</p>
          <button class="ws-text-button" @click="profileTab='facts'; verificationOpen=true">核验学籍<UiIcon name="shield" :size="16" /></button>
          <RouterLink class="ws-text-link" to="/grades">查看我的成绩<UiIcon name="arrow" :size="16" /></RouterLink>
        </section>
      </div>
    </Foldable><aside class="c2-profile-side" aria-label="画像操作与来源">
      <section><h2>核对与管理资料</h2><RouterLink class="btn" to="/chat">补充信息<UiIcon name="plus" :size="16" /></RouterLink><button class="btn" :disabled="loading" @click="loadWorkspace">{{ loading ? '正在读取…' : '刷新个人资料' }}</button><p>点开一条信息，可以查看依据、修改内容。更正后会标出受影响的判断。</p></section>
      <section><h2>这 {{ known.length }} 条从哪里来</h2><div v-for="source in SOURCE_GROUPS" :key="source.key" class="c2-source-row"><span>{{ source.label }}</span><span class="c2-source-track" role="meter" :aria-label="source.label" :aria-valuenow="known.filter(row => source.from.includes(row.desc)).length" :aria-valuemax="Math.max(1, known.length)" aria-valuemin="0"><i :style="{width: known.filter(row => source.from.includes(row.desc)).length / Math.max(1, known.length) * 100 + '%'}" /></span><b>{{ known.filter(row => source.from.includes(row.desc)).length }}</b></div></section>
      <section><h2>{{ identity.name }}</h2><p>{{ identity.line }}</p><p>已记录 {{ progress.known }} 条 · {{ confBands[0]?.title }} {{ confBands[0]?.count ?? 0 }} 条 · {{ confBands[2]?.title }} {{ confBands[2]?.count ?? 0 }} 条</p><Foldable variant="inline" title="查看来源与核实状态"><p>{{ statusLine }}</p><p>{{ coverageNote }}</p><p>这里不显示内部置信度分数；每条记录由来源与核实状态分别说明。</p></Foldable></section>
    </aside></InfoSheet>
    <InfoSheet :open="verificationOpen" shape="panel" title="核验学籍信息" @close="verificationOpen=false"><AcademicVerification /></InfoSheet>
    <!-- 更正是一条信息的小表单（`text` + 两个按钮），不是"从一行钻进去看细节"。
         所以 shape 是 dialog（缺省也是它，这里写出来是为了让形态是**显式**的）。 -->
    <InfoSheet shape="sheet" :open="correction !== null" :title="'更正' + (correction?.label ?? '信息')" @close="!saveBusy && (correction = null)">
      <form @submit.prevent="save">
        <label v-if="correction?.key === 'study_year'" class="ws-field">当前学习阶段<select v-model="value"><option v-for="option in STUDY_YEAR_OPTIONS" :key="option.code" :value="option.label">{{option.label}}</option></select></label>
        <label v-else class="ws-field">更正内容<textarea v-model="value" :disabled="saveBusy" /></label>
        <p v-if="multiple" class="ws-muted">每行填写一项；已有项目的偏好与有效期会保留。</p>
        <label v-for="item in preferenceItems" :key="item.value" class="ws-field">{{ item.value }}
          <select v-if="correction?.entryType === 'interest'" v-model="item.polarity" :disabled="saveBusy"><option :value="undefined">未注明偏好</option><option value="like">喜欢</option><option value="dislike">不喜欢</option><option value="unsure">还不确定</option></select>
          <select v-else v-model="item.state" :disabled="saveBusy"><option :value="undefined">未注明关注状态</option><option value="exploring">正在了解</option><option value="considering">正在考虑</option><option value="selected">已选择</option></select>
        </label>
        <FormConflict v-if="correctionLatest" :rows="correctionConflictRows" @confirm="confirmCorrectionConflict" />
        <p v-if="correctionError" class="ws-field-error" role="alert">{{ correctionError }}</p>
        <div class="ws-inline-actions">
          <button class="btn btn--primary" type="submit" :disabled="saveBusy || correctionLatest !== null">{{ saveBusy ? '正在保存…' : '保存更正' }}</button>
          <button class="btn" type="button" :disabled="saveBusy" @click="correction = null">取消</button>
        </div>
      </form>
    </InfoSheet>
    <InfoSheet shape="dialog" :open="deleting !== null" title="删除这条画像？" @close="closeDelete">
      <p>删除后这条不再作为咨询依据；依赖它的判断会标记待核对。历史聊天记录需要在会话里另行删除。</p>
      <p v-if="deleteError" class="ws-field-error" role="alert">{{ deleteError }}</p>
      <div class="ws-inline-actions">
        <button class="btn btn--danger" type="button" :disabled="deleteBusy" @click="confirmDelete">{{ deleteBusy ? '正在删除…' : '确认删除' }}</button>
        <button class="btn" type="button" :disabled="deleteBusy" @click="closeDelete">取消</button>
      </div>
    </InfoSheet>
  </div>
</template>

<style scoped>
.profile-fact-value{font-size:15px;line-height:1.75;white-space:pre-wrap;overflow-wrap:anywhere}
.p7-row__type{font-size:var(--fs-12);color:var(--c-text-3);white-space:nowrap}
.p7-row__main .p7-row__meta{position:static;transform:none;margin-top:4px}
.profile-fact-verification{font-size:var(--fs-12);color:var(--c-text-2)}
.p7-clue{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp-4)}
.p7-clue__body{min-width:0}
.p7-clue__text{margin:0;font-size:15px;line-height:1.7;color:var(--c-text-1)}
.p7-clue__evidence{margin-top:6px;font-size:12px;color:var(--c-text-3)}
.p7-clue .ws-text-button{flex:none;min-height:44px}
.p7-conflict{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp-4);flex-wrap:wrap}
.p7-conflict__body{min-width:0;flex:1 1 260px}
.p7-conflict__title{margin:0 0 6px;font-size:14px;font-weight:600;color:var(--c-text-1)}
.p7-conflict__line{display:flex;gap:8px;margin:2px 0;font-size:14px;color:var(--c-text-2)}
.p7-conflict__line span{flex:none;min-width:64px;font-size:12px;color:var(--c-text-3);padding-top:2px}
.p7-conflict__line--new{color:var(--c-text-1)}
.p7-conflict__reason{margin-top:6px;font-size:12px;color:var(--c-text-3)}
.p7-conflict__actions{display:flex;gap:var(--sp-3);flex:none;min-height:44px;align-items:center}
.profile-association-note p{font-size:13px;color:var(--c-text-3);margin-top:8px}@media(max-width:600px){.profile-identity__coverage{display:none}}

/* ═══════════════════════════════════════════════════════════════════════════
 * 用底色 / 描边 / 留白分层，不给所有内容套同一张卡片。
 *
 * v8 的触控纪律（只写在页面里，不动全局样式）：
 *   · 行内动作不再靠 padding 硬撑：命中区由**整行**承担（.p7-row__hit / .p7-concl__hit），
 *     注脚尺寸只留给信息与状态；动作全部在展开区内，用 ≥44px 的行承载。
 *   · 页面上真正的独立控件（页头按钮、视角切换、子筛选、度量口径、缺口动作）
 *     一律 min-height: 44px。
 *
 * 【2026-10-14 · P0-2】12px 的用途在这一页收死到"标注"。判据两条，缺一不算正文：
 *   ① 有没有主张 —— 这句话/这个词自己**承载一条要读进去的信息**（字段名、判断、状态、
 *      动作、说明），还是只在为别的信息当**坐标**（时间、来源、序号、计数、刻度、徽章）？
 *   ② 换掉它信息会不会丢 —— 删掉「靠 A 的」只剩一排依赖边、删掉「待补充」标签
 *      缺口卡照样成立 → 它是标注；删掉「专业」整行就不知道在说什么 → 它是正文。
 *   命中"正文"的提到 14px（字段名、说明句、动作词、依赖边）；命中"标注"的留在 12px，
 *   并在各条规则后写明理由。tokens.css 登记的 12px 用途是**来源 / 时间 / 序号 / 计数 /
 *   徽章 / 图表刻度 / chip**，所以留下来的那些不是"没改完"，是有意的。
 *   行距与字号反相关（CRAFT-BRIEF 4.1）：正文档 14px 一律 --lh-snug(1.45)，
 *   16px 保持 1.55，12px 的标注行也跟着收紧到 1.45（原来继承 1.7 在小字上太散）。
 *   中文一律不给正字距；本文件不给任何 <20px 的字号写负字距。
 * ======================================================================== */

.p7 .btn,
.profile-page :deep(.profile-insights .btn) { min-height: 44px; }
.p7 .ws-text-button,
.p7 .ws-text-link,
.p7 .ws-context__body .ws-text-link { min-height: 44px; }

.p7-meter {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-5);
  padding: var(--sp-4) 0 var(--sp-5);
  border-bottom: 1px solid var(--c-border);
}

.p7-ring { width: 84px; height: 84px; flex: none; transform: rotate(-90deg); }
.p7-ring__track { fill: none; stroke: var(--c-surface-3); stroke-width: 7; }
.p7-ring__fill { fill: none; stroke: var(--c-primary); stroke-width: 7; stroke-linecap: round; }

.p7-meter__read { min-width: 0; display: flex; flex-direction: column; gap: var(--sp-2); }
.p7-meter__top { display: flex; align-items: flex-start; flex-wrap: wrap; gap: var(--sp-3) var(--sp-5); }
/* 读数瓦片：`StatTile` 自己把「标签 / 读数 / 同刻度的条 / 脚注」按一列排好，
   所以这里不再有 30px 的裸数字，也不再有第二套图形。 */
.p7-meter__tile { width: min(260px, 100%); }
.p7-meter__line { display: flex; align-items: baseline; gap: var(--sp-3); }
.p7-meter__line h2 { font-size: var(--fs-20); line-height: var(--lh-snug); }
.p7-meter__line p { font-size: var(--fs-14); color: var(--c-text-2); }
.p7-meter__status { font-size: var(--fs-14); color: var(--c-text-2); }

/* 三档读数 + 覆盖度：四个 `StatTile`，同一把 0–1 的尺，排成**一行**。
   原来这里是一根 3px 的小刻度（宽 3px、高 14/9/5px）——与 A/B 段的三格徽标
   相隔 120 行却是第三套画法，同一个量（结实程度）在这页有三种印法。
   一行而不是网格：这一块是"度量摘要"，高度要能跟左边的环对齐，不许比正文还重。 */
/* 四个瓦片排成一行（不是网格）：这一块是"度量摘要"，高度要能跟左边的环对齐。
   实测这一列的可用宽是 456px：4 × 100 + 3 × 8 = 424，四个刚好一行；
   瓦片本身 `min-width: 0`，所以"比较确定 / 依旧不足"这种四字标签会按需收窄。 */
.p7-meter__stats { display: flex; flex-wrap: wrap; align-items: start; gap: var(--sp-2) var(--sp-2); }
.p7-meter__stats > * { flex: 0 1 100px; min-width: 0; }
/* P0-2 保留 12px：这句话是**计量口径标注**（谁算的、什么口径），数字在上一排。 */
.p7-meter__covnote { margin-top: var(--sp-1); font-size: var(--fs-12); line-height: var(--lh-snug); color: var(--c-text-3); }

/* 口径说明：Foldable 的 static 形态 = 一句眉标 + 永远可见的正文。
   它解释上面那根读数条，属于**这一格的脚注**，所以比正文轻一档（12px），
   但仍然默认可见 —— `DESIGN-LANGUAGE.md:102` 不许把"这是怎么来的"折起来。 */
.p7-meter__how :deep(.fold__static-head) { font-size: var(--fs-12); font-weight: var(--fw-regular); color: var(--c-text-3); }
.p7-meter__how :deep(.fold__body) { padding-top: var(--sp-1); }
.p7-meter__how p { max-width: 66ch; margin-top: var(--sp-1); font-size: var(--fs-12); color: var(--c-text-3); line-height: var(--lh-normal); }
.p7-meter__how code { font-size: var(--fs-12); background: var(--c-surface-3); padding: 1px 4px; border-radius: var(--r-sm); }

/* 溯源总账（原来折叠、现在始终可见）：内容从"点开才看到"变成"默认读到"，
   所以同一份信息的排布要更省纵向空间 —— 7 条已知来源在宽屏下用四列网格，
   每条仍然是"名字 + 一句来源"，只是不再各占一整行。
   列表在这里改成 grid（覆盖全局 `.ws-mini-list` 的 flex 单列）：只在本页生效。 */
.p7-sources :deep(.ws-context__body ul) { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--sp-2) var(--sp-5); }
.p7-sources :deep(.ws-context__body li) { min-width: 0; }
@media (max-width: 900px) {
  .p7-sources :deep(.ws-context__body ul) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

.p7-block { margin-top: var(--sp-7); position: relative; }
.p7-block__head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--sp-5); flex-wrap: wrap; margin-bottom: var(--sp-4); }
.p7-block__head h2 { display: flex; align-items: center; gap: var(--sp-3); font-size: var(--fs-20); line-height: var(--lh-snug); }
/* P0-2 提到 14px：这个 A/B/C 不是一个装饰方块，而是**下面整段的章节号**，
   用户是拿它跟「C 段第 3 张卡」这类指代对齐的。提到 14px 后它不再比同行的 20px 标题
   小到像是两个系统；方块的 22px 见方足够容纳单字符。 */
.p7-block__tag { display: inline-grid; place-items: center; width: 22px; height: 22px; flex: none; border-radius: var(--r-sm); background: var(--c-primary-weak); color: var(--c-primary); font-size: var(--fs-14); font-weight: var(--fw-semibold); }
.p7-block__head p { font-size: var(--fs-14); color: var(--c-text-3); margin-top: 6px; max-width: 68ch; }
/* P0-2 保留 12px：纯计数（「3 条待补充」），与行数、序号同类，是标注不是正文。 */
.p7-block__count { font-size: var(--fs-12); color: var(--c-text-3); }

/* 视角切换：这是"组织权在用户手里"的入口，做成实体控件而不是下拉 */
.p7-modes { display: flex; align-items: center; gap: var(--sp-3); }
/* P0-2 提到 14px：它是「组织方式」这组控件的组标签（等于分组标题），不是短标签。 */
.p7-modes__label { font-size: var(--fs-14); color: var(--c-text-3); line-height: var(--lh-snug); }
.p7-modes__set { display: inline-flex; padding: 2px; gap: 2px; border: 1px solid var(--c-border-strong); border-radius: var(--r-md); background: var(--c-surface); }
.p7-mode { min-height: 44px; padding: 0 var(--sp-4); border: 0; border-radius: var(--r-sm); background: transparent; color: var(--c-text-2); font-size: var(--fs-14); }
.p7-mode:hover { color: var(--c-text); background: var(--c-surface-2); }
.p7-mode--on { background: var(--c-primary-weak); color: var(--c-primary); font-weight: var(--fw-medium); }

.p7-groups { display: flex; flex-direction: column; gap: var(--sp-5); }
.p7-group { min-width: 0; }
.p7-group__head { display: flex; align-items: baseline; gap: var(--sp-3); padding-bottom: var(--sp-2); border-bottom: 1px solid var(--c-border-strong); }
.p7-group__head h3 { font-size: var(--fs-16); font-weight: var(--fw-semibold); }
/* P0-2 保留 12px：组头下面的提示是**元数据**（"有几条没来源"），不是正文，字号只为计数一致。 */
.p7-group__hint { font-size: var(--fs-12); color: var(--c-text-3); }
/* P0-2 保留 12px：纯计数（「4 条」）。 */
.p7-group__count { margin-left: auto; font-size: var(--fs-12); color: var(--c-text-3); }
/* 筛选后为空的组：EmptyState size="sm" 自己带内距与居中，这里只把图形收窄，
   免得它在 4 个分组里各占一屏。 */
.p7-group__empty :deep(.exp-motif) { width: 120px; margin-bottom: var(--sp-2); }
.p7-group__empty { padding: var(--sp-2) 0 var(--sp-4); }

/* 第二层收窄：来源与可信度共用同一排小按钮 */
.p7-subfilter { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: calc(var(--sp-2) * -1) 0 var(--sp-4); }
/* P0-2 提到 14px：它跟后面的 chip 是两组筛选的**组标签**，用户要照着它找"该点哪一组"。 */
.p7-subfilter > span { font-size: var(--fs-14); color: var(--c-text-3); line-height: var(--lh-snug); }
.p7-subfilter__note { color: var(--c-text-3); }
.p7-subchip { min-height: 44px; padding: 0 var(--sp-3); border: 1px solid var(--c-border-strong); border-radius: var(--r-pill); background: transparent; color: var(--c-text-2); font-size: var(--fs-12); }
.p7-subchip:hover { border-color: var(--c-primary-border); color: var(--c-primary); }
.p7-subchip--on { background: var(--c-primary-weak); border-color: var(--c-primary-border); color: var(--c-primary); font-weight: var(--fw-medium); }

/* A 段的一行：标签列固定宽 → 值 / 注脚两条基线固定。
   v8：整行是一个 <button>（.p7-row__hit），命中区就是整行——所以"支撑 N 条判断"
   与"原始依据与操作"不再是两个 20px 的小按钮，而是注脚行里的**状态与指示**。 */
.p7-rows { display: flex; flex-direction: column; }
.p7-row {
  border-bottom: 1px solid var(--c-border);
  border-left: 2px solid transparent;
  transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2) var(--ease-out);
}
.p7-row__hit {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  align-items: start;
  column-gap: var(--sp-3);
  width: 100%;
  min-height: 44px;
  padding: var(--sp-2) var(--sp-3);
  text-align: left;
}
.p7-row__hit:focus-visible { outline: 2px solid var(--c-focus); outline-offset: -2px; }
/* P0-2 提到 14px：这是**字段名**（"专业 / 年级 / 成绩层级"）。它是这一行"在说什么"的唯一
   线索，也是左列固定宽 78px 的那个对齐锚点；用户是拿它跨行比对的，属于要读的内容。
   行距 1.4（--lh-snug 以下一点点）：它几乎只出现在单行，收紧这一档是为了让"12→14px"
   不在每一行都换来一次行高增长——14×1.4=19.6px，正好抵掉旧值 16×1.55=24.8px 的标签列高。 */
.p7-row__label { color: var(--c-text-3); font-size: var(--fs-14); line-height: 1.4; overflow-wrap: anywhere; }
.p7-row__main { min-width: 0; display: flex; flex-direction: column; gap: 0; }
.p7-row__value { display: block; font-size: var(--fs-16); line-height: calc(var(--fs-16) * 1.55); overflow-wrap: anywhere; }
/* P0-2 收紧行距：这一排现在混了 12px（来源/时间/状态）与 14px（动作词），
   行距按 12px 那一档收紧到 1.45，让小字不再散着排，也不给上层白拿 2px。 */
.p7-row__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0 var(--sp-3); font-size: var(--fs-12); line-height: var(--lh-snug); }
/* 来源、可信度、时间同层：三者都交给组件自己的形态（色相 / 格子 / 字形），
   这一页不再为它们各写一套 CSS（原来 `.p7-conf :deep(.confidence__*)` 覆盖了 5 条）。 */
.p7-row__time { color: var(--c-text-3); }
/* P0-2 提到 14px：hint 是一句**说明**（"示例对话本人说明，待核对"），不是坐标值，
   提上来之后与同排 12px 的来源/时间形成两级，而不是"一堆一样小的字"。 */
.p7-row__hint { flex-basis: 100%; font-size: var(--fs-14); line-height: var(--lh-snug); color: var(--c-text-3); }
.p7-row__hint::before { content: "·"; margin-right: 6px; }
.p7-row__edited { color: var(--c-primary); }

/* 行末直接「更正」：原路径（查看依据 → 抽屉底部更正信息）保留，
     但用户不必再钻两层才找到修改入口（深度测试 D6）。 */
.p7-row__wrap { display: flex; align-items: center; gap: 4px; padding-right: 6px; }
.p7-row__wrap > :deep(.profile-fact) { flex: 1 1 auto; min-width: 0; }
.p7-row__quick { flex: none; min-height: 44px; min-width: 44px; padding: 0 8px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--c-primary); font-size: var(--fs-12); }
.p7-row__quick:hover, .p7-row__quick:focus-visible { border-color: var(--c-primary-border); background: var(--c-primary-weak); }

/* 关联反馈：被依赖 / 被展开时，这一条才亮起来 */
.p7-row--lit, .p7-row--open { background: var(--c-primary-weak); border-left-color: var(--c-primary); }

/* 关系状态（不是控件）：一个点 + 一句话，展开时同时表示"这一行已经钉住" */
/* P0-2 保留 12px：这是**机器算出来的关系值**（"支撑 3 条判断"），每个判断是几条由契约给定，
   用户不需要读它来做决定；它与来源、时间同一层，属标注。 */
.p7-support { display: inline-flex; align-items: center; gap: 5px; color: var(--c-text-3); font-size: var(--fs-12); white-space: nowrap; }
.p7-support__mark { width: 6px; height: 6px; border-radius: var(--r-pill); background: var(--c-border-strong); flex: none; transition: background-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out); }
.p7-support--on { color: var(--c-primary); }
.p7-support--on .p7-support__mark { background: var(--c-primary); box-shadow: 0 0 0 2px var(--c-primary-weak-2); }
.p7-support--none .p7-support__mark { background: transparent; border: 1px dashed var(--c-border-strong); }

/* 展开指示：文字 + 箭头，随 aria-expanded 翻转（状态可见，不靠动画表达） */
/* P0-2 提到 14px：它跟"靠 A 的"是同一类**动作/关系词**——"来历与操作"直接说明
   点下去会发生什么，是使用这一页的关键词；原来 12px 时它比同一行里的状态字还小，
   既是"最小的字承担最多内容"的典型，也弱化了这一页的主交互。 */
.p7-row__cue { display: inline-flex; align-items: center; gap: 3px; margin-left: auto; color: var(--c-text-3); font-size: var(--fs-14); white-space: nowrap; }
.p7-row__cue svg { transition: transform var(--dur-2) var(--ease-out); }
.p7-row__hit:hover .p7-row__cue { color: var(--c-primary); }
.p7-row__hit[aria-expanded='true'] .p7-row__cue { color: var(--c-primary); }
.p7-row__hit[aria-expanded='true'] .p7-row__cue svg { transform: rotate(180deg); }

/* 一层折叠：`Foldable variant=inline` 承载"展开/收起"的语义与键盘行为，
   命中的仍然是**整行**（.p7-row__hit）。
   折叠头在这里是结构性的：收起时它整块不参与布局（否则 12 行各多出 40px，
   而这一页的行高是上一轮实测过的基线），展开时才作为"这一层的标题"出现。
   这样同一行既不会有第二个 40px 的开关，也不会出现"按钮里套按钮"。 */
.p7-row__more :deep(.fold__head) { gap: var(--sp-2); }
.p7-row__more:not(.fold--open) :deep(.fold__head) { display: none; }
.p7-row__more :deep(.fold__label) { font-size: var(--fs-12); }
.p7-row__more :deep(.fold__body) { padding-top: var(--sp-1); }
/* 展开区：原始证据 + 撑起的判断 + 动作。动作在这里才有 44px 的尺寸。 */
.p7-row__more-body { padding: var(--sp-3) var(--sp-4) var(--sp-4); margin: 0 var(--sp-3) var(--sp-2); background: var(--c-surface-2); border-radius: var(--r-md); }
/* P0-2 保留 12px：`原始证据` 这类标题是**块内眉标**（后面紧跟的 ul 才是内容）。 */
.p7-facts__title { margin-top: var(--sp-3); font-size: var(--fs-12); color: var(--c-text-3); }
.p7-facts__title:first-child { margin-top: 0; }
.p7-evidence { margin: var(--sp-2) 0 0; }
/* 兜底句（"这条没有附原始证据"）：它是**说明**，不是坐标值，所以走 14px 正文档，
   不再用 `.ws-muted` 的 12px 灰字 —— 灰字与周围信息等重，读不出"这里什么都没有"。 */
.p7-evidence__none { margin-top: var(--sp-2); font-size: var(--fs-14); color: var(--c-text-3); line-height: var(--lh-snug); }
.p7-row__actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4); margin-top: var(--sp-3); padding-top: var(--sp-2); border-top: 1px solid var(--c-border); }

/* 折叠内的关系行 / 动作行：唯一有 44px 命中区的地方 */
.p7-links { display: flex; flex-direction: column; margin-top: var(--sp-2); border-top: 1px solid var(--c-border); }
.p7-link { display: flex; align-items: center; gap: var(--sp-3); width: 100%; min-height: 44px; padding: 0 var(--sp-2); border-bottom: 1px solid var(--c-border); border-radius: var(--r-sm); text-align: left; color: var(--c-text-2); font-size: var(--fs-14); }
.p7-link:hover { background: var(--c-surface-3); }
.p7-link__dot { width: 6px; height: 6px; border-radius: var(--r-pill); background: var(--c-primary); flex: none; }
.p7-link__label { flex: none; color: var(--c-text); font-weight: var(--fw-medium); }
.p7-link__value { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-text-3); font-size: var(--fs-12); }
.p7-link__go { flex: none; display: inline-flex; align-items: center; gap: 4px; color: var(--c-primary); font-size: var(--fs-12); }
.p7-link--missing .p7-link__dot { background: transparent; border: 1px solid var(--c-attention); }
.p7-link--missing .p7-link__go { color: var(--c-attention-strong); }

/* B 段：`needs_recompute` 现在是 StatTile（读数 + 状态同格）。
   这里只给它一个上限宽度，免得趋势句把页头挤成一长条；
   红底 + 左红条那套（三处里最重的一处）已经删掉，重量由组件的 state 承担。 */
.p7-recompute { flex: none; width: min(280px, 100%); }

/* P0-2 提到 14px：这是**读下去的说明句**（依赖关系从哪来、哪些是资料对应表），
   53 个字符的一句，不是坐标值。行距用 --lh-normal：它是这一段里唯一的正文型文本。 */
.p7-deps-note { font-size: var(--fs-14); color: var(--c-text-3); margin-bottom: var(--sp-3); max-width: 84ch; line-height: var(--lh-normal); }
.p7-deps-note strong { color: var(--c-text-2); font-weight: var(--fw-medium); }

.p7-concls { display: flex; flex-direction: column; border-top: 1px solid var(--c-border); }
.p7-concl {
  padding: 0 var(--sp-3);
  border-bottom: 1px solid var(--c-border);
  border-left: 2px solid transparent;
  transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2) var(--ease-out);
}
/* 维度判断与方向方案之间留一道结构缝，不是又加一个分区标题 */
.p7-concl--plan { margin-top: var(--sp-2); border-top: 1px solid var(--c-border-strong); }
.p7-concl--lit { background: var(--c-primary-weak); border-left-color: var(--c-primary); }
.p7-concl--stale { background: linear-gradient(90deg, var(--c-attention-weak), transparent 55%); }
.p7-concl--flash { animation: p7-flash 1.4s var(--ease-out) 1; }
@keyframes p7-flash { 0%, 100% { background-color: transparent; } 15%, 60% { background-color: var(--c-primary-weak-2); } }

/* 第一层：一行扫完 —— 名称 | 判断短语 | 把握。整行是一个 ≥44px 的按钮。 */
.p7-concl__hit {
  display: grid;
  grid-template-columns: minmax(110px, 20%) minmax(0, 1fr) auto;
  align-items: baseline;
  gap: var(--sp-1) var(--sp-3);
  width: 100%;
  min-height: 44px;
  padding: var(--sp-2) 0;
  text-align: left;
}
.p7-concl__hit:focus-visible { outline: 2px solid var(--c-focus); outline-offset: -2px; }
.p7-concl__label { display: flex; align-items: baseline; gap: var(--sp-2); flex-wrap: wrap; font-size: var(--fs-14); font-weight: var(--fw-medium); color: var(--c-text); }
/* P0-2 提到 14px：类别名（"个人特征与能力"）是主标签的一部分——它说明这条判断
   属于哪一组，用户按组读这一列；作为 14px 主标签的行内限定，不该掉到 12px。
   行距跟着主标签走，避免同行两种行距把行高撑高。 */
.p7-concl__kind { font-size: var(--fs-14); font-weight: var(--fw-regular); color: var(--c-text-3); line-height: var(--lh-snug); }
.p7-concl__brief { font-size: var(--fs-16); color: var(--c-text); overflow-wrap: anywhere; }
.p7-concl__side { display: inline-flex; align-items: center; gap: var(--sp-2); }
/* P0-2 保留 12px：把握档名（"待验证 / 依据充分"）。它旁边就是三根刻度条，
   文字只是**刻度的读法**，与来源、时间同层；放大它会把"量的示意"变成一句口号。 */
.p7-concl__conf { white-space: nowrap; }
/* P0-2 提到 14px：与 .p7-row__cue 同理，它是"完整判断与依据"这个**动作**的名字。 */
.p7-concl__cue { display: inline-flex; align-items: center; gap: 4px; color: var(--c-text-3); font-size: var(--fs-14); white-space: nowrap; }
.p7-concl__cue svg { transition: transform var(--dur-2) var(--ease-out); }
.p7-concl__hit:hover .p7-concl__cue { color: var(--c-primary); }
.p7-concl__hit[aria-expanded='true'] .p7-concl__cue { color: var(--c-primary); }
.p7-concl__hit[aria-expanded='true'] .p7-concl__cue svg { transform: rotate(180deg); }

/* 第二层：依赖 —— 这一页的立身之本。折叠外只**讲关系**（哪几条 / 缺哪几条 / 缺的在哪），
   可点的动作在下面展开区里的 44px 行上，所以这里没有 24px 的可点 chip。 */
.p7-concl__deps { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-1) var(--sp-3); margin: 0 0 var(--sp-2) calc(20% + var(--sp-3)); }
/* P0-2 保留 12px：`靠 A 的` 是依赖边那一排 chip 的**引导词**（5 个字），
   它下面的 chip 才是内容；引导词放大只会把这一行推高。 */
.p7-concl__deps-label { font-size: var(--fs-12); color: var(--c-text-3); }
.p7-deps__list { display: flex; flex-wrap: wrap; gap: 6px; }
/* P0-2 提到 14px：**依赖边本身就是这一页的立身之本**——"哪几条信息撑起了这条判断"
   是用户来这里要看的东西，不是 chip 装饰。原来 12px 时它比旁边的 16px 判断短语小两级，
   正是"最小的字承担最多的内容"。提到 14px 后它仍然明显服从判断短语（16px）。 */
.p7-dep { display: inline-flex; align-items: center; gap: 5px; min-height: 24px; padding: 0 var(--sp-2); border: 1px solid var(--c-border-strong); border-radius: var(--r-sm); background: var(--c-surface); color: var(--c-text-2); font-size: var(--fs-14); }
.p7-dep i { width: 6px; height: 6px; border-radius: var(--r-pill); background: var(--c-primary); flex: none; }
.p7-dep small { color: var(--c-attention-strong); }
.p7-dep__where { font-style: normal; color: var(--c-text-3); }
/* 悬停仍是"指向"：停在这条 chip 上，A 段对应那行会亮 */
.p7-dep--on:hover { border-color: var(--c-primary-border); color: var(--c-text); }
.p7-dep--missing { background: transparent; border-style: dashed; color: var(--c-text-3); }
.p7-dep--missing i { background: transparent; border: 1px solid var(--c-attention); }
.p7-dep--missing:hover { border-color: var(--c-attention); color: var(--c-attention-strong); }
.p7-dep--none { border-style: dashed; color: var(--c-text-3); }
.p7-concl__prov { font-size: var(--fs-12); color: var(--c-text-3); }

.p7-concl__more-body { padding: var(--sp-3) var(--sp-4); margin: 0 0 var(--sp-3); background: var(--c-surface-2); border-radius: var(--r-sm); }
.p7-concl__more-label { font-size: var(--fs-12); color: var(--c-text-3); margin-bottom: var(--sp-1); }
.p7-concl__more-body > .p7-concl__more-label:not(:first-child) { margin-top: var(--sp-3); }
.p7-concl__full { font-size: var(--fs-14); color: var(--c-text-2); line-height: var(--lh-normal); }
.p7-concl__note { font-size: var(--fs-12); color: var(--c-text-3); margin-top: var(--sp-2); line-height: var(--lh-normal); }
.p7-concl__more-body .p7-evidence { margin: var(--sp-2) 0 var(--sp-2); }
.p7-concl__more-body .ws-text-button { min-height: 44px; margin-top: var(--sp-2); }

/* C 段：竖列 + 发丝分隔。缺口只在这里讲全。 */
.p7-gaps { display: flex; flex-direction: column; border-top: 1px solid var(--c-border); }
.p7-gap {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-1) var(--sp-6);
  padding: var(--sp-3) var(--sp-2);
  border-bottom: 1px solid var(--c-border);
  border-left: 2px solid transparent;
  transition: background-color var(--dur-2) var(--ease-out);
}
/* P0-2 提到 14px：这是"下一步做什么"——**判断句**，用户读完要据此行动。 */
.p7-gap__next { display: block; margin-top: 2px; font-style: normal; color: var(--c-text-3); font-size: var(--fs-14); line-height: var(--lh-snug); }
.p7-gap--first { padding-top: var(--sp-2); }
.p7-gap--flash { animation: p7-flash 1.4s var(--ease-out) 1; }
.p7-gap__head { grid-column: 1 / -1; display: flex; align-items: center; gap: var(--sp-3); }
.p7-gap__head h3 { font-size: var(--fs-16); font-weight: var(--fw-semibold); }
/* P0-2 保留 12px：C1/C2/C3 与"待补充"是**序号与徽章**，tokens 登记给 12px 的用途。 */
.p7-gap__index { display: inline-grid; place-items: center; min-width: 26px; height: 20px; padding: 0 4px; border-radius: var(--r-sm); background: var(--c-attention-weak); color: var(--c-attention-strong); font-size: var(--fs-12); font-variant-numeric: tabular-nums; }
.p7-gap__why, .p7-gap__blocked, .p7-gap__where, .p7-gap__ask { min-width: 0; font-size: var(--fs-14); color: var(--c-text-2); line-height: var(--lh-normal); }
.p7-gap__why > span, .p7-gap__blocked > span, .p7-gap__where > span, .p7-gap__ask > span { display: block; font-size: var(--fs-12); color: var(--c-text-3); margin-bottom: 2px; }
.p7-gap__blocked { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }
.p7-gap__blocked > span { flex: 1 0 100%; }
/* P0-2 提到 14px：它是**可点的关系入口**（跳到 B 段那条判断），带标题与跳转语义；
   与 .p7-dep 同类，只是多了一条虚线边。 */
.p7-affect { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 var(--sp-2); border: 1px dashed var(--c-attention-border); border-radius: var(--r-sm); background: transparent; color: var(--c-text-2); font-size: var(--fs-14); }
.p7-affect i { width: 6px; height: 6px; border-radius: var(--r-pill); border: 1px solid var(--c-attention); flex: none; }
.p7-affect:hover { border-color: var(--c-attention); color: var(--c-attention-strong); }
.p7-gap__ask { border-left: 0; padding-left: var(--sp-3); }
.p7-gap__actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-4); grid-column: 1 / -1; }
.p7-gap__actions .ws-text-link { min-height: 44px; }
.p7-gap__actions .ws-text-button { min-height: 44px; }
.p7-none { padding: var(--sp-5) 0; }

@media (max-width: 760px) {
  .p7-meter { flex-direction: column; gap: var(--sp-4); }
  /* 窄屏两列：四个瓦片排成 2×2，不挤成一列也不溢出 */
  .p7-meter__stats > * { flex: 1 1 calc(50% - var(--sp-4)); }
  .p7-ring { width: 72px; height: 72px; }
  .p7-meter__top { flex-direction: column; align-items: flex-start; gap: var(--sp-1); }
  .p7-modes { width: 100%; flex-direction: column; align-items: flex-start; gap: var(--sp-2); }
  .p7-modes__set { width: 100%; }
  .p7-mode { flex: 1; padding: 0 var(--sp-2); }

  /* 手机：标签回到值上方；命中区仍是整行（≥44px），动作仍只在展开区内。
     P0-2：标签行距已由基础规则的 --lh-snug 承担，这里不再重复写一遍。 */
  .p7-row__hit { display: flex; flex-direction: column; align-items: stretch; gap: 2px; }
  .p7-row__cue { margin-left: 0; }

  .p7-concl__hit { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
  .p7-concl__brief { font-size: var(--fs-16); }
  .p7-concl__deps { margin-left: 0; }

  /* 展开区的动作行：窄屏让值换行，箭头留在标题那一行 */
  .p7-link { flex-wrap: wrap; padding: 8px var(--sp-2); row-gap: 2px; }
  .p7-link__value { order: 3; flex: 1 0 100%; white-space: normal; overflow: visible; }
  .p7-link__go { order: 2; margin-left: auto; }

  .p7-gap { grid-template-columns: minmax(0, 1fr); padding: var(--sp-4) 0; }
}

@media (prefers-reduced-motion: reduce) {
  .p7-row, .p7-concl, .p7-gap { transition: none; }
  .p7-support__mark, .p7-row__cue svg, .p7-concl__cue svg { transition: none; }
  .p7-concl--flash, .p7-gap--flash { animation: none; }
  .p7-ring__fill { transition: none; }
}
</style>
