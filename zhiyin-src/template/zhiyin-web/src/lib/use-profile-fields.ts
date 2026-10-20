import { computed, ref } from 'vue'
import type { ComputedRef } from 'vue'
import { demo } from '../store'
import { PROFILE_FIELDS } from '../data/student'
import type { FieldSource, ProfileField } from '../data/types'
import { profileLabel } from './server-copy'
import { backendDemo } from './backend-demo'
import { backendClient } from '../api/backend-client'
import type { ProfileSource } from '../api/backend-types'

type BackendState = typeof backendDemo.state
/** `backendDemo.state` 是 readonly 的，读出来的画像面板与原件也是只读结构 */
export type LiveProfilePanel = NonNullable<BackendState['liveWorkspace']>['profile_panel']
export type LiveProfileOriginals = BackendState['profileOriginals']

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

/**
 * 《个人画像设计-2026-10-20》第 9 节：页面围绕三种内容组织 ——
 * 用户提供的信息、系统基于证据的理解、近期补充与变化。
 * 后端的 8 个内容类别是组织视角，不铺成一张必填表格；这里只把它们归到三块。
 */
export type ContentSection = 'provided' | 'understanding' | 'supplement'

const CONTENT_SECTIONS: { key: ContentSection; title: string; hint: string }[] = [
  { key: 'provided', title: '你提供的信息', hint: '本人自述、本人确认与资料记录' },
  { key: 'understanding', title: '系统基于证据的理解', hint: '等待核对的线索，不是事实结论' },
  { key: 'supplement', title: '近期补充与变化', hint: '暂未归类、有来源的补充信息' },
]

/** 后端没有下发类别时（老数据 / 演示数据）的本地兜底：与 kernel 词表同口径。 */
const TYPE_BY_KEY: Record<string, string> = {
  school: 'learning_background', major: 'learning_background', department: 'learning_background',
  study_year: 'learning_background', degree_level: 'learning_background', enrollment_status: 'learning_background',
  student_name: 'learning_background', student_no: 'learning_background', duration: 'learning_background',
  study_mode: 'learning_background', enrolled_at: 'learning_background', expected_graduation: 'learning_background',
  courses: 'learning_background', scores: 'learning_background', current_status: 'learning_background',
  interest: 'interest', interests: 'interest', style: 'interest', preferences: 'interest',
  experience: 'experience', internship: 'experience', project: 'experience',
  skills: 'ability', resume_material: 'ability', award: 'ability', weakness: 'ability',
  target_direction: 'career_focus', target_direction_job_posting: 'career_focus', target_job: 'career_focus',
  career_interest: 'career_focus', career_focus: 'career_focus', direction: 'career_focus',
  values: 'values', constraints: 'condition', city: 'condition', jobtype: 'condition', salary: 'condition',
  family: 'condition', time: 'condition', weekly_hours: 'condition', pipeline: 'condition', schedule: 'condition',
  stuck_point: 'condition', supplement: 'supplement', supplement_info: 'supplement',
}

const TYPE_LABELS: Record<string, string> = {
  learning_background: '学习背景', interest: '兴趣与偏好', experience: '经历', ability: '能力与技能',
  career_focus: '职业关注', values: '价值取向', condition: '现实条件', supplement: '补充信息',
}

const VERIFICATION_LABELS: Record<string, string> = {
  self_reported: '本人自述', user_confirmed: '本人确认', record: '资料记录', verified: '已核验', pending: '待核对',
}

/** 核实状态决定一条记录属于“用户提供”还是“系统理解”，不用置信度分数混合这两件事。 */
function verificationOf(row: { source: ProfileSource; verification?: string }): string {
  if (row.verification) return row.verification
  if (row.source === 'user_edit') return 'user_confirmed'
  if (row.source === 'record' || row.source === 'resume') return 'record'
  if (row.source === 'assessment' || row.source === 'behavior_inference') return 'pending'
  return 'self_reported'
}

const CONF_GROUPS = [
  { key: 'high', title: '有来源支持', hint: '本人确认或资料记录' },
  { key: 'mid', title: '本人自述', hint: '来自对话，尚未外部核验' },
  { key: 'low', title: '待核对', hint: '系统理解或信息不全' },
]

function sectionOf(entryType: string, verification: string): ContentSection {
  if (entryType === 'supplement') return 'supplement'
  if (verification === 'pending') return 'understanding'
  return 'provided'
}

/* ═══════════════════════════════════════════════════════════════════════════
 * 4. A 段数据：每条默认带来源 / 可信度 / 时间
 * ======================================================================== */

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
  /** 内容类别（学习背景 / 兴趣 / 经历 / 能力 / 职业关注 / 价值取向 / 现实条件 / 补充信息） */
  entryType: string
  typeLabel: string
  /** 核实状态：本人自述 / 本人确认 / 资料记录 / 已核验 / 待核对 */
  verification: string
  verificationLabel: string
  /** 待核对：系统理解或信息不全，不显示成“已确认” */
  needsCheck: boolean
  /** 页面三块：你提供的信息 / 系统基于证据的理解 / 近期补充与变化 */
  section: ContentSection
  /** 原话或资料来源引用（服务端写入时固化，不在前端编造） */
  originRef: string
}

