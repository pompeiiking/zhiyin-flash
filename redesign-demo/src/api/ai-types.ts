// SSE result shapes follow zhiyin-business/contracts/ai_tasks.py; OpenAPI has no SSE body schema.
export type AiResult<T> = { data: T; citations: { source: string; detail: string; confidence?: number; at?: string; origin?: string }[]; meta: { by: string; at: string; ms: number; cached: boolean }; rationale?: string }
export type AnalysisPoint = { label: string; why: string }
export type PortraitAnalysis = { headline: string; reading: string; strengths: AnalysisPoint[]; watchouts: AnalysisPoint[]; next: AnalysisPoint[] }
export type DimensionReading = { id: string; name: string; conclusion: string; reading: string; score?: number; delta?: number; bench?: number; trend: { at: string; v: number; why: string }[]; next: string }
export type GapClarify = { question: string; options: { label: string; why: string }[]; whyNow: string }
export type MatchResult = { cells: { track: string; skill: string; need: number; have: number }[]; ranking: { track: string; fit: number; gap: string; why: string }[]; recommend: { title: string; body: string; because: string[] } }
export type BriefToday = { headline: string; because: { text: string; from: string }[]; changed: { text: string; at: string }[]; ifYouSkip: string; next: { id: string; label: string; why: string }[] }
export type DayAdvice = { date: string; headline: string; reading: string; plan: AnalysisPoint[]; watch: string }
export type TimetablePlan = { headline: string; windows: { day: string; slot: string; why: string }[]; moves: { at: string; what: string; why: string }[] }
export type TodoSuggestion = { id: string; label: string; why: string; from: string; when: string; weight: number }
export type BindResult = { steps: { id: string; label: string; detail: string; got: number; source: string }[]; courses: unknown[]; lifted: { dim: string; from: number; to: number; because: string }[] }
