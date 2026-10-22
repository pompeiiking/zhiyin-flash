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
