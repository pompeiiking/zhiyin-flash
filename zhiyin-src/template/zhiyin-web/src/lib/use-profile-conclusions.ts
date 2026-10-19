import { computed } from 'vue'
import type { ComputedRef } from 'vue'
import { COLLECT_ITEMS, DIRECTION_PLANS, REPORT_SECTIONS } from '../data/student'
import { backendDemo } from './backend-demo'
import { exactProfileKeys } from './profile-organization'
import { LEGACY_CONF } from './use-profile-fields'
import type { FieldRow, MissingRow } from './use-profile-fields'
import type { DependencyEdgeView } from '../api/backend-types'

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
  study_year: '当前学习阶段', grade: '当前学习阶段', major: '专业', rank: '成绩层级', schedule: '本周课表与空档',
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
 *      供给→jobtype/city、成绩→rank、地域偏好→city/family），再加上当前学习阶段（study_year）。
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
  d1: ['major', 'interest', 'jobtype', 'city', 'internship', 'study_year'],
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
 * 3. 依赖关系：先契约、后演示
 * ======================================================================== */

/** backendDemo.state 是 readonly 的，读出来的边也是只读结构；这里只读不写 */
type ReadonlyEdge = { readonly from_asset: string; readonly to_asset: string; readonly via_profile_keys?: readonly string[] }


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

interface ProfileConclusionsDeps {
  live: ComputedRef<boolean>
  known: ComputedRef<FieldRow[]>
  rowsBase: ComputedRef<Omit<FieldRow, 'supports'>[]>
  fieldLabels: ComputedRef<Map<string, string>>
  missing: ComputedRef<MissingRow[]>
}

export function useProfileConclusions(deps: ProfileConclusionsDeps) {
  const { live, known, rowsBase, fieldLabels, missing } = deps

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
 * 7. B 段数据：下游结论 + 它依赖 A 里的哪几条
 * ======================================================================== */

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

  const reportFields=computed(()=>new Set(edges.value.filter(e=>e.to_asset==='report'||e.to_asset===backendDemo.state.liveReport?.report_id).flatMap(e=>e.via_profile_keys??[])))
  const needsCheck=computed(()=>known.value.filter(row=>!Number.isFinite(row.conf)||row.conf<0.8))

  const priorityConclusions = computed(() => Object.values(conclusionMap.value)
    .sort((a, b) => Number(b.kind === 'direction') - Number(a.kind === 'direction'))
    .slice(0, 3))

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
        origin: collect?.origin ?? (item.source === 'chsi' ? '来自学信网' : item.source === 'academic' ? '来自教务系统' : item.source === 'conversation' ? '来自对话' : item.key === 'internship' || item.key === 'project' ? '可以自己写一段发过来' : '来自对话'),
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

  return {
    depsSourceNote, conclusionMap, fieldDeps, reportFields, needsCheck,
    priorityConclusions, changedFields, recomputeIds, needsRecompute, depsMixed,
    gapRows, priorityGaps, gapIndex,
  }
}

export type { LinkedField, Conclusion, GapRow }
