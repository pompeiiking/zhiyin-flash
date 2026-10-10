import type { ActionPlan, ActionTask } from '@/api/client'
import type { GuideTask } from './asks'

/** 只完成当前展示的整条任务；拆小的动作不能代替整个计划任务。 */
export function actionTaskForGuide(plan: ActionPlan | null, guide: GuideTask | null): ActionTask | null {
  if (!plan || !guide?.text.trim()) return null
  const tasks = (plan.phases ?? []).flatMap((phase) => phase.tasks ?? [])
  const text = guide.text.trim()
  const byId = guide.task_id ? tasks.find((task) => task.task_id === guide.task_id) : null
  if (byId) return byId.text.trim() === text ? byId : null

  // 模型的引导 id 未必是计划 id。文字完整相同且唯一时才允许对齐。
  const matches = tasks.filter((task) => task.text.trim() === text)
  return matches.length === 1 ? matches[0] : null
}
