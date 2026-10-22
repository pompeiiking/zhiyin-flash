import type { ConversationMessageView, ConversationTurnView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'

export function mapMessage(message: ConversationMessageView, id: string): ChatTurn {
  return { ...message, id, from: message.role === 'user' ? 'me' : message.role === 'agent' ? 'host' : 'system',
    speaker: message.agent_name || message.agent_id || undefined, text: message.text }
}

/** Guidance belongs to the last answer of this turn, never to an older user turn. */
export function withGuide(turns: ChatTurn[], snapshot: ConversationTurnView | null, id: string): ChatTurn[] {
  if (!snapshot) return turns
  const g = snapshot.guide
  const hasGuide = !!(g?.text || g?.question || g?.options?.length || g?.task || g?.reminder)
  const hasStatus = !!(snapshot.pipeline_cards?.length || snapshot.changed_assets?.length)
  const hasDisclosure = !!snapshot.disclosure?.text
  if (!hasGuide && !hasStatus && !hasDisclosure) return turns
  const result = turns.map(t => ({ ...t }))
  if (hasGuide || hasStatus) {
    const last = result.at(-1)
    const target = last?.from === 'host' && (!last.speaker || [snapshot.badge.name, snapshot.badge.agent_id].includes(last.speaker)) ? last : undefined
    const answer: ChatTurn = target ?? { id, from: 'host', speaker: snapshot.badge.name, text: '' }
    const same = (value?: string | null) => !value || value.trim() === answer.text.trim()
    if (g) {
      answer.guideText = same(g.text) ? undefined : g.text
      answer.question = same(g.question) || g.question?.trim() === answer.guideText?.trim() ? undefined : g.question ?? undefined
      answer.guideTask = g.task ?? undefined
      answer.reminder = g.reminder ?? undefined
      answer.options = g.options?.filter(o => !o.option_id.startsWith('action.')).map(o => o.label)
      answer.optionRefs = g.options?.filter(o => !o.option_id.startsWith('action.')).map(o => ({ ...o, value: o.value }))
    }
    answer.pipelineCards = snapshot.pipeline_cards?.length ? snapshot.pipeline_cards.map(card => ({ ...card })) : undefined
    answer.changedAssets = snapshot.changed_assets?.length ? snapshot.changed_assets.map(asset => ({ ...asset })) : undefined
    if (!target) result.push(answer)
  }
  if (hasDisclosure) {
    // 交接告知属于这一轮回答之前的一行状态，不是整段会话的开头：
    // 放在最后一条主理回复前面，刷新历史时也按同一个位置恢复。
    const answerIndex = result.map(turn => turn.from).lastIndexOf('host')
    result.splice(answerIndex >= 0 ? answerIndex : result.length, 0, {
      id: `${id}-notice`, from: 'system', text: snapshot.disclosure!.text,
    })
  }
  return result
}

export function answerParts(text: string) {
  return { lead: '', body: text }
}

export function replyTurns(result: ConversationTurnView, id: string): ChatTurn[] {
  const turns = (result.messages ?? []).filter(m => m.role !== 'user').map((m, i) => mapMessage(m, `${id}-${i}`))
  return withGuide(turns, result, `${id}-guide`)
}
