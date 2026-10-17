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
import { personalizedStudyYearEntries, STUDY_YEAR_OPTIONS, studyYearIntro, studyYearLabel } from '../lib/study-year'
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
import '../styles/conversation.css'
const route = useRoute()
const router = useRouter()
const turns = computed(() => demo.state.chatTurns)
const saved = backendDemo.getDraft(demo.state.currentSessionId)
const draft = ref(saved.text), attached = ref(saved.materials.map(m => ({ ...m })))
const selectedOption = ref<NonNullable<ChatTurn['optionRefs']>[number] | null>(null)
const flow = ref<HTMLElement | null>(null), input = ref<HTMLTextAreaElement | null>(null), fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false), thinking = ref(false), stopped = ref(false)
const { followTail, showLatest, bottom, onScroll } = useConversationScroll(flow)
const elapsed = ref(0), draggingFiles = ref(false)
let waitTimer: ReturnType<typeof setInterval> | undefined
let requestStarted = 0
const pending = ref<{ text: string; agent: string; note: string } | null>(null)
type OptionRef = NonNullable<ChatTurn['optionRefs']>[number]
type FailedSend = { request: MessageRequest; materials: { id: string; name: string }[]; error: string; at: string }
// 快捷选项覆盖草稿：先确认，替换后还能撤销（问题 4）。无草稿时行为完全不变。
const fillRequest = ref<{ text: string; option?: OptionRef; previousText: string; previousOption: OptionRef | null } | null>(null)
const replacedDraft = ref<{ text: string; option: OptionRef | null } | null>(null)
// 发送失败的消息与错误按会话持久化，刷新后仍然可见、可重新尝试（问题 15）。
const failedSend = ref<FailedSend | null>(null)
// 已点过按钮的确认不再重复出现（问题 2：可以 / 先不要）。
const confirmDismissed = ref<string[]>([])
const askPending = ref('')
// 生成中刷新/切页：本轮回复没有落库时，提示"上一轮中断"并给出重新发送入口。
const interrupted = ref<{ text: string; turnId: string } | null>(null)
const copiedTurn = ref('')
let copyTimer: ReturnType<typeof setTimeout> | undefined
const uploadError = ref('')
const requestError = ref(''), profileError = ref(''), guideSaving = ref('')
const profileOpen = ref(false), historyOpen = ref(false), profileLoading = ref(false)
const choosingTopic = ref(false)
// 恢复会话的短暂空态：避免刚刷新时先闪一句"新会话已就绪/咨询对话"。
const restoring = ref(false)
// 发送后极短时间内的"停止"点击要忽略：按钮在同一位置从"发送"变成"停止"，
// 双击发送的第二次点击会命中停止，把刚发出的问题撤回（实测 DEF-C1）。
const stopArmed = ref(true)
let stopArmTimer: ReturnType<typeof setTimeout> | undefined
// 「新开一条会话」模式：点主题时新建会话，而不是续接同主题的旧会话。
const freshTopic = ref(false)
const profileLoaded = ref(false), studyYearSaving = ref(''), studyYearError = ref(''), editingStudyYear = ref(false), savedStudyYear = ref('')
const theoryCards = ref<Record<string, TheoryCardView>>({}), theoryErrors = ref<Record<string, string>>({})
const theoryLoading = ref<Record<string, boolean>>({})
const sessions = computed(() => [...backendDemo.state.sessions]
 // 与后端会话列表口径一致：还没有任何消息的会话不进历史。
 // 否则 fresh 新建的空会话会先出现在列表里、刷新后又消失（DEF-C2）。
 .filter(session => (session.message_count ?? 0) > 0 || !!session.last_message)
 .sort((a,b) => ((b.last_message_at || b.last_active_at) || '').localeCompare((a.last_message_at || a.last_active_at) || '')))
