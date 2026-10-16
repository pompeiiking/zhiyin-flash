// Derived presentation only. Never infer waiting, partial completion or task duration.
export function dateKey(value) {
  if (!value) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
}
export function deadline(value, now = new Date()) {
  const key = dateKey(value)
  if (!key) return { label: '未设截止日期', days: null, overdue: false }
  const [y,m,d] = key.split('-').map(Number)
  const days = Math.round((Date.UTC(y,m-1,d)-Date.UTC(now.getFullYear(),now.getMonth(),now.getDate()))/86400000)
  return { label: days < 0 ? `已过截止日 ${-days} 天` : days === 0 ? '今天截止' : `距截止 ${days} 天`, days, overdue: days < 0 }
}
export function actionRows(plan) {
  return (plan?.phases ?? []).flatMap((phase, phaseIndex) => (phase.tasks ?? []).map(task => ({ ...task, phase: task.phase || phase.name, phaseIndex })))
}
export function actionStatusMatches(task, filter) {
  if (filter === 'all') return true
  if (filter === 'done') return !!task.done
  if (task.done) return false
  if (filter === 'pending') return !task.status || task.status === 'pending'
  return task.status === filter
}
export function taskGroup(task, now = new Date()) {
  if (task.done) return 'done'
  const due = deadline(task.due_date, now)
  return due.days === null ? 'undated' : due.days < 0 ? 'overdue' : due.days === 0 ? 'today' : 'upcoming'
}
export function directionRanking(plans, order) {
  if (order !== 'score') return [...plans]
  // No zero substitution for missing scores. No fabricated criteria or normalization.
  return [...plans].sort((a,b) => {
    const aValid = typeof a.match_score === 'number' && Number.isFinite(a.match_score) && a.match_score >= 0 && a.match_score <= 1
    const bValid = typeof b.match_score === 'number' && Number.isFinite(b.match_score) && b.match_score >= 0 && b.match_score <= 1
    return aValid && bValid ? b.match_score-a.match_score : aValid ? -1 : bValid ? 1 : 0
  })
}
