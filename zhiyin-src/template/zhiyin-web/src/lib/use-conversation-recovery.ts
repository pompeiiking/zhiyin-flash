import { computed, nextTick, ref, type Ref } from 'vue'
import { demo } from '../store'
import { backendDemo } from './backend-demo'
import { systemData } from './system-data'
import type { ChatTurn } from '../data/types'
import type { MessageRequest } from '../api/backend-types'
import type { OptionRef } from './use-conversation-draft'

type FailedSend = { request: MessageRequest; materials: { id: string; name: string }[]; error: string; at: string }
export type InterruptedItem = { text: string; turnId: string; clientMsgId?: string; materials?: { id: string; name: string }[] }

type RecoveryDeps = {
  turns: { readonly value: ChatTurn[] }
  thinking: Ref<boolean>
  stopped: Ref<boolean>
  pending: Ref<{ text: string; agent: string; note: string } | null>
  requestError: Ref<string>
  input: Ref<HTMLTextAreaElement | null>
  send: (retry?: boolean, choice?: { text: string; option?: OptionRef }, resend?: { clientMsgId?: string; materials?: { id: string; name: string }[] }) => Promise<void>
  setFailedRequest: (value: MessageRequest | null) => void
  hasBackgroundRun: () => boolean
}
/** 发送失败与生成中刷新/切页留下的残局：失败消息、确认条、中断提示与重新尝试入口。 */
export function useConversationRecovery({ turns, thinking, stopped, pending, requestError, input, send, setFailedRequest, hasBackgroundRun }: RecoveryDeps) {
  // 发送失败的消息与错误按会话持久化，刷新后仍然可见、可重新尝试（问题 15）。
  const failedSend = ref<FailedSend | null>(null)
  // 已点过按钮的确认不再重复出现（问题 2：可以 / 先不要）。
  const confirmDismissed = ref<string[]>([])
  const askPending = ref('')
  // 生成中刷新/切页：本轮回复没有落库时，提示"上一轮中断"并给出重新发送入口。
  const interrupted = ref<InterruptedItem | null>(null)
  function failureKey(id: string) { return id ? `zhiyin-chat-failure:${id}` : '' }
  function rememberFailure(sessionId: string, data: FailedSend) {
    failedSend.value = data
    const key = failureKey(sessionId)
    if (!key) return
    try { localStorage.setItem(key, JSON.stringify(data)) } catch { /* 存储不可用时至少保留本次内存态 */ }
  }
  function clearFailure(sessionId = demo.state.currentSessionId) {
    failedSend.value = null
    const key = failureKey(sessionId)
    if (!key) return
    try { localStorage.removeItem(key) } catch { /* 忽略清理失败 */ }
  }
  function loadFailure(sessionId: string) {
    failedSend.value = null
    if (!sessionId) return
    try {
      const raw = localStorage.getItem(failureKey(sessionId))
      if (!raw) return
      const data = JSON.parse(raw) as FailedSend
      if (!data?.request?.message) return
      failedSend.value = data
      setFailedRequest(data.request)
      // 刷新后要让人知道上一轮没成功：把错误也放回对话提示里（含「重新尝试」）。
      requestError.value = data.error || '上一轮回复没有完成，可以重新尝试。'
    } catch { /* 坏数据直接忽略，不阻塞会话 */ }
  }
  function discardFailure() {
    clearFailure()
    setFailedRequest(null)
    requestError.value = ''
  }
  // 登出/切换账号时清掉失败消息，避免下一次登录看到上一个账号的聊天内容。
  function clearAllFailures() {
    failedSend.value = null
    setFailedRequest(null)
    try {
      for (let index = localStorage.length - 1; index >= 0; index -= 1) {
        const key = localStorage.key(index)
        if (key?.startsWith('zhiyin-chat-failure:')) localStorage.removeItem(key)
      }
    } catch { /* 存储不可用时只剩内存态 */ }
  }
  const showFailedSend = computed(() => {
    const data = failedSend.value
    if (!data) return false
    return !turns.value.some(turn => turn.from === 'me' && (turn.id === `${data.request.client_msg_id}-user` || turn.text === data.request.message))
  })
  function pendingKey(id: string) { return `zhiyin-chat-pending:${id}` }
  function markChatPending(id: string) { try { sessionStorage.setItem(pendingKey(id), '1') } catch { /* 无 storage 时由服务端状态兜底 */ } }
  function markChatStopped(id: string) { try { sessionStorage.setItem(pendingKey(id), 'stopped') } catch { /* ignore */ } }
  function clearChatPending(id: string) { try { sessionStorage.removeItem(pendingKey(id)) } catch { /* ignore */ } }
  function hasChatPending(id: string) { try { return sessionStorage.getItem(pendingKey(id)) === '1' } catch { return false } }
  function hasChatStopped(id: string) { try { return sessionStorage.getItem(pendingKey(id)) === 'stopped' } catch { return false } }
  /**
   * 生成中刷新/切页的残局修复。
   *
   * openSession 恢复时会用会话快照里的 guide（属于**上一轮**回复）补齐最后一个助手回合；
   * 如果最后一条其实是用户刚发出、还没等到回复的提问，就会把上一轮的引导/残片挂到这条
   * 提问下面，看起来像"本轮回答"（深度测试 DEF-DS-02）。
   * 这里把这种伪回合摘掉，换成一条明确的"回复中断"提示，并保留重新发送入口。
   */
  function syncInterruptedNotice() {
    if (thinking.value || systemData.busy) return
    // A server-side run still streaming is not an interrupted reply. Reporting
    // it as one creates a retry button that send() immediately refuses.
    if (hasBackgroundRun()) { interrupted.value = null; return }
    const list = turns.value
    const last = list.at(-1)
    const previous = list.at(-2)
    const markerPending = hasChatPending(demo.state.currentSessionId)
    if (hasChatStopped(demo.state.currentSessionId)) {
      stopped.value = true
      // 主动停止不是“刷新导致的中断”：刷新后明确告诉用户上一轮是停止的，
      // 不出现“重新发送这个问题”，避免把未完成说成系统故障。
      // 标记保留到下一轮发送/用户明确处理，刷新后仍能区分“主动停止”和“异常中断”。
      interrupted.value = null
      if (!requestError.value) requestError.value = '上一轮回复是你主动停止的，没有继续生成。你可以继续补充或重新提问。'
      return
    }
    const phantom = last?.from === 'host' && !last.text?.trim() && last.id.endsWith('-guide') && previous?.from === 'me' ? last : undefined
    // 先摘掉伪回合：不管有没有失败提示，上一轮的引导都不能显示在这条提问下面。
    if (phantom) {
      demo.setChatTurns(list.slice(0, -1), demo.state.currentSessionId)
      backendDemo.saveTurns(demo.state.currentSessionId, demo.state.chatTurns)
    }
    const question = phantom ? previous : last?.from === 'me' && (!pending.value || markerPending) ? last : undefined
    if (!question) {
      if (last?.from === 'host') {
        interrupted.value = null
        if (markerPending) clearChatPending(demo.state.currentSessionId)
      }
      return
    }
    // 已有失败态时优先走"重新尝试"那条通道，避免两条重试入口同时出现。
    if (failedSend.value || requestError.value) { interrupted.value = null; return }
    if (interrupted.value?.turnId !== question.id) interrupted.value = {
      text: question.text,
      turnId: question.id,
      clientMsgId: question.client_msg_id || (question.id.endsWith('-user') ? question.id.slice(0, -5) : undefined),
      materials: question.materials?.map(item => ({ id: item.id, name: item.name })),
    }
    if (markerPending) clearChatPending(demo.state.currentSessionId)
  }
  function retryInterrupted() {
    const item = interrupted.value
    if (!item || thinking.value || systemData.busy) return
    if (hasBackgroundRun()) {
      requestError.value = '上一轮仍在处理，请等它完成或先停止后再重试。'
      return
    }
    interrupted.value = null
    // 复用原 client_msg_id / 材料：服务端已保存这条用户消息，重发只补回答，
    // 不再新增一条重复的用户气泡。
    void send(false, { text: item.text }, { clientMsgId: item.clientMsgId, materials: item.materials })
  }
  function dismissInterrupted() {
    interrupted.value = null
    clearChatPending(demo.state.currentSessionId)
    void nextTick(() => input.value?.focus())
  }
  return { failedSend, confirmDismissed, askPending, interrupted, showFailedSend, rememberFailure, clearFailure, loadFailure, discardFailure, clearAllFailures, syncInterruptedNotice, retryInterrupted, dismissInterrupted, markChatPending, markChatStopped, clearChatPending }
}
