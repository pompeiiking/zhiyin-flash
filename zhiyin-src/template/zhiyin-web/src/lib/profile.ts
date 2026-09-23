/*
 * 画像里的**两类东西** —— 档案事实 与 判断维度。
 *
 * 这条线不划清，画像就会变成一张奇形怪状的雷达图：顶点是"学校 / 层次 / 学制 /
 * 预计毕业"，值全是 1.00 —— 那不是一个人的画像，那是一张学籍表的截图。
 * 事实没有"把握度"可言（它就是 1.00，因为它是从权威记录里抄下来的），
 * 把事实画进"维度图"，图上每一条都顶满，等于什么都没说。
 *
 * 所以口径按**来源**分，而不是按我们怎么想：
 *
 *   · 档案（fact）：从学信网 / 教务系统导进来的行政事实 —— 姓名、学校、院系、
 *     专业、层次、学制、学习形式、入学日期、预计毕业、学籍状态、课程、成绩。
 *     后端 `ProfileSource.record` 认的就是这一批（见 `policies/collection.py`
 *     的 `source: chsi / academic`）。它们**只回答"你在哪儿"，不回答"你是谁"**。
 *   · 判断（judgment）：价值取向、兴趣、经历、能力自评、目标方向、现实约束、
 *     卡住的地方 —— 这些要么是他亲口说的，要么是系统从他做过的事里推的，
 *     每一条都带一个**真的会变的**把握度。只有这一类值得画成图。
 *
 * 键表与 `data/registry/collection_rules.json` 的来源列一一对应；
 * 那边加了新的 chsi / academic 字段，这里要跟着加 —— 两处不同步时，
 * 表现是"多出来一个 1.00 的顶点把图撑满"，不难发现。
 */

/** 权威档案的字段键（学信网 + 教务系统） */
export const FACT_KEYS: ReadonlySet<string> = new Set([
  'student_name',
  'student_no',
  'school',
  'department',
  'major',
  'degree_level',
  'duration',
  'study_mode',
  'enrolled_at',
  'expected_graduation',
  'enrollment_status',
  'courses',
  'scores',
])

/** 判断维度：不是档案键，而且来源不是"导入的记录" */
export function isJudgment(field: { key: string; source?: string }): boolean {
  if (FACT_KEYS.has(field.key)) return false
  return field.source !== 'record'
}

/**
 * 把一份画像切成两堆。
 *
 * 数组顺序保持后端给的顺序 —— 后端按采集顺序排，那个顺序本身就是"先说哪件事"。
 */
export function splitProfile<T extends { key: string; source?: string }>(
  fields: readonly T[],
): { facts: T[]; judgments: T[] } {
  const facts: T[] = []
  const judgments: T[] = []
  for (const field of fields) (isJudgment(field) ? judgments : facts).push(field)
  return { facts, judgments }
}

/**
 * 把握度的三档。
 *
 * 0.6 / 0.85 两刀不是拍脑袋定的：0.6 是采集口径里的"缺口语义线"
 * （低于它的字段同时会出现在 gaps 里，见 `policies/collection_gate`），
 * 0.85 是"可以拿去做判断"的那一档。
 */
export function tierOf(value: number): 'low' | 'mid' | 'high' {
  return value < 0.6 ? 'low' : value < 0.85 ? 'mid' : 'high'
}
