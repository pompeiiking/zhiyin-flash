<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch, type DeepReadonly } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demo, toast } from '../store'
import { backendDemo } from '../lib/backend-demo'
import { auth } from '../lib/auth'
import { useConversationScroll } from '../lib/use-conversation-scroll'
import { isComposingKey } from '../lib/scroll-intent'
import { vScrollFade } from '../lib/scroll-fade'
import { navigation } from '../lib/layout'
import { consultantLabel, agentKeyOf, cleanConsultantText } from '../lib/consultant'
import { conversationPresentation, journeyState, partialReplySpeaker } from '../lib/conversation-presentation'
import { needsInitialStudyYearChoice, personalizedStudyYearEntries, STUDY_YEAR_OPTIONS, studyYearIntro, studyYearLabel } from '../lib/study-year'
import { messageLengthError } from '../lib/message-limits'
import { newSession, openSession, loadShell, systemData } from '../lib/system-data'
import { replyTurns } from '../lib/conversation-turns'
import { backendClient } from '../api/backend-client'
import { streamBackend } from '../api/backend-stream'
import { studentApi } from '../api/student-capabilities'
import type { ActionPhaseView, ActionTaskView, ConversationTurnView, MessageRequest, TheoryCardView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'
import AgentAvatar from '../components/AgentAvatar.vue'
import UiIcon from '../components/UiIcon.vue'
import ReadableText from '../components/ReadableText.vue'
import DetailPopover from '../components/DetailPopover.vue'
import AnchoredCard from '../components/AnchoredCard.vue'
import RenderableBlock from '../components/RenderableBlock.vue'
import ConversationProfile from '../components/ConversationProfile.vue'
import ConversationOperations from '../components/ConversationOperations.vue'
import StatusBanner from '../components/StatusBanner.vue'
import type { ConversationRuntimeState } from '../api/backend-client'
import { errorCode, friendlyError } from '../lib/use-conversation-errors'
import { type OptionRef, useConversationDraft } from '../lib/use-conversation-draft'
import { useConversationMaterials } from '../lib/use-conversation-materials'
import { useConversationRecovery } from '../lib/use-conversation-recovery'
import { useConversationSessions } from '../lib/use-conversation-sessions'
import { useConversationCapabilities } from '../lib/use-conversation-capabilities'
import '../styles/conversation.css'
const route = useRoute()
const router = useRouter()
const turns = computed(() => demo.state.chatTurns)
const flow = ref<HTMLElement | null>(null), input = ref<HTMLTextAreaElement | null>(null)
const thinking = ref(false), stopped = ref(false)
const startingTopic = ref(false)
const { followTail, showLatest, bottom, onScroll } = useConversationScroll(flow)
const elapsed = ref(0), replyAnnouncement = ref('')
let waitTimer: ReturnType<typeof setInterval> | undefined
let requestStarted = 0
const pending = ref<{ text: string; agent: string; note: string } | null>(null)
const runtimeState = ref<ConversationRuntimeState | null>(null)
const runtimeError = ref('')
let runtimeSerial = 0
const backgroundRun = computed(() => runtimeState.value?.runs.find(r => r.state === 'running'))
let recoveryTimer: ReturnType<typeof setInterval> | undefined
const activeRunId = ref('')
const liveFocus = ref('')
let controller: AbortController | null = null, serial = 0, disposed = false
let failedRequest: MessageRequest | null = null
const requestError = ref(''), profileError = ref(''), guideSaving = ref('')
const askConfirm = ref<{ text: string; previousText: string; previousOption: OptionRef | null } | null>(null)
// The shell banner and the in-conversation error often describe the same
// failed session read. Show the more specific one instead of two retry paths.
const systemErrorVisible = computed(() => !!systemData.error && !requestError.value)
const profileOpen = ref(false), historyOpen = ref(false), profileLoading = ref(false)
const choosingTopic = ref(false)
// 恢复会话的短暂空态：避免刚刷新时先闪一句"新会话已就绪/咨询对话"。
const restoring = ref(false)
// 发送后极短时间内的"停止"点击要忽略：按钮在同一位置从"发送"变成"停止"，
// 双击发送的第二次点击会命中停止，把刚发出的问题撤回（实测 DEF-C1）。
const stopArmed = ref(true)
let stopArmTimer: ReturnType<typeof setTimeout> | undefined
// 新建入口每次创建独立会话；旧会话通过历史列表继续。
let handledNewTopicIntent = ''
const profileLoaded = ref(false), studyYearSaving = ref(''), studyYearError = ref(''), editingStudyYear = ref(false), savedStudyYear = ref('')
// 用户点了一个主题、但还缺学习阶段时，先记住这个选择：确认完年级直接开始，
// 不用让他回头再点一次。
const pendingTopic = ref<{ code: string; label: string } | null>(null)
const theoryCards = ref<Record<string, TheoryCardView>>({}), theoryErrors = ref<Record<string, string>>({})
const theoryLoading = ref<Record<string, boolean>>({})
const copiedTurn = ref('')
let copyTimer: ReturnType<typeof setTimeout> | undefined
const { failedSend, confirmDismissed, askPending, interrupted, showFailedSend, rememberFailure, clearFailure, loadFailure, discardFailure, clearAllFailures, syncInterruptedNotice, retryInterrupted, dismissInterrupted, markChatPending, markChatStopped, clearChatPending } = useConversationRecovery({
  turns, thinking, stopped, pending, requestError, input, send, setFailedRequest: value => { failedRequest = value },
  hasBackgroundRun: () => !!backgroundRun.value,
})
const { draft, attached, selectedOption, fillRequest, replacedDraft, fill, applyFill, confirmFillReplace, cancelFillReplace, undoFillReplace, remember, resizeInput } = useConversationDraft({ flow, input, profileOpen, thinking })
const { uploading, draggingFiles, uploadError, fileInput, upload, dragOver, dropFiles, pasteFiles } = useConversationMaterials({ thinking, attached, isDisposed: () => disposed })
async function refreshRuntime() {
 const id = demo.state.currentSessionId
 const serial = ++runtimeSerial
 if (!id) { runtimeState.value = null; runtimeError.value = ''; return }
 try {
  const value = await backendClient.conversationRuntime(id)
  if (serial !== runtimeSerial || demo.state.currentSessionId !== id) return
  runtimeError.value = ''
  const recovering = runtimeState.value?.runs.some(r => r.state === 'running')
  runtimeState.value = value
  if (!thinking.value) {
   const run = value.runs[value.runs.length - 1]
   if (run?.state === 'running') activeRunId.value = run.id
   else if (recovering) { await openSession(id); syncInterruptedNotice() }
  }
 } catch {
  // A hidden runtime error means approval cards silently disappear and a
  // still-running reply gets mistaken for an interrupted one.
  if (serial === runtimeSerial && demo.state.currentSessionId === id) {
   runtimeError.value = '这一步的执行状态暂时没有取得。审批卡和后台回复可能暂时看不到，请重试。'
  }
 }
}
function decideAction(id: string, accept: boolean) {
 void send(false, { text: accept ? '确认执行这项变更' : '暂不执行这项变更', option: { option_id: `action.${id}.${accept ? 'accept' : 'decline'}`, label: accept ? '确认执行' : '暂不执行', value: {action_id: id} } })
}
watch(() => demo.state.currentSessionId, () => { liveFocus.value = ''; runtimeState.value = null; void refreshRuntime() }, { immediate: true })
const { sessions, filteredSessions, sessionQuery, sessionListLoading, sessionListError, renamingId, renameDraft, renameError, renameBusy, deletingId, deleteBusy, deleteError, refreshSessionList, refreshSessionsOnFocus, sessionTimeLabel, startRename, cancelRename, saveRename, askDelete, cancelDelete, confirmDelete } = useConversationSessions({ historyOpen, thinking, choosingTopic, requestError, uploadError, interrupted, pending, isDisposed: () => disposed, clearFailure, resume, refreshProfile })
const { capabilitiesOpen, capabilitiesLoading, capabilitiesError, capabilities, capabilityItems, capabilityStatus, loadCapabilities } = useConversationCapabilities()
const title = computed(() => showStudyYearQuestion.value ? '开始咨询' : choosingTopic.value ? '选择咨询主题' : backendDemo.currentSession.value?.task_name || '咨询对话')
const latestHostId = computed(() => turns.value.at(-1)?.from === 'host' ? turns.value.at(-1)?.id : undefined)
const presentation = computed(() => conversationPresentation(demo.state.currentSessionId, systemData.snapshot, backendDemo.currentSession.value, liveFocus.value, thinking.value))
const currentStage = computed(() => presentation.value.stage)
const journey = [
 { key:'collect', label:'了解自己', short:'了解' }, { key:'diagnose', label:'梳理判断', short:'判断' },
 { key:'decide', label:'比较选择', short:'选择' }, { key:'act', label:'安排下一步', short:'行动' },
 { key:'review', label:'回顾调整', short:'回顾' },
]
const journeyKeys = journey.map(item => item.key)
const stageState = (key: string) => journeyState(journeyKeys, currentStage.value, key)
const host = computed(() => presentation.value.host)
const studyYearField = computed(() => backendDemo.state.liveWorkspace?.profile_panel?.fields?.find(field => field.key === 'study_year'))
const studyYear = computed(() => savedStudyYear.value || String(studyYearField.value?.value ?? ''))
const showStudyYearQuestion = computed(() => profileLoaded.value && editingStudyYear.value)
const starters = computed(() => personalizedStudyYearEntries(auth.state.bootstrap?.task_entries ?? [], studyYear.value))
// 对话任务卡：guideTask.task_id 可能来自旧计划，甚至只是模型给的一条建议（不在计划里）。
const planTaskRows = computed(() => {
  const rows: { task: DeepReadonly<ActionTaskView>; phase: DeepReadonly<ActionPhaseView> }[] = []
  for (const phase of backendDemo.state.liveAction?.phases ?? []) for (const task of phase.tasks ?? []) rows.push({ task, phase })
  return rows
})
const normalizeTaskText = (text: string) => text.replace(/[\s\p{P}\p{S}]/gu, '').toLowerCase()
function resolveGuideTask(guideTask: ChatTurn['guideTask']) {
  if (!guideTask) return undefined
  const rows = planTaskRows.value
  const direct = rows.find(row => row.task.task_id === guideTask.task_id)
  if (direct) return direct
  const legacy = rows.find(row => row.task.text === guideTask.task_id || `${row.phase.name}:${row.task.text}` === guideTask.task_id)
  if (legacy) return legacy
  const target = normalizeTaskText(guideTask.text)
  if (!target) return undefined
  const matches = rows.filter(row => normalizeTaskText(row.task.text) === target)
  return matches.length === 1 ? matches[0] : undefined
}
type GuideTaskState = 'done' | 'pending' | 'missing'
function guideTaskState(guideTask: ChatTurn['guideTask']): GuideTaskState {
  const found = resolveGuideTask(guideTask)
  if (!found) return 'missing'
  return found.task.done ? 'done' : 'pending'
}
function guideTaskLabel(guideTask: ChatTurn['guideTask']) {
  const state = guideTaskState(guideTask)
  return state === 'done' ? '恢复任务' : state === 'pending' ? '完成任务' : '加入阶段计划'
}
// 最后一条带「可以 / 先不要」的回复：确认条常驻在输入框上方，不会被后续输入淹没。
const pendingConfirm = computed(() => {
  for (let index = turns.value.length - 1; index >= 0; index -= 1) {
    const turn = turns.value[index]
    if (turn.from !== 'host' || !turn.optionRefs?.length || confirmDismissed.value.includes(turn.id)) continue
    const yes = turn.optionRefs.find(option => option.label.includes('可以'))
    const no = turn.optionRefs.find(option => option.label.includes('先不要') || option.label.includes('不要'))
    // 只认最近一条带选项的回复；更早的确认已经被它取代，不再常驻。
    return yes && no ? { turnId: turn.id, yes, no } : null
  }
  return null
})
function chooseConfirm(choice: OptionRef) {
  const item = pendingConfirm.value
  if (!item || thinking.value || uploading.value || systemData.busy) return
  confirmDismissed.value = [...confirmDismissed.value, item.turnId]
  // 如果输入框里正是这个选项（之前点过只填入），点确认就直接发走，别留下重复草稿。
  if (draft.value.trim() === choice.label.trim()) { draft.value = ''; selectedOption.value = null; remember() }
  void send(false, { text: choice.label, option: choice })
}
function safeLink(url?: string | null) { try { const u = new URL(url || ''); return ['http:', 'https:'].includes(u.protocol) ? u.href : undefined } catch { return undefined } }
function displayDate(raw: string) { const date = new Date(raw); return Number.isNaN(date.getTime()) ? raw : date.toLocaleString('zh-CN', {month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'}) }
function evidenceCount(t: ChatTurn) { return (t.theory_refs?.length ?? 0) + (t.intel_refs?.length ?? 0) + (t.clues?.length ?? 0) }
function assetLabel(type: string) { return ({ report:'诊断报告', direction_plan:'方向方案', action_plan:'行动计划' } as Record<string,string>)[type] || '关联资料' }
async function theory(id: string) { if (theoryCards.value[id] || theoryLoading.value[id]) return; theoryErrors.value[id] = ''; theoryLoading.value[id] = true; try { theoryCards.value[id] = await backendClient.theory(id) } catch (e) { theoryErrors.value[id] = friendlyError(e) } finally { theoryLoading.value[id] = false } }
async function refreshProfile(options: { promptMissingStudyYear?: boolean } = {}) { profileLoading.value = true; profileError.value = ''; try { const result = await backendClient.workspace(); if (!disposed) { backendDemo.setWorkspace(result); const stored = result.profile_panel?.fields?.find(field => field.key === 'study_year'); if (stored) savedStudyYear.value = String(stored.value ?? ''); if (options.promptMissingStudyYear && needsInitialStudyYearChoice({ studyYear: studyYear.value, hasSession: !!demo.state.currentSessionId, hasTurns: turns.value.length > 0, hasPending: !!pending.value })) editingStudyYear.value = true } } catch (e) { if (!disposed) profileError.value = friendlyError(e) } finally { if (!disposed) { profileLoading.value = false; profileLoaded.value = true } } }
function clearTopicQuery() { if (route.query.new === undefined) return; const query = { ...route.query }; delete query.new; void router.replace({ path:route.path, query }) }
function chooseTopic() {
 if (thinking.value || systemData.busy || !systemData.shellReady) return
 // 没有学习阶段时先把那一问摆出来：以前只有“已有年级”的摘要按钮能打开它，
 // 结果是缺年级的人永远看不到这张卡。
 if (profileLoaded.value && !studyYear.value) editingStudyYear.value = true
 choosingTopic.value = true; historyOpen.value = false; profileOpen.value = false; requestError.value = ''
 void nextTick(() => { if (flow.value) flow.value.scrollTop = 0 })
}
function closeTopic() { choosingTopic.value = false; clearTopicQuery(); void bottom(true) }
function cancelStudyYear() { editingStudyYear.value = false; pendingTopic.value = null; choosingTopic.value = true }
async function reloadConversation() {
 if (thinking.value || systemData.busy) return
 requestError.value = ''
 interrupted.value = null
 if (demo.state.currentSessionId) await resume(demo.state.currentSessionId)
}
async function resume(id: string, startup = false) { if (thinking.value) return; try { await openSession(id); if (startup && typeof route.query.new === 'string') applyNewTopicIntent(); else { choosingTopic.value = false; clearTopicQuery() } historyOpen.value = false; pending.value = null; requestError.value = ''; syncInterruptedNotice(); await bottom(true) } catch (e) { requestError.value = friendlyError(e) } }
async function create(code: string, fresh = false): Promise<boolean> { if (thinking.value || systemData.busy) return false; try { await newSession(code, fresh); choosingTopic.value = false; clearTopicQuery(); pending.value = null; requestError.value = ''; await loadShell(); input.value?.focus(); return true } catch (e) { requestError.value = friendlyError(e); return false } }
async function start(code: string, label: string) {
 if (startingTopic.value || thinking.value || uploading.value || systemData.busy || restoring.value || !systemData.shellReady) return
 if (!profileLoaded.value) { requestError.value = '正在读取个人资料，请稍候再试。'; void refreshProfile(); return }
 if (!studyYear.value) {
  // 先确认年级，再建会话；确认后由 saveStudyYear 接着开始这个主题。
  pendingTopic.value = { code, label }
  editingStudyYear.value = true
  choosingTopic.value = true
  requestError.value = ''
  return
 }
 startingTopic.value = true
 try {
  // 先确认新会话创建成功，再把用户选中的问题交给模型，避免失败时发到旧会话。
  if (!await create(code, true)) return
  if (code !== 'free_chat') await send(false, { text: label })
  else void nextTick(() => input.value?.focus())
 } finally { startingTopic.value = false }
}
async function saveStudyYear(label: string) {
 if (studyYearSaving.value) return
 studyYearSaving.value = label; studyYearError.value = ''
 try {
  const updated = await backendClient.correct('study_year', label, studyYearField.value?.updated_at ?? null)
  savedStudyYear.value = String(updated.value ?? label)
  const pending = pendingTopic.value
  pendingTopic.value = null
  editingStudyYear.value = false; choosingTopic.value = !pending
  await refreshProfile()
  if (pending) await start(pending.code, pending.label)
 } catch (e) {
  studyYearError.value = friendlyError(e)
  if ((e as { code?: number }).code === 1003) await refreshProfile()
 } finally { studyYearSaving.value = '' }
}
/**
 * 对话里的任务卡：先对齐真实计划，再按状态决定动作。
 *
 * 深度测试 DEF-DS-01：卡片上的 guideTask.task_id 有时不在当前计划里（计划已重排，
 * 或这条只是主理给的建议），直接拿它勾选会得到 404「行动任务不存在」。现在的顺序是：
 * ① 先取最新计划并按 id/文本对齐；② 对上了就勾完成/恢复；③ 对不上就把它加进当前阶段，
 * 让「✓完成任务」不再是一条死路。成功后阶段计划与今日行动读的是同一份 liveAction。
 */
async function toggleTask(guideTask: NonNullable<ChatTurn['guideTask']>) {
  if (guideSaving.value) return
  guideSaving.value = guideTask.task_id
  try {
    const latest = await backendClient.action()
    backendDemo.setAction(latest)
    const found = resolveGuideTask(guideTask)
    if (found) {
      backendDemo.setAction(await backendClient.actionDone({ task_id: found.task.task_id, done: !found.task.done }))
      toast(found.task.done ? '已恢复为待执行，今日行动同步更新。' : '已完成，今日行动与阶段计划同步更新。')
      return
    }
    const phases = (latest.phases ?? []).filter(phase => phase.id)
    if (!phases.length) { toast('这条建议还没进阶段计划，也找不到可用的阶段。请先到「阶段计划」新建阶段。'); return }
    const nextId = latest.next_task?.task_id
    const preferred = nextId ? phases.find(phase => (phase.tasks ?? []).some(task => task.task_id === nextId)) : undefined
    const phase = preferred ?? phases.find(row => !row.blocked_by?.length) ?? phases[0]
    if (!phase.id) { toast('这条建议暂时加不进阶段计划，请到「阶段计划」手动添加。'); return }
    backendDemo.setAction(await studentApi.saveTask({
      client_request_id: crypto.randomUUID(),
      expected_task: null,
      text: guideTask.text,
      phase_id: phase.id,
      status: 'pending',
      progress: 0,
      waiting_reason: '',
      due_date: guideTask.due_date ?? null,
      scheduled_at: null,
      estimated_minutes: null,
      parent_task_id: null,
    }))
    toast(`这条建议还没进阶段计划，已先加入「${phase.name}」，可到今日行动继续推进。`)
  } catch (e) {
    if (errorCode(e) === 404) toast('这条建议对应的任务已不在当前计划里（计划可能更新过）。已刷新计划，可到「阶段计划」核对后重试。')
    else toast(friendlyError(e))
  } finally { guideSaving.value = '' }
}
function stop() { if (!stopArmed.value) return; stopped.value = true; markChatStopped(demo.state.currentSessionId); if (activeRunId.value) void backendClient.cancelConversationRun(demo.state.currentSessionId, activeRunId.value).catch(() => toast('已停止接收，执行状态请稍后核对。')); controller?.abort() }
async function send(retry = false, choice?: { text: string; option?: OptionRef }, resend?: { clientMsgId?: string; materials?: { id: string; name: string }[] }) {
 if (thinking.value || uploading.value || systemData.busy || backgroundRun.value) {
  if (backgroundRun.value && !thinking.value) requestError.value = '上一轮仍在处理，请等它完成或先停止后再发送。'
  return
 }
 // 刷新后 failedRequest 会因为本轮普通消息成功而被清空，失败态里仍保存着原始请求。
 const retried = retry ? (failedRequest ?? failedSend.value?.request ?? null) : null
 const text = retry ? retried?.message : choice ? choice.text : draft.value.trim() || (attached.value.length ? '请结合我上传的材料提供建议。' : '')
 if (!text) return
 // 超长消息在发出去之前就拦下：不渲染成气泡、不清空输入、不进入“重试”死循环。
 // 重试一条历史超长请求时，把原文放回输入框让他能直接删短。
 const lengthIssue = messageLengthError(text)
 if (lengthIssue) {
  requestError.value = lengthIssue
  if (retry) { draft.value = text; remember() }
  return
 }
 const outgoingMaterials = resend?.materials ?? (retry ? (failedSend.value?.materials ?? attached.value.map(m => ({ ...m }))) : choice ? [] : attached.value.map(m => ({ ...m })))
 const outgoingOption = choice ? choice.option : selectedOption.value, outgoingDraft = draft.value
 if (!demo.state.currentSessionId) { const code = starters.value[0]?.code; if (!code) { requestError.value = '当前没有可用的咨询入口。'; return }; await create(code); if (!demo.state.currentSessionId || requestError.value) return }
 const sessionId = demo.state.currentSessionId
 markChatPending(sessionId)
 const request: MessageRequest = retried ?? { task_id:sessionId, message:text, client_msg_id:resend?.clientMsgId || crypto.randomUUID(), material_ids:outgoingMaterials.map(m => m.id), ...(outgoingOption ? { option_id:outgoingOption.option_id, option_value:outgoingOption.value } : {}) }
 const run = ++serial
 failedRequest = request; requestError.value = ''; stopped.value = false
 controller = new AbortController(); thinking.value = true
 // 发送后 700ms 内忽略"停止"点击，避免双击发送把刚发出的消息撤回。
 stopArmed.value = false; clearTimeout(stopArmTimer)
 stopArmTimer = setTimeout(() => { stopArmed.value = true }, 700)
 liveFocus.value = ''; pending.value = { text:'', agent:host.value, note:'正在分析你的问题' }; activeRunId.value = request.client_msg_id || ''
 if (!retry && !resend?.clientMsgId) {
  demo.addChatTurn({ id:`${request.client_msg_id}-user`, from:'me', text, materials:outgoingMaterials })
  if (!choice) { if (draft.value === outgoingDraft) draft.value = ''; attached.value = attached.value.filter(m => !outgoingMaterials.some(s => s.id === m.id)); selectedOption.value = null; remember() }
 }
 followTail.value = true; void bottom(true)
 try {
  const result = await streamBackend<ConversationTurnView>('messageStream', { body:request, signal:controller.signal }, frame => {
   if (run !== serial || demo.state.currentSessionId !== sessionId || !pending.value) return
   if (frame.text !== undefined) pending.value.text = frame.text
   if (frame.type === 'role.selected' && typeof frame.stage === 'string') liveFocus.value = frame.stage
   if (frame.agent) pending.value.agent = frame.agent
   if (frame.note) pending.value.note = frame.note
   if (frame.type === 'approval.required') void refreshRuntime()
   void bottom()
  })
  if (run !== serial || demo.state.currentSessionId !== sessionId) return
  // 重新尝试成功时，失败的这条用户消息要正式进入对话流（之前只存在失败态里）。
  // 刷新恢复的会话里服务端消息 id 不是 client_msg_id，按文本再查一次，避免同一句出现两次。
  if (retry && !turns.value.some(turn => turn.id === `${request.client_msg_id}-user` || (turn.from === 'me' && turn.text === text))) {
   demo.addChatTurn({ id:`${request.client_msg_id}-user`, from:'me', text, materials:outgoingMaterials })
  }
  demo.setChatTurns([...turns.value, ...replyTurns(result, request.client_msg_id || crypto.randomUUID())], sessionId)
  systemData.snapshot = result; pending.value = null; failedRequest = null; void refreshRuntime()
  clearChatPending(sessionId)
  // 只有"重新尝试"成功才清掉失败记录；普通新消息成功不应抹掉另一条待重试的消息。
  if (retry) clearFailure(sessionId)
  else if (failedSend.value) failedRequest = failedSend.value.request
  backendDemo.saveTurns(sessionId, demo.state.chatTurns)
  void loadShell(); void refreshProfile(); void bottom()
 } catch (e) { if (run === serial) {
   if (stopped.value) {
    // 停止不是"撤回提问"：问题已经发出并落库，保留它；已收到的部分正文留着，
    // 并明确标注没说完（不伪装成完整回复）。
    const partial = pending.value?.text?.trim() ?? ''
    const speaker = partialReplySpeaker(pending.value?.agent, host.value)
    pending.value = null
    if (partial) demo.addChatTurn({
      id: `${request.client_msg_id}-partial`,
      from: 'host',
      speaker,
      text: partial,
      guideText: '（已停止接收，以上是已经收到的部分，没有说完。）',
    })
    requestError.value = '已停止接收这一轮回复。你的问题已发出；可以继续补充，或稍后重新提问。'
    remember()
   } else {
    requestError.value = friendlyError(e)
    // 失败的消息与错误按会话落盘：刷新后仍能看到、仍可重新尝试。
    if (demo.state.currentSessionId === sessionId) rememberFailure(sessionId, { request, materials: outgoingMaterials, error: requestError.value, at: new Date().toISOString() })
   }
  } }
 finally { if (run === serial) { thinking.value = false; liveFocus.value = ''; controller = null; if (!stopped.value) clearChatPending(sessionId) } }
}
async function copy(text: string, turnId?: string) {
  const done = (ok: boolean) => {
    if (!ok) { toast('复制失败，请手动选择文字复制。'); return }
    if (turnId) { copiedTurn.value = turnId; clearTimeout(copyTimer); copyTimer = setTimeout(() => { copiedTurn.value = '' }, 2000) } else toast('已复制')
  }
  try {
    await navigator.clipboard.writeText(text)
    done(true)
    return
  } catch { /* 无剪贴板权限/非安全上下文：退回 execCommand */ }
  try {
    // 兜底：临时 textarea + execCommand。headless/受限权限下 clipboard API 会失败，
    // 但 execCommand('copy') 仍可用，避免"点了复制只能手动选中"。
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    area.setSelectionRange(0, area.value.length)
    const ok = document.execCommand('copy')
    area.remove()
    done(ok)
  } catch {
    toast('复制失败，请手动选择文字复制。')
  }
}
function keydown(e: KeyboardEvent) { if (e.key === 'Enter' && !e.shiftKey && !isComposingKey(e) && navigation.width.value > 760) { e.preventDefault(); void send() } }
watch(thinking, (busy, wasBusy) => {
 demo.setChatBusy(busy); clearInterval(waitTimer)
 if (busy) { elapsed.value = 0; requestStarted = Date.now(); replyAnnouncement.value = '正在接收回复。'; waitTimer = setInterval(() => { elapsed.value = Math.floor((Date.now() - requestStarted) / 1000) }, 1000) }
 else if (wasBusy) replyAnnouncement.value = stopped.value ? '回复已停止，已接收的内容保留。' : '回复已到，可以继续提问。'
}, { flush:'sync' })
watch(() => route.query.history, value => {
 if (value === '1') historyOpen.value = true
}, { immediate: true })
watch(() => navigation.width.value, () => { void nextTick(resizeInput) })
watch(requestError, message => {
 if (!message) return
 // Only a real send attempt can be announced as a reply failure. Session-list
 // and shell errors are operations, not a reply the user just sent.
 const attemptedReply = !!failedRequest || thinking.value || !!pending.value || stopped.value
 replyAnnouncement.value = stopped.value
  ? '回复已停止，已接收的内容保留。'
  : attemptedReply ? '回复失败，可以重试。' : '这一步没有完成，请按页面提示重试。'
})
watch([draft, attached], () => { remember(); void nextTick(resizeInput) }, { deep:true })
watch(() => demo.state.currentSessionId, (_id, previous) => {
 backendDemo.saveDraft(previous, draft.value, attached.value, flow.value?.scrollTop ?? null)
 const data = backendDemo.getDraft(demo.state.currentSessionId); draft.value = data.text; attached.value = data.materials.map(m => ({ ...m }))
 selectedOption.value = null; failedRequest = null; pending.value = null; requestError.value = ''; uploadError.value = ''; stopped.value = false; choosingTopic.value = false; followTail.value = true
 fillRequest.value = null; replacedDraft.value = null; confirmDismissed.value = []; interrupted.value = null
 // 朗读状态属于当前会话：切走之后不能把上一段的“回复已停止”念给新会话听。
 replyAnnouncement.value = ''
 pendingTopic.value = null
 loadFailure(demo.state.currentSessionId)
 // 记住"这个标签页正在看哪条会话"：刷新后优先回到它，而不是账号级最近会话。
 // （多标签页看不同会话时，按账号恢复会互相抢位置。）
 try { if (demo.state.currentSessionId) sessionStorage.setItem('zhiyin-current-session', demo.state.currentSessionId) } catch { /* 私人模式等不可用 */ }
 syncInterruptedNotice()
 void bottom(true)
}, { flush:'sync' })
// 刷新/切页恢复到"最后一条是提问、没有回复"的会话时，修复残局并给出中断提示。
// 也监听 systemData.busy：刷新恢复走的是 App 壳的 loadShell→openSession，
// 消息是在 busy=true 期间写入的，等 busy 落回 false 后还要再检查一次。
watch([turns, thinking, () => systemData.busy, () => demo.state.currentSessionId, () => !!backgroundRun.value], () => syncInterruptedNotice(), { flush: 'post' })
function applyConsultationContext() {
 // 报告页等入口用 ?ask= 直接发起一句咨询：自动填入并发送，发送后清掉参数。
 const ask = typeof route.query.ask === 'string' ? route.query.ask.trim() : ''
 if (ask) {
  // Do not delete ?ask before it is actually sent: if the user leaves while the
  // page is restoring, the next visit can still finish the explicit action.
  if (draft.value.trim() && draft.value.trim() !== ask) {
   askConfirm.value = { text: ask, previousText: draft.value, previousOption: selectedOption.value }
   askPending.value = ''
   return
  }
  askPending.value = ask
  void runAsk()
  return
 }
 if (typeof route.query.new === 'string') { applyNewTopicIntent(); return }
 const query = route.query
 const text = typeof query.question === 'string' ? query.question
  : typeof query.topic === 'string' ? '我想讨论：' + query.topic
  : typeof query.label === 'string' ? '我想补充' + query.label + '：' : ''
 if (!text) return
 // Preserve an unfinished draft when arriving from another page, but do not
 // append the same deep-link sentence twice on repeated navigation.
 const existing = draft.value.trim()
 applyFill(existing && existing !== text
  ? (existing.includes(text) ? existing : existing + '\n\n' + text)
  : text)
 remember()
 const rest = { ...query }; for (const key of ['question', 'topic', 'label', 'gap']) delete rest[key]
 void router.replace({ path: route.path, query: rest })
}
watch(() => route.query, applyConsultationContext)
// Consume the route token once. Busy/restore changes must not reopen the
// selector after the user has chosen a topic and created the new session.
function applyNewTopicIntent() {
 const token = route.query.new
 if (typeof token !== 'string' || token === handledNewTopicIntent || !systemData.shellReady || thinking.value || systemData.busy || restoring.value) return
 handledNewTopicIntent = token
 chooseTopic()
}
watch([() => systemData.busy, () => systemData.shellReady, thinking, restoring], applyNewTopicIntent)
function clearAskQuery() {
 if (typeof route.query.ask !== 'string') return
 const query = { ...route.query }; delete query.ask
 void router.replace({ path: route.path, query })
}
function sendAskReplacingDraft() {
 const request = askConfirm.value
 if (!request) return
 askConfirm.value = null
 replacedDraft.value = { text: request.previousText, option: request.previousOption }
 askPending.value = request.text
 void runAsk()
}
function keepDraft() {
 askConfirm.value = null
 askPending.value = ''
 clearAskQuery()
}
async function runAsk() {
 if (!askPending.value || thinking.value || uploading.value || systemData.busy) return
 // 等壳层、画像与首屏问句就绪，避免把消息发进一个还没准备好的会话、跳过年级确认。
 if (!systemData.shellReady || !profileLoaded.value || showStudyYearQuestion.value) return
 // 从报告页等入口带 ?ask= 进入时，页面可能正停在"选择咨询主题"。
 // 直接提问是用户的明确动作：收起主题选择，交给 send() 自动建会话。
 if (choosingTopic.value) choosingTopic.value = false
 const ask = askPending.value
 askPending.value = ''
 draft.value = ask
 await send()
 // send() clears the draft only after it accepted the turn. If it refused
 // (busy/background run/no entrance), keep ?ask so the action is not lost.
 if (draft.value !== ask) clearAskQuery()
}
watch([() => systemData.shellReady, () => systemData.busy, () => showStudyYearQuestion.value, () => profileLoaded.value, choosingTopic, thinking, uploading], () => void runAsk())
watch(showStudyYearQuestion, open => {
 if (open) void nextTick(() => { if (flow.value) flow.value.scrollTop = 0 })
})
onMounted(() => {
 recoveryTimer = setInterval(() => { if (!thinking.value && backgroundRun.value && document.visibilityState === 'visible') void refreshRuntime() }, 2500)
 window.addEventListener('focus', refreshSessionsOnFocus)
 window.addEventListener('zhiyin:session-cleared', clearAllFailures)
 document.addEventListener('visibilitychange', refreshSessionsOnFocus)
 void nextTick(resizeInput)
 if (demo.state.currentSessionId && !systemData.busy) {
  restoring.value = true
  void resume(demo.state.currentSessionId, true).finally(() => { restoring.value = false })
 }
 loadFailure(demo.state.currentSessionId)
 void refreshProfile({ promptMissingStudyYear: true })
 // Sessions created elsewhere (report/approval flows) are not in the shell
 // snapshot loaded at app start. Refresh silently without changing selection.
 void refreshSessionList(false, true)
 applyConsultationContext()
 void bottom(true)
})
onUnmounted(() => { disposed = true; clearInterval(recoveryTimer); window.removeEventListener('focus', refreshSessionsOnFocus); window.removeEventListener('zhiyin:session-cleared', clearAllFailures); document.removeEventListener('visibilitychange', refreshSessionsOnFocus); clearInterval(waitTimer); clearTimeout(copyTimer); remember(); serial++; controller?.abort(); demo.setChatBusy(false) })
</script>
<template>
<section class="consultation-page" aria-label="咨询对话空间">
 <div class="consult-main">
  <header class="consult-header">
   <div class="consult-header__top"><div class="consult-heading"><h1>咨询对话</h1><p v-if="!choosingTopic && demo.state.currentSessionId" class="consult-session-title" :title="title">{{ title }}</p></div><div class="consult-header__actions">
    <AnchoredCard v-model="historyOpen" class="consult-icon consult-history-button" title="历史会话" side="bottom" align="end" size="wide"><template #trigger><UiIcon name="chat" :size="18" /></template><div class="session-manage">
     <div class="session-manage__tools"><label class="information-search session-search"><span class="sr-only">搜索历史会话</span><input v-model="sessionQuery" type="search" aria-label="搜索历史会话" placeholder="搜索标题或最后一句" autocomplete="off" /></label><button type="button" class="ws-text-button" :disabled="sessionListLoading" @click="refreshSessionList(true)">{{ sessionListLoading ? '刷新中…' : '刷新列表' }}</button></div>
     <p v-if="sessionListError" class="consult-error session-manage__error" role="alert">{{ sessionListError }}<button type="button" @click="refreshSessionList(true)">重试</button></p>
     <div class="session-manage__copy"><button type="button" class="ws-text-button" :disabled="!turns.length" @click="copy(turns.map(t => (t.from === 'me' ? '我' : t.speaker || '系统') + '：' + t.text).join('\n\n'))">复制当前会话记录</button></div>
     <p v-if="!sessions.length" class="ws-muted">还没有历史会话。开始咨询后会自动保存在这里。</p>
     <p v-else-if="!filteredSessions.length" class="ws-muted">没有找到匹配「{{ sessionQuery }}」的会话。</p>
     <ul v-else class="session-rows">
      <li v-for="session in filteredSessions" :key="session.task_id" class="session-row" :class="{ 'is-current': session.task_id === demo.state.currentSessionId }">
       <form v-if="renamingId === session.task_id" class="session-row__rename" @submit.prevent="saveRename(session)">
        <label class="ws-field"><span>会话名称</span><input v-model="renameDraft" type="text" maxlength="60" aria-label="会话名称" :aria-invalid="!!renameError" @keydown.esc="cancelRename" /></label>
        <p class="session-row__hint">2–60 个字；只改标题，不影响对话内容。</p>
        <p v-if="renameError" class="ws-field-error" role="alert">{{ renameError }}</p>
        <div class="session-row__edit-actions"><button type="submit" class="btn btn--primary btn--sm" :disabled="renameBusy">{{ renameBusy ? '保存中…' : '保存' }}</button><button type="button" class="btn btn--sm" :disabled="renameBusy" @click="cancelRename">取消</button></div>
       </form>
       <div v-else-if="deletingId === session.task_id" class="session-row__confirm" role="alert">
        <strong>删除「{{ session.task_name }}」？</strong>
        <p>删除后不可恢复，这段对话记录会一起移除。</p>
        <p v-if="deleteError" class="ws-field-error">{{ deleteError }}</p>
        <div class="session-row__edit-actions"><button type="button" class="btn btn--danger btn--sm" :disabled="deleteBusy" @click="confirmDelete(session)">{{ deleteBusy ? '删除中…' : '确认删除' }}</button><button type="button" class="btn btn--sm" :disabled="deleteBusy" @click="cancelDelete">取消</button></div>
       </div>
       <template v-else>
        <button type="button" class="session-row__main" :aria-pressed="session.task_id === demo.state.currentSessionId" :disabled="thinking || systemData.busy" :title="thinking ? '当前回复生成中，完成后可切换会话' : undefined" @click="resume(session.task_id)"><strong>{{ session.task_name }}</strong><span class="consult-session-preview">{{ session.last_message || '还没有消息' }}</span><small><template v-if="session.message_count">{{ session.message_count }} 条 · </template>{{ sessionTimeLabel(session) }}</small></button>
        <div class="session-row__actions"><button type="button" class="session-row__action" :aria-label="`重命名会话：${session.task_name}`" @click="startRename(session)">重命名</button><button type="button" class="session-row__action session-row__action--danger" :aria-label="`删除会话：${session.task_name}`" @click="askDelete(session)">删除</button></div>
       </template>
      </li>
     </ul>
     <p class="session-manage__note">重命名只改标题；删除不可恢复。</p>
    </div></AnchoredCard>
    <button class="consult-icon consult-new-button" aria-label="新建对话" :disabled="thinking || systemData.busy" @click="chooseTopic"><UiIcon name="plus" :size="19" /></button>
    <AnchoredCard v-model="capabilitiesOpen" class="consult-icon consult-capability-button" title="能做什么" side="bottom" align="end" size="wide"><template #trigger><UiIcon name="spark" :size="18" /><span class="consult-header__label">能做什么</span></template><div class="capability-panel">
     <p class="capability-panel__intro">这里列出当前账号能用和用不了的能力。不能用的会写明原因，并给出可以替代的做法。</p>
     <p v-if="capabilitiesLoading" class="capability-panel__status" role="status">正在读取能力清单…</p>
     <div v-else-if="capabilitiesError" class="consult-error" role="alert"><p>{{ capabilitiesError }}</p><button type="button" :disabled="capabilitiesLoading" @click="loadCapabilities(true)">重新读取</button></div>
     <template v-else-if="capabilityItems.length">
      <ul class="capability-list">
       <li v-for="item in capabilityItems" :key="item.key" class="capability-item" :data-state="item.available ? 'available' : 'unavailable'">
        <div class="capability-item__head"><strong>{{ item.label }}</strong><span class="capability-badge" :data-state="item.available ? 'available' : 'unavailable'">{{ capabilityStatus(item) }}</span></div>
        <p v-if="!item.available && item.reason" class="capability-item__reason">原因：{{ item.reason }}</p>
        <p v-if="item.fallback" class="capability-item__fallback">替代：{{ item.fallback }}</p>
       </li>
      </ul>
      <p v-if="capabilities?.generated_at" class="capability-panel__meta">清单更新时间：{{ displayDate(capabilities.generated_at) }}</p>
     </template>
     <p v-else class="ws-muted">当前还没有登记可用能力。</p>
    </div></AnchoredCard>
    <AnchoredCard v-model="profileOpen" class="consult-icon consult-profile-button" title="个人画像" side="bottom" align="end"><template #trigger><UiIcon name="profile" :size="19" /><span class="consult-header__label">个人画像</span></template><ConversationProfile embedded :loading="profileLoading" :error="profileError" @close="profileOpen = false" @refresh="refreshProfile" @supplement="fill" /></AnchoredCard>
   </div></div>
   <ol v-if="!choosingTopic && demo.state.currentSessionId" class="consult-journey" aria-label="咨询进度：已走过的阶段、当前工作重点与后续阶段，可随话题调整"><li v-for="item in journey" :key="item.key" :data-state="stageState(item.key)" :aria-current="currentStage === item.key ? 'step' : undefined"><i /><span><em class="consult-journey__full">{{ item.label }}</em><em class="consult-journey__short">{{ item.short }}</em></span></li></ol>
  </header>
  <div class="consult-banners">
   <StatusBanner v-if="systemErrorVisible" class="consult-system-error" tone="error" :message="systemData.error" retry-label="重新读取" @retry="loadShell" @dismiss="systemData.error = ''" />
   <StatusBanner v-if="runtimeError" class="consult-system-error" tone="info" :message="runtimeError" retry-label="重新读取执行状态" @retry="refreshRuntime" @dismiss="runtimeError = ''" />
  </div>
  <div ref="flow" v-scroll-fade class="consult-flow" tabindex="0" aria-label="对话记录" @scroll.passive="onScroll">
   <div v-if="systemData.busy || restoring" class="consult-loading" role="status">正在读取会话…</div>
   <div v-else-if="!profileLoaded && !demo.state.currentSessionId" class="consult-loading" role="status">正在读取个人资料…</div>
   <div v-else-if="showStudyYearQuestion || choosingTopic || (!turns.length && !pending && !showFailedSend && !demo.state.currentSessionId)" class="consult-intro" :class="{'consult-intro--onboarding':showStudyYearQuestion}">
    <AgentAvatar agent="career_advisor" :size="64" aria-label="知音 · 待命" title="知音 · 职业发展顾问" />
    <template v-if="showStudyYearQuestion">
     <p class="consult-intro__eyebrow">开始前确认一项信息</p>
     <h2>先确认一下：你现在大几？</h2>
     <p>只用于调整默认咨询方向，不会限制你可以提出的问题。</p>
     <div class="consult-year-options" role="group" aria-label="选择年级"><button v-for="option in STUDY_YEAR_OPTIONS" :key="option.code" :disabled="!!studyYearSaving" :aria-pressed="studyYearLabel(studyYear) === option.label" @click="saveStudyYear(option.label)"><span>{{ option.label }}</span><small v-if="studyYearSaving === option.label">正在保存…</small><UiIcon v-else name="arrow" :size="16" /></button></div>
     <p v-if="studyYearError" class="consult-error" role="alert">{{ studyYearError }}</p>
     <button v-if="editingStudyYear && (studyYear || pendingTopic)" class="consult-resume" @click="cancelStudyYear">取消修改</button>
    </template>
    <template v-else>
     <button v-if="studyYear" class="consult-year-summary" @click="editingStudyYear=true"><span>当前阶段：{{ studyYearLabel(studyYear) }}</span><small>修改</small></button>
     <h2>{{ studyYear ? `已按${studyYearLabel(studyYear)}安排咨询重点` : '从你现在关心的事开始' }}</h2><p>{{ studyYear ? studyYearIntro(studyYear) : '先选一个主题。进入后仍可自由补充，不会覆盖已有会话。' }}</p>
     <div class="consult-topics"><button v-for="(entry,i) in starters" :key="entry.code" :class="{'consult-topic--free':entry.code==='free_chat'}" :disabled="!systemData.shellReady || systemData.busy || restoring || startingTopic || uploading" @click="start(entry.code, entry.label)"><UiIcon :name="['profile','directions','action','review'][i % 4]" :size="21" /><span>{{ entry.label }}</span><UiIcon name="arrow" :size="17" /></button></div>
     <p v-if="requestError" class="consult-error" role="alert">{{ requestError }}</p>
     <button v-if="choosingTopic && demo.state.currentSessionId" class="consult-resume" @click="closeTopic">返回当前会话</button>
     <button v-else-if="sessions.length && sessions[0].task_id !== demo.state.currentSessionId" class="consult-resume" :disabled="thinking || systemData.busy" @click="resume(sessions[0].task_id)">继续最近的咨询：{{ sessions[0].task_name }}</button>
    </template>
   </div>
   <div v-else class="consult-messages" :aria-busy="thinking">
    <div v-if="!turns.length && !pending && demo.state.currentSessionId" class="consult-empty" role="status">
     <AgentAvatar agent="career_advisor" :size="52" aria-label="知音 · 待命" title="知音 · 职业发展顾问" />
     <h2>新会话已就绪</h2>
     <p>直接在下面说说你现在最想解决的问题；想换个主题就点右上角「＋」。</p>
    </div>
    <article v-for="turn in turns" :key="turn.id" class="consult-turn" :class="['consult-turn--' + turn.from, { 'consult-turn--latest': turn.id === latestHostId }]">
     <div v-if="turn.from === 'me'" class="consult-user"><p>{{ turn.text }}</p><small v-for="m in turn.materials" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}</small></div>
     <p v-else-if="turn.from === 'system'" class="consult-system">{{ cleanConsultantText(turn.text) }}</p>
     <template v-else><AgentAvatar :agent="agentKeyOf(turn.speaker)" :size="38" :aria-label="consultantLabel(turn.speaker)" :title="consultantLabel(turn.speaker)" /><div class="consult-answer">
      <span class="consult-speaker"><b>{{ consultantLabel(turn.speaker || '咨询顾问') }}</b><small v-if="turn.id === latestHostId">当前建议</small></span>
      <div v-if="turn.text || turn.guideText" class="consult-answer-copy">
       <ReadableText v-if="turn.text" :text="cleanConsultantText(turn.text)" class="consult-prose" />
       <ReadableText v-if="turn.guideText" :text="cleanConsultantText(turn.guideText)" class="consult-guide" />
      </div>
      <div class="consult-references">
        <DetailPopover v-if="evidenceCount(turn)" title="本轮线索" side="top" class="consult-evidence" @update:model-value="open => open && turn.theory_refs?.forEach(r => theory(r.theory_id))"><template #trigger><UiIcon name="shield" :size="15" /><span>查看线索</span><small>{{ evidenceCount(turn) }}</small></template>
         <h3 v-if="turn.clues?.length">判断标准与待核实项</h3><div v-for="(clue, index) in turn.clues" :key="index" class="consult-source"><p>{{ clue }}</p></div><p v-if="turn.clues?.length" class="ws-muted">以上为本轮分析说明；资料出处与参考方法列在下方。</p><h3 v-if="turn.intel_refs?.length">检索资料</h3><div v-for="r in turn.intel_refs" :key="r.id" class="consult-source"><strong>{{ r.title || '资料来源' }}</strong><p v-if="r.source_name">{{ r.source_name }}</p><a v-if="safeLink(r.source_url)" :href="safeLink(r.source_url)" target="_blank" rel="noopener noreferrer">查看原始资料</a></div>
         <h3 v-if="turn.theory_refs?.length">参考方法</h3><div v-for="r in turn.theory_refs" :key="r.theory_id" class="consult-source"><strong>{{ r.name }}</strong><p v-if="theoryCards[r.theory_id]">{{ theoryCards[r.theory_id].summary || '暂无详细方法说明。' }}</p><p v-else-if="theoryLoading[r.theory_id]" role="status">正在读取方法说明…</p><button v-else @click="theory(r.theory_id)">重新读取方法说明</button><p v-if="theoryErrors[r.theory_id]" role="alert">{{ theoryErrors[r.theory_id] }}</p></div>
        </DetailPopover>
      <p v-if="turn.changedAssets?.length" class="consult-saved-assets" aria-label="本轮保存结果"><span v-for="asset in turn.changedAssets" :key="asset.asset_id">已更新{{ assetLabel(asset.asset_type) }} · 第 {{ asset.version }} 版</span></p>
      </div>
        <div v-if="turn.renderables?.length" class="consult-renderables"><RenderableBlock v-for="(block,i) in turn.renderables" :key="i" :item="block" /></div>
      <div v-if="turn.guideTask" class="consult-task"><UiIcon name="action" :size="21" /><div><small>把建议变成一步</small><p>{{ turn.guideTask.text }}</p><small v-if="turn.guideTask.due_date">{{ displayDate(turn.guideTask.due_date) }}</small><small v-if="guideTaskState(turn.guideTask) === 'missing'" class="consult-task-note">还没加入阶段计划，点右侧按钮可以加进去。</small></div><button :disabled="!!guideSaving" :title="guideTaskLabel(turn.guideTask)" :aria-label="guideTaskLabel(turn.guideTask)" @click="toggleTask(turn.guideTask)"><UiIcon :name="guideTaskState(turn.guideTask) === 'done' ? 'check' : 'plus'" :size="19" /></button></div>
      <div v-if="turn.reminder" class="consult-reminder"><UiIcon name="bell" :size="17" /><div><strong>{{ turn.reminder.title }}</strong><p v-if="turn.reminder.detail">{{ turn.reminder.detail }}</p><small v-if="turn.reminder.due_at">{{ displayDate(turn.reminder.due_at) }}</small></div></div>
      <p v-if="turn.question" class="consult-question">{{ cleanConsultantText(turn.question) }}</p>
      <div v-if="turn.optionRefs?.length" class="consult-option-group"><p>接下来，你可以</p><div class="consult-options"><button v-for="option in turn.optionRefs" :key="option.option_id" :aria-pressed="selectedOption?.option_id === option.option_id" :disabled="thinking" @click="fill(option.label, option)"><span>{{ cleanConsultantText(option.label) }}</span><UiIcon :name="selectedOption?.option_id === option.option_id ? 'check' : 'plus'" :size="14" /></button></div></div>
      <button class="consult-copy" :aria-label="copiedTurn === turn.id ? '已复制回复' : '复制回复'" @click="copy([turn.text, turn.guideText, turn.question].filter(Boolean).join('\n\n'), turn.id)"><UiIcon :name="copiedTurn === turn.id ? 'check' : 'copy'" :size="15" /><span v-if="copiedTurn === turn.id" role="status">已复制</span></button>
     </div></template>
    </article>
    <article v-if="showFailedSend && failedSend" class="consult-turn consult-turn--me consult-turn--failed" aria-label="未发送成功的消息">
     <div class="consult-user">
      <p>{{ failedSend.request.message }}</p>
      <small v-for="m in failedSend.materials" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}</small>
      <div class="consult-failed" role="alert">
       <span>这条消息没有发送成功：{{ failedSend.error }}</span>
       <div><button type="button" :disabled="thinking || systemData.busy" @click="send(true)">重新尝试</button><button type="button" @click="discardFailure">丢弃这条</button></div>
      </div>
     </div>
    </article>
    <div v-if="interrupted" class="consult-error consult-interrupted" role="alert">
     <p>上一轮回复在生成过程中中断了（刷新或切换页面导致），这一轮没有收到回答，上面也不会显示上一轮的旧内容。</p>
     <div class="consult-interrupted__actions">
      <button type="button" :disabled="thinking || systemData.busy" @click="retryInterrupted">重新发送这个问题</button>
      <button type="button" @click="dismissInterrupted">继续自己输入</button>
     </div>
    </div>
    <article v-if="pending" class="consult-turn consult-turn--host consult-pending" aria-label="当前回复"><AgentAvatar :agent="agentKeyOf(pending.agent)" :aria-label="consultantLabel(pending.agent)" :title="consultantLabel(pending.agent)" :size="38" :state="thinking ? pending.text ? 'speaking' : 'thinking' : 'idle'" /><div class="consult-answer"><span class="consult-speaker">{{ consultantLabel(pending.agent) }}</span><ReadableText v-if="pending.text" :text="cleanConsultantText(pending.text)" class="consult-prose" /><div v-else-if="thinking" class="consult-wait" role="status"><span class="consult-wait-orbit" aria-hidden="true"><i /><i /><i /></span><div><p>{{ pending.note }}</p><small>正在接收回复<span v-if="elapsed >= 3"> · {{ elapsed }} 秒</span></small></div></div><p v-if="thinking && pending.text" class="consult-live-note" role="status">{{ pending.note }}</p><span v-if="thinking && pending.text" class="consult-cursor" aria-label="正在回复" /><small v-if="!thinking">{{ stopped ? '接收已停止' : '回复未完成' }}</small></div></article>
    <div v-if="requestError && !showFailedSend" class="consult-error" role="alert"><p>{{ requestError }}</p><button v-if="failedRequest && !stopped" @click="send(true)">重试</button><button v-else :disabled="thinking" @click="reloadConversation">刷新会话</button></div>
   </div>
   <p v-if="backgroundRun && !thinking" role="status">{{ backgroundRun.last_status || '这轮仍在处理，完成后会自动恢复结果。' }}</p>
   <p class="sr-only" role="status" aria-live="polite">{{ replyAnnouncement }}</p>
  </div>
  <footer v-if="!choosingTopic && !showStudyYearQuestion" class="consult-compose-area">
   <div v-if="uploadError" class="consult-error" role="alert"><p>{{ uploadError }}</p><button :disabled="uploading || thinking" @click="fileInput?.click()">重新选择材料</button><button @click="uploadError = ''">关闭上传提示</button></div>
   <button v-if="showLatest" class="consult-latest" @click="followTail = true; bottom(true)"><UiIcon name="down" :size="15" />回到最新消息</button>
   <ConversationOperations v-if="runtimeState" :actions="runtimeState.actions" :busy="thinking || systemData.busy" @decide="decideAction" /><div v-if="pendingConfirm && !runtimeState?.actions.some(a => a.state === 'proposed')" class="consult-confirm" role="status" aria-label="待确认事项">
    <div class="consult-confirm__copy"><strong>有一条确认还没回复</strong><p>可以直接点选；继续输入其他内容也不会自动取消它。</p></div>
    <div class="consult-confirm__actions">
     <button type="button" :disabled="thinking || systemData.busy" @click="chooseConfirm(pendingConfirm.yes)">{{ cleanConsultantText(pendingConfirm.yes.label) }}</button>
     <button type="button" :disabled="thinking || systemData.busy" @click="chooseConfirm(pendingConfirm.no)">{{ cleanConsultantText(pendingConfirm.no.label) }}</button>
    </div>
   </div>
   <div v-if="askConfirm" class="consult-draft-bar" role="alert">
    <p>输入框里还有一段未发送的草稿。要先发送系统带来的这个问题吗？</p>
    <div><button type="button" @click="sendAskReplacingDraft">发送问题</button><button type="button" @click="keepDraft">保留草稿</button></div>
   </div>
   <div v-else-if="fillRequest" class="consult-draft-bar" role="alert">
    <p>输入框里已有草稿，要替换成「{{ cleanConsultantText(fillRequest.text) }}」吗？</p>
    <div><button type="button" @click="confirmFillReplace">替换</button><button type="button" @click="cancelFillReplace">保留草稿</button></div>
   </div>
   <div v-else-if="replacedDraft" class="consult-draft-bar consult-draft-bar--undo" role="status">
    <p>已替换输入内容，原草稿可以恢复。</p>
    <div><button type="button" @click="undoFillReplace">撤销替换</button><button type="button" @click="replacedDraft = null">知道了</button></div>
   </div>
   <form class="consult-composer" :class="{ 'consult-composer--drop': draggingFiles }" @dragover="dragOver" @dragleave="!($event.currentTarget as HTMLElement).contains($event.relatedTarget as Node) && (draggingFiles = false)" @drop="dropFiles" @submit.prevent="send()">
    <div v-if="draggingFiles" class="consult-drop-label" aria-hidden="true"><UiIcon name="attachment" :size="20" />松开以添加材料</div>
    <div v-if="attached.length" class="consult-attachments"><span v-for="(m,i) in attached" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}<button type="button" :aria-label="'移除' + m.name" @click="attached.splice(i,1)"><UiIcon name="close" :size="14" /></button></span></div>
    <textarea ref="input" v-model="draft" rows="1" aria-label="输入咨询内容" placeholder="说说你的想法，或添加材料…" @input="selectedOption?.label !== draft && (selectedOption = null)" @keydown="keydown" @paste="pasteFiles" />
    <div class="consult-compose-tools"><input ref="fileInput" type="file" hidden multiple :disabled="uploading || thinking" @change="upload" /><button type="button" class="consult-attach" :disabled="uploading || thinking" @click="fileInput?.click()"><UiIcon name="plus" :size="18" />{{ uploading ? '上传中…' : '添加材料' }}</button><span class="consult-send-hint">{{ thinking ? '回复生成中，可先准备下一条消息' : 'Enter 发送 · Shift + Enter 换行' }}</span><button v-if="thinking" type="button" class="consult-send consult-stop" :disabled="!stopArmed" aria-label="停止接收" @click="stop"><span /></button><button v-else type="submit" class="consult-send" aria-label="发送消息" :disabled="(!draft.trim() && !attached.length) || uploading || systemData.busy || !!backgroundRun"><UiIcon name="arrow" :size="20" /></button></div>
   </form>
   <p class="consult-disclaimer">建议供参考，重要决定由你做出。<DetailPopover title="资料使用说明" side="top"><template #trigger><UiIcon name="info" :size="13" /></template><p>材料和对话将按你的资料偏好参与分析。你可以查看、更正个人画像，或调整资料使用范围。</p><RouterLink to="/settings">管理资料偏好</RouterLink></DetailPopover></p>
  </footer>
 </div>
</section>
</template>
<style scoped>
/* 移动端阶段条 9px、「当前建议」10px 在 390 宽下读不清：统一抬到 11px，桌面保持原样。 */
@media (max-width: 767px) {
 .consult-journey li { font-size: 11px; }
 .consult-speaker small { font-size: 11px; }
}
.consult-confirm { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin: 0 0 8px; padding: 10px 12px; border: 1px solid var(--c-primary-border); border-radius: var(--r-md); background: var(--c-primary-weak); }
.consult-confirm__copy { display: grid; gap: 2px; min-width: 0; }
.consult-confirm__copy strong { color: var(--c-text); font-size: var(--fs-14); }
.consult-confirm__copy p { margin: 0; color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.5; }
.consult-confirm__actions { display: flex; flex: none; gap: 8px; }
.consult-confirm__actions button { min-height: 40px; padding: 0 14px; border: 1px solid var(--c-primary); border-radius: var(--r-pill); background: var(--c-surface); color: var(--c-primary); font-size: var(--fs-12); cursor: pointer; }
.consult-confirm__actions button:first-child { background: var(--c-primary); color: var(--c-on-primary); }
.consult-draft-bar { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin: 0 0 8px; padding: 10px 12px; border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-surface-2); }
.consult-draft-bar p { margin: 0; color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.5; }
.consult-draft-bar > div { display: flex; flex: none; gap: 8px; }
.consult-draft-bar button, .consult-failed button { min-height: 40px; padding: 0 12px; border: 1px solid var(--c-border-strong); border-radius: var(--r-pill); background: var(--c-surface); color: var(--c-text); font-size: var(--fs-12); cursor: pointer; }
.consult-draft-bar button:first-child, .consult-failed button:first-child { color: var(--c-primary); border-color: var(--c-primary); }
.consult-draft-bar--undo { border-color: var(--c-primary-border); background: var(--c-primary-weak); }
.consult-turn--failed .consult-user { border-color: var(--c-attention); }
.consult-failed { display: grid; gap: 8px; margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--c-attention); }
.consult-failed > span { color: var(--c-attention-strong); font-size: var(--fs-12); line-height: 1.55; }
.consult-failed > div { display: flex; gap: 8px; }
.consult-session-preview { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-text-3); font-size: var(--fs-12); text-align: left; }
.consult-session-list button strong { display: block; text-align: left; }
.consult-task-note { display: block; margin-top: 6px; color: var(--c-text-3); font-size: var(--fs-12); }
.consult-interrupted { align-items: flex-start; }
.consult-interrupted__actions { display: flex; flex: none; gap: 8px; }
.consult-interrupted__actions button { min-height: 40px; padding: 0 12px; border: 1px solid var(--c-primary); border-radius: var(--r-pill); background: var(--c-surface); color: var(--c-primary); font-size: var(--fs-12); cursor: pointer; }
.consult-interrupted__actions button:first-child { background: var(--c-primary); color: var(--c-on-primary); }
.consult-empty { display: grid; justify-items: center; gap: 6px; padding: 40px 20px; text-align: center; color: var(--c-text-2); }
.consult-empty h2 { margin: 4px 0 0; font-size: var(--fs-18); color: var(--c-text); }
.consult-empty p { margin: 0; font-size: var(--fs-13); line-height: 1.7; }
@media (max-width: 767px) {
 .consult-confirm, .consult-draft-bar { align-items: stretch; flex-direction: column; }
 .consult-confirm__actions, .consult-draft-bar > div { justify-content: flex-end; }
 .consult-confirm__actions button, .consult-draft-bar button, .consult-failed button { min-height: 44px; }
}
/* ---- F8 会话历史管理 ---- */
.session-manage { display: grid; gap: 10px; }
.session-manage__tools { display: flex; align-items: center; gap: 10px; }
.session-search { flex: 1; min-width: 0; margin: 0; }
.session-search input { width: 100%; min-height: 40px; padding: 8px 10px; border: 1px solid var(--c-border); border-radius: 8px; background: var(--c-bg); color: var(--c-text); }
.session-manage__tools .ws-text-button { flex: none; min-height: 40px; }
.session-manage__error { margin: 0; }
.session-manage__copy .ws-text-button { min-height: 36px; padding: 0; }
.session-manage__note { margin: 2px 0 0; color: var(--c-text-3); font-size: var(--fs-12); }
.session-rows { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }
.session-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 10px; align-items: center; padding: 10px 0; border-top: 1px solid var(--c-border); }
.session-row.is-current { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.session-row__main { display: grid; gap: 2px; min-width: 0; padding: 6px 8px; border: 0; border-radius: 8px; background: none; color: var(--c-text); text-align: left; cursor: pointer; }
.session-row__main:hover { background: var(--c-surface-2); }
.session-row__main[aria-pressed="true"] { color: var(--c-primary); }
.session-row__main strong { overflow: hidden; font-size: var(--fs-14); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.session-row__main small { color: var(--c-text-3); font-size: var(--fs-12); }
.session-row__actions { display: flex; flex: none; gap: 4px; }
.session-row__action { min-height: 36px; padding: 0 8px; border: 1px solid var(--c-border); border-radius: var(--r-pill); background: var(--c-surface); color: var(--c-text-2); font-size: var(--fs-12); cursor: pointer; }
.session-row__action:hover { border-color: var(--c-primary-border); color: var(--c-primary); }
.session-row__action--danger:hover { border-color: var(--c-attention); color: var(--c-attention-strong); }
.session-row__rename, .session-row__confirm { grid-column: 1 / -1; display: grid; gap: 6px; padding: 6px 2px; }
.session-row__rename .ws-field { margin: 0; }
.session-row__hint, .session-row__confirm p { margin: 0; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.6; }
.session-row__confirm strong { color: var(--c-text); font-size: var(--fs-14); }
.session-row__edit-actions { display: flex; gap: 8px; }
.session-row__edit-actions .btn { min-height: 40px; }
/* ---- F9 能力面板 ---- */
.capability-panel { display: grid; gap: 10px; }
.capability-panel__intro { margin: 0; color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.65; }
.capability-panel__status { margin: 6px 0; color: var(--c-text-2); font-size: var(--fs-13); }
.capability-panel__meta { margin: 2px 0 0; color: var(--c-text-3); font-size: var(--fs-12); }
.capability-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.capability-item { display: grid; gap: 4px; padding: 10px 12px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-surface); }
.capability-item[data-state="unavailable"] { background: var(--c-surface-2); }
.capability-item__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.capability-item__head strong { color: var(--c-text); font-size: var(--fs-14); }
.capability-badge { flex: none; padding: 2px 8px; border: 1px solid var(--c-border-strong); border-radius: var(--r-pill); color: var(--c-text-2); font-size: var(--fs-12); }
.capability-badge[data-state="available"] { border-color: var(--c-primary-border); background: var(--c-primary-weak); color: var(--c-primary); }
.capability-item__reason, .capability-item__fallback { margin: 0; color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.6; }
.capability-item__fallback { color: var(--c-text-3); }
.consult-system-error { margin: 12px 24px 0; }
@media (max-width: 767px) {
 .consult-system-error { margin: 8px 12px 0; }
 .session-row { grid-template-columns: minmax(0, 1fr); }
 .session-row__actions { justify-content: flex-end; }
 .session-row__action, .session-row__edit-actions .btn, .session-search input, .session-manage__tools .ws-text-button { min-height: 44px; }
 /* The profile drawer remains available from the mobile navigation; keep the chat header focused on history and new chat. */
 .consult-header__actions :deep(.consult-profile-button) { display: none; }
}
</style>