const title = computed(() => showStudyYearQuestion.value ? '开始咨询' : choosingTopic.value ? '选择咨询主题' : backendDemo.currentSession.value?.task_name || '咨询对话')
const journey = [
 { key:'collect', label:'了解自己', short:'了解' },
 { key:'diagnose', label:'梳理判断', short:'判断' },
 { key:'decide', label:'比较选择', short:'选择' },
 { key:'act', label:'安排下一步', short:'行动' },
 { key:'review', label:'回顾调整', short:'回顾' },
] as const
const currentStage = computed(() => backendDemo.currentSession.value?.stage || systemData.snapshot?.stage || 'collect')
const profileFieldCount = computed(() => backendDemo.state.liveWorkspace?.profile_panel?.fields?.length ?? 0)
const profileGapCount = computed(() => backendDemo.state.liveWorkspace?.profile_panel?.gaps?.length ?? 0)
const latestHostId = computed(() => turns.value.at(-1)?.from === 'host' ? turns.value.at(-1)?.id : undefined)
const host = computed(() => systemData.snapshot?.badge.name || backendDemo.currentSession.value?.lead_agent_name || '咨询顾问')
const studyYearField = computed(() => backendDemo.state.liveWorkspace?.profile_panel?.fields?.find(field => field.key === 'study_year'))
const studyYear = computed(() => savedStudyYear.value || String(studyYearField.value?.value ?? ''))
const firstUse = computed(() => systemData.shellReady && !demo.state.currentSessionId && sessions.value.length === 0 && turns.value.length === 0)
const showStudyYearQuestion = computed(() => profileLoaded.value && (editingStudyYear.value || (!studyYear.value && firstUse.value)))
const starters = computed(() => personalizedStudyYearEntries(auth.state.bootstrap?.task_entries ?? [], studyYear.value))
let controller: AbortController | null = null, serial = 0, disposed = false
let failedRequest: MessageRequest | null = null
function remember() { backendDemo.saveDraft(demo.state.currentSessionId, draft.value, attached.value, flow.value?.scrollTop ?? null) }
function resizeInput() { if (input.value) { input.value.style.height = 'auto'; input.value.style.height = Math.min(input.value.scrollHeight, 144) + 'px' } }
function applyFill(text: string, option?: OptionRef) { draft.value = text; selectedOption.value = option ?? null; profileOpen.value = false; void nextTick(() => input.value?.focus()) }
function fill(text: string, option?: OptionRef) {
  if (thinking.value) return
  // 已有非空草稿时不能静默覆盖：先让用户确认，替换后仍可撤销。
  if (draft.value.trim() && draft.value.trim() !== text.trim()) {
    fillRequest.value = { text, option, previousText: draft.value, previousOption: selectedOption.value }
    replacedDraft.value = null
    profileOpen.value = false
    return
  }
  applyFill(text, option)
  // 点快捷选项只填入不发送：给一句明确反馈，避免"点了没反应"（深度测试观察项）。
  if (option) toast('已填入输入框，点发送即可。')
}
function confirmFillReplace() {
  const request = fillRequest.value
  if (!request) return
  fillRequest.value = null
  applyFill(request.text, request.option)
  replacedDraft.value = { text: request.previousText, option: request.previousOption }
  if (request.option) toast('已替换为所选内容，点发送即可。原草稿可点「撤销替换」恢复。')
}
function cancelFillReplace() { fillRequest.value = null }
function undoFillReplace() {
  const previous = replacedDraft.value
  if (!previous) return
  replacedDraft.value = null
  applyFill(previous.text, previous.option ?? undefined)
}
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
    failedRequest = data.request
    // 刷新后要让人知道上一轮没成功：把错误也放回对话提示里（含「重新尝试」）。
    requestError.value = data.error || '上一轮回复没有完成，可以重新尝试。'
  } catch { /* 坏数据直接忽略，不阻塞会话 */ }
}
function discardFailure() {
  clearFailure()
  failedRequest = null
  requestError.value = ''
}
// 登出/切换账号时清掉失败消息，避免下一次登录看到上一个账号的聊天内容。
function clearAllFailures() {
  failedSend.value = null
  failedRequest = null
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

/**
 * 统一把技术异常收敛成中文可操作提示（深度测试 DEF：解析异常/英文校验文案漏到对话里）。
 * 中文业务提示原样保留；英文或 JSON/解析类异常一律换成"稍后重试/改格式"的说法。
 */
const TECHNICAL_ERROR = /(Expected property name|Unexpected token|Unexpected end of JSON|is not valid JSON|JSON\.parse|SyntaxError|TypeError|ReferenceError|Traceback|ValidationError|String should|Input should|failed to fetch|NetworkError|Load failed)/i
function friendlyError(error: unknown) {
  const message = (error instanceof Error ? error.message : typeof error === 'string' ? error : '').trim()
  if (!message) return '这次操作没有完成，请稍后重试。'
  if (TECHNICAL_ERROR.test(message)) return '服务返回的内容无法识别，请稍后重试；如果正在上传材料，请改用 TXT/CSV 等文本格式。'
  if (!/[\u4e00-\u9fa5]/.test(message)) return '这次操作没有完成，请稍后重试。'
  return message
}
function errorCode(error: unknown) { return (error as { code?: number } | null)?.code }
/**
 * 材料预校验：能在前端拦住的就不要发请求。
 * 后端对 PDF/Word/Excel/图片/压缩包有专门的中文说明（infra/textfile.py），这里给同样的口径；
 * 其余非文本格式（.exe 等）后端会按文本解码成乱码，必须在前端拦下。
 */
const MAX_MATERIAL_BYTES = 2_000_000
const TEXT_SUFFIXES = new Set(['txt', 'text', 'csv', 'tsv', 'json', 'jsonl', 'md', 'markdown', 'log', 'xml', 'html', 'htm', 'yaml', 'yml', 'sql', 'ini', 'cfg', 'conf', 'properties', 'py', 'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'vue', 'java', 'c', 'h', 'cpp', 'hpp', 'cs', 'go', 'rs', 'rb', 'php', 'css', 'scss', 'less', 'srt', 'vtt', 'tex', 'bib', 'r'])
const BINARY_LABELS: Record<string, string> = { pdf: 'PDF', doc: 'Word 文档', docx: 'Word 文档', xls: 'Excel 工作簿', xlsx: 'Excel 工作簿', xlsm: 'Excel 工作簿', ppt: 'PPT', pptx: 'PPT', zip: '压缩包', rar: '压缩包', '7z': '压缩包', png: '图片', jpg: '图片', jpeg: '图片', gif: '图片', webp: '图片', bmp: '图片', heic: '图片', svg: '矢量图', exe: '可执行文件', dll: '程序文件', msi: '安装包', bin: '二进制文件', iso: '光盘镜像', mp3: '音频', wav: '音频', mp4: '视频', mov: '视频', avi: '视频', ttf: '字体', otf: '字体', woff: '字体', woff2: '字体', psd: '设计文件' }
function fileSuffix(name: string) { const index = name.lastIndexOf('.'); return index > 0 ? name.slice(index + 1).toLowerCase() : '' }
function materialRejection(file: File) {
  const suffix = fileSuffix(file.name)
  if (file.size > MAX_MATERIAL_BYTES) return `「${file.name}」超过 2MB 上限，请截取相关的那一段后再上传。`
  if (!file.size) return `「${file.name}」是空文件，请换一份有内容的文本。`
  if (!suffix || TEXT_SUFFIXES.has(suffix)) return ''
  const label = BINARY_LABELS[suffix]
  // 认不出的后缀不抢后端判断权：后端会按内容识别二进制并给出中文说明，别误伤可读文本。
  if (!label) return ''
  if (suffix === 'pdf') return '暂不支持直接读取 PDF：请把需要分析的文字复制为 TXT 后上传，或直接粘贴到输入框。'
  if (label === 'Word 文档' || label === 'Excel 工作簿' || label === 'PPT') return `暂不支持直接读取${label}：请在 Office 里另存为 CSV 或 TXT 后上传。`
  if (label === '图片' || label === '矢量图') return '图片里的文字读不出来：请把文字复制成文本，或直接用文字描述图片内容。'
  if (label === '压缩包') return '压缩包读不了：请先解压，再上传其中的 TXT、CSV 等文本文件。'
  return `不支持 .${suffix} 文件：对话里只能读取文字，请上传 TXT、CSV、MD 等文本文件。`
}
function friendlyMaterialError(error: unknown) {
  const message = error instanceof Error ? error.message : ''
  if (errorCode(error) === 413 || /413|entity too large|payload too large/i.test(message)) return '材料超过大小限制（最多 2MB），请截取相关的那一段后再上传。'
  if (errorCode(error) === 422) {
    // 后端对 PDF/Word/Excel 等有专门说明时保留原话；纯校验/技术文案统一成"格式不支持"。
    if (/暂不支持|请复制|请上传|TXT|CSV/i.test(message) && /[\u4e00-\u9fa5]/.test(message) && !TECHNICAL_ERROR.test(message)) return message
    return '这个文件格式不支持，请上传 TXT、CSV、MD 等文本文件。'
  }
  return friendlyError(error)
}
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
  const list = turns.value
  const last = list.at(-1)
  const previous = list.at(-2)
  const phantom = last?.from === 'host' && !last.text?.trim() && last.id.endsWith('-guide') && previous?.from === 'me' ? last : undefined
  // 先摘掉伪回合：不管有没有失败提示，上一轮的引导都不能显示在这条提问下面。
  if (phantom) {
    demo.setChatTurns(list.slice(0, -1), demo.state.currentSessionId)
    backendDemo.saveTurns(demo.state.currentSessionId, demo.state.chatTurns)
  }
  const question = phantom ? previous : last?.from === 'me' && !pending.value ? last : undefined
  if (!question) {
    if (last?.from === 'host') interrupted.value = null
    return
  }
  // 已有失败态时优先走"重新尝试"那条通道，避免两条重试入口同时出现。
  if (failedSend.value || requestError.value) { interrupted.value = null; return }
  if (interrupted.value?.turnId !== question.id) interrupted.value = { text: question.text, turnId: question.id }
}
function retryInterrupted() {
  const item = interrupted.value
  if (!item || thinking.value || systemData.busy) return
  interrupted.value = null
  void send(false, { text: item.text })
}
function dismissInterrupted() {
  interrupted.value = null
  void nextTick(() => input.value?.focus())
}
function safeLink(url?: string | null) { try { const u = new URL(url || ''); return ['http:', 'https:'].includes(u.protocol) ? u.href : undefined } catch { return undefined } }
function displayDate(raw: string) { const date = new Date(raw); return Number.isNaN(date.getTime()) ? raw : date.toLocaleString('zh-CN', {month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'}) }
function evidenceCount(t: ChatTurn) { return (t.theory_refs?.length ?? 0) + (t.intel_refs?.length ?? 0) }
function assetLabel(type: string) { return ({ report:'诊断报告', direction_plan:'方向方案', action_plan:'行动计划' } as Record<string,string>)[type] || '关联资料' }
function stageLabel(stage: string) { return ({ collect:'了解情况', diagnose:'梳理判断', decide:'比较选择', act:'安排下一步', review:'回顾调整' } as Record<string,string>)[stage] || '处理中' }
function journeyState(stage: string) { const current = journey.findIndex(item => item.key === currentStage.value); const index = journey.findIndex(item => item.key === stage); return index === current ? 'current' : index < current ? 'past' : 'future' }
async function theory(id: string) { if (theoryCards.value[id] || theoryLoading.value[id]) return; theoryErrors.value[id] = ''; theoryLoading.value[id] = true; try { theoryCards.value[id] = await backendClient.theory(id) } catch (e) { theoryErrors.value[id] = friendlyError(e) } finally { theoryLoading.value[id] = false } }
async function refreshProfile() { profileLoading.value = true; profileError.value = ''; try { const result = await backendClient.workspace(); if (!disposed) { backendDemo.setWorkspace(result); const stored = result.profile_panel?.fields?.find(field => field.key === 'study_year'); if (stored) savedStudyYear.value = String(stored.value ?? '') } } catch (e) { if (!disposed) profileError.value = friendlyError(e) } finally { profileLoading.value = false; profileLoaded.value = true } }
function clearTopicQuery() { if (route.query.new === undefined) return; const query = { ...route.query }; delete query.new; void router.replace({ path:route.path, query }) }
async function refreshSessionsOnFocus() {
 if (document.visibilityState !== 'visible') return
 try {
  const result = await backendClient.sessions()
  if (!disposed) backendDemo.setSessions(result.sessions ?? [], demo.state.currentSessionId)
 } catch { /* Keep the current conversation usable if the refresh fails. */ }
}
function chooseTopic() { if (thinking.value || systemData.busy) return; freshTopic.value = false; choosingTopic.value = true; historyOpen.value = false; profileOpen.value = false; requestError.value = ''; void nextTick(() => { if (flow.value) flow.value.scrollTop = 0 }) }
function closeTopic() { choosingTopic.value = false; clearTopicQuery(); void bottom(true) }
async function resume(id: string) { if (thinking.value) return; try { await openSession(id); choosingTopic.value = false; clearTopicQuery(); historyOpen.value = false; pending.value = null; requestError.value = ''; syncInterruptedNotice(); await bottom(true) } catch (e) { requestError.value = friendlyError(e) } }
async function create(code: string, fresh = false) { if (thinking.value || systemData.busy) return; try { await newSession(code, fresh); choosingTopic.value = false; clearTopicQuery(); pending.value = null; requestError.value = ''; await loadShell(); input.value?.focus() } catch (e) { requestError.value = friendlyError(e) } }
async function start(code: string, label: string) {
 const fresh = freshTopic.value
 await create(code, fresh)
 if (!requestError.value) {
  freshTopic.value = false
  // 新会话不预填主题句：让用户自己说第一句，历史里也不会多一条"只有一句模板"的记录。
  if (fresh || code === 'free_chat') { void nextTick(() => input.value?.focus()) } else { fill(label) }
 }
}
async function saveStudyYear(label: string) {
 if (studyYearSaving.value) return
 studyYearSaving.value = label; studyYearError.value = ''
 try {
  const updated = await backendClient.correct('study_year', label, studyYearField.value?.updated_at ?? null)
  savedStudyYear.value = String(updated.value ?? label)
  editingStudyYear.value = false; choosingTopic.value = true
  await refreshProfile()
 } catch (e) {
  studyYearError.value = friendlyError(e)
  if ((e as { code?: number }).code === 1003) await refreshProfile()
 } finally { studyYearSaving.value = '' }
}
async function upload(event: Event) { await uploadFiles(Array.from((event.target as HTMLInputElement).files ?? [])) }
async function uploadFiles(files: File[]) {
 if (!files.length || uploading.value || thinking.value) return
 // 先做格式与大小预校验：能当场说清楚的不发请求（深度测试 DEF-DS-03/04）。
 const problems = files.map(file => materialRejection(file)).filter(Boolean)
 const acceptable = files.filter(file => !materialRejection(file))
 uploadError.value = problems.join(' ')
 if (!acceptable.length) { if (fileInput.value) fileInput.value.value = ''; return }
 uploading.value = true
 const sessionId = demo.state.currentSessionId
 try { for (const file of acceptable) { const material = await backendClient.material(file); if (disposed || sessionId !== demo.state.currentSessionId) return; if (!attached.value.some(item => item.id === material.material_id)) attached.value.push({ id: material.material_id, name: material.name || file.name }) } }
 catch (e) { if (!disposed && sessionId === demo.state.currentSessionId) uploadError.value = friendlyMaterialError(e) }
 finally { uploading.value = false; if (fileInput.value) fileInput.value.value = '' }
}
function dragOver(event: DragEvent) {
 if (!event.dataTransfer?.types.includes('Files')) return
 event.preventDefault(); event.dataTransfer.dropEffect = uploading.value || thinking.value ? 'none' : 'copy'; draggingFiles.value = !uploading.value && !thinking.value
}
function dropFiles(event: DragEvent) {
 if (!event.dataTransfer?.types.includes('Files')) return
 event.preventDefault(); draggingFiles.value = false; void uploadFiles(Array.from(event.dataTransfer.files))
}
function pasteFiles(event: ClipboardEvent) {
 const files = Array.from(event.clipboardData?.files ?? [])
 if (files.length && !event.clipboardData?.getData('text/plain')) { event.preventDefault(); void uploadFiles(files) }
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
function stop() { if (!stopArmed.value) return; stopped.value = true; controller?.abort() }
async function send(retry = false, choice?: { text: string; option?: OptionRef }) {
 if (thinking.value || uploading.value || systemData.busy) return
 // 刷新后 failedRequest 会因为本轮普通消息成功而被清空，失败态里仍保存着原始请求。
 const retried = retry ? (failedRequest ?? failedSend.value?.request ?? null) : null
 const text = retry ? retried?.message : choice ? choice.text : draft.value.trim() || (attached.value.length ? '请结合我上传的材料提供建议。' : '')
 if (!text) return
 const outgoingMaterials = retry ? (failedSend.value?.materials ?? attached.value.map(m => ({ ...m }))) : choice ? [] : attached.value.map(m => ({ ...m }))
 const outgoingOption = choice ? choice.option : selectedOption.value, outgoingDraft = draft.value
 if (!demo.state.currentSessionId) { const code = starters.value[0]?.code; if (!code) { requestError.value = '当前没有可用的咨询入口。'; return }; await create(code); if (!demo.state.currentSessionId || requestError.value) return }
 const sessionId = demo.state.currentSessionId
 const request: MessageRequest = retried ?? { task_id:sessionId, message:text, client_msg_id:crypto.randomUUID(), material_ids:outgoingMaterials.map(m => m.id), ...(outgoingOption ? { option_id:outgoingOption.option_id, option_value:outgoingOption.value } : {}) }
 const run = ++serial
 failedRequest = request; requestError.value = ''; stopped.value = false
 controller = new AbortController(); thinking.value = true
 // 发送后 700ms 内忽略"停止"点击，避免双击发送把刚发出的消息撤回。
 stopArmed.value = false; clearTimeout(stopArmTimer)
 stopArmTimer = setTimeout(() => { stopArmed.value = true }, 700)
 pending.value = { text:'', agent:host.value, note:'正在分析你的问题' }
 if (!retry) {
  demo.addChatTurn({ id:`${request.client_msg_id}-user`, from:'me', text, materials:outgoingMaterials })
  if (!choice) { if (draft.value === outgoingDraft) draft.value = ''; attached.value = attached.value.filter(m => !outgoingMaterials.some(s => s.id === m.id)); selectedOption.value = null; remember() }
 }
 followTail.value = true; void bottom(true)
 try {
  const result = await streamBackend<ConversationTurnView>('messageStream', { body:request, signal:controller.signal }, frame => {
   if (run !== serial || demo.state.currentSessionId !== sessionId || !pending.value) return
   if (frame.text !== undefined) pending.value.text = frame.text
   if (frame.agent) pending.value.agent = frame.agent
   if (frame.note) pending.value.note = frame.note
   void bottom()
  })
  if (run !== serial || demo.state.currentSessionId !== sessionId) return
  // 重新尝试成功时，失败的这条用户消息要正式进入对话流（之前只存在失败态里）。
  // 刷新恢复的会话里服务端消息 id 不是 client_msg_id，按文本再查一次，避免同一句出现两次。
  if (retry && !turns.value.some(turn => turn.id === `${request.client_msg_id}-user` || (turn.from === 'me' && turn.text === text))) {
   demo.addChatTurn({ id:`${request.client_msg_id}-user`, from:'me', text, materials:outgoingMaterials })
  }
  demo.setChatTurns([...turns.value, ...replyTurns(result, request.client_msg_id || crypto.randomUUID())], sessionId)
  systemData.snapshot = result; pending.value = null; failedRequest = null
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
    pending.value = null
    if (partial) demo.addChatTurn({
      id: `${request.client_msg_id}-partial`,
      from: 'host',
      speaker: host.value,
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
 finally { if (run === serial) { thinking.value = false; controller = null } }
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
watch(thinking, busy => {
 demo.setChatBusy(busy); clearInterval(waitTimer)
 if (busy) { elapsed.value = 0; requestStarted = Date.now(); waitTimer = setInterval(() => { elapsed.value = Math.floor((Date.now() - requestStarted) / 1000) }, 1000) }
}, { flush:'sync' })
watch(() => navigation.width.value, () => { void nextTick(resizeInput) })
watch([draft, attached], () => { remember(); void nextTick(resizeInput) }, { deep:true })
watch(() => demo.state.currentSessionId, (_id, previous) => {
 backendDemo.saveDraft(previous, draft.value, attached.value, flow.value?.scrollTop ?? null)
 const data = backendDemo.getDraft(demo.state.currentSessionId); draft.value = data.text; attached.value = data.materials.map(m => ({ ...m }))
 selectedOption.value = null; failedRequest = null; pending.value = null; requestError.value = ''; uploadError.value = ''; stopped.value = false; choosingTopic.value = false; followTail.value = true
 fillRequest.value = null; replacedDraft.value = null; confirmDismissed.value = []; interrupted.value = null
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
watch([turns, thinking, () => systemData.busy, () => demo.state.currentSessionId], () => syncInterruptedNotice(), { flush: 'post' })
function applyConsultationContext() {
 // 报告页等入口用 ?ask= 直接发起一句咨询：自动填入并发送，发送后清掉参数。
 const ask = typeof route.query.ask === 'string' ? route.query.ask.trim() : ''
 if (ask) {
  const query = { ...route.query }; delete query.ask
  void router.replace({ path: route.path, query })
  askPending.value = ask
  void runAsk()
  return
 }
 if (typeof route.query.new === 'string') { chooseTopic(); return }
 const query = route.query
 const text = typeof query.question === 'string' ? query.question
  : typeof query.topic === 'string' ? '我想讨论：' + query.topic
  : typeof query.label === 'string' ? '我想补充' + query.label + '：' : ''
 if (!text) return
 // Preserve an unfinished draft when arriving from another page.
 applyFill(draft.value.trim() && draft.value.trim() !== text ? draft.value.trim() + '\n\n' + text : text)
 remember()
 const rest = { ...query }; for (const key of ['question', 'topic', 'label', 'gap']) delete rest[key]
 void router.replace({ path: route.path, query: rest })
}
watch(() => route.query, applyConsultationContext)
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
}
watch([() => systemData.shellReady, () => systemData.busy, () => showStudyYearQuestion.value, () => profileLoaded.value, choosingTopic, thinking, uploading], () => void runAsk())
watch(showStudyYearQuestion, open => {
 if (open) void nextTick(() => { if (flow.value) flow.value.scrollTop = 0 })
})
onMounted(() => {
 window.addEventListener('focus', refreshSessionsOnFocus)
 window.addEventListener('zhiyin:session-cleared', clearAllFailures)
 document.addEventListener('visibilitychange', refreshSessionsOnFocus)
 void nextTick(resizeInput)
 if (demo.state.currentSessionId && !systemData.busy) {
  restoring.value = true
  void resume(demo.state.currentSessionId).finally(() => { restoring.value = false })
 }
 loadFailure(demo.state.currentSessionId)
 void refreshProfile()
 applyConsultationContext()
 void bottom(true)
})
onUnmounted(() => { disposed = true; window.removeEventListener('focus', refreshSessionsOnFocus); window.removeEventListener('zhiyin:session-cleared', clearAllFailures); document.removeEventListener('visibilitychange', refreshSessionsOnFocus); clearInterval(waitTimer); clearTimeout(copyTimer); remember(); serial++; controller?.abort(); demo.setChatBusy(false) })
</script>
<template>
<section class="consultation-page" aria-label="咨询对话空间">
 <div class="consult-main">
  <header class="consult-header">
   <div class="consult-header__top"><div class="consult-heading"><h1 :title="title">{{ title }}</h1><p v-if="!choosingTopic && demo.state.currentSessionId"><span>当前阶段：{{ stageLabel(currentStage) }}</span><span v-if="profileFieldCount">已记录 {{ profileFieldCount }} 项信息</span><span v-if="profileGapCount">{{ profileGapCount }} 项待补</span></p></div><div class="consult-header__actions">
    <AnchoredCard v-model="historyOpen" class="consult-icon consult-history-button" title="历史会话" side="bottom" align="end"><template #trigger><UiIcon name="chat" :size="18" /></template><div class="consult-session-list"><button :disabled="!turns.length" @click="copy(turns.map(t => (t.from === 'me' ? '我' : t.speaker || '系统') + '：' + t.text).join('\n\n'))">复制当前会话记录</button><button v-for="session in sessions" :key="session.task_id" :disabled="thinking || systemData.busy" :aria-pressed="session.task_id === demo.state.currentSessionId" @click="resume(session.task_id)"><strong>{{ session.task_name }}</strong><span class="consult-session-preview">{{ session.last_message || '还没有消息' }}</span><small><template v-if="session.message_count">{{ session.message_count }} 条 · </template>{{ (session.last_message_at || session.last_active_at) ? new Date(session.last_message_at || session.last_active_at || '').toLocaleString('zh-CN', { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '' }}</small></button><p v-if="!sessions.length">还没有历史会话。开始咨询后会自动保存在这里。</p></div></AnchoredCard>
    <button class="consult-icon consult-new-button" aria-label="选择咨询主题" :disabled="thinking || systemData.busy" @click="chooseTopic"><UiIcon name="plus" :size="19" /></button>
    <AnchoredCard v-model="profileOpen" class="consult-icon" title="个人画像" side="bottom" align="end"><template #trigger><UiIcon name="profile" :size="19" /><span class="consult-header__label">个人画像</span></template><ConversationProfile embedded :loading="profileLoading" :error="profileError" @close="profileOpen = false" @refresh="refreshProfile" @supplement="fill" /></AnchoredCard>
   </div></div>
   <ol v-if="!choosingTopic && demo.state.currentSessionId" class="consult-journey" aria-label="咨询轨迹"><li v-for="item in journey" :key="item.key" :data-state="journeyState(item.key)" :aria-current="journeyState(item.key) === 'current' ? 'step' : undefined"><i /><span><em class="consult-journey__full">{{ item.label }}</em><em class="consult-journey__short">{{ item.short }}</em></span></li></ol>
  </header>
  <div ref="flow" v-scroll-fade class="consult-flow" tabindex="0" aria-label="对话记录" @scroll.passive="onScroll">
   <div v-if="systemData.busy || restoring" class="consult-loading" role="status">正在读取会话…</div>
   <div v-else-if="showStudyYearQuestion || choosingTopic || (!turns.length && !pending && !showFailedSend && !demo.state.currentSessionId)" class="consult-intro" :class="{'consult-intro--onboarding':showStudyYearQuestion}">
    <AgentAvatar agent="career" :size="64" />
    <template v-if="showStudyYearQuestion">
     <p class="consult-intro__eyebrow">开始前确认一项信息</p>
     <h2>为了更准确地安排咨询重点，先确认一下：你目前处于哪个学习阶段？</h2>
     <p>只用于调整默认咨询方向，不会限制你可以提出的问题。</p>
     <div class="consult-year-options" role="group" aria-label="选择当前学习阶段"><button v-for="option in STUDY_YEAR_OPTIONS" :key="option.code" :disabled="!!studyYearSaving" :aria-pressed="studyYearLabel(studyYear) === option.label" @click="saveStudyYear(option.label)"><span>{{ option.label }}</span><small v-if="studyYearSaving === option.label">正在保存…</small><UiIcon v-else name="arrow" :size="16" /></button></div>
     <p v-if="studyYearError" class="consult-error" role="alert">{{ studyYearError }}</p>
     <button v-if="editingStudyYear" class="consult-resume" @click="editingStudyYear=false">取消修改</button>
    </template>
    <template v-else>
     <button v-if="studyYear" class="consult-year-summary" @click="editingStudyYear=true"><span>当前阶段：{{ studyYearLabel(studyYear) }}</span><small>修改</small></button>
     <h2>{{ studyYear ? `已按${studyYearLabel(studyYear)}安排咨询重点` : '从你现在关心的事开始' }}</h2><p>{{ studyYear ? studyYearIntro(studyYear) : '先选一个主题。进入后仍可自由补充，不会覆盖已有会话。' }}</p>
     <button v-if="demo.state.currentSessionId" type="button" class="consult-fresh" :aria-pressed="freshTopic" @click="freshTopic = !freshTopic"><UiIcon :name="freshTopic ? 'check' : 'plus'" :size="16" />{{ freshTopic ? '将新开一条会话（旧会话留在历史里）' : '想从头开始？新开一条会话' }}</button>
     <div class="consult-topics"><button v-for="(entry,i) in starters" :key="entry.code" :class="{'consult-topic--free':entry.code==='free_chat'}" @click="start(entry.code, entry.label)"><UiIcon :name="['profile','directions','action','review'][i % 4]" :size="21" /><span>{{ entry.label }}</span><UiIcon name="arrow" :size="17" /></button></div>
     <button v-if="choosingTopic && demo.state.currentSessionId" class="consult-resume" @click="closeTopic">返回当前会话</button>
     <button v-else-if="sessions.length && sessions[0].task_id !== demo.state.currentSessionId" class="consult-resume" @click="resume(sessions[0].task_id)">继续最近的咨询：{{ sessions[0].task_name }}</button>
    </template>
   </div>
   <div v-else class="consult-messages" :aria-busy="thinking">
    <div v-if="!turns.length && !pending && demo.state.currentSessionId" class="consult-empty" role="status">
     <AgentAvatar agent="career" :size="52" />
     <h2>新会话已就绪</h2>
     <p>直接在下面说说你现在最想解决的问题；想换个主题就点右上角「＋」。</p>
    </div>
    <article v-for="turn in turns" :key="turn.id" class="consult-turn" :class="['consult-turn--' + turn.from, { 'consult-turn--latest': turn.id === latestHostId }]">
     <div v-if="turn.from === 'me'" class="consult-user"><p>{{ turn.text }}</p><small v-for="m in turn.materials" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}</small></div>
     <p v-else-if="turn.from === 'system'" class="consult-system">{{ cleanConsultantText(turn.text) }}</p>
     <template v-else><AgentAvatar :agent="agentKeyOf(turn.speaker)" :size="38" /><div class="consult-answer">
      <span class="consult-speaker"><b>{{ consultantLabel(turn.speaker || '咨询顾问') }}</b><small v-if="turn.id === latestHostId">当前建议</small></span>
      <div v-if="turn.text || turn.guideText" class="consult-answer-copy">
       <ReadableText v-if="turn.text" :text="cleanConsultantText(turn.text)" class="consult-prose" />
       <ReadableText v-if="turn.guideText" :text="cleanConsultantText(turn.guideText)" class="consult-guide" />
      </div>
      <div class="consult-references">
        <DetailPopover v-if="evidenceCount(turn)" title="本轮参考资料" side="top" class="consult-evidence" @update:model-value="open => open && turn.theory_refs?.forEach(r => theory(r.theory_id))"><template #trigger><UiIcon name="shield" :size="15" /><span>查看线索</span><small>{{ evidenceCount(turn) }}</small></template>
         <p class="ws-muted">以下为本轮检索资料与参考方法，不代表每项资料均能直接支持当前结论；是否适用请结合回复中的限制说明核对。</p><h3 v-if="turn.intel_refs?.length">检索资料</h3><div v-for="r in turn.intel_refs" :key="r.id" class="consult-source"><strong>{{ r.title || '资料来源' }}</strong><p v-if="r.source_name">{{ r.source_name }}</p><a v-if="safeLink(r.source_url)" :href="safeLink(r.source_url)" target="_blank" rel="noopener noreferrer">查看原始资料</a></div>
         <h3 v-if="turn.theory_refs?.length">参考方法</h3><div v-for="r in turn.theory_refs" :key="r.theory_id" class="consult-source"><strong>{{ r.name }}</strong><p v-if="theoryCards[r.theory_id]">{{ theoryCards[r.theory_id].summary || '暂无详细方法说明。' }}</p><p v-else-if="theoryLoading[r.theory_id]" role="status">正在读取方法说明…</p><button v-else @click="theory(r.theory_id)">重新读取方法说明</button><p v-if="theoryErrors[r.theory_id]" role="alert">{{ theoryErrors[r.theory_id] }}</p></div>
        </DetailPopover>
      <DetailPopover v-if="turn.pipelineCards?.length || turn.changedAssets?.length" title="本轮处理记录" side="top" class="consult-evidence"><template #trigger><UiIcon name="check" :size="15" /><span>处理记录</span></template>
        <div v-if="turn.pipelineCards?.length || turn.changedAssets?.length" class="consult-turn-status" aria-label="本轮处理结果"><span v-for="card in turn.pipelineCards" :key="card.stage" :data-status="card.status"><UiIcon :name="card.status === 'done' ? 'check' : 'review'" :size="15" />{{ stageLabel(card.stage) }}</span><span v-for="asset in turn.changedAssets" :key="asset.asset_id"><UiIcon name="report" :size="15" />已更新{{ assetLabel(asset.asset_type) }} · 第 {{ asset.version }} 版</span></div>
      </DetailPopover>
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
    <article v-if="pending" class="consult-turn consult-turn--host consult-pending" aria-label="当前回复"><AgentAvatar :agent="agentKeyOf(pending.agent)" :size="38" :state="thinking ? pending.text ? 'speaking' : 'thinking' : 'idle'" /><div class="consult-answer"><span class="consult-speaker">{{ consultantLabel(pending.agent) }}</span><ReadableText v-if="pending.text" :text="cleanConsultantText(pending.text)" class="consult-prose" /><div v-else-if="thinking" class="consult-wait" role="status"><span class="consult-wait-orbit" aria-hidden="true"><i /><i /><i /></span><div><p>{{ pending.note }}</p><small>正在接收回复<span v-if="elapsed >= 3"> · {{ elapsed }} 秒</span></small></div></div><span v-if="thinking && pending.text" class="consult-cursor" aria-label="正在回复" /><small v-if="!thinking">{{ stopped ? '接收已停止' : '回复未完成' }}</small></div></article>
    <div v-if="uploadError" class="consult-error" role="alert"><p>{{ uploadError }}</p><button :disabled="uploading || thinking" @click="fileInput?.click()">重新选择材料</button><button @click="uploadError = ''">关闭上传提示</button></div>
    <div v-if="requestError && !showFailedSend" class="consult-error" role="alert"><p>{{ requestError }}</p><button v-if="failedRequest && !stopped" @click="send(true)">重新尝试</button><button :disabled="thinking" @click="resume(demo.state.currentSessionId)">重新读取会话</button></div>
   </div>
  </div>
  <footer v-if="!choosingTopic && !showStudyYearQuestion" class="consult-compose-area">
   <button v-if="showLatest" class="consult-latest" @click="followTail = true; bottom(true)"><UiIcon name="down" :size="15" />回到最新消息</button>
   <div v-if="pendingConfirm" class="consult-confirm" role="status" aria-label="待确认事项">
    <div class="consult-confirm__copy"><strong>有一条确认还没回复</strong><p>可以直接点选；继续输入其他内容也不会自动取消它。</p></div>
    <div class="consult-confirm__actions">
     <button type="button" :disabled="thinking || systemData.busy" @click="chooseConfirm(pendingConfirm.yes)">{{ cleanConsultantText(pendingConfirm.yes.label) }}</button>
     <button type="button" :disabled="thinking || systemData.busy" @click="chooseConfirm(pendingConfirm.no)">{{ cleanConsultantText(pendingConfirm.no.label) }}</button>
    </div>
   </div>
   <div v-if="fillRequest" class="consult-draft-bar" role="alert">
    <p>输入框里已有草稿，要替换成「{{ cleanConsultantText(fillRequest.text) }}」吗？</p>
    <div><button type="button" @click="confirmFillReplace">替换</button><button type="button" @click="cancelFillReplace">保留草稿</button></div>
   </div>
   <div v-else-if="replacedDraft" class="consult-draft-bar consult-draft-bar--undo" role="status">
    <p>已替换输入内容，原草稿可以恢复。</p>
    <div><button type="button" @click="undoFillReplace">撤销替换</button><button type="button" @click="replacedDraft = null">知道了</button></div>
   </div>
   <p v-if="requestError && !turns.length && !pending && !showFailedSend" role="alert" class="consult-error">{{ requestError }}</p>
   <form class="consult-composer" :class="{ 'consult-composer--drop': draggingFiles }" @dragover="dragOver" @dragleave="!($event.currentTarget as HTMLElement).contains($event.relatedTarget as Node) && (draggingFiles = false)" @drop="dropFiles" @submit.prevent="send()">
    <div v-if="draggingFiles" class="consult-drop-label" aria-hidden="true"><UiIcon name="attachment" :size="20" />松开以添加材料</div>
    <div v-if="attached.length" class="consult-attachments"><span v-for="(m,i) in attached" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}<button type="button" :aria-label="'移除' + m.name" @click="attached.splice(i,1)"><UiIcon name="close" :size="14" /></button></span></div>
    <textarea ref="input" v-model="draft" rows="1" aria-label="输入咨询内容" placeholder="说说你的想法，或添加材料…" @input="selectedOption?.label !== draft && (selectedOption = null)" @keydown="keydown" @paste="pasteFiles" />
    <div class="consult-compose-tools"><input ref="fileInput" type="file" hidden multiple @change="upload" /><button type="button" class="consult-attach" :disabled="uploading || thinking" @click="fileInput?.click()"><UiIcon name="plus" :size="18" />{{ uploading ? '上传中…' : '添加材料' }}</button><span class="consult-send-hint">{{ thinking ? '回复生成中，可先准备下一条消息' : 'Enter 发送 · Shift + Enter 换行' }}</span><button v-if="thinking" type="button" class="consult-send consult-stop" :disabled="!stopArmed" aria-label="停止接收" @click="stop"><span /></button><button v-else type="submit" class="consult-send" aria-label="发送消息" :disabled="(!draft.trim() && !attached.length) || uploading || systemData.busy"><UiIcon name="arrow" :size="20" /></button></div>
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
.consult-fresh { display: flex; align-items: center; gap: 6px; margin: 2px auto 12px; padding: 8px 14px; border: 1px dashed var(--c-border-strong); border-radius: var(--r-pill); background: var(--c-surface); color: var(--c-text-2); font-size: var(--fs-12); cursor: pointer; }
.consult-fresh[aria-pressed="true"] { border-color: var(--c-primary); color: var(--c-primary); background: var(--c-primary-weak); }
.consult-empty { display: grid; justify-items: center; gap: 6px; padding: 40px 20px; text-align: center; color: var(--c-text-2); }
.consult-empty h2 { margin: 4px 0 0; font-size: var(--fs-18); color: var(--c-text); }
.consult-empty p { margin: 0; font-size: var(--fs-13); line-height: 1.7; }
@media (max-width: 767px) {
 .consult-confirm, .consult-draft-bar { align-items: stretch; flex-direction: column; }
 .consult-confirm__actions, .consult-draft-bar > div { justify-content: flex-end; }
 .consult-confirm__actions button, .consult-draft-bar button, .consult-failed button { min-height: 44px; }
}
</style>
