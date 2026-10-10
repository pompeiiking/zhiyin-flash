import type { MatchResult } from '@/ai/registry'
import type { ActionPlan } from '@/api/client'

export function isMatchAccepted(result: MatchResult, plan: ActionPlan | null): boolean {
  const ids = new Set((plan?.phases ?? []).flatMap((phase) => (phase.tasks ?? []).map((task) => task.task_id)))
  return result.actions.length > 0 && result.actions.every((_, index) => ids.has(`match_${result.recommendation_id}_${index}`))
}

export async function saveMatchAcceptance(
  result: MatchResult,
  save: (id: string) => Promise<ActionPlan | null>,
  apply: (plan: ActionPlan) => void,
): Promise<ActionPlan> {
  const plan = await save(result.recommendation_id)
  if (!plan || !isMatchAccepted(result, plan)) throw new Error('没有确认任务保存成功，请稍后重新采纳。')
  apply(plan)
  return plan
}
