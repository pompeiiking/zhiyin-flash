import type { ConversationMessageView, ConversationTurnView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'

export function mapMessage(message: ConversationMessageView, id: string): ChatTurn {
  return { ...message, id, from: message.role === 'user' ? 'me' : message.role === 'agent' ? 'host' : 'system',
    speaker: message.agent_name || message.agent_id || undefined, text: message.text }
}

/** Guidance belongs to the last answer of this turn, never to an older user turn. */
export function withGuide(turns: ChatTurn[], snapshot: ConversationTurnView | null, id: string): ChatTurn[] {
  if (!snapshot?.guide) return turns
  const g = snapshot.guide
  if (!(g.text || g.question || g.options?.length || g.task || g.reminder)) return turns
  const result = turns.map(t => ({ ...t }))
  const last = result.at(-1)
  const target = last?.from === 'host' && (!last.speaker || [snapshot.badge.name, snapshot.badge.agent_id].includes(last.speaker)) ? last : undefined
  const answer: ChatTurn = target ?? { id, from: 'host', speaker: snapshot.badge.name, text: '' }
  const same = (value?: string | null) => !value || value.trim() === answer.text.trim()
  answer.guideText = same(g.text) ? undefined : g.text
  answer.question = same(g.question) || g.question?.trim() === answer.guideText?.trim() ? undefined : g.question ?? undefined
  answer.guideTask = g.task ?? undefined
  answer.reminder = g.reminder ?? undefined
  answer.options = g.options?.map(o => o.label)
  answer.optionRefs = g.options?.map(o => ({ ...o, value: o.value }))
  if (!target) result.push(answer)
  return result
}

export function answerParts(text: string) {
  const boundary = text.search(/[。！？!?\n]/)
  if (boundary >= 7 && boundary <= 72) return { lead:text.slice(0, boundary + 1), body:text.slice(boundary + 1).trim() }
  return text.length <= 60 ? { lead:text, body:'' } : { lead:'', body:text }
}

export function replyTurns(result: ConversationTurnView, id: string): ChatTurn[] {
  const turns = (result.messages ?? []).filter(m => m.role !== 'user').map((m, i) => mapMessage(m, `${id}-${i}`))
  const answers = withGuide(turns, result, `${id}-guide`)
  if (result.disclosure?.text) answers.unshift({ id: `${id}-notice`, from: 'system', text: result.disclosure.text })
  return answers
}
