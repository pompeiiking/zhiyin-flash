/**
 * 日期与百分比的统一出口（F2）。
 *
 * 背景：同一个"生成时间"在不同页面被写成 `2026-10-18`、`2026年10月18日`、
 * `10/18`、`2026-10-18T04:11:00Z` 四种样子，学生无法比较；百分比也散落成
 * `Math.round(x * 100) + '%'`。这里只做**显示层**格式化：
 *   · 不解析后端字段、不改变数据、不推断时区（按浏览器本地时间显示）；
 *   · 拿不到/解析失败时返回空串或"—"，由调用方决定兜底文案；
 *   · 所有页面都从这一个文件取格式，新增页面不要自己写 Intl 选项。
 *
 * 约定：
 *   formatDate       2026年10月18日
 *   formatDateTime   2026年10月18日 04:11（24 小时制）
 *   formatMonthDay   10月18日（日历/区间用）
 *   formatDateRange  10月12日 — 10月18日
 *   formatRelative   今天 / 昨天 / 3 天前 / 2026年10月18日
 *   formatPercent    0–1 或 0–100 统一成整数百分比（100%）
 */

function toDate(value: unknown): Date | null {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(String(value))
  return Number.isNaN(date.getTime()) ? null : date
}

const pad2 = (value: number) => String(value).padStart(2, '0')

/** 2026年10月18日 */
export function formatDate(value: unknown): string {
  const date = toDate(value)
  if (!date) return ''
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`
}

/** 2026年10月18日 04:11 */
export function formatDateTime(value: unknown): string {
  const date = toDate(value)
  if (!date) return ''
  return `${formatDate(date)} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

/** 10月18日 */
export function formatMonthDay(value: unknown): string {
  const date = toDate(value)
  if (!date) return ''
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

/** 10月12日 — 10月18日（跨年时补年份） */
export function formatDateRange(start: unknown, end: unknown): string {
  const from = toDate(start)
  const to = toDate(end)
  if (!from || !to) return ''
  if (from.getFullYear() !== to.getFullYear()) return `${formatDate(from)} — ${formatDate(to)}`
  return `${formatMonthDay(from)} — ${formatMonthDay(to)}`
}

/** 今天 / 昨天 / N 天前 / 10月18日 / 2025年3月2日 */
export function formatRelative(value: unknown, now: Date = new Date()): string {
  const date = toDate(value)
  if (!date) return ''
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days > 1 && days <= 30) return `${days} 天前`
  return date.getFullYear() === now.getFullYear() ? formatMonthDay(date) : formatDate(date)
}

/**
 * 百分比：0–1 视为比例（0.62 → 62%），>1 视为已经是百分数（62 → 62%）。
 * 非数字返回 "—"；调用方需要无占位时可传 fallback。
 */
export function formatPercent(value: unknown, digits = 0, fallback = '—'): string {
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return fallback
  const percent = Math.abs(num) <= 1 ? num * 100 : num
  const rounded = Number(percent.toFixed(digits))
  return `${rounded}%`
}

/** 数量 + 单位：3 条 / 0 项（数字与中文单位之间保留一个空格，和全站口径一致） */
export function formatCount(value: unknown, unit: string): string {
  const num = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(num) ? `${num} ${unit}` : `— ${unit}`
}

/**
 * 原始证据的展示口径：滤掉**内部追溯引用**，只留给人读的话。
 *
 * 画像字段的 evidence / 判断依据里可能混有 `chsi-pdf://imports/…`、
 * `derived://…` 这类内部键 —— 它们是给溯源和幂等用的（`origin_ref` 同款），
 * 展示到卡片上就是一串"开发数据"。http(s) 链接是真实出处，保留。
 * 数据不删不改，只影响显示。
 */
export function visibleEvidence(items: readonly string[] | undefined | null): string[] {
  return (items ?? []).filter(item => !/^(?!https?:\/\/)[a-z][a-z0-9+.-]*:\/\//i.test(item.trim()))
}

/**
 * 已知的画像字段中文名（内部键 → 学生看的叫法）。
 * 兜底用：渲染层优先拿后端下发的 label（profile_panel / 报告快照都有）。
 */
const FIELD_LABELS: Record<string, string> = {
  school: '学校', department: '院系', major: '专业', major_name: '专业',
  degree_level: '学历层次', duration: '学制', study_mode: '学习形式',
  enrolled_at: '入学日期', expected_graduation: '预计毕业时间',
  enrollment_status: '学籍状态', study_year: '当前学习阶段', grade: '年级',
  student_no: '学号', student_name: '姓名',
}

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? '画像资料'
}

/**
 * 把模型/存量数据里的**内部追溯记号**翻译成给学生看的话。
 *
 * 评估结论与报告引用里可能出现：`chsi-pdf://imports/<id>`（PDF 导入回执键）、
 * `derived://study_year/...`（推算键）、`field:<key>` / `evidence:<key>:<n>` /
 * `conflict:<id>`（评估的内部编号）。它们是溯源用的，落到卡片上就是开发数据。
 * 只影响显示，不改数据；评估提示词已要求新产出的模型文本不再携带这些记号，
 * 这里兜住**已经存库**的旧文本。
 */
export function studentizeRefs(text: string | undefined | null): string {
  const raw = String(text ?? '')
  if (!raw) return ''
  return raw
    .replace(/chsi-pdf:\/\/[a-z0-9/:._-]+/gi, '学信网学籍报告（PDF 导入）')
    .replace(/derived:\/\/[a-z0-9/:._=-]+/gi, '按入学日期推算')
    .replace(/verification=([a-z_]+)/gi, (_m, value: string) => `核实状态：${VERIFY_LABELS[value] ?? value}`)
    .replace(/assertion_type=([a-z_]+)/gi, (_m, value: string) => ASSERT_LABELS[value] ?? value)
    .replace(/evidence:([a-z_][a-z0-9_]*):(\d+)/gi, (_m, key: string, index: string) => `${fieldLabel(key)}的第${Number(index) + 1}份材料`)
    .replace(/evidence:([a-z_][a-z0-9_]*)/gi, (_m, key: string) => `${fieldLabel(key)}的相关材料`)
    .replace(/field:([a-z_][a-z0-9_]*)/gi, (_m, key: string) => fieldLabel(key))
    .replace(/conflict:[A-Za-z0-9_-]+/g, '一条待核对的冲突')
}

const VERIFY_LABELS: Record<string, string> = {
  self_reported: '本人自述，尚无独立核实', user_confirmed: '本人确认',
  verified: '已核验', record: '客观记录', pending: '待核对',
}
const ASSERT_LABELS: Record<string, string> = {
  affirmative_self_statement: '本人自述', explicit_correction: '本人更正',
  conflict_candidate: '待核对候选', negative: '否定表述', hypothetical: '假设',
  quoted: '引用原文', uncertain: '不确定', refusal: '拒绝回答',
}
