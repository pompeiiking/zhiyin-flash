export type AcademicTermState = 'current' | 'history' | 'upcoming' | 'unknown'

type ParsedTerm = { startYear: number; semester: 1 | 2 }

/** Parse the term formats used by imports: 2026-2027-1, 2016-2017 1, 2025-2026学年第二学期. */
export function parseAcademicTerm(term: string): ParsedTerm | null {
  const value = String(term || '').trim()
  const years = value.match(/(20\d{2})\s*[-—至/]\s*(20\d{2})/)
  if (!years) return null
  const semesterMatch = value.match(/(?:[-_\s])([12])\s*$|第\s*([一二12])\s*学期/)
  if (!semesterMatch) return null
  const raw = semesterMatch[1] || semesterMatch[2]
  const semester = raw === '一' || raw === '1' ? 1 : raw === '二' || raw === '2' ? 2 : null
  if (!semester) return null
  return { startYear: Number(years[1]), semester }
}

export function currentAcademicTerm(now = new Date()): ParsedTerm {
  const year = now.getFullYear()
  const month = now.getMonth() + 1
  if (month >= 8) return { startYear: year, semester: 1 }
  if (month === 1) return { startYear: year - 1, semester: 1 }
  return { startYear: year - 1, semester: 2 }
}

export function academicTermState(term: string, now = new Date()): AcademicTermState {
  const parsed = parseAcademicTerm(term)
  if (!parsed) return 'unknown'
  const current = currentAcademicTerm(now)
  if (parsed.startYear === current.startYear && parsed.semester === current.semester) return 'current'
  if (parsed.startYear < current.startYear) return 'history'
  if (parsed.startYear === current.startYear && parsed.semester < current.semester) return 'history'
  return 'upcoming'
}

export function academicTermStatusLabel(term: string, now = new Date()): string {
  const state = academicTermState(term, now)
  if (state === 'current') return '当前学期'
  if (state === 'history') return '历史学期'
  if (state === 'upcoming') return '未来学期'
  return '学期待确认'
}
