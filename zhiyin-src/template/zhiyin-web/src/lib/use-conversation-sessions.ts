import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { demo, toast } from '../store'
import { backendDemo } from './backend-demo'
import { backendClient } from '../api/backend-client'
import { systemData } from './system-data'
import { friendlyError } from './use-conversation-errors'
import type { InterruptedItem } from './use-conversation-recovery'
import type { SessionListView, TaskSessionView } from '../api/backend-types'

type SessionsDeps = {
  historyOpen: Ref<boolean>
  thinking: Ref<boolean>
  choosingTopic: Ref<boolean>
  requestError: Ref<string>
  uploadError: Ref<string>
  interrupted: Ref<InterruptedItem | null>
  pending: Ref<{ text: string; agent: string; note: string } | null>
  isDisposed: () => boolean
  clearFailure: (sessionId?: string) => void
  resume: (id: string) => Promise<void>
  refreshProfile: () => Promise<void>
}
/** 会话历史列表：搜索、行内重命名、二次确认删除，以及打开历史浮层时的刷新。 */
export function useConversationSessions({ historyOpen, thinking, choosingTopic, requestError, uploadError, interrupted, pending, isDisposed, clearFailure, resume, refreshProfile }: SessionsDeps) {
  // ---- F8 会话历史管理：搜索 / 行内重命名 / 二次确认删除 ----
  const sessionQuery = ref('')
  const sessionListLoading = ref(false), sessionListError = ref('')
  const renamingId = ref(''), renameDraft = ref(''), renameError = ref(''), renameBusy = ref(false)
  const deletingId = ref(''), deleteBusy = ref(false), deleteError = ref('')
  const sessions = computed(() => [...backendDemo.state.sessions]
    // 与后端会话列表口径一致：还没有任何消息的会话不进历史。
    // 否则 fresh 新建的空会话会先出现在列表里、刷新后又消失（DEF-C2）。
    .filter(session => (session.message_count ?? 0) > 0 || !!session.last_message)
    .sort((a,b) => ((b.last_message_at || b.last_active_at) || '').localeCompare((a.last_message_at || a.last_active_at) || '')))
  // 会话搜索：按标题与会话最后一句内容实时过滤（无结果时给明确空态）。
  const filteredSessions = computed(() => {
    const keyword = sessionQuery.value.trim().toLowerCase()
    if (!keyword) return sessions.value
    return sessions.value.filter(session => `${session.task_name || ''} ${session.last_message || ''}`.toLowerCase().includes(keyword))
  })
  const sessionMutationBusy = computed(() => renameBusy.value || deleteBusy.value)
  /**
   * 会话列表刷新：重命名/删除的响应优先直接落地（契约返回 SessionListView），
   * 只有响应不可用时才再请求一次——避免操作后重复请求。
   */
  function applySessionListResult(result: SessionListView | { removed?: string } | null | undefined) {
    const sessionsResult = result && Array.isArray((result as SessionListView).sessions) ? result as SessionListView : null
    if (!sessionsResult) return false
    const list = sessionsResult.sessions ?? []
    const current = demo.state.currentSessionId
    const keep = list.some(session => session.task_id === current) ? current : (sessionsResult.current_task_id || '')
    backendDemo.setSessions(list, keep)
    return true
  }
  async function refreshSessionList(notify = false) {
    if (sessionListLoading.value) return false
    sessionListLoading.value = true
    if (notify) sessionListError.value = ''
    try {
      const result = await backendClient.sessions()
      if (!isDisposed()) applySessionListResult(result)
      return true
    } catch (e) {
      if (notify && !isDisposed()) sessionListError.value = friendlyError(e)
      return false
    } finally { if (!isDisposed()) sessionListLoading.value = false }
  }
  async function refreshSessionsOnFocus() {
    if (document.visibilityState !== 'visible') return
    // 焦点回到页面时静默刷新；历史浮层打开时把错误显示在浮层里。
    await refreshSessionList(historyOpen.value)
  }
  function sessionTimeLabel(session: TaskSessionView) {
    const raw = session.last_message_at || session.last_active_at
    if (!raw) return ''
    const date = new Date(raw)
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }
  function startRename(session: TaskSessionView) {
    if (sessionMutationBusy.value) { toast('正在处理上一个会话操作，请稍候。'); return }
    deletingId.value = ''
    renamingId.value = session.task_id
    renameDraft.value = session.task_name
    renameError.value = ''
    void nextTick(() => {
      // 行内输入框在 v-for 里，不用模板 ref（会变成数组），按容器查询后聚焦更稳。
      const field = document.querySelector('.session-row__rename input') as HTMLInputElement | null
      field?.focus()
      field?.select()
    })
  }
  function cancelRename() {
    if (renameBusy.value) return
    renamingId.value = ''
    renameError.value = ''
  }
  async function saveRename(session: TaskSessionView) {
    if (renameBusy.value) return
    const name = renameDraft.value.trim()
    // 校验口径与后端一致：2–60 个字（不含首尾空白）。
    if (name.length < 2 || name.length > 60) { renameError.value = '会话名称需要 2–60 个字。'; return }
    if (name === session.task_name) { renamingId.value = ''; return }
    renameBusy.value = true
    renameError.value = ''
    try {
      const result = await backendClient.sessionRename(session.task_id, name)
      if (!applySessionListResult(result) && !await refreshSessionList(true)) throw new Error('名称已提交，但会话列表暂时没有刷新成功，请重新打开历史会话查看。')
      renamingId.value = ''
      toast('会话名称已更新。')
    } catch (e) {
      renameError.value = friendlyError(e)
    } finally { renameBusy.value = false }
  }
  function askDelete(session: TaskSessionView) {
    if (sessionMutationBusy.value) { toast('正在处理上一个会话操作，请稍候。'); return }
    renamingId.value = ''
    deletingId.value = session.task_id
    deleteError.value = ''
  }
  function cancelDelete() {
    if (deleteBusy.value) return
    deletingId.value = ''
    deleteError.value = ''
  }
  async function confirmDelete(session: TaskSessionView) {
    if (deleteBusy.value) return
    const wasCurrent = session.task_id === demo.state.currentSessionId
    if (wasCurrent && thinking.value) { deleteError.value = '回复生成中，等这一轮结束后再删除当前会话。'; return }
    deleteBusy.value = true
    deleteError.value = ''
    try {
      const result = await backendClient.sessionDelete(session.task_id)
      // 删除后清掉该会话的失败缓存与草稿，避免下次打开残留旧内容。
      clearFailure(session.task_id)
      backendDemo.saveDraft(session.task_id, '', [], null)
      deletingId.value = ''
      if (!applySessionListResult(result) && !await refreshSessionList(true)) throw new Error('会话已经删除，但列表暂时没有刷新成功，请重新打开历史会话查看最新状态。')
      toast(`已删除会话「${session.task_name}」。`)
      if (wasCurrent) {
        historyOpen.value = false
        const next = sessions.value[0]
        if (next) await resume(next.task_id)
        else {
          // 没有剩余会话：回到"从主题开始"的空态。
          demo.setChatTurns([], '')
          demo.setChatBusy(false)
          systemData.snapshot = null
          pending.value = null
          interrupted.value = null
          requestError.value = ''
          uploadError.value = ''
          choosingTopic.value = false
          void refreshProfile()
        }
      }
    } catch (e) {
      deleteError.value = friendlyError(e)
    } finally { deleteBusy.value = false }
  }
  watch(historyOpen, open => { if (open) void refreshSessionList(true) })
  return { sessions, filteredSessions, sessionQuery, sessionListLoading, sessionListError, sessionMutationBusy, renamingId, renameDraft, renameError, renameBusy, deletingId, deleteBusy, deleteError, applySessionListResult, refreshSessionList, refreshSessionsOnFocus, sessionTimeLabel, startRename, cancelRename, saveRename, askDelete, cancelDelete, confirmDelete }
}
