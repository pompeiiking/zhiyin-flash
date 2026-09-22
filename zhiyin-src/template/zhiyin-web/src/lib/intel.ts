import type { IntelItem } from '@/api/client'

/**
 * 外部情报的"读法"。
 *
 * 后端给的是一条条**抓回来的原文片段**（`IntelItem.text`），形状是
 * `字段名：值` 一行一行排下来的 —— 那是爬虫最好写、也最忠实于原页面的形状：
 *
 *   专业：会计学
 *   简介：本专业培养……
 *   年招生规模：100000人以上
 *   满意度：4.4（215148 人评价）
 *   对口职业：会计/会计师（占比 21%）、财务分析经理/主管（占比 7%）、银行会计/柜员（占比 6%）
 *   升学方向：金融、税务、马克思主义理论、法律（非法学）
 *
 * 直接把这一段贴到界面上就是"一坨字"：用户读不出"哪一句是结论、哪几个数能比"。
 * 但也不能让前端**重写**这些内容 —— 那是编。所以这里只做一件事：
 * **把已经存在于文本里的结构读出来**（拆字段、认占比、拆顿号列表），
 * 一个字的正文都不新增。
 *
 * 为什么规则写得宽松：情报是三类东西（专业 / 职业 / 校友案例）共用同一个字段，
 * 每类的字段名都不一样（简介 / 职业定义 / 摘要）。凡是认不出的行，
 * 原样留成一行文字 —— 宁可少做一层排版，也不丢原文。
 */

/** 一行里的字段名最多几个字 —— 再长就不是字段名，是正文里的冒号 */
const LABEL_MAX = 10
const LABEL_LINE = new RegExp(`^([^：:]{1,${LABEL_MAX}})[：:]\\s*(.*)$`)

/** 这几行的值就是这块内容的"正文"，其余是它的属性 */
const INTRO_LABELS = new Set(['简介', '职业定义', '摘要', '说明', '基本信息'])
/** 这几行重复了标题（"专业：会计学"而标题就叫会计学），不重复显示 */
const TITLE_LABELS = new Set(['专业', '职业', '案例', '专业名称', '职业名称'])

export interface IntelField {
  label: string
  value: string
}

export interface IntelReading {
  /** 一段话（简介 / 职业定义 / 摘要） */
  intro: string
  /** 其余带字段名的行，按原文顺序 */
  fields: IntelField[]
  /** 认不出字段名的散行，原样留着 */
  loose: string[]
}

export function readIntelText(text: string, title = ''): IntelReading {
  const lines = String(text ?? '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

  const fields: IntelField[] = []
  const loose: string[] = []
  let intro = ''

  for (const line of lines) {
    const matched = line.match(LABEL_LINE)
    if (!matched) {
      if (!intro) intro = line
      else loose.push(line)
      continue
    }
    const [, label, value] = matched
    if (!value) continue
    if (TITLE_LABELS.has(label)) {
      // "专业：会计学"和标题重复 —— 但万一标题是空的，它就是这块的名字，留着
      if (title && value === title) continue
      if (!title) {
        fields.push({ label, value })
        continue
      }
    }
    if (INTRO_LABELS.has(label) && !intro) {
      intro = value
      continue
    }
    fields.push({ label, value })
  }

  return { intro, fields, loose }
}

export interface IntelShare {
  name: string
  /** 占比，百分数（21 表示 21%）。认不出占比时是 null */
  percent: number | null
}

/**
 * 把"对口职业"那一行读成可以画成条的数据。
 *
 * 原文是 `会计/会计师（占比 21%）、财务分析经理/主管（占比 7%）、…`。
 * 认得出占比就画条；认不出（老页面只有名字）就退回成一串名字，
 * 界面照样读得下去 —— 这也是"不编"的一部分：不猜、不补。
 */
export function readShares(value: string): IntelShare[] {
  const out: IntelShare[] = []
  for (const raw of String(value ?? '').split('、')) {
    const part = raw.trim()
    if (!part) continue
    const matched = part.match(/^(.*?)\s*[（(]\s*[^）)]*?([\d.]+)\s*%\s*[）)]\s*$/)
    if (matched) {
      const name = matched[1].trim()
      const percent = Number(matched[2])
      if (name) out.push({ name, percent: Number.isFinite(percent) ? percent : null })
      continue
    }
    out.push({ name: part.replace(/[（(]\s*[）)]/g, '').trim(), percent: null })
  }
  return out
}

/** 一长串顿号/逗号分隔的名字 → 数组（"毕业去向行业""升学方向"用） */
export function readList(value: string): string[] {
  return String(value ?? '')
    .split(/[、,，]/)
    .map((part) => part.trim())
    .filter(Boolean)
}

/**
 * 三类情报的天然顺序 —— **专业 → 职业 → 校友案例**。
 *
 * 这不是排版喜好，是这份数据本身的关系：学了这个专业 → 对口哪些职业 →
 * 走过这条路的人后来怎么样。按 kind 的字母序排会把这条链打断。
 */
const KIND_RANK: Record<string, number> = {
  speciality: 10,
  occupation: 20,
  /* 后端给的是 career_case（界面上叫"校友案例"）。旧名 occucase 也认，
     免得改过一次的取值在缓存里留下老数据时排到最后一行。 */
  career_case: 30,
  occucase: 30,
}

export function kindRank(kind: string): number {
  return KIND_RANK[kind] ?? 50
}

export interface IntelGroup {
  kind: string
  label: string
  items: IntelItem[]
}

/** 按类别分组，组内按取回顺序，组间按"专业 → 职业 → 校友案例" */
export function groupIntel(items: IntelItem[]): IntelGroup[] {
  const map = new Map<string, IntelGroup>()
  for (const item of items) {
    const kind = item.kind || 'other'
    const group = map.get(kind) ?? { kind, label: item.kind_label || '公开信息', items: [] }
    group.items.push(item)
    map.set(kind, group)
  }
  return [...map.values()].sort((a, b) => kindRank(a.kind) - kindRank(b.kind))
}

/**
 * 取回时间的读法。
 *
 * 后端这个字段**两种形状都出现过**（实测：列表接口给 `09/22/2026 22:21:17`，
 * 刷新接口给 `2026-09-22T14:29:10.326376+00:00`）。所以两种都要认，
 * 而界面上只留「月/日 时:分」：秒对用户没有意义，年份在这一屏也没有
 * （情报只有"新不新"这一个属性）。
 *
 * ISO 那一路要**转成本地时间**再显示 —— 直接切字符串会把 UTC 的 14:29
 * 当成 14:29 给用户看（差 8 小时，用户会以为情报是下午取的）。
 * 认不出来就原样返回，不猜。
 */
export function readFetched(value: string): string {
  const raw = String(value ?? '')
  const slash = raw.match(/^(\d{2})\/(\d{2})\/\d{4}\s+(\d{2}:\d{2})/)
  if (slash) return `${slash[1]}/${slash[2]} ${slash[3]}`
  const parsed = new Date(raw)
  if (!Number.isNaN(parsed.getTime())) {
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${pad(parsed.getMonth() + 1)}/${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  }
  return raw
}

/** 三类各自的语气色 —— 和外壳的彩铅分类色对齐 */
export const KIND_TONE: Record<string, string> = {
  speciality: 'var(--mk-blue)',
  occupation: 'var(--mk-orange)',
  career_case: 'var(--mk-purple)',
  occucase: 'var(--mk-purple)',
}

export const toneOfKind = (kind: string) => KIND_TONE[kind] ?? 'var(--ink-3)'
