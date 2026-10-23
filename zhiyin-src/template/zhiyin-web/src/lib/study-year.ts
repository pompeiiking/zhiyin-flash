import type { TaskEntryView } from '../api/backend-types'

export type StudyYearCode = 'year_1' | 'year_2' | 'year_3' | 'year_4'

export const STUDY_YEAR_OPTIONS: ReadonlyArray<{ code: StudyYearCode; label: string }> = [
  { code: 'year_1', label: '大一' },
  { code: 'year_2', label: '大二' },
  { code: 'year_3', label: '大三' },
  { code: 'year_4', label: '大四' },
]

const TOPICS: Record<StudyYearCode, ReadonlyArray<{ code: string; label: string }>> = {
  year_1: [
    { code: 'confused', label: '认识自己的兴趣与优势' },
    { code: 'verify_direction', label: '了解专业可以走向哪里' },
    { code: 'how_to_act', label: '建立大学阶段的行动起点' },
    { code: 'free_chat', label: '聊聊当前的困惑' },
  ],
  year_2: [
    { code: 'verify_direction', label: '探索并验证职业方向' },
    { code: 'how_to_act', label: '规划项目、竞赛与实践' },
    { code: 'undecided', label: '比较升学、就业等选择' },
    { code: 'confused', label: '梳理自己的能力与偏好' },
    { code: 'free_chat', label: '直接说说想解决的事' },
  ],
  year_3: [
    { code: 'undecided', label: '收敛求职或升学方向' },
    { code: 'how_to_act', label: '准备实习、项目与简历' },
    { code: 'verify_direction', label: '验证目标岗位是否合适' },
    { code: 'stuck', label: '解决准备过程中的卡点' },
    { code: 'free_chat', label: '直接说说想解决的事' },
  ],
  year_4: [
    { code: 'how_to_act', label: '推进校招、补录或升学' },
    { code: 'undecided', label: '比较岗位、升学与其他去向' },
    { code: 'stuck', label: '准备面试并处理求职卡点' },
    { code: 'review_due', label: '复盘结果并调整毕业计划' },
    { code: 'free_chat', label: '直接说说想解决的事' },
  ],
}

const INTRO: Record<StudyYearCode, string> = {
  year_1: '先从适应专业、认识自己和探索可能性开始。',
  year_2: '可以开始验证方向，并用项目与实践积累证据。',
  year_3: '建议优先收敛方向，准备实习、项目和升学或求职。',
  year_4: '建议围绕毕业去向，推进求职、升学与备选方案。',
}

export function studyYearLabel(value: unknown): string {
  const raw = String(value ?? '').trim()
  return STUDY_YEAR_OPTIONS.find(option => option.code === raw || option.label === raw)?.label ?? raw
}

export function studyYearCode(value: unknown): StudyYearCode | null {
  const raw = String(value ?? '').trim()
  return STUDY_YEAR_OPTIONS.find(option => option.code === raw || option.label === raw)?.code ?? null
}

export function studyYearIntro(value: unknown): string {
  const code = studyYearCode(value)
  return code ? INTRO[code] : '从你现在最关心的事开始。'
}

/** 新账号第一次进入对话：还没有年级、会话和首轮内容时，先确认年级。 */
export function needsInitialStudyYearChoice(input: {
  studyYear: unknown
  hasSession: boolean
  hasTurns: boolean
  hasPending: boolean
}): boolean {
  return !String(input.studyYear ?? '').trim() && !input.hasSession && !input.hasTurns && !input.hasPending
}

export function personalizedStudyYearEntries(entries: readonly TaskEntryView[], value: unknown): TaskEntryView[] {
  const code = studyYearCode(value)
  if (!code) return [...entries].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
  const byCode = new Map(entries.map(entry => [entry.code, entry]))
  return TOPICS[code].flatMap((topic, index) => {
    const entry = byCode.get(topic.code)
    return entry ? [{ ...entry, label: topic.label, sort_order: index + 1 }] : []
  })
}
