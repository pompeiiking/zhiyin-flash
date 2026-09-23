import type { AiTask } from './types'

/*
 * 生成任务的登记处 —— 也可以理解成"前端要的 AI 接口清单"。
 *
 * 每一个 key 就是一条前后端约定（路径 = 后端 /api/v1 下的正式端点）：
 *
 *   key            →  后端接口                          产出                   依据从哪来
 *   ---------------------------------------------------------------------------------------
 *   brief.today    →  POST /app/brief/today             今天为什么是这两件事    画像 + 待办 + 时间轴
 *   dim.<key>      →  POST /app/dimensions/{key}        一条维度的完整解读      该画像字段的全部依据
 *   gap.<key>      →  POST /app/gaps/{key}/clarify      一条缺口的追问话术      缺口定义
 *   report.summary →  POST /app/report/summary          整份报告的结论段        报告资产全部维度
 *   bind.chsi      →  POST /app/chsi/bind               学籍核验               学信网
 *   plan.timetable →  POST /app/plan/timetable          课表→可投入时间         学信网课程 + 行为日志
 *   plan.todos     →  POST /app/plan/todos/suggestions  待办建议（可采纳）      课表 + 缺口 + 窗口
 *   match.careers  →  POST /app/match/careers           方向匹配矩阵与推荐      画像 + 成绩 + 学职网
 *
 * 前端不写 prompt、不拼依据、**也不自备一份产出**：那是后端（AI 编排层）的事。
 * 这里只声明"我要什么"，拿到的一定是 { data, citations, meta, rationale } 这个形状。
 *
 * ⚠️ 此前每个任务还带一段本地 `produce`，在后端不可达时会端出一份像模像样的假内容
 * （今天该做的两件事、维度得分、匹配矩阵…）。那段代码没有任何 Provider 会调用，
 * 却让"没实现"看起来像"已经实现"—— 已整体删除。
 */

/**
 * 产出形状：与后端 `zhiyin-business/.../contracts/ai_tasks.py` 一一对应。
 *
 * 为什么这里仍然是手写的：SSE 端点没有 OpenAPI 响应体（流式，终帧才是结果），
 * 所以 `npm run gen:api` 生成不到它们。字段名与别名（`ifYouSkip` / `whyNow`）必须
 * 与后端契约一致 —— 改后端那几张模型时，这里要一起改。
 */

export interface ReportSummary {
  headline: string
  paragraphs: string[]
  moves: { label: string; why: string }[]
}

export interface BriefToday {
  headline: string
  because: { text: string; from: string }[]
  changed: { text: string; at: string }[]
  ifYouSkip: string
  next: { id: string; label: string; why: string }[]
}

export interface TrendPoint {
  at: string
  v: number
  why: string
}

/** 一条画像维度的深度解读（后端 `DimensionReading`）。 */
export interface DimensionReading {
  id: string
  name: string
  conclusion: string
  reading: string
  score: number
  delta: number
  /** 决策线 / 岗位基准；0 表示这条没有基准，不是"线上是 0" */
  bench: number
  trend: TrendPoint[]
  next: string
}

/**
 * 一条缺口的追问话术（后端 `GapClarify`）。
 *
 * 这一份**现在还没有界面入口**：画像页里点一条缺口，展开的是采集策略给出的
 * 现成理由与建议（`ProfileGapView` 里的 `question` / `suggested`），
 * 没有走模型生成。契约仍然对齐着，因为仓库有一条守卫要求"后端每种产出形状，
 * 前端都得有对应的一份"（见 `tests/test_ai_task_contract_alignment.py`）——
 * 那种一致不是装饰：要接的时候，接上的是同一份声明，不用先追一遍后端改了什么。
 */
export interface GapClarify {
  question: string
  options: { label: string; why: string }[]
  whyNow: string
}

/** 一条分析里的结论 + 它凭什么（后端 `AnalysisPoint`）。 */
export interface AnalysisPoint {
  label: string
  why: string
}

/**
 * 「对你的分析」（后端 `PortraitAnalysis`）。
 *
 * 与 `DimensionReading` 的分工：那一条是**一条字段**的注解，这一份是
 * **整份画像合起来**的判断 —— 手里有什么、方向有多确定、卡在哪、下一步先动什么。
 * 画像页第一屏放的就是它。
 */
export interface PortraitAnalysis {
  headline: string
  reading: string
  strengths: AnalysisPoint[]
  watchouts: AnalysisPoint[]
  next: AnalysisPoint[]
}

/** 「这一天的建议」（后端 `DayAdvice`）：日历里点开某一天时生成。 */
export interface DayAdvice {
  date: string
  headline: string
  reading: string
  plan: AnalysisPoint[]
  watch: string
}

export interface BindStep {
  id: string
  label: string
  detail: string
  /** 这一步产出的条目数（0 表示只是流程节点） */
  got: number
  source: string
}

export interface BindResult {
  steps: BindStep[]
  courses: unknown[]
  /** 导入之后画像里哪几条被抬高了 */
  lifted: { dim: string; from: number; to: number; because: string }[]
}

export interface TimetablePlan {
  headline: string
  windows: { day: string; slot: string; why: string }[]
  moves: { at: string; what: string; why: string }[]
}

export interface TodoSuggestion {
  id: string
  label: string
  why: string
  from: string
  when: string
  weight: number
}

