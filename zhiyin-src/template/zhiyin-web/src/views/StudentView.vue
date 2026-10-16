<script setup lang="ts">
const MAX_CHARS = 40
import {PROFILE_TOPICS, profilePriority, exactProfileKeys} from '../lib/profile-organization'
import {profileLabel} from '../lib/server-copy'
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { LayoutGroup, motion } from 'motion-v'
import { demo } from '../store'
import { COLLECT_ITEMS, DIRECTION_PLANS, PROFILE_FIELDS, REPORT_SECTIONS, STUDENT } from '../data/student'
import type { FieldSource, ProfileField } from '../data/types'
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
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import ProfileInsights from '../components/ProfileInsights.vue'
import AcademicVerification from '../components/AcademicVerification.vue'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import type { DependencyEdgeView, ProfileFieldView, ProfileSource } from '../api/backend-types'

/* ═══════════════════════════════════════════════════════════════════════════
 * 1. 静态口径：主题、来源分组、缺口说明、依赖映射
 * ======================================================================== */

const SOURCE_NAMES: Record<string, ProfileField['source']> = {
  resume: '简历材料', conversation: '对话', assessment: '综合分析',
  behavior_inference: '行为记录', mentor: '导师记录', record: '学校', user_edit: '本人填写',
}

/**
 * 演示资料的来源名 → 后端 `ProfileSource` 枚举（`backend-types.ts:335`）。
 *
 * 为什么要有这张表：`SourceChip` 的 `source` 是**必填的 7 值枚举**，
 * 而演示数据里的 `ProfileField.source` 是中文的自由串（`data/types.ts:23`）。
 * 契约模式下 `field.source` 本身就是枚举，直接传；只有演示数据需要过这张表。
 * 表是 `Record<FieldSource, ProfileSource>` —— 演示数据加一个来源名会**编译报错**，
 * 不会悄悄落成一个"未知来源"的灰 chip。
 */
const SOURCE_ENUM: Record<FieldSource, ProfileSource> = {
  简历材料: 'resume',
  对话: 'conversation',
  综合分析: 'assessment',
  行为记录: 'behavior_inference',
  导师记录: 'mentor',
  学校: 'record',
  学信网: 'record',
  教务系统: 'record',
  本人填写: 'user_edit',
}

/**
 * 可信度只有一把尺：0–1（后端口径）。
 * 演示数据（`data/types.ts:15` 的 `{level,label,bars}`）没有 0–1，所以按档位取中点折算 ——
 * 与 `ConfidenceBadge` 内部兼容旧对象的 `LEGACY_SCORE` 同值，**不新增第二套口径**。
 *
 * 原来这里是 `Math.max(1, Math.round(conf * 3))`：`conf === 0` 会被抬成"1 格"，
 * 于是"完全没有依据"印成"依据很少"（`ConfidenceBadge.vue:26-29` 明确要求这两者分开）。
 * 换成 0–1 之后 `0 / undefined` 都会落到"还没有依据"，这条 bug 自然消失。
 */
const LEGACY_CONF: Record<ProfileField['confidence']['level'], number> = { high: 0.9, mid: 0.6, low: 0.2 }

/** 职业线索优先，学籍资料保持独立可查。 */
const TOPICS = PROFILE_TOPICS

/** 来源视角：把原来的「来源筛选」并进视角切换，不再两套并存 */
const SOURCE_GROUPS: { key: string; label: string; from: ProfileField['source'][] }[] = [
  { key: 'school', label: '学校档案', from: ['学校', '学信网', '教务系统'] },
  { key: 'talk', label: '咨询记录', from: ['对话'] },
  { key: 'material', label: '材料与分析', from: ['简历材料', '综合分析', '导师记录'] },
  { key: 'behavior', label: '行为记录', from: ['行为记录'] },
  { key: 'user', label: '本人填写', from: ['本人填写'] },
]

const CONF_GROUPS = [
  { key: 'high', title: '比较确定', hint: '有正式来源或多处印证' },
  { key: 'mid', title: '还要核对', hint: '来自对话，尚未核验' },
  { key: 'low', title: '依据不足', hint: '只提过一次或待补充' },
]

/** 缺口说明：demo 数据里没有 reason / suggested_next_action，所以在这里显式写清楚 */
const GAP_META: Record<string, { why: string; next: string }> = {
  internship: { why: '两条方向的匹配依据都落在"有没有一段能讲的项目或实习"上', next: '暑假或最近一段能沾产业线的经历，6 周就够写' },
  jobtype: { why: '岗位供给与门槛要求这两条结论都还没法落到具体方向上', next: '先在一两个方向里各挑 3 条真实岗位看要求' },
  salary: { why: '决策条件里的城市取舍、以及方向方案的排序都会受影响', next: '先说出一个"低于它会犹豫"的数，不用给范围' },
  budget: { why: '城市取舍与"要不要去外省"的取舍都得先知道生活成本兜不兜得住', next: '说一个每月可接受的租房+生活上限就行' },
  project: { why: '呈现能力与门槛要求这两条判断都卡在"有没有拿得出手的东西"上', next: '把一次实验或课程大作业的目标、你的动作、结果写成三句' },
}

/** 采集动线 → 字段 key（用于 C 段"去哪补"） */
const COLLECT_OF: Record<string, string> = {
  grade: '专业与年级', major: '专业与年级', rank: '成绩层级', schedule: '本周课表与空档',
  award: '在校获奖与处分', jobtype: '目标岗位类型', salary: '薪资底线', city: '是否接受外省',
}

/**
 * 依赖映射 —— **本地资料对应关系，不是契约**。
 *
 * live 模式下，只要契约的 workspace.dependencies 里有能匹配到这个结论的边，
 * 就用契约的 via_profile_keys；只有一条都匹配不上时，才退回下面这张表。
 * 两者**不会混在同一条判断里**：用哪一套是逐条判定的（见 depsOf / fieldEdges）。
 *
 * 这张表的定法（三条，缺一条就不写进来）：
 *   ① 结论 key 与画像字段 key 同名 → 直接就是依赖（interest / style / city / family / time）；
 *   ② 不同名但报告维度的原文里点了名的能力对象 → 按对象取字段
 *      （present 讲"经历表达"→ internship + weakness + pipeline；compete 讲"对比里的差距"
 *       → internship + rank + award；demand / threshold 讲岗位要求 → jobtype + rank + city）；
 *   ③ 方向方案取它 evidence 里逐条点到的画像项（专业对口→major、兴趣倾向→interest、
 *      供给→jobtype/city、成绩→rank、地域偏好→city/family），再加上"学校与年级"（grade）。
 * 关键词不做任何推断；改这张表就是改演示里的追溯结果。
 */
const DEMO_CONCL_FIELDS: Record<string, string[]> = {
  interest: ['interest'],
  style: ['style'],
  present: ['weakness', 'internship', 'pipeline'],
  demand: ['jobtype', 'city', 'rank'],
  threshold: ['internship', 'rank', 'jobtype'],
  compete: ['internship', 'rank', 'award'],
  city: ['city', 'family'],
  family: ['family'],
  time: ['time', 'schedule'],
  d1: ['major', 'interest', 'jobtype', 'city', 'internship', 'grade'],
  d2: ['major', 'interest', 'rank', 'schedule', 'time'],
  d3: ['major', 'city', 'family', 'jobtype', 'time'],
}

