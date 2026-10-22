import type { ConversationTurnView, TaskSessionView } from '../api/backend-types'

const stages = new Set(['collect', 'diagnose', 'decide', 'act', 'review'])

export function conversationPresentation(
  sessionId: string,
  snapshot: Pick<ConversationTurnView, 'task_id' | 'stage' | 'badge'> | null,
  session: Pick<TaskSessionView, 'task_id' | 'stage' | 'lead_agent_name'> | undefined,
  liveFocus: string,
  streaming: boolean,
) {
  const current = snapshot?.task_id === sessionId ? snapshot : null
  const stored = session?.task_id === sessionId ? session : undefined
  return {
    stage: streaming && stages.has(liveFocus) ? liveFocus : current?.stage || stored?.stage || 'collect',
    host: current?.badge.name || stored?.lead_agent_name || '咨询顾问',
  }
}

export function partialReplySpeaker(pendingAgent: string | undefined, previousHost: string) {
  return pendingAgent || previousHost
}

export type JourneyState = 'past' | 'current' | 'future'

/**
 * 阶段条三态：当前阶段之前的算已走过，当前阶段高亮，之后的仍是未到。
 *
 * 这是固定顺序的进度条，不是访问日志：阶段真正由模型按当前工作需要切换，
 * 可能回到更早的环节；一旦回到更早环节，它之后的阶段就重新显示为未到。
 */
export function journeyState(stages: readonly string[], current: string, key: string): JourneyState {
  const currentIndex = stages.indexOf(current)
  const index = stages.indexOf(key)
  if (index < 0 || currentIndex < 0) return 'future'
  if (index < currentIndex) return 'past'
  if (index === currentIndex) return 'current'
  return 'future'
}