export interface MatchResult {
  cells: { track: string; skill: string; need: number; have: number }[]
  ranking: { track: string; fit: number; gap: string; why: string }[]
  recommend: { title: string; body: string; because: string[] }
}

export const AI_ENDPOINTS = {
  'brief.today': { path: '/api/v1/app/brief/today' },
  'dim.<id>': { path: '/api/v1/app/dimensions/{id}' },
  'portrait.analysis': { path: '/api/v1/app/portrait/analysis' },
  'day.<id>': { path: '/api/v1/app/day/{id}/advice' },
  'gap.<id>': { path: '/api/v1/app/gaps/{id}/clarify' },
  'report.summary': { path: '/api/v1/app/report/summary' },
  'bind.chsi': { path: '/api/v1/app/chsi/bind' },
  'plan.timetable': { path: '/api/v1/app/plan/timetable' },
  'plan.todos': { path: '/api/v1/app/plan/todos/suggestions' },
  'match.careers': { path: '/api/v1/app/match/careers' },
} as const

/** task key → 实际请求路径（dim.<id> / gap.<id> 这类带参数的在这里展开） */
export function aiPath(key: string): string {
  const [head, arg] = key.split('.') as [string, string?]
  const entry =
    (AI_ENDPOINTS as Record<string, { path: string }>)[key] ??
    (AI_ENDPOINTS as Record<string, { path: string }>)[`${head}.<id>`]
  if (!entry) throw new Error(`未登记的 AI 任务 key：${key}`)
  return entry.path.replace('{id}', encodeURIComponent(arg ?? ''))
}

/** 今天为什么是这两件事 —— 打招呼那块点开要看的东西 */
export function briefTask(): AiTask<BriefToday> {
  return { key: 'brief.today', label: '正在把今天要做的两件事排出来' }
}

/**
 * 一条画像维度的完整解读 —— 画像里点开某个字段时生成。
 *
 * `fieldKey` 是画像字段的 key（`profile_panel.fields[].key`）：后端按它取该字段的
 * 全部依据再解读。所以这里传的是 key，不是展示名 —— 名字是给人看的，取数要用 key。
 */
export function dimensionTask(fieldKey: string, label = ''): AiTask<DimensionReading> {
  return {
    key: `dim.${fieldKey}`,
    label: label ? `正在读「${label}」的全部依据` : '正在读这条维度的全部依据',
  }
}

/**
 * 「对你的分析」—— 画像打开时生成的那一段整体判断。
 *
 * 不带参数：它读的是**整份画像**，不是某一条字段。所以它和维度解读是两件
 * 不同的产物，缓存 key 也不同（`portrait.analysis` vs `dim.<字段>`）。
 */
export function portraitTask(): AiTask<PortraitAnalysis> {
  return { key: 'portrait.analysis', label: '正在把整份画像读成一段判断' }
}

/**
 * 「这一天的建议」—— 日历里点开某一天时生成。
 *
 * 日期进的是 **key**（`day.2026-09-22`），和 `dim.<字段>` 同一种做法：
 * key 就是缓存键，所以每一天各存一份，来回点也不会重复算。
 */
export function dayAdviceTask(day: string): AiTask<DayAdvice> {
  return {
    key: `day.${day}`,
    label: `正在看 ${day} 这一天`,
    // 时区偏移（分钟，东为正）：后端存的是 UTC，"那一天"得按用户那边的日界线算
    arg: String(-new Date().getTimezoneOffset()),
  }
}

/**
 * 一条缺口的追问话术 —— 用户点"补这一条"时生成。
 *
 * 注意：这一条**目前没有界面入口**（见上面 `GapClarify` 的说明），
 * 但它是后端 `/app/gaps/{key}/clarify` 的对应声明 ——
 * 仓库守卫要求后端每个端点在前端都有使用者，删掉它只会让守卫变红，
 * 而真正该做的是把它接上（或者连后端一起下掉，那是一次产品决定）。
 */
export function gapTask(gapKey: string): AiTask<GapClarify> {
  return { key: `gap.${gapKey}`, label: '正在准备这一条的追问' }
}

/** 整份报告的结论段 —— 报告页打开时生成 */
export function reportTask(): AiTask<ReportSummary> {
  return { key: 'report.summary', label: '正在把全部维度收成一段结论' }
}

/**
 * 学信网绑定：核验用户提供的**在线验证码**，读回本人学籍。
 *
 * 为什么是验证码而不是账号密码：学信网没有面向第三方的个人数据接口，
 * 唯一官方允许的机器可读通道就是"在线验证报告 + 验证码"。
 * 全程不需要、也不应该拿到用户的学信网账号。
 *
 * 覆盖边界：报告里只有学籍/学历/学位，**没有课程表与成绩单**。
 */
export function bindChsiTask(code: string): AiTask<BindResult> {
  return { key: 'bind.chsi', label: '正在向学信网核验这份报告', arg: code.trim() }
}

/** 课表 → 可投入时间 */
export function timetableTask(): AiTask<TimetablePlan> {
  return { key: 'plan.timetable', label: '正在把你的课表读成可投入的时间' }
}

/** 待办建议（智能体给的，可采纳） */
export function todoTask(): AiTask<TodoSuggestion[]> {
  return { key: 'plan.todos', label: '正在把该做的事排进你的空档' }
}

/** 方向匹配矩阵与推荐 */
export function matchTask(): AiTask<MatchResult> {
  return { key: 'match.careers', label: '正在拿学职网的职业条目比对你的课程与成绩' }
}