/** 一条“系统基于证据的理解”：它必须能单独展示、单独否认，不能混进事实字段。 */
export interface ClueRow {
  id: string
  text: string
  evidence: string[]
  createdAt: string
}

export interface MissingRow {
  key: string
  label: string
  reason: string
  next: string
  source: string
}

/** 一条冲突提案：与当前记录并存的另一种说法，等待用户裁定。 */
export interface ConflictRow {
  id: string
  key: string
  label: string
  value: string
  currentValue: string
  reason: string
  createdAt: string
}

interface ValueParts { head: string; tail: string; hasHint: boolean }

interface RowGroup {
  key: string
  title: string
  hint: string
  rows: FieldRow[]
}

export interface ProfileFieldsDeps {
  live: ComputedRef<boolean>
  livePanel: ComputedRef<LiveProfilePanel>
  originalLive: ComputedRef<LiveProfileOriginals>
  progress: ComputedRef<{ known: number; total: number; gap: number }>
  getFieldDeps: () => Record<string, string[]>
}

export function useProfileFields(deps: ProfileFieldsDeps) {
  const { live, livePanel, originalLive, progress, getFieldDeps } = deps

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
        // 类别与核实状态由服务端下发；老数据缺这两个字段时按同一份受控词表兜底。
        const entryType = field.entry_type ?? TYPE_BY_KEY[field.key] ?? 'supplement'
        const verification = verificationOf({ source: field.source, verification: field.verification })
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
          entryType,
          typeLabel: field.entry_type_label || TYPE_LABELS[entryType] || '补充信息',
          verification,
          verificationLabel: field.verification_label || VERIFICATION_LABELS[verification] || '待核对',
          needsCheck: verification === 'pending',
          section: sectionOf(entryType, verification),
          originRef: field.origin_ref ?? '',
        }
      })
    }
    return PROFILE_FIELDS.slice(0, progress.value.known).map((field) => {
      const touched = !!demo.state.profileEdits[field.key]
      const entryType = TYPE_BY_KEY[field.key] ?? 'supplement'
      const verification: string = touched ? 'user_confirmed' : 'self_reported'
      return {
        ...field,
        desc: touched ? '本人填写' as const : field.source,
        src: touched ? 'user_edit' as const : SOURCE_ENUM[field.source],
        conf: LEGACY_CONF[field.confidence.level],
        prior: touched ? field.source : '',
        iso: '',
        evidence: [] as string[],
        touched,
        entryType,
        typeLabel: TYPE_LABELS[entryType] ?? '补充信息',
        verification,
        verificationLabel: VERIFICATION_LABELS[verification] ?? '待核对',
        needsCheck: verification === 'pending',
        section: sectionOf(entryType, verification),
        originRef: '',
      }
    })
  })

  /** 依赖解析只需要"这一条在不在、叫什么"，所以断在 rowsBase 上，别绕回 known */
  const fieldLabels = computed<Map<string, string>>(() => new Map(rowsBase.value.map((row) => [row.key, row.label])))

  /** A 段最终形态：在 rowsBase 上补上"支撑 N 条判断"。关系与 B 段同源，不另算一套。 */
  const known = computed<FieldRow[]>(() => rowsBase.value.map((row) => ({ ...row, supports: (getFieldDeps()[row.key] ?? []).length })))

  /**
   * 值的排版：长值让整行高度失控，是因为长度差全落在"折几行"上。
   * 演示数据里把"本人说明，待核对"这类括注挪到注脚那一行，
   * 主值回到一个短语，行高就稳了。真实数据（live）一个字都不动。
   */
  const LONG_VALUE = 15

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

  const missing = computed(() => {
    const rows = live.value
      ? (livePanel.value?.gaps ?? []).map((gap) => ({ key: gap.key, label: gap.label ?? gap.key, reason: gap.reason, next: gap.suggested_next_action ?? '', source: '' }))
      : PROFILE_FIELDS.slice(progress.value.known).map((field) => ({ key: field.key, label: field.label, reason: '', next: '', source: '' }))
    if (!live.value) return rows
    // 画像面板的 gaps 只收"影响判断"的缺口；采集清单里没拿到的学校/专业/层次等也要进待补充列表，
    // 否则会出现"资料完整度 1/15"却"暂未发现缺口"的自相矛盾。
    const knownKeys = new Set(rows.map((row) => row.key))
    for (const item of backendDemo.state.liveWorkspace?.collection_panel?.items ?? []) {
      if (item.got || knownKeys.has(item.key)) continue
      knownKeys.add(item.key)
      rows.push({ key: item.key, label: item.label ?? item.key, reason: item.why ?? '', next: item.ask ?? '', source: item.source ?? '' })
    }
    return rows
  })

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
    // 分档按「核实状态」，不按内部置信度：来源与核实状态分开表达（设计第 3.1/4 节）。
    const firm = rows.filter((row) => ['user_confirmed', 'record', 'verified'].includes(row.verification)).length
    const check = rows.filter((row) => row.verification === 'self_reported').length
    const thin = rows.filter((row) => row.verification === 'pending').length
    const confirmedTotal = rows.length + missing.value.length
    const computedCoverage = confirmedTotal ? rows.length / confirmedTotal : 0
    const fromBackend = backendRatio(livePanel.value?.coverage)
    const coverage = fromBackend ?? computedCoverage
    const coverageSource: 'backend' | 'local' | 'backend-count' = fromBackend !== null ? 'backend' : live.value ? 'backend-count' : 'local'
    // 兼容字段：页面不再展示整体置信度百分比，这个数只留给旧调用方读取。
    const backendTrust = backendRatio(livePanel.value?.overall_confidence)
    const trust = backendTrust !== null ? Math.round(backendTrust * 100) : 0
    return { firm, check, thin, coverage, coverageSource, trust, trustFromBackend: backendTrust !== null, localTrust: 0, fromTalk: rows.filter((row) => row.desc === '对话').length, total: confirmedTotal }
  })

  const statusLine = computed(() => {
    const t = tally.value
    const parts = [`${t.firm} 条有来源支持`, `${t.check} 条本人自述`, `${t.thin} 条待核对`]
    parts.push(`${missing.value.length} 条可以补充`)
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
  function stopTween() { cancelAnimationFrame(trustFrame) }

  function fieldValue(row: FieldRow) {
    if (live.value) return row.value
    return demo.state.profileEdits[row.key] ?? (row.key === 'grade' ? demo.use.scenario.value.grade + '（在读）' : row.value)
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   * 6. 全量资料：按《个人画像设计》第 9 节的三种内容组织
   * ======================================================================== */

  const TYPE_ORDER: Record<string, number> = {
    learning_background: 0, career_focus: 1, interest: 2, experience: 3,
    ability: 4, values: 5, condition: 6, supplement: 7,
  }

  const groups = computed<RowGroup[]>(() => {
    const rows = [...known.value].sort((a, b) =>
      (TYPE_ORDER[a.entryType] ?? 9) - (TYPE_ORDER[b.entryType] ?? 9) || a.key.localeCompare(b.key))
    return CONTENT_SECTIONS.map((section) => ({
      key: section.key,
      title: section.title,
      hint: section.hint,
      rows: rows.filter((row) => row.section === section.key),
    }))
  })

  /** 系统理解（待验证线索）：只展示仍待核对的；已失效的不再当结论反复出现。 */
  const clues = computed<ClueRow[]>(() =>
    (livePanel.value?.clues ?? [])
      .filter((clue) => !clue.status || clue.status === 'proposed')
      .map((clue) => ({
        id: clue.id,
        text: clue.text,
        evidence: [...(clue.evidence ?? [])],
        createdAt: clue.created_at,
      })),
  )

  async function denyClue(id: string) {
    if (!live.value) return
    await backendClient.denyProfileClue(id)
    const workspace = JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace))
    if (workspace?.profile_panel) {
      workspace.profile_panel.clues = (workspace.profile_panel.clues ?? []).filter((clue: { id: string }) => clue.id !== id)
    }
    if (workspace) backendDemo.setWorkspace(workspace)
  }

  /** 冲突提案：与当前值并存的另一种说法；当前值从投影里取，不改写事实。 */
  const conflicts = computed<ConflictRow[]>(() =>
    (livePanel.value?.conflicts ?? []).map((item) => ({
      id: item.id,
      key: item.key,
      label: item.label || item.key,
      value: human(item.value),
      currentValue: known.value.find((row) => row.key === item.key)?.value ?? '未记录',
      reason: item.change_reason || '与当前记录不一致，等待核对',
      createdAt: item.created_at,
    })),
  )

  async function resolveConflict(id: string, choice: 'revision' | 'current') {
    if (!live.value) return
    await backendClient.resolveProfileConflict(id, choice)
    // 裁定可能改当前投影：重新读一次，别用乐观更新覆盖别的字段。
    const workspace = await backendClient.workspace()
    backendDemo.setWorkspace(workspace)
  }

  return {
    fieldValue, valueParts, rowsBase, fieldLabels, missing, known,
    tally, statusLine, confBands, trustOrigin, coverageCount, coverageNote,
    groups, clues, denyClue, conflicts, resolveConflict, reduced, trustShown, tweenTo, stopTween,
  }
}

export type { FieldRow }
export { LEGACY_CONF }