/** 演示用的依赖边：正式产品里这条链由后端给（WorkspacePageView.dependencies） */
const DEMO_EDGES: DependencyEdgeView[] = (() => {
  const reportKeys = REPORT_SECTIONS.flatMap((section) => section.dimensions.map((dimension) => dimension.key))
  const planKeys = DIRECTION_PLANS.map((plan) => plan.id)
  const edges: DependencyEdgeView[] = []
  for (const [target, keys] of Object.entries(DEMO_CONCL_FIELDS)) {
    const from_asset = reportKeys.includes(target) ? 'report:demo-report' : planKeys.includes(target) ? 'direction_plan:demo-plan' : 'report:demo-report'
    for (const key of keys) edges.push({ from_asset, to_asset: target, via_profile_keys: [key] })
  }
  return edges
})()

/* ═══════════════════════════════════════════════════════════════════════════
 * 2. 读取与更正（能力与原来一致：demo / service 双模式，逐条更正写回）
 * ======================================================================== */

const profileTab = ref<'facts' | 'judgments' | 'gaps' | 'sources'>('facts')
const profileRoute = useRoute()
const verificationOpen = ref(false)
watch(() => profileRoute.query.section, async section => { if(section === 'enrollment') { await nextTick(); document.getElementById('enrollment-title')?.scrollIntoView({block:'start'}) } }, {immediate:true})
const isVerified = computed(() => backendDemo.chsiVerified.value)
const loading = ref(false)
const serviceError = ref('')
const relatedError = ref('')
const livePanel = computed(() => backendDemo.state.liveWorkspace?.profile_panel)
/** 是不是"服务这次真的给了档案"。缺口清单、依赖边都以这次读取为准，不用演示数据兜底。 */
const live = computed(() => backendDemo.state.dataMode === 'service')
const originalLive = computed(() => backendDemo.state.profileOriginals)
const insights = ref<InstanceType<typeof ProfileInsights> | null>(null)

