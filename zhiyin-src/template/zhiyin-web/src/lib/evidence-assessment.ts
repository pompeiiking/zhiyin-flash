import type { EvidenceAssessment } from '../api/backend-types'

export const assessmentStatus: Record<string, string> = {
  pending: '待评估', processing: '评估中', stale: '资料已变化，待重新评估',
  failed: '评估失败', insufficient: '依据不足，暂无法评估', evaluated: '已评估',
}
export function assessmentPercent(assessment?: EvidenceAssessment | null): string | null {
  if (assessment?.status !== 'evaluated' || typeof assessment.score !== 'number'
      || !Number.isFinite(assessment.score) || assessment.score < 0 || assessment.score > 1) return null
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(assessment.score * 100) + '%'
}
/** Unknown statuses and half-written evaluations must not masquerade as complete. */
export function assessmentLabel(assessment?: EvidenceAssessment | null): string {
  const percent = assessmentPercent(assessment)
  if (percent) return percent
  if (assessment?.status === 'evaluated') return '评估结果不完整'
  return assessmentStatus[assessment?.status ?? 'pending'] ?? '状态未知'
}