async function loadWorkspace() {
  if (loading.value) return
  loading.value = true
  serviceError.value = ''
  relatedError.value = ''
  try {
    const data = await backendClient.workspace()
    if (!data?.profile_panel) throw new Error('Incomplete profile')
    backendDemo.setWorkspace(data)
    const results=await Promise.allSettled([backendClient.report(),backendClient.directions()])
    if(results[0].status==='fulfilled')backendDemo.setReport(results[0].value)
    if(results[1].status==='fulfilled')backendDemo.setLiveDirections(results[1].value)
    const unavailable=[]
    if(results[0].status==='rejected')unavailable.push('分析报告')
    if(results[1].status==='rejected')unavailable.push('方向方案')
    if(unavailable.length)relatedError.value=`个人资料已读取，但${unavailable.join('和')}暂时没有更新；下方判断可能不完整。`
  } catch {
    serviceError.value = '最新档案暂时没有取得，请重试。现有内容仍保留。'
  } finally {
    loading.value = false
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * 3. 依赖关系：先契约、后演示
 * ======================================================================== */

/** backendDemo.state 是 readonly 的，读出来的边也是只读结构；这里只读不写 */
type ReadonlyEdge = { readonly from_asset: string; readonly to_asset: string; readonly via_profile_keys?: readonly string[] }

/** 本轮实际使用的依赖边：契约里有就用契约的，一条都没有才用演示边（两者不混用） */
const edges = computed<readonly ReadonlyEdge[]>(() => {
  const declared = backendDemo.state.liveWorkspace?.dependencies ?? []
  const usable = declared.filter((edge) => (edge.via_profile_keys ?? []).length > 0)
  return live.value ? usable : DEMO_EDGES
})
const depsFromContract = computed(() => edges.value !== DEMO_EDGES)
const depsSourceNote = computed(() =>
  depsFromContract.value
    ? '仅展示明确对应这条判断的资料关联。整份报告的关联资料不等于每条判断的依据。'
    : '当前按资料与判断的对应关系整理，尚未提供逐项关联记录。',
)

/** 资产 id 的写法在不同实现里有差异，这里按"能对上就用"的顺序收窄，不做语义猜测 */
function matchesAsset(asset: string, conclusionKey: string, kind: 'dimension' | 'direction'): boolean {
  const normalized = asset.trim().toLowerCase()
  if (normalized === conclusionKey.toLowerCase()) return true
  if (normalized.startsWith(conclusionKey.toLowerCase() + ':')) return true
  if (normalized.endsWith(':' + conclusionKey.toLowerCase())) return true
  return kind === 'direction' && /^(direction_plan|direction|plan)$/.test(normalized)
}

/** 某条判断依赖 A 里的哪几条，以及这组关系是从哪来的 */
function depsOf(conclusionKey: string, kind: 'dimension' | 'direction'): { keys: string[]; fromContract: boolean } {
  const mine = edges.value.filter((edge) => matchesAsset(edge.to_asset, conclusionKey, kind))
  if (mine.length) {
    const keys: string[] = []
    for (const edge of mine) for (const key of edge.via_profile_keys ?? []) if (!keys.includes(key)) keys.push(key)
    if (keys.length) return { keys, fromContract: depsFromContract.value }
  }
  if (depsFromContract.value) return { keys: [], fromContract: true }
  return { keys: DEMO_CONCL_FIELDS[conclusionKey] ?? [], fromContract: false }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * 4. A 段数据：每条默认带来源 / 可信度 / 时间
 * ======================================================================== */

/** 已有 / 总数 / 缺口：demo 走画像池切片，service 走本次读取的档案 */
const progress = computed(() =>
  live.value
    ? { known: livePanel.value?.fields?.length ?? 0, total: (livePanel.value?.fields?.length ?? 0) + (livePanel.value?.gaps?.length ?? 0), gap: livePanel.value?.gaps?.length ?? 0 }
    : demo.use.profileProgress.value,
)

interface FieldRow extends ProfileField {
  /** 图上看到的来源（本人更正后要换掉） */
  desc: ProfileField['source']
  /** 后端口径的来源枚举 —— `SourceChip` 要的是它，不是 `desc` 那个中文串 */
  src: ProfileSource
  /** 0–1 的可信度（唯一口径）。演示数据没有 0–1，由 `LEGACY_CONF` 折算 */
  conf: number
  /** 更早的来源（这条被本人改过时才出现） */
  prior: string
  /** YYYY-MM-DD，给 <time> 用；拿不到就是空 */
  iso: string
  /** 原始证据列表——唯一允许放在一层折叠里的东西 */
  evidence: string[]
  /** 本人更正过 */
  touched: boolean
  /** 依赖它的判断条数 */
  supports: number
}

function human(value: unknown): string {
  if (value == null) return '尚待补充'
  if (Array.isArray(value)) return value.map(human).join('、')
  if (typeof value === 'object') return Object.values(value).map(human).join('；')
  return String(value)
}

const rowsBase = computed<Omit<FieldRow, 'supports'>[]>(() => {
  if (live.value) {
    return (livePanel.value?.fields ?? []).map((field) => {
      const conf = field.confidence
      const level: 'high' | 'mid' | 'low' = conf === undefined ? 'low' : conf >= 0.8 ? 'high' : conf >= 0.5 ? 'mid' : 'low'
      const label = conf === undefined ? '待确认' : conf >= 0.8 ? '比较确定' : conf >= 0.5 ? '还要核对' : '依据不足'
      const at = field.updated_at ? new Date(field.updated_at) : null
      const edited = field.source === 'user_edit'
      const priorKey = originalLive.value[field.key]
      return {
        key: field.key, label: profileLabel(field.key,field.label || field.key), value: human(field.value),
        source: SOURCE_NAMES[field.source] ?? '学校',
        // 契约模式：来源本来就是枚举，直接透传；没有 0–1 时按档位折算（未知仍是未知）
        src: field.source,
        conf: conf === undefined ? LEGACY_CONF[level] : conf,
        // 档位与文案仍由后端置信度决定；模板不再读它，只有 tally 的分档与筛选读
        confidence: { level, label, bars: 0 },
        noted: at ? at.toLocaleString('zh-CN') : '未记录时间',
        desc: SOURCE_NAMES[field.source] ?? '学校',
        prior: edited && priorKey ? SOURCE_NAMES[priorKey.source] ?? '原来源' : '',
        iso: at && !Number.isNaN(at.getTime()) ? at.toISOString().slice(0, 10) : '',
        evidence: [...(field.evidence ?? [])],
        touched: edited,
      }
    })
  }
  return PROFILE_FIELDS.slice(0, progress.value.known).map((field) => {
    const touched = !!demo.state.profileEdits[field.key]
    return {
      ...field,
      desc: touched ? '本人填写' as const : field.source,
      src: touched ? 'user_edit' as const : SOURCE_ENUM[field.source],
      conf: LEGACY_CONF[field.confidence.level],
      prior: touched ? field.source : '',
      iso: '',
      evidence: [] as string[],
      touched,
    }
  })
})

/** 依赖解析只需要"这一条在不在、叫什么"，所以断在 rowsBase 上，别绕回 known */
const fieldLabels = computed<Map<string, string>>(() => new Map(rowsBase.value.map((row) => [row.key, row.label])))

/**
 * 值的排版：长值让整行高度失控，是因为长度差全落在"折几行"上。
 * 演示数据里把"本人说明，待核对"这类括注挪到注脚那一行，
 * 主值回到一个短语，行高就稳了。真实数据（live）一个字都不动。
 */
const LONG_VALUE = 15
interface ValueParts { head: string; tail: string; hasHint: boolean }
const valueCache = new Map<string, ValueParts>()
function valueParts(row: FieldRow): ValueParts {
  const cacheKey = `${row.key}||${live.value ? 'live' : 'demo'}||${fieldValue(row)}`
  const cached = valueCache.get(cacheKey)
  if (cached) return cached
  const raw = fieldValue(row)
  // 真实数据一个字都不动；只有演示文案里的括注会被挪到注脚行，避免行高忽高忽低
  const parts: ValueParts = { head: raw, tail: '', hasHint: false }
  const match = live.value ? null : raw.match(/^(.*?)[（(]([^（()）]*)[)）]\s*$/)
  if (match) {
    const head = match[1]!.trim()
    if (head && head.length <= LONG_VALUE) {
      parts.head = head
      parts.tail = match[2]!.trim()
      parts.hasHint = !/^在读$/.test(parts.tail)
    }
  }
  valueCache.set(cacheKey, parts)
  return parts
}

const missing = computed(() =>
  live.value
    ? (livePanel.value?.gaps ?? []).map((gap) => ({ key: gap.key, label: gap.label ?? gap.key, reason: gap.reason, next: gap.suggested_next_action ?? '' }))
    : PROFILE_FIELDS.slice(progress.value.known).map((field) => ({ key: field.key, label: field.label, reason: '', next: '' })),
)

/* ═══════════════════════════════════════════════════════════════════════════
 * 5. 覆盖度与整体可信度：后端的数先用，说明白它是谁算的
 * ======================================================================== */

/** 后端给的数（缺省时为 undefined，缺一不可才自算） */
function backendRatio(value: number | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.max(0, Math.min(1, value > 1 ? value / 100 : value))
}

const tally = computed(() => {
  const rows = known.value
  const firm = rows.filter((row) => row.confidence.level === 'high').length
  const check = rows.filter((row) => row.confidence.level === 'mid').length
  const thin = rows.filter((row) => row.confidence.level === 'low').length
  const confirmedTotal = rows.length + missing.value.length
  const computedCoverage = confirmedTotal ? rows.length / confirmedTotal : 0
  const fromBackend = backendRatio(livePanel.value?.coverage)
  const coverage = fromBackend ?? computedCoverage
  const coverageSource: 'backend' | 'local' | 'backend-count' = fromBackend !== null ? 'backend' : live.value ? 'backend-count' : 'local'
  // 后端没给整体可信度时才自算：各条可信度按三段取平均（资料对应关系），有缺口再整体打折
  const sum = firm * 1 + check * 0.62 + thin * 0.3
  const base = rows.length ? sum / rows.length : 0
  const localTrust = coverage ? Math.round(base * (0.6 + 0.4 * coverage) * 100) : 0
  const backendTrust = backendRatio(livePanel.value?.overall_confidence)
  const trust = backendTrust !== null ? Math.round(backendTrust * 100) : localTrust
  return { firm, check, thin, coverage, coverageSource, trust, trustFromBackend: backendTrust !== null, localTrust, fromTalk: rows.filter((row) => row.desc === '对话').length, total: confirmedTotal }
})

const statusLine = computed(() => {
  const t = tally.value
  const parts = [`${t.firm} 条已确认`, `${t.check} 条还要核对`]
  if (t.thin) parts.push(`${t.thin} 条依据不足`)
  parts.push(`${missing.value.length} 条待补充`)
  return parts.join(' · ')
})

/** 三档读数的**数值**（标题与口径仍来自 CONF_GROUPS，不再另写一份文案） */
const CONF_COUNT_KEY: Record<string, 'firm' | 'check' | 'thin'> = { high: 'firm', mid: 'check', low: 'thin' }
const confBands = computed(() =>
  CONF_GROUPS.map((group) => ({ key: group.key, title: group.title, count: tally.value[CONF_COUNT_KEY[group.key]!] })),
)

/** 口径说明：把"这个数是谁算的、怎么算的"写在数字旁边 */
const trustOrigin = computed(() => (tally.value.trustFromBackend ? '后端给出' : live.value ? '本地按各条可信度折算（后端未给出整体可信度）' : '本地按资料对应关系折算'))
const coverageCount = computed(() => `${known.value.length}/${tally.value.total} 条`)
const coverageNote = computed(() => {
  if (tally.value.coverageSource === 'backend') return `覆盖度取自后端（已收到 ${coverageCount.value}）`
  if (tally.value.coverageSource === 'backend-count') return `本次读取：收到 ${coverageCount.value}`
  return `资料对应关系：画像池收到 ${coverageCount.value}`
})

/** 覆盖度数值：进入页面从 0 生长到实际值；reduced-motion 下直接给终值 */
const reduced = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const trustShown = ref(0)
let trustFrame = 0
function tweenTo(target: number, duration = 760) {
  cancelAnimationFrame(trustFrame)
  const from = trustShown.value
  if (reduced() || from === target) { trustShown.value = target; return }
  const start = performance.now()
  const tick = (now: number) => {
    const p = Math.min(1, (now - start) / duration)
    trustShown.value = from + (target - from) * (1 - (1 - p) ** 3)
    if (p < 1) trustFrame = requestAnimationFrame(tick)
    else trustShown.value = target
  }
  trustFrame = requestAnimationFrame(tick)
}
// 这个 watch 依赖 tally，而 tally 又依赖 known（由结论侧的依赖关系算出来）——
// 所以它必须注册在 known 之后，否则 immediate 求值时 known 还在 TDZ 里。


/* ═══════════════════════════════════════════════════════════════════════════
 * 6. 全量资料：不设搜索、范围或组织方式筛选，进入页面就按主题完整展示
 * ======================================================================== */

interface RowGroup {
  key: string
  title: string
  hint: string
  rows: FieldRow[]
}

const groups = computed<RowGroup[]>(() => {
  const rows = [...known.value].sort((a,b) => profilePriority(a.key)-profilePriority(b.key))
  const extra = rows.filter((row) => !TOPICS.some((topic) => topic.keys.includes(row.key))).map((row) => row.key)
  return [
    ...TOPICS.map((topic) => ({ key: topic.key, title: topic.title, hint: '', rows: rows.filter((row) => topic.keys.includes(row.key)) })),
    { key: 'other', title: '其他已记录信息', hint: '', rows: rows.filter((row) => extra.includes(row.key)) },
  ]
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 7. B 段数据：下游结论 + 它依赖 A 里的哪几条
 * ======================================================================== */

interface LinkedField { key: string; label: string; present: boolean; value: string }

interface Conclusion {
  key: string
  kind: 'dimension' | 'direction'
  section: string
  label: string
  /** 第一层：能一行扫完的判断；第二层显示完整句子 */
  brief: string
  full: string
  /** 0–1 的把握（唯一口径，`data/types.ts` 的档位在这里折算一次） */
  conf: number
  /** 正向：它依赖 A 里的哪几条 */
  deps: LinkedField[]
  /** 这组依赖是从契约来的还是资料对应表来的 */
  depsFromContract: boolean
  /** 依赖里手上还没有的 */
  missingKeys: string[]
  /** 报告里逐条列出的依据（demo 数据里的原句） */
  evidence: string[]
  /** 门槛解释 / 判断说明 —— 第二层 */
  note: string
  risk: string
  ripple: string
}

/** 方向方案的完整句子在 evidence[0]；它本身就是画像项的罗列（"专业对口：材料科学与工程"），
 *  所以拿它当能扫完的那一句，剩下的原依据进第二层。 */
function briefOf(text: string): string {
  const cut = text.split(/[。；]/)[0]!.trim()
  return cut || text
}

const conclusionMap = computed<Record<string, Conclusion>>(() => {
  const rows = new Map(rowsBase.value.map((row) => [row.key, row]))
  const link = (key: string): LinkedField => {
    const row = rows.get(key)
    return { key, label: row?.label ?? fieldLabels.value.get(key) ?? key, present: !!row, value: row ? row.value : '待补充' }
  }
  const map: Record<string, Conclusion> = {}

  if(live.value){
    for(const section of backendDemo.state.liveReport?.sections??[])for(const dimension of section.items??[]){
      const key=section.id+'.'+dimension.index
      const keys=exactProfileKeys(edges.value,key)
      const links=[...new Set(keys)].map(link)
      map[key]={key,kind:'dimension',section:section.title,label:dimension.name,brief:briefOf(dimension.conclusion),full:dimension.conclusion,conf:NaN,deps:links,depsFromContract:true,missingKeys:links.filter(x=>!x.present).map(x=>x.key),evidence:dimension.evidence?[dimension.evidence]:[],note:dimension.tag,risk:'',ripple:''}
    }
    for(const plan of backendDemo.state.liveDirections?.plans??[]){
      const links=exactProfileKeys(edges.value,plan.id).map(link)
      map[plan.id]={key:plan.id,kind:'direction',section:'方向方案',label:plan.name,brief:briefOf(plan.fit_reason??''),full:plan.fit_reason??'',conf:NaN,deps:links,depsFromContract:true,missingKeys:links.filter(x=>!x.present).map(x=>x.key),evidence:[],note:plan.target_desc??'',risk:plan.main_risk??'',ripple:''}
    }
    return map
  }
  for (const section of REPORT_SECTIONS) {
    for (const dimension of section.dimensions) {
      const deps = depsOf(dimension.key, 'dimension')
      const links = deps.keys.map(link)
      map[dimension.key] = {
        key: dimension.key,
        kind: 'dimension',
        section: section.title,
        label: dimension.label,
        brief: briefOf(dimension.conclusion),
        full: dimension.conclusion,
        conf: LEGACY_CONF[dimension.confidence.level],
        deps: links,
        depsFromContract: deps.fromContract,
        missingKeys: links.filter((item) => !item.present).map((item) => item.key),
        evidence: [...dimension.evidence],
        note: dimension.threshold ?? '',
        risk: '',
        ripple: '',
      }
    }
  }

  for (const plan of DIRECTION_PLANS) {
    const deps = depsOf(plan.id, 'direction')
    const links = deps.keys.map(link)
    map[plan.id] = {
      key: plan.id,
      kind: 'direction',
      section: '方向方案',
      label: plan.title,
      brief: briefOf(plan.evidence[0] ?? plan.risk),
      full: plan.evidence[0] ?? plan.risk,
      conf: LEGACY_CONF[plan.fit.level],
      deps: links,
      depsFromContract: deps.fromContract,
      missingKeys: links.filter((item) => !item.present).map((item) => item.key),
      evidence: plan.evidence.slice(1),
      note: '',
      risk: plan.risk,
      ripple: `${plan.ripple} 处会跟着改：${plan.ripplePoints.join('、')}`,
    }
  }

  return map
})

/** 反查：字段被哪些判断依赖（由结论侧的依赖表推出，不手写第二份） */
const fieldDeps = computed<Record<string, string[]>>(() => {
  const map: Record<string, string[]> = {}
  for (const item of Object.values(conclusionMap.value)) {
    for (const dep of item.deps) (map[dep.key] ??= []).push(item.key)
  }
  return map
})

/** A 段最终形态：在 rowsBase 上补上"支撑 N 条判断"。关系与 B 段同源，不另算一套。 */
const reportFields=computed(()=>new Set(edges.value.filter(e=>e.to_asset==='report'||e.to_asset===backendDemo.state.liveReport?.report_id).flatMap(e=>e.via_profile_keys??[])))
const needsCheck=computed(()=>known.value.filter(row=>!Number.isFinite(row.conf)||row.conf<0.8))
const fieldReading=ref<FieldRow|null>(null)
async function readField(row:FieldRow){openField.value=null;await nextTick();fieldReading.value=row}
async function readAnalysis(){openField.value=null;await nextTick();profileTab.value='judgments'}
const known = computed<FieldRow[]>(() => rowsBase.value.map((row) => ({ ...row, supports: (fieldDeps.value[row.key] ?? []).length })))

const priorityConclusions = computed(() => Object.values(conclusionMap.value)
  .sort((a, b) => Number(b.kind === 'direction') - Number(a.kind === 'direction'))
  .slice(0, 3))

/** 覆盖度环：进入页面从 0 生长到实际值；reduced-motion 直接给终值 */
watch(() => tally.value.trust, (value) => tweenTo(value), { immediate: true })

onBeforeUnmount(() => {
  cancelAnimationFrame(trustFrame)
  window.clearTimeout(flashTimer)
  window.clearTimeout(gapTimer)
})

/** 更正过的字段：demo 用 backendDemo 的共享标记位模拟，service 用后端的 needs_recompute */
const changedFields = computed(() => new Set(backendDemo.state.assetChanges.profileKeys))
const recomputeIds = computed(() => new Set(Object.keys(conclusionMap.value).filter((key) => conclusionMap.value[key]!.deps.some((dep) => changedFields.value.has(dep.key)))))
const needsRecompute = computed(() => recomputeIds.value.size)

/** 依赖关系沿用哪一套：整页只出现一种说法，不混用 */
const depsMixed = computed(() => {
  const values = Object.values(conclusionMap.value).map((item) => item.depsFromContract)
  return values.some(Boolean) && values.some((value) => !value)
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 8. C 段数据 + 关系高亮 + 缺口联动
 * ======================================================================== */

interface GapRow {
  key: string
  label: string
  why: string
  next: string
  origin: string
  blocked: string
  ask: string
  /** 它卡住了哪几条判断 —— 这是 B 段与 C 段之间唯一的那次表达 */
  affects: { key: string; label: string; brief: string }[]
}

const collectSourceOf = computed(() => {
  const map: Record<string, { origin: string; blocked: string }> = {}
  for (const item of COLLECT_ITEMS) {
    const key = Object.keys(COLLECT_OF).find((field) => COLLECT_OF[field] === item.label)
    if (!key) continue
    map[key] = item.fetchable ? { origin: `来自${item.from}`, blocked: '' } : { origin: '', blocked: item.blockedBy ?? '' }
  }
  return map
})

function gapAsk(key: string) {
  if (!live.value) return ''
  const items = backendDemo.state.liveWorkspace?.collection_panel?.items ?? []
  return items.find((item) => item.key === key)?.ask ?? ''
}

const gapRows = computed<GapRow[]>(() =>
  missing.value.map((item) => {
    const meta = GAP_META[item.key]
    const collect = collectSourceOf.value[item.key]
    const affects = (fieldDeps.value[item.key] ?? []).map((key) => {
      const conclusion = conclusionMap.value[key]
      return { key, label: conclusion?.label ?? key, brief: conclusion?.brief ?? '' }
    })
    return {
      key: item.key,
      label: item.label,
      why: item.reason || meta?.why || '这条信息还没有拿到，相关判断暂时只能给到"待确认"。',
      next: item.next || meta?.next || '在一次咨询里说清楚就可以',
      origin: collect?.origin ?? (item.key === 'internship' || item.key === 'project' ? '可以自己写一段发过来' : '来自对话'),
      blocked: collect?.blocked ?? '',
      ask: gapAsk(item.key),
      affects,
    }
  }),
)

const priorityGaps = computed(() => gapRows.value.slice(0, 3))

/** B 段缺口的落点：这里给出"为什么重要"和"去哪补"，补的是 C 段里那条的实话 */
const gapIndex = computed(() => {
  const map: Record<string, number> = {}
  gapRows.value.forEach((gap, index) => { map[gap.key] = index + 1 })
  return map
})

/** 双向高亮：悬停/聚焦一边，另一边的关联项要看得见 */
const hoverField = ref<string | null>(null)
const hoverConclusion = ref<string | null>(null)
const lingerConclusion = ref<string | null>(null)

/**
 * 行内展开的状态。
 * v8 把「撑起哪些判断」和「原始依据与操作」合并成**一次行内展开**：
 * 整行可点 → 展开后里面既有关系（撑起的判断，可跳）、也有来历（证据）与动作（≥44px）。
 * 所以"钉住关系高亮"不再是第二个小按钮，它就是"这一行开着的时候"。
 */
const openField = ref<string | null>(null)
const openConclusion = ref<string | null>(null)

const activeField = computed(() => hoverField.value ?? openField.value)
const activeConclusion = computed(() => hoverConclusion.value ?? lingerConclusion.value)
const litFields = computed(() => new Set(activeConclusion.value ? conclusionMap.value[activeConclusion.value]?.deps.map((dep) => dep.key) ?? [] : []))
const litConclusions = computed(() => new Set(activeField.value ? fieldDeps.value[activeField.value] ?? [] : []))

/** A 段：一行一次展开（键盘由 <button> 原生负责 Enter / Space） */

/** B 段：一条判断一次展开 */
function toggleConclusion(key: string) { openConclusion.value = openConclusion.value === key ? null : key }
/**
 * B 段整行可点：点在第一行按钮以外的位置（依赖 chip、留白）也展开。
 * 展开区里的任何点击都不切换——读原文、选字、点动作行时不会被误收起。
 */
function conclRowClick(event: MouseEvent, key: string) {
  const target = event.target as HTMLElement | null
  if (!target) return
  if (target.closest('.p7-concl__more-body')) return
  if (target.closest('button:not(.p7-concl__hit), a[href], [role="button"]')) return
  toggleConclusion(key)
}
function toggleLingerConclusion(key: string) { lingerConclusion.value = lingerConclusion.value === key ? null : key }

const conclusionEls = new Map<string, HTMLElement>()
function bindConclusion(key: string, el: Element | null) {
  if (el instanceof HTMLElement) conclusionEls.set(key, el)
  else conclusionEls.delete(key)
}
const flashId = ref('')
let flashTimer = 0
async function jumpToConclusion(key: string) {
  openField.value = null
  await nextTick()
  profileTab.value = 'judgments'
  await nextTick()
  conclusionEls.get(key)?.scrollIntoView({ block: 'center', behavior: reduced() ? 'instant' : 'smooth' })
  flashId.value = key
  window.clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => { flashId.value = '' }, 1400)
}

/** B 段的缺口标记 → C 段那条缺口：滚过去 + 闪一下，让"堵在哪"有落点 */
const gapFlash = ref('')
let gapTimer = 0
async function jumpToGap(key: string) {
  profileTab.value = 'gaps'
  await nextTick()
  document.querySelector(`[data-gap="${key}"]`)?.scrollIntoView({ block: 'center', behavior: reduced() ? 'instant' : 'smooth' })
  gapFlash.value = key
  window.clearTimeout(gapTimer)
  gapTimer = window.setTimeout(() => { gapFlash.value = '' }, 1400)
}

/** B 段 → A 段：滚到全量资料里的对应字段并展开。 */
async function jumpToField(key: string) {
  profileTab.value = 'facts'
  await nextTick()
  openField.value = key
  await nextTick()
  const el = document.querySelector<HTMLElement>(`.p7-row[data-key="${key}"]`)
  el?.scrollIntoView({ block: 'center', behavior: reduced() ? 'instant' : 'smooth' })
}

/* ═══════════════════════════════════════════════════════════════════════════
 * 9. 更正：40 字上限、错误提示、写回 demo / service
 * ======================================================================== */

const correction = ref<FieldRow | null>(null)
const value = ref('')
const correctionError = ref('')

function fieldValue(row: FieldRow) {
  if (live.value) return row.value
  return demo.state.profileEdits[row.key] ?? (row.key === 'grade' ? demo.use.scenario.value.grade + '（在读）' : row.value)
}

async function inspectField(row: FieldRow) {
  openField.value = null
  await nextTick()
  insights.value?.inspect(row.key, row.label)
}

function edit(row: FieldRow) {
  openField.value = null
  correction.value = row
  value.value = fieldValue(row)
  correctionError.value = ''
}

async function save() {
  if (!value.value.trim()) { correctionError.value = '请填写更正后的信息。'; return }
  if (value.value.trim().length > MAX_CHARS) { correctionError.value = '更正内容最多 40 个字。'; return }
  if (correction.value && live.value) {
    const field = correction.value
    const previous = livePanel.value?.fields?.find((item) => item.key === field.key)
    serviceError.value = ''
    try {
      const updated = await backendClient.correct(field.key, value.value.trim())
      if (previous && !originalLive.value[field.key]) backendDemo.rememberProfileOriginal(field.key)
      const workspace = JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace))
      workspace.profile_panel.fields = workspace.profile_panel.fields.map((item: ProfileFieldView) => (item.key === updated.key ? updated : item))
      backendDemo.setWorkspace(workspace)
    } catch {
      correctionError.value = '更正没有保存成功，输入仍保留，请重试。'
      return
    }
  }
  if (correction.value) demo.updateProfileField(correction.value.key, value.value)
  correction.value = null
}

const identity = computed(() => {
  const pick = (key: string) => known.value.find((row) => row.key === key)?.value
  const name = live.value ? pick('name') || demo.state.account : STUDENT.name
  const school = live.value ? pick('school') : demo.state.profileEdits.school ?? STUDENT.school
  const grade = live.value ? pick('grade') : demo.state.profileEdits.grade ?? demo.use.scenario.value.grade
  if (!live.value && demo.state.account === 'fresh') return { name: '新用户', line: '学校与年级待补充' }
  return { name: name || '个人档案', line: [school, pick('major'), grade || pick('degree_level')].filter(Boolean).join(' · ') || '学校与年级待补充' }
})
const profileStatement = computed(() => {
  const first = priorityConclusions.value[0]
  if (!first) return '资料还在形成中。先补充一段真实经历或一个明确偏好，再开始比较方向。'
  return `${first.brief || first.full}。因此，当前更适合把“${first.label}”作为优先验证方向，而不是过早定型。`
})
const enrollmentRows = computed(() => {
  const pick = (...keys: string[]) => known.value.find((row) => keys.includes(row.key))
  return [
    { label: '学校', row: pick('school', 'university') },
    { label: '专业', row: pick('major', 'major_name') },
    { label: '年级 / 学历', row: pick('grade', 'degree_level', 'education') },
    { label: '在读状态', row: pick('student_status', 'enrollment_status', 'study_status') },
  ].map(item => ({ ...item, value: item.row ? fieldValue(item.row) : '待补充' }))
})
function exportProfile(){const url=URL.createObjectURL(new Blob([JSON.stringify({profile:known.value,gaps:gapRows.value,source:live.value?'本次读取的档案':'个人画像'},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='职引-个人画像.json';a.click();URL.revokeObjectURL(url)}
onMounted(()=>{ void loadWorkspace() })
</script>

<template>
  <div class="ws-page profile-page p7">
    <PageHeading title="个人画像" description="把零散经历整理成可核对、可继续验证的职业探索档案。"><template #meta><div class="c2-page-meta"><span v-if="live">已读取的档案</span><span>{{ known.length }} 条已知 · {{ progress.gap }} 条待补充</span><span>判断可追溯到资料</span></div></template>
      <RouterLink class="btn btn--primary" to="/chat">{{ progress.gap ? '补充关键信息' : '更新信息' }}<UiIcon name="arrow" :size="16" /></RouterLink>
      <button class="btn" @click="exportProfile"><UiIcon name="download" :size="16"/>导出画像</button>
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

    <section class="profile-dossier" aria-labelledby="profile-dossier-title">
      <header class="profile-dossier__header">
        <div class="profile-dossier__identity">
          <div class="profile-dossier__portrait" aria-hidden="true">{{ identity.name.slice(0,1) }}</div>
          <div>
            <p class="profile-dossier__label">职业探索档案</p>
            <h2 id="profile-dossier-title">{{ identity.name }}</h2>
            <p>{{ identity.line }}</p>
          </div>
          <DetailPopover title="个人资料概况" label="查看个人资料概况"><p>已记录 {{ known.length }} 项信息，{{ progress.gap }} 项待补充。</p><p>依据充分 {{ confBands[0]?.count ?? 0 }} 项，待核对 {{ confBands[1]?.count ?? 0 }} 项。</p></DetailPopover>
        </div>
        <div class="profile-dossier__coverage">
          <div><span>资料完整度</span><strong>{{ known.length }}<small> / {{ known.length + progress.gap }}</small></strong></div>
          <div class="profile-dossier__track" :aria-label="'已记录'+known.length+'项，待补充'+progress.gap+'项'"><i v-for="n in known.length + progress.gap" :key="n" :class="{'is-known':n<=known.length}"/></div>
          <p>{{ progress.gap ? `还差 ${progress.gap} 项关键信息` : '关键信息已基本齐全' }}</p>
        </div>
      </header>

      <div class="profile-dossier__statement">
        <span>当前画像</span>
        <p>{{ profileStatement }}</p>
      </div>

      <div class="profile-dossier__body">
        <section class="profile-directions" aria-labelledby="profile-directions-title">
          <header>
            <div><h3 id="profile-directions-title">正在浮现的方向</h3><p>这些是接下来值得验证的假设，不是替你做出的职业定论。</p></div>
            <button class="ws-text-button" type="button" @click="profileTab='judgments'">查看完整分析<UiIcon name="arrow" :size="14"/></button>
          </header>
          <ul v-if="priorityConclusions.length">
            <li v-for="item in priorityConclusions" :key="item.key">
              <DetailPopover class="profile-direction" :title="item.label" :label="item.label + '：' + item.brief" side="bottom"><template #trigger>
                <span class="profile-direction__mark" aria-hidden="true"></span><span><strong>{{ item.label }}</strong><small>{{ item.brief || '这条判断暂时没有摘要。' }}</small></span><UiIcon name="info" :size="16" aria-hidden="true"/>
              </template><p>{{ item.full || item.brief }}</p><p class="profile-popover-meta">{{ item.section }} · {{ item.deps.length ? item.deps.length + ' 项资料支撑' : '逐项依据待核对' }}</p><p v-if="item.note">判断说明：{{ item.note }}</p><p v-if="item.risk">需要留意：{{ item.risk }}</p><p v-if="item.missingKeys.length">仍缺 {{ item.missingKeys.length }} 项关键资料。</p><button class="ws-text-button" type="button" @click="jumpToConclusion(item.key)">在完整分析中核对</button></DetailPopover>
            </li>
          </ul>
          <p v-else class="profile-focus-empty">当前还没有可展示的方向。补充资料后，再开始比较。</p>
        </section>

        <aside class="profile-next" aria-labelledby="profile-next-title">
          <p class="profile-next__label">下一步只做一件事</p>
          <template v-if="priorityGaps[0]">
            <h3 id="profile-next-title">{{ priorityGaps[0].label }}</h3>
            <p>{{ priorityGaps[0].why }}</p>
            <div class="profile-next__suggestion"><span>可以先这样做</span><strong>{{ priorityGaps[0].next }}</strong></div>
            <RouterLink class="btn btn--primary" :to="'/chat?gap='+encodeURIComponent(priorityGaps[0].key)+'&label='+encodeURIComponent(priorityGaps[0].label)">去补充这条信息<UiIcon name="arrow" :size="14"/></RouterLink>
            <button class="ws-text-button" type="button" @click="profileTab='gaps'">查看全部待补充信息</button>
          </template>
          <template v-else>
            <h3 id="profile-next-title">核对已有资料</h3>
            <p>当前没有明确缺口，可以从标为“待核对”的信息开始确认。</p>
          </template>
          <p v-if="needsCheck.length" class="profile-next__check">另有 {{ needsCheck.length }} 项资料需要核对</p>
        </aside>
      </div>
    </section>
<section class="enrollment" aria-labelledby="enrollment-title"><header><div><span class="enrollment__eyebrow">学校档案</span><h2 id="enrollment-title">学籍信息</h2><p>核对学校、专业与在读状态，查看学籍核验结果。</p></div><button class="btn" @click="verificationOpen=true"><UiIcon name="shield" :size="16" />{{ isVerified ? '重新核验' : '核验学籍' }}</button></header><dl><div v-for="item in enrollmentRows" :key="item.label"><dt>{{item.label}}</dt><dd :class="{'is-missing':item.value==='待补充'}">{{item.value}}</dd></div></dl><footer><span :class="['enrollment__state', isVerified ? 'is-verified' : '']"><i />{{ isVerified ? '已包含学信来源' : '尚未完成学信核验' }}</span><RouterLink class="ws-text-link" to="/grades">查看我的成绩<UiIcon name="arrow" :size="14" /></RouterLink></footer></section>



    

    <!-- ═══ A · 我知道什么 ═══ -->
    <section class="p7-block" aria-labelledby="p7-a-title">
      <header class="profile-facts-head"><div><span class="profile-focus-kicker">资料底稿</span><h2 id="p7-a-title">组成这份画像的信息</h2><p>所有字段完整展示；点开一项可核对来源、可信度和关联判断。</p></div><button class="btn" type="button" @click="profileTab='sources'">资料来源<UiIcon name="arrow" :size="14"/></button></header>

      <!-- 全量资料按主题展开，不设置搜索、范围或组织方式筛选。 -->
      <LayoutGroup>
        <motion.div class="p7-groups" :layout="true" :layout-dependency="0" :transition="{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }">
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
                <!-- 整行就是命中区：这一行的关系与来历都从这一下开始，注脚尺寸只留给信息本身 -->
                <DetailPopover class="profile-fact" :title="row.label" :label="row.label + '：' + fieldValue(row) + '，查看依据'" :model-value="openField === row.key" @update:model-value="(open: boolean) => openField = open ? row.key : null"><template #trigger>
                  <span class="p7-row__label">{{ row.label }}</span>
                  <span class="p7-row__main">
                    <span class="p7-row__value" :title="fieldValue(row)">{{ valueParts(row).head }}</span>
                    <span v-if="valueParts(row).hasHint" class="p7-row__hint">{{ valueParts(row).tail }}</span>
                    <span class="p7-row__meta">
                      <span v-if="!Number.isFinite(row.conf) || row.conf < 0.8" class="profile-needs-check">待核对</span><span class="p7-row__cue"><span class="sr-only">查看依据</span><UiIcon name="info" :size="16" /></span>
                    </span>
                  </span>
                </template><p class="profile-fact-value">{{fieldValue(row).slice(0,240)}}{{fieldValue(row).length>240?'…':''}}</p><div class="profile-fact-popover-meta"><SourceChip :source="row.src" :at="row.iso || null"/><ConfidenceBadge :confidence="row.conf" /></div><p class="profile-popover-meta">记录时间：{{ row.noted }}</p><p v-if="row.touched" class="profile-popover-meta">本人已更正<template v-if="row.prior">，原内容：{{ row.prior }}</template></p>
                  <div :id="`p7-more-${row.key}`" class="p7-row__more-body">
                    <div class="p7-row__actions">
                      <button class="ws-text-button" type="button" @click="inspectField(row)">深入了解这项信息</button>
                      <button class="ws-text-button" type="button" @click="edit(row)">更正信息<UiIcon name="arrow" :size="14" /></button>
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
                          <span class="p7-link__value" :title="conclusionMap[key]?.brief">{{ conclusionMap[key]?.brief }}</span>
                          <span class="p7-link__go" aria-hidden="true"><UiIcon name="arrow" :size="14" /></span>
                        </button>
                      </li>
                    </ul>
                    <div v-else class="profile-association-note"><template v-if="reportFields.has(row.key)"><button class="ws-text-button" @click="readAnalysis">查看关联报告<UiIcon name="arrow" :size="14"/></button><p>这项资料关联整份报告，尚未明确对应哪些具体判断。</p></template><p v-else>尚未提供这项资料与具体判断的关联依据。</p></div><button v-if="fieldDeps[row.key]?.length > 3" class="ws-text-button" @click="jumpToConclusion(fieldDeps[row.key][0])">查看全部分析与判断<UiIcon name="arrow" :size="14" /></button>


                  </div>
                </DetailPopover>
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
      <EmptyState v-if="!known.length" kind="profile" :heading-level="2" title="暂无个人信息" description="可以从一次咨询开始，也可以导入已有的学校资料。">
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
<InfoSheet :open="profileTab === 'judgments'" shape="panel" title="分析与判断" @close="profileTab='facts'"><section><ProfileInsights ref="insights" /></section><section class="p7-block" aria-labelledby="p7-b-title">
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
          :trend="{ label: `你更正了 ${changedFields.size} 条信息 · ${live ? '服务标记' : '依据关联资料更新'}` }"
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
              <span class="p7-concl__brief">{{ item.brief }}</span>
              <span class="p7-concl__side">
                <ConfidenceBadge v-if="Number.isFinite(item.conf)" class="p7-concl__conf" :confidence="item.conf" />
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
            <p class="p7-concl__full">{{ item.full }}</p>
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
            <button v-else class="ws-text-button" type="button" @click="insights?.inspect(item.key, item.label)">
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
        <span class="p7-block__count">{{ gapRows.length }} 条待补充</span>
      </header>

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
            <span class="chip chip--attention">待补充</span>
          </div>
          <p class="p7-gap__why"><span>为什么重要</span>{{ gap.why }}</p>
          <p class="p7-gap__blocked">
            <span>卡住了</span>
            <template v-if="gap.affects.length">
              <button v-for="affect in gap.affects" :key="affect.key" class="p7-affect" type="button" :title="affect.brief" @click="jumpToConclusion(affect.key)">
                <i aria-hidden="true" />{{ affect.label }}
              </button>
            </template>
            <template v-else>暂时没有判断直接用到它</template>
          </p>
          <p class="p7-gap__where">
            <span>去哪补</span>{{ gap.origin }}<template v-if="gap.blocked"> · {{ gap.blocked }}</template>
            <template v-if="gap.next"><em class="p7-gap__next">下一步：{{ gap.next }}</em></template>
          </p>
          <p v-if="gap.ask" class="p7-gap__ask"><span>可以直接回答</span>{{ gap.ask }}</p>
          <div class="p7-gap__actions">
            <RouterLink class="ws-text-link" :to="'/chat?gap=' + encodeURIComponent(gap.key) + '&label=' + encodeURIComponent(gap.label)">在咨询里补充<UiIcon name="arrow" :size="14" /></RouterLink>
            <button class="ws-text-button" type="button" @click="insights?.inspect(gap.key, gap.label, true)">看看需要补充什么</button>
          </div>
        </li>
      </ul>
      <p v-else class="ws-muted p7-none">暂未发现缺口。已记录的信息会继续按来源与可信度核对。</p>
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
      <section><h2>核对与管理资料</h2><RouterLink class="btn" to="/chat">补充一条信息<UiIcon name="plus" :size="16" /></RouterLink><button class="btn" :disabled="loading" @click="loadWorkspace">{{ loading ? '正在读取…' : '重新核对档案' }}</button><p>点开一条信息，可以查看依据、修改内容。更正后会标出受影响的判断。</p></section>
      <section><h2>这 {{ known.length }} 条从哪里来</h2><div v-for="source in SOURCE_GROUPS" :key="source.key" class="c2-source-row"><span>{{ source.label }}</span><span class="c2-source-track" role="meter" :aria-label="source.label" :aria-valuenow="known.filter(row => source.from.includes(row.desc)).length" :aria-valuemax="Math.max(1, known.length)" aria-valuemin="0"><i :style="{width: known.filter(row => source.from.includes(row.desc)).length / Math.max(1, known.length) * 100 + '%'}" /></span><b>{{ known.filter(row => source.from.includes(row.desc)).length }}</b></div></section>
      <section><h2>{{ identity.name }}</h2><p>{{ identity.line }}</p><p>整体可信度 {{ Math.round(trustShown) }}% · 覆盖 {{ known.length }} / {{ tally.total }}</p><Foldable variant="inline" title="查看计算依据"><p>{{ trustOrigin }}。{{ statusLine }}</p><p>{{ coverageNote }}</p></Foldable></section>
    </aside></InfoSheet>
    <InfoSheet :open="verificationOpen" shape="panel" title="核验学籍信息" @close="verificationOpen=false"><AcademicVerification /></InfoSheet>
    <!-- 更正是一条信息的小表单（`text` + 两个按钮），不是"从一行钻进去看细节"。
         所以 shape 是 dialog（缺省也是它，这里写出来是为了让形态是**显式**的）。 -->
    <InfoSheet shape="dialog" :open="correction !== null" :title="'更正' + (correction?.label ?? '信息')" @close="correction = null">
      <form @submit.prevent="save">
        <label class="ws-field">更正内容<textarea v-model="value" maxlength="40" /></label>
        <p v-if="correctionError" class="ws-field-error" role="alert">{{ correctionError }}</p>
        <div class="ws-inline-actions">
          <button class="btn btn--primary" type="submit">保存更正</button>
          <button class="btn" type="button" @click="correction = null">取消</button>
        </div>
      </form>
    </InfoSheet>
  </div>
</template>

<style scoped>
.profile-fact-value{font-size:15px;line-height:1.75;white-space:pre-wrap;overflow-wrap:anywhere}.profile-association-note p{font-size:13px;color:var(--c-text-3);margin-top:8px}@media(max-width:600px){.profile-identity__coverage{display:none}}
.enrollment{margin:18px 0 24px;padding:22px 24px;border:1px solid var(--c-border);border-radius:var(--r-lg);background:var(--c-surface)}.enrollment header{display:flex;align-items:start;justify-content:space-between;gap:24px}.enrollment__eyebrow{font-size:var(--fs-12);font-weight:var(--fw-semibold);color:var(--c-primary)}.enrollment h2{margin-top:3px;font-size:var(--fs-18);font-weight:var(--fw-semibold)}.enrollment header p{max-width:64ch;margin-top:5px;font-size:var(--fs-13);line-height:1.7;color:var(--c-text-2)}.enrollment dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-top:20px;border-top:1px solid var(--c-border);border-bottom:1px solid var(--c-border)}.enrollment dl>div{padding:15px 16px}.enrollment dl>div+div{border-left:1px solid var(--c-border)}.enrollment dt{font-size:var(--fs-12);color:var(--c-text-3)}.enrollment dd{margin-top:6px;font-size:var(--fs-14);font-weight:var(--fw-medium);color:var(--c-text)}.enrollment dd.is-missing{font-weight:var(--fw-regular);color:var(--c-text-3)}.enrollment footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:14px}.enrollment__state{display:flex;align-items:center;gap:7px;font-size:var(--fs-12);color:var(--c-text-3)}.enrollment__state i{width:7px;height:7px;border-radius:50%;background:var(--c-border-strong)}.enrollment__state.is-verified{color:var(--c-primary)}.enrollment__state.is-verified i{background:var(--c-primary)}
@media(max-width:760px){.enrollment{padding:18px}.enrollment header{flex-direction:column}.enrollment header .btn{width:100%}.enrollment dl{grid-template-columns:1fr 1fr}.enrollment dl>div:nth-child(3){border-left:0;border-top:1px solid var(--c-border)}.enrollment dl>div:nth-child(4){border-top:1px solid var(--c-border)}.enrollment footer{align-items:flex-start;flex-direction:column}}

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
