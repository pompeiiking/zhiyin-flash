<script setup lang="ts">
import RenderableBlock from '../components/RenderableBlock.vue'
import DetailPopover from '../components/DetailPopover.vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { demo } from '../store'
import { PROFILE_FIELDS } from '../data/student'
import { useStreaming } from '../lib/motion'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import type { ChatTurn } from '../data/types'
import { backendDemo } from '../lib/backend-demo'
import {auth} from '../lib/auth'
import { backendClient } from '../api/backend-client'
import { newSession as createSession, openSession, mapMessage, loadShell, systemData } from '../lib/system-data'
import { toast } from '../store'
import type { GuideOptionView, MessageRequest } from '../api/backend-types'
import { consultantLabel, agentKeyOf } from '../lib/consultant'
import { navigation } from '../lib/layout'
import { agentOf } from '../lib/agents'
import AgentAvatar from '../components/AgentAvatar.vue'
import EvidenceList from '../components/EvidenceList.vue'
import ReadableText from '../components/ReadableText.vue'
import AssetNotice from '../components/AssetNotice.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StatTile from '../components/StatTile.vue'
const route = useRoute()
const turns = computed(() => demo.state.chatTurns)
const restoredDraft = backendDemo.getDraft(demo.state.currentSessionId)
const draft = ref(restoredDraft.text)
const thinking = ref(false)
const flow = ref<HTMLElement | null>(null)
const input = ref<HTMLTextAreaElement | null>(null)
const panel = ref<'profile' | 'outcomes' | 'sessions' | null>(null)
const attachmentInput = ref<HTMLInputElement | null>(null)
const attachmentError = ref('')
const attached = ref<{ id: string; name: string }[]>(restoredDraft.materials.map(m => ({ ...m })))
const theoryOpen = ref(false)
const activeTheory = ref<import('../api/backend-types').TheoryCardView|null>(null)
const theoryError=ref('')
async function readTheory(id:string){try{activeTheory.value=await backendClient.theory(id)}catch(e){theoryError.value=(e as Error).message}}
const followTail = ref(true)
const announcement = ref('')
/** 「资料使用说明」展开态：解释挂在输入区旁边，不占常驻空间，也不与主行动争位置 */

/**
 * 桌面（宽导航模式）才给右侧 rail 让出一列。
 * 用导航模式而不是纯 width 媒体查询：页面宽度与"壳层是不是窄导航"是一致的，
 * 两者用同一个判据，才不会出现"壳层已经收成窄导航、页面还留着一列 rail"的错位。
 */
const hasRail = computed(() => navigation.mode.value === 'desktop' && navigation.width.value >= 1280)

/* =============================================================================
 * 回答 = 分块，不是一段话
 * -----------------------------------------------------------------------------
 * 【判定规则 · 先看内容类型，再选块形态】
 *   1. 主张（这个判断是什么）        → 结论块：一句话、大字、永远在最前。
 *      取不到结构就不硬凑：无法拆句时整段落在结论块里，不在正文外再造一层包装。
 *   2. 支撑（凭什么这么说）——同级材料，做成**可切换的卡片组**：
 *        · 依据块：编号证据 + 来源（citations 有几条就是几条）
 *        · 数据块：后端契约里的可视件形状 renderables(kind=bars_chart)
 *        · 方法块：演示里不投递 renderables 时的降级支撑（同样带来源）
 *      三者都是"支撑材料"，地位相同 → 同组可切换；**只有一张时不显示切换器**。
 *   3. 展开说明（结论装不下的正文）  → 说明块：不抢结论的视线，跟在后面。
 *   4. 要你做的事                    → 行动块（沿用 dialogue-action 的形态与交互）。
 *   5. 你还能怎么接                  → 后续问题块（沿用 options）。
 * 一句话：依据多就出依据块，有数据就出数据块，有任务就出行动块 —— **不把所有回答套同一种卡**。
 * ========================================================================== */

/** 一条编号依据 */
type EvidenceItem = { body: string; source: string }
/** 后端契约 renderables 里唯一注册的 kind：bars_chart，payload 形如 {unit, points:[{label,value}]} */
type BarsChart = { unit: string; points: { label: string; value: number }[] }
/** 同级支撑材料：同一时刻只有一张站在前面 */
type PeerCard =
  | { id: string; kind: 'evidence'; label: string; items: EvidenceItem[] }
  | { id: string; kind: 'data'; label: string; chart: BarsChart; demo: boolean }
  | { id: string; kind: 'method'; label: string; name: string; summary: string; source: string }
/** 一条回答的块序列；`active` 是其中"当前站在前面"的那张支撑卡 */
type TurnBlocks = {
  lead: string
  detail: string
  peers: PeerCard[]
  options: string[]
  optionRefs: { option_id: string; label: string; value: unknown }[]
  hasTask: boolean
  active: string
}

/**
 * 依据里的"来源"。
 *
 * 演示数据把来源写在括号尾巴上（「岗位要求：…（来源：招聘信息抽样）」）。
 * 把它拆出来单独站一行 —— 来源和结论一样是信息，不该混在正文里靠用户自己找。
 */
function splitSource(citation: string): EvidenceItem {
  const text = citation.trim()
  const parenthesized = text.match(/^(.*?)[（(]\s*(?:来源|出处|依据)\s*[:：]\s*([^）)]+)[）)]\s*$/)
  if (parenthesized) return { body: parenthesized[1].trim(), source: parenthesized[2].trim() }
  const tail = text.match(/^(.*?)[（(]([^）)]{1,18})[）)]\s*$/)
  if (tail) return { body: tail[1].trim(), source: tail[2].trim() }
  return { body: text, source: '' }
}

/** 结论取"第一句话"：第一个句末标点，限 44 字，避免把整句长段落又搬进大字里 */
function leadOf(text: string): string {
  const body = text.trim()
  const stop = body.search(/[。！？!?]/)
  if (stop >= 6 && stop < 44) return body.slice(0, stop + 1)
  if (body.length <= 44) return body
  const soft = body.search(/[，,；;]/)
  if (soft >= 8 && soft <= 30) return body.slice(0, soft + 1)
  return body.slice(0, 44)
}

/**
 * 数据块（演示）。
 *
 * 真实链路上 renderables 由后端投递；当前 demo 数据不投，所以这里按契约的
 * bars_chart 形状本地造一份，并在卡片上标注"演示数据"——不伪装成真实统计。
 * 只在两条真正谈"匹配 / 差距"的回答上挂，避免变成每句话都配一张图。
 */
function chartFor(_text: string, _speaker?: string): BarsChart | null { return null }

const optionRefsOf = (turn: ChatTurn): { option_id: string; label: string; value: unknown }[] =>
  turn.optionRefs?.map(item => ({ ...item })) ?? []

/** 一条回答 → 块序列。纯函数，模板直接调（不做缓存：块是这条消息的函数，消息变了块就该重算） */
function turnBlocks(turn: ChatTurn): TurnBlocks {
  const empty: TurnBlocks = { lead: '', detail: '', peers: [], options: [], optionRefs: [], hasTask: false, active: '' }
  if (turn.from !== 'host') return empty
  const text = turn.text.trim()
  const lead = leadOf(text)
  const detail = text.slice(lead.length).replace(/^…/, '').trim()
  const peers: PeerCard[] = []
  if (turn.citations?.length) {
    peers.push({ id: turn.id + '-evidence', kind: 'evidence', label: '支持依据', items: turn.citations.map(splitSource) })
  }
  const chart = chartFor(text, turn.speaker)
  if (chart) peers.push({ id: turn.id + '-data', kind: 'data', label: '数据对比', chart, demo: true })
  if (!chart && activeTheory.value && turn.theory_refs?.some(r=>r.theory_id===activeTheory.value?.id)) {
    peers.push({
      id: turn.id + '-method',
      kind: 'method',
      label: '方法依据',
      name: activeTheory.value.name,
      summary: activeTheory.value.summary ?? '',
      source: '职引方法卡 · 来自后端理论卡配置',
    })
  }
  return { lead, detail, peers, options: [...(turn.options ?? [])], optionRefs: optionRefsOf(turn), hasTask: !!turn.task, active: peers[0]?.id ?? '' }
}

const chartPoints = (chart: BarsChart) => chart.points.map(p => ({ ...p, ratio: p.value / Math.max(...chart.points.map(x => x.value), 1) }))
/**
 * 刻度轴：**0 也画**，且最后一个刻度要贴近最大值。
 *
 * 没有零点的条形图看不出"长度是从哪儿量起的"；刻度只走到 50 而条长到 72，
 * 读者就无法从轴上读出最长那根 —— 所以步长取"能让刻度数落在 4–5 个"的那一档，
 * 并且从 0 起画。整值优先（1/2/5/10/20/25/50…），避免出现 13.33 这种刻度。
 */
const chartTicks = (chart: BarsChart) => {
  const max = Math.max(...chart.points.map(p => p.value), 1)
  const steps = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000]
  let step = steps[steps.length - 1]
  for (const candidate of steps) {
    if (max / candidate <= 4.5) { step = candidate; break }
  }
  const out: number[] = []
  for (let v = step; v <= max + 1e-9 && out.length < 5; v += step) out.push(v)
  return [0, ...(out.length ? out : [max])]
}
const chartSummary = (chart: BarsChart) =>
  '' + chart.points.map(p => `${p.label} ${p.value}${chart.unit}`).join('，')

const completedReply = ref<string | null>(null)
let completionTimer: ReturnType<typeof setTimeout> | null = null
function clearCompletion() {
  if (completionTimer) clearTimeout(completionTimer)
  completionTimer = null
  completedReply.value = null
}
const { stream, textOf, isStreaming } = useStreaming((id, text) => {
  if (stopped.value.includes(id) || !turns.value.some(turn => turn.id === id)) return
  announcement.value = consultantLabel(host.value) + '：' + text
  clearCompletion()
  completedReply.value = id
  completionTimer = setTimeout(clearCompletion, 700)
})
let requestSerial = 0
let messageController: AbortController | null = null
const guideSaving = ref('')
const guideDone = computed(() => new Set(backendDemo.state.liveAction?.phases?.flatMap(p => p.tasks ?? []).filter(t=>t.done).map(t=>t.task_id) ?? []))
async function completeGuide(taskId: string) {
 if(guideSaving.value)return
 guideSaving.value=taskId
 try { backendDemo.setAction(await backendClient.actionDone({task_id:taskId,done:!guideDone.value.has(taskId)})); toast('任务状态已保存') } catch(e) {toast((e as Error).message)} finally {guideSaving.value=''}
}
let retryRequest: MessageRequest | null = null
const requestError = ref('')
let seq = Date.now()
const progress = computed(() => demo.use.profileProgress.value)
const known = computed(() => (backendDemo.state.liveWorkspace?.profile_panel?.fields??[]).map(f=>({...f,value:String(f.value??'')})))
const planned = computed(() => [...demo.use.now.value, ...demo.use.waiting.value])
const handoffs = computed(() => turns.value.filter((t) => t.handoff).map((t) => t.handoff!))
const host = computed(() => [...turns.value].reverse().find((t) => t.from === 'host' && t.speaker)?.speaker ?? '了解你情况的人')
const taskAdded = (title: string) => demo.state.tasks.some(task => task.title === title)
/**
 * 右栏第一张卡的读数：**已经落到行动清单上的建议**。
 *
 * 与「咨询成果」这个标题必须同义 —— 用 `planned.length`（今日行动 + 待办）而不是
 * 会话里出现过几次建议，否则用户点进成果页会发现数字对不上。
 */
const outcomeCount = computed(() => planned.value.length)
/**
 * 右栏第二张卡的读数与进度：**已知 / 总数**，进度条就画这个比例。
 * 逐段（12 段 = 画像池全量）比一条连续的百分比条更贴靶子，也更老实：
 * 段数就是待补充的项数，用户能一段一段数出来。
 */
const profileKnown = computed(() => progress.value.known)
const profileTotal = computed(() => progress.value.total)
const profileOn = computed(() => Math.max(0, Math.min(profileTotal.value, profileKnown.value)))
const taskAddedAt = ref('')
const topicLabels: Record<string, { title: string; description: string; icon: string }> = { confused: { title: '兴趣与能力', description: '了解个人特点与适合的领域', icon: 'profile' }, undecided: { title: '方向选择', description: '比较备选方向与决策依据', icon: 'directions' }, how_to_act: { title: '行动规划', description: '将目标转化为具体行动', icon: 'action' }, stuck: { title: '执行调整', description: '分析执行障碍并调整方案', icon: 'review' } }
const starters = computed(()=>(auth.state.bootstrap?.task_entries??[]).map(t => ({ ...t, ...(topicLabels[t.code] ?? {title:t.label,description:'',icon:'chat'}) })))
async function startTopic(code:string,label:string){try{await createSession(code);await send(label)}catch(e){requestError.value=(e as Error).message;errorVisible.value=true}}
function answered(turn:ChatTurn){return turns.value.slice(turns.value.indexOf(turn)+1).some(t=>t.from==='me')}

/* =============================================================================
 * 后续问题 —— 「过程可见」五问的第四问（DESIGN-LANGUAGE §3）
 * -----------------------------------------------------------------------------
 * 【为什么这一块必须存在，而且必须在两个状态下都存在】
 * 前四问里，主体在场、交接说明、结论块讲的都是"顾问在做什么"；只有这一问
 * 讲的是"**你**接下来能做什么"。少了它，对话页就退回单列文字流：用户读完一条
 * 回答，眼前只剩一个空白输入框 —— 有话想说的人会打字，没有话想说的人就走了。
 *
 * 【两个来源，一个出口】
 *   · 首选后端随这条回答投递的 options（turn.options + optionRefs）：
 *     点它会带上 option_id 一起走 send()，后端能记账；
 *   · 这一轮没投 options 时（例如预置的旗舰回答 c7）用下面三句兜底。
 *     它们不是占位文案：每一句都落在 reply() 一个真实存在的回答分支上
 *     （能力差距 / 方向比较 / 行动起步），点下去必然有下文。
 *
 * 【空态用的是同一个块、同一条链路】
 * 空态那三句是**开场问题**，不是"后续问题"：从学生自己的处境开口
 * （"我不知道自己适合什么"就是产品里最真实的第一句），而不是
 * "你可以问我……"这种把选择权又推回给用户的空话。
 * 形态与发送链路和回答之后的后续问题完全一致：同一个 .dialogue-options，
 * 同一个 send()。区别只在文案与出现时机，不另造一套。
 * ========================================================================== */
const OPENING_QUESTIONS = [
  '我不知道自己适合什么',
  '有几个感兴趣的方向，我该怎样比较',
  '知道该做什么，但一直没有开始',
]
const FOLLOW_UP_FALLBACK = [
  '我离目标岗位的门槛还差多少',
  '这几个方向我拿不准该选哪个',
  '把下一步拆成 5 分钟能做完的事',
]
/** 这条回答后面能点的接法。后端给了就用后端的（它们带着 option_id），没给才兜底。 */
function followUpsOf(turn: ChatTurn): string[] {
  const own = turn.options ?? []
  return own.length ? [...own] : FOLLOW_UP_FALLBACK
}

const copyStatus = ref('')
const copiedId = ref('')
const copyLabel = ref('复制')

/* ---- 错误态：demo 里没有真实失败，但必须可触发、可操作 ----
 * 触发口子只有查询参数 `?demo-error=1`——它**不是产品功能**，界面上不留按钮。
 * 所以这里用一次性快照而不是 computed：进页面时带上参数，这一次咨询就会走失败分支，
 * 之后即使用户把地址栏里的参数删掉，本轮错误态也不会凭空消失。 */
/** demo 数据里那条"未能生成"的系统消息：它本身就是可触发的一次真实失败 */
const failureTurn = computed(() => turns.value.find(t => t.from === 'system' && /未能生成/.test(t.text)) ?? null)
const errorVisible = ref(false)
/** 重试之后这条失败记录就不再占位（不改 store，只在本地隐去） */
const retriedIds = ref<string[]>([])
const showFailure = computed(() => !!failureTurn.value && !retriedIds.value.includes(failureTurn.value.id))
const errorText = computed(() => requestError.value || (failureTurn.value?.text ?? '本次未能生成内容。').trim())
function retry() {
  const last = [...turns.value].reverse().find(t => t.from === 'me')
  const failed = failureTurn.value
  if (failed) retriedIds.value = [...retriedIds.value, failed.id]
  errorVisible.value = false
  announcement.value = '正在重新生成。'
  if (!last) return
  if (!draft.value.trim()) draft.value = last.text
  send(last.text)
}
/** 依据块：默认露出两条，其余"长出来"，展开是内容增加而不是替换 */
const evidenceOpen = ref<Record<string, boolean>>({})
const evidenceRest = (total: number) => Math.max(0, total - 2)
const evidenceRestId = (turnId: string) => `chat-evidence-rest-${turnId}`
/** EvidenceList 只吃字符串，所以来源在这里并回一行（编号仍由它自己给） */
const evidenceLines = (items: EvidenceItem[]) => items.map(item => item.source ? `${item.body}（来源：${item.source}）` : item.body)
function toggleEvidence(turnId: string) { evidenceOpen.value = { ...evidenceOpen.value, [turnId]: !evidenceOpen.value[turnId] } }

/* =============================================================================
 * 流式生成中的「停止生成」
 * -----------------------------------------------------------------------------
 * 这套流式是演示用的逐字播放（lib/motion.ts），没有 abort 口子。
 * 但"停止"必须真的**停在当下**，而不是继续在后台吐字：
 * 所以这里把"用户已经停止"的那些 turn 记下来，并让几个判定函数
 * （isLive / ready / isSpeaking / liveText）一起把它当成"已经出完"——
 *   逐字停住 → 已经出现的那部分留在原地 → 后面的块（依据 / 说明 / 行动）立刻落位。
 * 结果与"生成被中断"在界面上完全一致：话停在这里，但已经生成的部分不会消失。
 * ========================================================================== */
const stopped = ref<string[]>([])
const stalled = ref(false)
/** 当前正在逐字输出的那一条（没有就是 null） */
const streamingTurn = computed(() => turns.value.find(t => isStreaming(t.id) && !stopped.value.includes(t.id)) ?? null)
/** 输入区是否处于"可以停下"的状态：等待回复、或正在逐字输出 */
const canStop = computed(() => thinking.value || stalled.value || !!streamingTurn.value)
function stopGeneration() {
  messageController?.abort()
  clearCompletion()
  const current = streamingTurn.value
  if (current) stopped.value = [...stopped.value, current.id]
  if (thinking.value) { stalled.value = true; thinking.value = false }
  requestSerial++
  announcement.value = '已停止等待。服务器可能仍在处理，可重新读取这段会话核对结果。'
}

/**
 * 一条回答里"此刻该显示到什么程度"的唯一出处。
 *
 * 停止生成时**必须整段显示**：逐字播放器不是可中断的，它下一秒仍会把剩下的字补上；
 * 如果这里只取 textOf 的当前进度，用户会看到自己那半句话先消失、再被后续内容顶掉。
 */
function liveText(id: string, full: string): string {
  return stopped.value.includes(id) ? full : textOf(id, full)
}
/** 结论块：只有在**已经有字**的时候才占位，否则流式开头会出现一个空的大字块 */
function leadText(t: ChatTurn): string {
  return t.from === 'host' ? liveText(t.id, blocksFor(t).lead) : ''
}

/**
 * 流式期间"还在长的那一段正文"（结论之后剩下的部分）。
 *
 * 它决定**光标画在哪里**：正文还有残余时光标跟着正文走，否则跟着结论。
 * 这样全页永远只有一个光标，而且它总在真实增长的那个字后面 ——
 * 顶端身份牌删掉之后，"顾问正在说"这件事只剩这一处可以看见（另一处是思考行）。
 */
function liveDetail(t: ChatTurn): string {
  if (!isLive(t.id)) return ''
  return textOf(t.id, t.text).slice(blocksFor(t).lead.length).replace(/^…/, '')
}

/** 一条回答的支撑材料是否已经可以出场：正文出完（或不需要逐字、或用户已停止）之后才落位 */
function ready(turn: ChatTurn): boolean {
  return turn.from !== 'host' || !isLive(turn.id)
}

/* =============================================================================
 * 卡片组：同级支撑材料可切换
 * -----------------------------------------------------------------------------
 * 空间隐喻：卡片排成一条横列，切换 = **整列在横向平移**，所以退场与进场方向相反。
 * 顺序在前的卡从左边进来、顺序在后的从右边进来 —— 用户看到的是"换了另一张卡"，
 * 而不是"这张卡的内容变了"。
 * ========================================================================== */
/**
 * 卡片组的状态：**派生为主，用户的选择只是覆盖**。
 *
 * 这样组里卡片数量变化时（依据条数变了、后端补投了 renderables）无需任何同步逻辑：
 * 缓存里的顺序与当前组不一致就自动作废，回落到默认第一张。
 */
const cardGroups = ref<Record<string, string>>({})
const cardOrder = computed(() => {
  const map: Record<string, { order: string[]; active: string }> = {}
  for (const turn of turns.value) {
    const blocks = turnBlocks(turn)
    const order = blocks.peers.map(p => p.id)
    const picked = cardGroups.value[turn.id]
    map[turn.id] = { order, active: picked && order.includes(picked) ? picked : blocks.active }
  }
  return map
})

function blocksFor(turn: ChatTurn): TurnBlocks { return turnBlocks(turn) }

function isActive(turn: ChatTurn, id: string): boolean { return cardOrder.value[turn.id]?.active === id }
function activeIndex(turn: ChatTurn): number { return Math.max(0, cardOrder.value[turn.id]?.order.indexOf(cardOrder.value[turn.id]?.active ?? '') ?? 0) }
/** ·1 / ·-1：位移方向。不是装饰 —— 位移方向就是"这张卡在原列的哪一侧" */
function enterDir(turn: ChatTurn, id: string): number {
  const group = cardOrder.value[turn.id]
  if (!group) return 1
  return group.order.indexOf(id) < group.order.indexOf(group.active) ? -1 : 1
}
function dirMark(dir: number): string { return dir < 0 ? 'is-from-left' : 'is-from-right' }
function tabRef(turnId: string, index: number) { return `cardtab-${turnId}-${index}` }
function cardRef(turnId: string, index: number) { return `cardpanel-${turnId}-${index}` }
function setCard(turn: ChatTurn, id: string) {
  if (isActive(turn, id)) return
  cardGroups.value = { ...cardGroups.value, [turn.id]: id }
  const index = cardOrder.value[turn.id]?.order.indexOf(id) ?? 0
  void nextTick(() => { const el = document.getElementById(tabRef(turn.id, index)); (el as HTMLElement | null)?.focus() })
}
function cardKeydown(turn: ChatTurn, event: KeyboardEvent) {
  const group = cardOrder.value[turn.id]
  if (!group?.order.length) return
  const index = Math.max(0, group.order.indexOf(group.active))
  const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
  if (step) {
    event.preventDefault()
    setCard(turn, group.order[(index + step + group.order.length) % group.order.length])
  } else if (event.key === 'Home') { event.preventDefault(); setCard(turn, group.order[0]) }
  else if (event.key === 'End') { event.preventDefault(); setCard(turn, group.order[group.order.length - 1]) }
}

/**
 * 窄屏是横滑卡片组：滚动位置就是"当前在看第几张"，所以要反着同步回来。
 * 三点必要性判断：单卡不读、不溢出（桌面）不读、每帧最多读一次。
 */
let scrollFrame = 0
function syncScrollGroup(turn: ChatTurn, event: Event) {
  const track = event.currentTarget as HTMLElement | null
  if (!track) return
  if (track.scrollWidth - track.clientWidth < 8) return
  cancelAnimationFrame(scrollFrame)
  scrollFrame = requestAnimationFrame(() => {
    const cards = Array.from(track.querySelectorAll<HTMLElement>('.chat-card'))
    if (!cards.length) return
    let nearest = 0
    let best = Infinity
    cards.forEach((card, index) => {
      const distance = Math.abs(card.offsetLeft - track.scrollLeft)
      if (distance < best) { best = distance; nearest = index }
    })
    const group = cardOrder.value[turn.id]
    const id = group?.order[nearest]
    if (id && id !== group.active) cardGroups.value = { ...cardGroups.value, [turn.id]: id }
  })
}

/** 切换会话时缓存的选择就不能留：卡片的 id 里带 turn 前缀，不清理只是变脏，但会一直长 */
watch(() => demo.state.currentSessionId, () => { clearCompletion(); cardGroups.value = {}; stopped.value = []; stalled.value = false; errorVisible.value = false })

/** 区块不是"同时铺开"，而是**顺序落位**：结论 → 支撑 → 行动 → 后续问题 */
function blockDelay(step: number): Record<string, string> { return { '--block-step': String(step) } }

/**
 * 同一个人连着说几句时，只在第一句显示头像与名字。
 *
 * 否则一屏里会出现四个一模一样的头像，头像就退化成了装饰；
 * 「谁在说」只需要标记一次，后续内容靠缩进对齐就够。
 */
function isGroupStart(index: number): boolean {
  const prev = turns.value[index - 1]
  const turn = turns.value[index]
  if (!prev || prev.handoff) return true
  return prev.from !== turn.from || prev.speaker !== turn.speaker
}

/** 交接卡要说清「从谁交给谁」，所以得回头看这一条之前最后一位主理。 */
function speakerBefore(index: number): string {
  for (let i = index - 1; i >= 0; i--) {
    const prior = turns.value[i]
    if (prior.from === 'host' && prior.speaker) return prior.speaker
  }
  return host.value
}

/**
 * 正在逐字输出的那条，头像进入「说话」状态；其余保持 idle。
 *
 * 【2026-10-14 · P0-3】它就是 .chat-who__state 那行「正在回答」的同一个判据
 * （都走 isLive）。两处必须同源：状态词说你正在回答、头像却还睁着眼发呆，
 * 是比"没有头像"更容易被看见的不一致 —— 在场感就是这两件事必须同时成立。
 */
function isSpeaking(id: string): boolean {
  return isLive(id)
}

/**
 * 「这一条此刻真的还在吐字吗」。
 * 与 isStreaming 分开：用户点了停止之后，播放器可能还在后台跑（演示用的逐字不是可中断的），
 * 但界面上必须立刻当作已经结束 —— 逐字停住、块落位、输入区解除忙碌。
 */
function isLive(id: string): boolean {
  return isStreaming(id) && !stopped.value.includes(id)
}

/** 一条消息该用哪个身份的头像：学生 / 系统 / 对应主理。 */
function turnAgent(turn: ChatTurn): string {
  if (turn.from === 'system') return 'system'
  if (turn.from === 'me') return 'me'
  return agentKeyOf(turn.speaker)
}

/**
 * 「在场主理」的状态。
 *
 * 这一条是整页"活"的总开关：等待回复时它在思考、逐字输出时它在说话、
 * 停下来时它在看着你。
 *
 * **落点变了**（v9）：顶端那块常驻身份牌删掉之后，状态不再挂在一个页头组件上，
 * 而是回到**话语发生处** —— 思考态那一行（`.chat-turn--thinking`）与正在逐字输出的
 * 那一条（头像状态 + 光标）。理由：同一条信息（谁在说、什么状态）在每条顾问消息上
 * 已经有了，页头再说一遍只是重复；而"进行时"必须在事情正在发生的位置被看见。
 */
const hostState = computed<'idle' | 'thinking' | 'speaking'>(() => {
  if (thinking.value) return 'thinking'
  return turns.value.some((t) => isLive(t.id)) ? 'speaking' : 'idle'
})
/**
 * 状态词：只说"此刻在干什么"，不给角色名（角色名就在同一行的 .chat-who 上）。
 *
 * 【2026-10-14 · 对齐 c2-hbu】词表从"正在分析你的问题 / 正在回答 / 在线"收到
 * 靶子的三个短词（正在想 / 正在说 / 在听）：在场卡的形态与间距照靶子搬，
 * 状态词就不该比靶子长一倍 —— 那是同一行里唯一还在"解释"的东西。
 * 它不是新的状态源：判据仍然是 hostState，而 hostState 由真实字段驱动
 * （thinking / isStreaming，见下面的 hostState 定义）。
 */
const presencePreview = ref<'idle' | 'thinking' | 'speaking' | null>(null)
const presenceState = computed(() => demo.state.chatBusy ? hostState.value : completedReply.value ? 'done' : backendDemo.state.dataMode === 'service' ? hostState.value : presencePreview.value ?? hostState.value)
watch(() => demo.state.chatBusy, busy => { if (busy) presencePreview.value = null })
const presenceStateLabel = computed(() => presenceState.value === 'thinking' ? '正在想' : presenceState.value === 'speaking' ? '正在说' : presenceState.value === 'done' ? '已回复' : '在听')

const presenceLabel = computed(() =>
  hostState.value === 'thinking' ? '正在想' : hostState.value === 'speaking' ? '正在说' : '在听',
)
/** 头部那一行左侧的会话名（可截断；完整名字走 title） */
const sessionName = computed(() => backendDemo.currentSession.value?.task_name || '围绕当前问题开展咨询')
/** 此刻主理这一段的顾问（会话头第三行「谁在跟你说话」用它，与在场卡同源） */
const hostLabel = computed(() => consultantLabel(host.value))

/**
 * 会话头第二行的时间：**取自真实字段** `last_active_at`，不写死。
 *
 * 它是"最近一次活动"，所以不冒充靶子那句「今天 14:20 开始」——
 * 拿不到确切开始时间就如实说"最近活跃"，绝不用一句更漂亮的话替掉真话。
 * 该字段在 service 模式下由后端投递，格式也按它自己解析；解析不了就整行不显示。
 */
const sessionTime = computed(() => {
  const raw = backendDemo.currentSession.value?.last_active_at
  if (!raw) return ''
  const at = new Date(raw)
  if (Number.isNaN(at.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${at.getMonth() + 1}-${pad(at.getDate())} ${pad(at.getHours())}:${pad(at.getMinutes())}`
})
async function copyReply(id: string, text: string) {
  copiedId.value = id
  try { await navigator.clipboard.writeText(text); copyStatus.value = '回复已复制。'; copyLabel.value = '已复制' }
  catch { copyStatus.value = '未能复制，请选中正文手动复制。'; copyLabel.value = '复制失败' }
}

/* =============================================================================
 * 页头两个动作：总结这段咨询 / 导出记录
 * -----------------------------------------------------------------------------
 * 靶子页头右边就是这两个动作（c2-hbu index.html:7040-7049），现网没有它们。
 * 搬过来的同时必须**真的做事**，否则它们是两枚假按钮：
 *   · 总结这段咨询 → 复用已经存在的产出面板（咨询成果 sheet）：
 *     它本来就是"这一段咨询产出了什么"的落点，不另造一个总结弹层；
 *   · 导出记录 → 真的把这一轮对话写成文本放进剪贴板。
 *     移动端 Safari 不给剪贴板权限时**必须留退路**：把文本显示在成果面板里，
 *     让用户自己选区复制 —— 不允许出现"点了没反应"。
 * ========================================================================== */
const exportText = ref('')
function summaryOf(): string {
  return turns.value.map((t, i) => {
    const who = t.from === 'me' ? '我' : t.from === 'system' ? '系统提示' : consultantLabel(t.speaker)
    // 「从谁交给谁」只能回头看这一条之前最后一位主理 —— handoff 自己只记了 to
    const extra = t.handoff ? `（${consultantLabel(speakerBefore(i))}交给${consultantLabel(t.handoff.to)}：${t.handoff.why}）` : ''
    return `${who}：${t.text}${extra}`
  }).join('\n\n')
}
function exportRecord() {
  const body = summaryOf()
  if (!body.trim()) { copyStatus.value = '这段咨询还没有内容可以导出。'; announcement.value = copyStatus.value; return }
  exportText.value = body
  const task = navigator.clipboard?.writeText(body)
  if (!task) { panel.value = 'outcomes'; announcement.value = '已把这段咨询整理成文本，放在「咨询成果」里，可自行复制。'; return }
  void task.then(
    () => { announcement.value = '这段咨询已整理成文本并复制到剪贴板。' },
    () => { panel.value = 'outcomes'; announcement.value = '浏览器没给剪贴板权限，已把文本放在「咨询成果」里，可自行复制。' },
  )
}
function goToLatest() { followTail.value = true; void scrollToEnd() }
async function newSession() {
  rememberDraft()
  try { await createSession(); panel.value=null; announcement.value='' } catch(e){toast((e as Error).message)}
}
async function selectSession(id:string){rememberDraft();try{await openSession(id);panel.value=null}catch(e){toast((e as Error).message)}}
async function attach(event:Event){
 const el=event.target as HTMLInputElement, file=el.files?.[0];if(!file)return
 attachmentError.value=''
 try{if(attached.value.length>=5)throw new Error('每轮最多添加 5 份材料。');const receipt=await backendClient.material(file);attached.value.push({id:receipt.material_id,name:receipt.name||file.name})}catch(e){attachmentError.value=(e as Error).message}finally{el.value=''}
}
function readingRoot() {
  const main = flow.value?.closest<HTMLElement>('.app__main')
  return main && getComputedStyle(main).overflowY === 'auto' ? main : null
}
function readingPosition() { return readingRoot()?.scrollTop ?? window.scrollY }
async function scrollToEnd() {
  await nextTick()
  const root = readingRoot()
  const top = turns.value.length ? (root?.scrollHeight ?? document.documentElement.scrollHeight) : 0
  if (root) root.scrollTop = top
  else window.scrollTo({ top, behavior: 'instant' })
}
function followScroll() {
  const root = readingRoot()
  followTail.value = root ? root.scrollHeight - root.scrollTop - root.clientHeight < 100 : document.documentElement.scrollHeight - window.scrollY - window.innerHeight < 100
}
function append(turn: Omit<ChatTurn, 'id'>, animate = true) {
  const complete = { ...turn, id: 'turn-' + (++seq), optionRefs: turn.optionRefs }
  demo.addChatTurn(complete)
  if (animate && turn.from === 'host' && !turn.handoff) {
    announcement.value = ''
    stream(complete.id, complete.text)
  }
  if (followTail.value) void scrollToEnd()
}

/* =============================================================================
 * 等待回复时的加载态：**骨架盖在已有内容上，而不是把内容摘掉**
 * -----------------------------------------------------------------------------
 * `SkeletonBlock.vue:19-26` 定的规矩："组件自己不摘内容；刷新时用 overlay 盖在
 * 仍在 DOM 的内容上，不要用 v-if 摘掉"。本页最容易犯这个错的时刻恰好是
 * **第二次提问之后的等待**：此时上一条完整回答已经在页面上，如果为了放骨架
 * 而把它 v-if 掉，用户就会看到"读到一半的回答凭空消失、再重建"。
 *
 * 所以骨架挂在**上一条顾问回答的 body 里**（`inset: 0` 铺满它），那条回答的每个
 * 节点都还在 DOM 里，只是暂时被盖住。三点做不到就退化成普通骨架：
 *   · 没有任何回答可盖（首轮提问）→ 不挂 overlay；
 *   · 失败重试路径（`?demo-error=1`）→ 不挂（那一路要的是"重试"这个动作，不是骨架）；
 *   · 上一条就是失败记录 → 不挂（盖住一条错误信息等于把问题藏起来）。
 * 头像与「正在分析你的问题」在 body 外面，所以盖住的只有内容，不是"人在不在"。
 * ========================================================================== */
/** 要盖住的那条回答：最后一条、不是失败记录、此刻也没在逐字输出（也就是已经出完了） */
const coveredTurn = computed(() => {
  if (!thinking.value || errorVisible.value) return null
  const last = [...turns.value].reverse().find(t => t.from === 'host' && !t.handoff)
  if (!last || (failureTurn.value && failureTurn.value.id === last.id)) return null
  return last.id
})
function isCovered(id: string): boolean { return coveredTurn.value === id }
async function send(text?: string, option?: GuideOptionView) {
 const content=(text ?? draft.value).trim()
 if(!content||thinking.value)return
 if(!demo.state.currentSessionId){try{await createSession()}catch(e){requestError.value=(e as Error).message;errorVisible.value=true;return}}
 const serial=++requestSerial, sessionId=demo.state.currentSessionId
 const request:MessageRequest = retryRequest && retryRequest.message===content && retryRequest.task_id===sessionId ? retryRequest : {task_id:sessionId,message:content,client_msg_id:crypto.randomUUID(),option_id:option?.option_id,option_value:option?.value,material_ids:attached.value.map(m=>m.id)}
 const retrying=request===retryRequest
 retryRequest=request;thinking.value=true;stalled.value=false;errorVisible.value=false;requestError.value='';clearCompletion();followTail.value=true
 if(!retrying)append({from:'me',text:content,materials:attached.value.map(m=>({...m}))},false)
 try {
   messageController = new AbortController()
   const result=await backendClient.message(request,messageController.signal)
   if(serial!==requestSerial || sessionId!==demo.state.currentSessionId)return
   if(result.disclosure)append({from:'system',text:result.disclosure.text,handoff:result.disclosure.kind==='lead_change'?{to:result.disclosure.to_agent||result.badge.name,why:result.disclosure.text,basedOn:''}:undefined},false)
   const messages=(result.messages??[]).filter(m=>m.role!=='user')
   for(const message of messages){const turn=mapMessage(message,crypto.randomUUID());append(turn)}
   if(result.badge.theory_refs?.[0])void readTheory(result.badge.theory_refs[0].theory_id)
   systemData.snapshot=result
   const guide=result.guide
   if(guide && (guide.question || guide.options?.length || guide.task || guide.reminder || (!messages.length && guide.text)))append({from:'host',speaker:result.badge.name,text:guide.text||guide.question||'',guideTask:guide.task??undefined,reminder:guide.reminder??undefined,question:guide.question??undefined,options:guide.options?.map(o=>o.label),optionRefs:guide.options?.map(o=>({...o,value:o.value}))})
   draft.value='';attached.value=[];retryRequest=null;backendDemo.saveDraft('', '', [], null)
   backendDemo.saveTurns(sessionId,demo.state.chatTurns)
   void loadShell()
 }catch(e){if(serial===requestSerial){requestError.value=(e as Error).message;errorVisible.value=true}}
 finally{if(serial===requestSerial)thinking.value=false}
}
function grow() {
  if (!input.value) return
  input.value.style.height = 'auto'
  input.value.style.height = Math.min(input.value.scrollHeight, 180) + 'px'
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send() }
}
watch(() => turns.value.length, () => { if (followTail.value) void scrollToEnd() })
function rememberDraft() { if (demo.state.authed) backendDemo.saveDraft(demo.state.currentSessionId, draft.value, attached.value, readingPosition()) }
watch(() => demo.state.currentSessionId, (_id, previousId) => {
  if (demo.state.authed) backendDemo.saveDraft(previousId, draft.value, attached.value, readingPosition())
  const saved = backendDemo.getDraft(demo.state.currentSessionId)
  draft.value = saved.text; attached.value = saved.materials.map(m => ({ ...m })); attachmentError.value = ''; panel.value = null; announcement.value = ''
  followTail.value = true
  void scrollToEnd()
}, { flush: 'sync' })
watch([draft,attached],()=>rememberDraft(),{deep:true,flush:'sync'})
watch(() => thinking.value || turns.value.some(t => isStreaming(t.id) && !stopped.value.includes(t.id)), value => demo.setChatBusy(value), { flush: 'sync' })
watch(() => {
  const last = turns.value[turns.value.length - 1]
  return last ? textOf(last.id, last.text) : ''
}, () => { if (followTail.value) void scrollToEnd() })
onMounted(() => {
  if(demo.state.currentSessionId)void openSession(demo.state.currentSessionId).catch(e=>{requestError.value=e.message;errorVisible.value=true})
  window.addEventListener('scroll', followScroll, { passive: true })
  flow.value?.closest('.app__main')?.addEventListener('scroll', followScroll, { passive: true })
  const question = typeof route.query.question === 'string' ? route.query.question : ''
  if (question && !draft.value) draft.value = question
  const topic = typeof route.query.topic === 'string' ? route.query.topic : ''
  if (topic && !draft.value) draft.value = '我想讨论：' + topic
  const gap = PROFILE_FIELDS.find(f => f.key === route.query.gap)
  const gapLabel = gap?.label || backendDemo.state.liveWorkspace?.profile_panel?.gaps?.find(g=>g.key===route.query.gap)?.label || (typeof route.query.label==='string'?route.query.label:'')
  if (gapLabel && !draft.value) draft.value = '我想补充' + gapLabel + '：'
  /* 错误态只由查询参数触发（界面上没有按钮）：?demo-error=1 */
  if (restoredDraft.scroll !== null) void nextTick(() => { const root = readingRoot(); if (root) root.scrollTop = restoredDraft.scroll!; else window.scrollTo(0, restoredDraft.scroll!); followScroll() })
  else void scrollToEnd()
})
onUnmounted(() => {
  clearCompletion()
  window.removeEventListener('scroll', followScroll)
  flow.value?.closest('.app__main')?.removeEventListener('scroll', followScroll)
  rememberDraft()
  requestSerial++; messageController?.abort()
  /* 停止生成之后离开页面：那条回复按"已停止"落在原地，不再补一次完整回答 */
  demo.setChatBusy(false)
})
</script>
<template>
  <section class="ws-conversation dialogue-page" :class="{ 'has-rail': hasRail }" aria-label="对话空间">
    <!--
      头部只有**一行**：会话名 + 演示标识 + 4 个入口。
      「错误状态预览」是调试口子 → 只由 ?demo-error=1 触发，界面上不留按钮。
      ---------------------------------------------------------------------------
      「现在跟你说话的是 + 头像 + 名字 + 职责」那块常驻身份牌**已删除**。
      原因是同一件事说了两遍：每条顾问消息的组首已经有头像、名字、职责
      （`.chat-who`），页头再说一遍，代价是桌面约 123px、手机约 242px 的常驻高度。
      「谁在说、此刻在干什么」改由**话语发生处**承担：
        · 思考态那一行（`.chat-turn--thinking`：头像 thinking 状态 + 状态词 + 骨架）
        · 正在逐字输出的那一条（头像 speaking 状态 + 状态词 + 流式光标）
      这一行里放什么：
        · 左：会话名（小字号，可截断，完整名走 title）
        · 中：演示数据小标识 —— 与操作同行，不另起一块
        · 右：「咨询成果 / 个人画像」（产出与依据，桌面另有 rail）+「新对话 / 历史会话」
      窄屏（≤760px）四个入口收成 44×44 图标按钮（aria-label + title 保名），
      为的是把宽度让给会话名、把高度彻底让给消息：任何"再起一行"都会吃掉
      首屏 44px，而首屏让出的空间是这次改动的硬指标。
    -->
    <!--
      页头 = 靶子的三行结构（c2-hbu index.html:7031-7050）：
        第一行 会话名（20px/700，主题字体）
        第二行 「最近活跃 10-12 10:00」+「<顾问> 主理」+ 演示数据 + 四个入口
        右侧   「总结这段咨询」「导出记录」两个动作
      与靶子的差别只有措辞：靶子写「今天 14:20 开始」，那是**写死的演示文案**；
      这里的时间来自真实字段 `last_active_at`，所以只说它真的表示的事（"最近活跃"）。
      ---------------------------------------------------------------------------
      「现在跟你说话的是 + 头像 + 名字 + 职责」那块**常驻在场卡**在页头下面
      （.dialogue-presence），96px 头像 + 名字 + 职责 + 状态词；空态与有消息时
      都在场 —— 它就是靶子那块 .agent 卡，也是「谁在说、此刻在干什么」的落点。
    -->
    <header class="ws-chat-head">
      <div class="dialogue-chat-head__id">
        <h1 class="dialogue-chat-head__title" :title="sessionName">{{ sessionName }}</h1>
        <div class="dialogue-chat-head__meta">
          <span v-if="sessionTime" class="dialogue-chip">最近活跃 {{ sessionTime }}</span>
          <span class="dialogue-chip">{{ hostLabel }} 主理</span>

        </div>
      </div>
      <div class="dialogue-chat-head__acts">
        <button type="button" class="dialogue-chipbtn" @click="panel = 'outcomes'"><UiIcon name="report" :size="16" />总结这段咨询</button>
        <button type="button" class="dialogue-chipbtn" @click="exportRecord"><UiIcon name="upload" :size="16" />导出记录</button>
      </div>
      <nav v-if="!hasRail" class="ws-chat-head__flow" aria-label="这次咨询的产出与依据">
        <button type="button" aria-label="咨询成果" title="咨询成果" @click="panel = 'outcomes'"><UiIcon name="report" :size="18" /><span class="ws-chat-head__label">咨询成果</span></button>
        <button type="button" aria-label="个人画像" title="个人画像" @click="panel = 'profile'"><UiIcon name="profile" :size="18" /><span class="ws-chat-head__label">个人画像</span></button>
      </nav>
      <div class="ws-chat-head__tools">
        <button type="button" :disabled="demo.state.chatBusy" aria-label="新对话" title="新对话" @click="newSession"><UiIcon name="plus" :size="18" /><span class="ws-chat-head__label">新对话</span></button>
        <button type="button" :disabled="demo.state.chatBusy" aria-label="历史会话" title="历史会话" @click="panel = 'sessions'"><UiIcon name="chat" :size="18" /><span class="ws-chat-head__label">历史会话</span></button>
      </div>
    </header>
    <!--
      在场卡（靶子的 .agent 卡）：96px 头像 + 名字 + 职责 + 状态。
      它**不受空态约束** —— 靶子里它常驻页头，所以现网也常驻：
      原来这块只在 `v-if="!turns.length"` 的空态里出现（消息一来"顾问"就消失），
      那正是 HANDOFF §5.2 说的"顾问在场该块不存在"。
      状态由 hostState 驱动（真实字段，见 script 里的定义），不是演示台控件。
    -->
    <section class="dialogue-presence" :class="'is-' + presenceState" aria-label="此刻在场的主理">
      <AgentAvatar :agent="agentKeyOf(host)" :size="96" :state="presenceState" />
      <div class="dialogue-presence__intro">
        <p class="dialogue-presence__who">
          <strong>{{ hostLabel }}</strong>
          <span class="dialogue-presence__state"><i class="dialogue-presence__dot" aria-hidden="true" />{{ presenceStateLabel }}</span>
        </p>
        <p class="dialogue-presence__role">{{ agentOf(agentKeyOf(host)).role }}</p><span class="dialogue-presence__status"><i />{{ presenceStateLabel }}</span>
      </div>
    </section>
    <!-- 桌面右侧 rail：产物与依据常驻在旁边，窄屏收起（见 dialogue.css） -->
    <aside class="dialogue-rail" aria-label="这次咨询的产出与依据">
      <p class="dialogue-rail__title">这段咨询的成果</p>
      <button type="button" class="dialogue-rail__card" :aria-pressed="panel === 'outcomes'" @click="panel = 'outcomes'">
        <span class="dialogue-rail__top">
          <span class="dialogue-rail__ic" aria-hidden="true"><UiIcon name="check" :size="16" /></span>
          <span class="dialogue-rail__num"><strong>{{ outcomeCount }}</strong> 项</span>
        </span>
        <span class="dialogue-rail__t">咨询成果</span>
        <span class="dialogue-rail__d">{{ outcomeCount ? '已形成 ' + outcomeCount + ' 条可执行建议，已加入今日行动或待办。' : '还没有形成建议。咨询里定下的行动会汇总到这里。' }}</span>
        <span class="dialogue-rail__foot">看全部成果 <span aria-hidden="true">→</span></span>
      </button>
      <button type="button" class="dialogue-rail__card" :aria-pressed="panel === 'profile'" @click="panel = 'profile'">
        <span class="dialogue-rail__top">
          <span class="dialogue-rail__ic" aria-hidden="true"><UiIcon name="profile" :size="16" /></span>
          <span class="dialogue-rail__num"><strong>{{ profileKnown }}</strong> / {{ profileTotal }}</span>
        </span>
        <span class="dialogue-rail__t">个人画像</span>
        <span class="dialogue-rail__d">{{ profileKnown }} 项已知、{{ progress.gap }} 项待补充。每一段就是画像池里的一项。</span>
        <span class="dialogue-rail__meter" role="img" :aria-label="'画像进度：' + profileTotal + ' 项里已知 ' + profileKnown + ' 项'">
          <i v-for="seg in profileTotal" :key="seg" :class="{ 'is-on': seg <= profileOn }" />
        </span>
        <span class="dialogue-rail__foot">去核对画像与来源 <span aria-hidden="true">→</span></span>
      </button>
      <p class="dialogue-rail__note">这两项是这次咨询的产出与依据，会话本身只有「新对话 / 历史会话」。</p>
    </aside>
    <div class="exp-conversation-body"><div ref="flow" class="ws-chat-flow" tabindex="0" role="log" aria-live="off" aria-label="对话记录" @scroll="followScroll"><div class="dialogue-thread">
      <div v-if="!turns.length" class="ws-chat-welcome">
        <!--
          空态：页头那块在场卡（.dialogue-presence）已经在上面常驻了，
          所以这里**不再放第二张身份牌** —— 一屏两块"我是谁"就是同一件事说两遍。
          这里只留"从哪句话开始"：一句引导 + 四张起步卡（从哪一类事聊起）
          + 三句开场问题（直接点一句就发出去，见下面的 .dialogue-options）。
        -->
        <div class="exp-intro"><div><h2>从你正在想的事聊起</h2><p>方向还没想清楚也没关系。先选一类最像你的，也可以直接问下面这一句。</p></div></div>
        <div class="ws-chat-prompts"><button v-for="topic in starters" :key="topic.code" @click="startTopic(topic.code,topic.title)"><UiIcon :name="topic.icon" :size="22" /><span><strong>{{ topic.title }}</strong><small>{{ topic.description }}</small></span><UiIcon name="arrow" :size="16" /></button></div>
        <!--
          开场问题：**点一句就发出去**，不是把话填进输入框让用户再按一次发送。
          与"回答之后的后续问题"共用 .dialogue-options / .ws-chat-options
          （所以密度、触控目标 44px、悬停都同一套），区别只有文案与出现时机。
        -->
        <div class="dialogue-options" aria-label="开场问题">
          <p>也可以直接问这一句</p>
          <div class="ws-chat-options"><button v-for="q in OPENING_QUESTIONS" :key="q" type="button" @click="send(q)">{{ q }}</button></div>
        </div>
      </div>
      <template v-for="(t, i) in turns" :key="t.id">
        <section v-if="t.handoff" class="chat-handoff" aria-label="顾问交接">
<AgentAvatar :agent="agentKeyOf(t.handoff.to)" :size="24"/><span>{{ consultantLabel(t.handoff.to) }}接手</span><DetailPopover title="顾问交接依据" label="查看顾问交接依据"><p>{{ consultantLabel(speakerBefore(i)) }} → {{ consultantLabel(t.handoff.to) }}</p><p>{{ t.handoff.why }}</p><p>依据：{{ t.handoff.basedOn }}</p></DetailPopover>
        </section>
        <article v-else class="chat-turn" :class="['chat-turn--' + t.from, { 'chat-turn--cont': !isGroupStart(i) }]" :aria-label="t.from === 'me' ? '你的消息' : consultantLabel(t.speaker) + '的回复'">
          <template v-if="t.from === 'me'">
            <div class="chat-turn__body">
              <div class="chat-bubble chat-bubble--me"><ReadableText :text="t.text" /></div>
              <div v-if="t.materials?.length" class="desk-attachments"><span v-for="m in t.materials" :key="m.id" class="desk-attachment"><UiIcon name="attachment" :size="16" />{{ m.name }} · 附件记录</span></div>
            </div>
          </template>
          <template v-else>
            <AgentAvatar v-if="isGroupStart(i)" class="chat-turn__avatar" :agent="turnAgent(t)" :size="40" :state="isSpeaking(t.id) ? 'speaking' : completedReply === t.id ? 'done' : 'idle'" />
            <span v-else class="chat-turn__avatar chat-turn__avatar--gap" aria-hidden="true" />
            <div class="chat-turn__body">
              <!--
                身份行只在组首出现（同一个人连着说几句不重复贴名字）。
                它现在也承担**在场感**：正在逐字输出的那一条，名字旁边直接写"正在回答"，
                「谁在说、什么状态」就在话语发生处，不用回到页头去看。
              -->
              <p v-if="isGroupStart(i)" class="chat-who">
                <strong>{{ t.from === 'system' ? '系统提示' : consultantLabel(t.speaker) }}</strong>
                <span v-if="t.from === 'host'">{{ agentOf(agentKeyOf(t.speaker)).role }}</span>
                <span v-if="t.from === 'host' && isLive(t.id)" class="chat-who__state">正在回答</span>
              </p>

              <!-- 系统提示：成功路径上不拆块（没有主张、没有依据、没有行动）；
                   但"未能生成"这条是**真实失败**，原地升级成可重试的错误态 -->
              <template v-if="t.from === 'system'">
                <div v-if="showFailure" class="chat-error chat-error--inline" role="alert">
                  <div class="chat-error__head"><UiIcon name="info" :size="18" /><strong>这次没有生成成功</strong></div>
                  <p>{{ t.text }}你的上一条消息已保留。</p>
                  <div class="chat-error__actions"><button class="btn btn--primary" type="button" @click="retry">重试这一条<UiIcon name="arrow" :size="17" /></button></div>
                </div>
                <div v-else class="chat-bubble chat-bubble--system"><ReadableText :text="t.text" /></div>
              </template>

              <!-- 一条顾问回答 = 按内容类型选出来的若干块，依次落位 -->
              <div v-else class="chat-answer" :class="{ 'is-live': isLive(t.id) }">
                <!-- 块一 · 结论：一句话主张，极大字，不等用户去段落里找。
                     形态照靶子（c2-hbu .lead）：**左侧 3px 粗色条 + --fs-30 的大字**，
                     外面套一层白卡（靶子那层 .lead 的材质）。
                     `aria-label="结论"` 只是给屏幕阅读器的分组名，**页面上不出现"结论"二字** ——
                     HANDOFF §4.3 明确记载"给结论块加「结论」小标"这条要求已作废，
                     DESIGN-LANGUAGE 禁止结构自述词，评审也判定现网"不加标签"是对的。 -->
                <section v-if="leadText(t)" class="chat-block chat-block--lead" :class="{ 'is-live': isLive(t.id) }" :style="blockDelay(0)" aria-label="结论">
                  <p class="chat-block--lead__text"><ReadableText :text="leadText(t)" /><span v-if="isLive(t.id) && !liveDetail(t)" class="chat-caret" aria-hidden="true" /></p>
                </section>
                <!-- 块二的支撑材料出完之后才轮到"接下来做什么"，所以行动与后续问题都排在它后面 -->

                <!-- 块二 · 支撑：依据 / 数据 / 方法 —— 同级材料，做成可切换的卡片组 -->
                <section v-if="ready(t) && blocksFor(t).peers.length" class="chat-block chat-block--support" :style="blockDelay(1)" aria-label="支撑材料">
                  <div class="chat-cards">
                    <!-- 卡头只做一件事：说明这是"可切换的一组支撑材料"。
                         切换控件 ≥44px；单卡时不渲染切换器，改由内层那条可见的摘要行承担展开。 -->
                    <div v-if="blocksFor(t).peers.length > 1" class="chat-cards__head">
                      <span class="chat-cards__eyebrow"><UiIcon name="shield" :size="15" />支撑材料</span>
                      <div class="chat-cards__tabs" role="tablist" aria-label="支撑材料切换">
                        <button v-for="(card, ci) in blocksFor(t).peers" :key="card.id" :id="tabRef(t.id, ci)" class="chat-cards__tab" :class="{ 'is-on': isActive(t, card.id) }" type="button" role="tab" :aria-selected="isActive(t, card.id)" :aria-controls="cardRef(t.id, ci)" :tabindex="isActive(t, card.id) ? 0 : -1" @click="setCard(t, card.id)" @keydown="cardKeydown(t, $event)"><span class="chat-cards__dot" aria-hidden="true" />{{ card.label }}</button>
                      </div>
                      <span class="chat-cards__pos"><strong>{{ activeIndex(t) + 1 }}</strong> / {{ blocksFor(t).peers.length }}<button type="button" class="chat-cards__step" aria-label="上一张卡片" @click="setCard(t, blocksFor(t).peers[(activeIndex(t) - 1 + blocksFor(t).peers.length) % blocksFor(t).peers.length].id)"><UiIcon name="back" :size="18" /></button><button type="button" class="chat-cards__step" aria-label="下一张卡片" @click="setCard(t, blocksFor(t).peers[(activeIndex(t) + 1) % blocksFor(t).peers.length].id)"><UiIcon name="arrow" :size="18" /></button></span>
                    </div>
                    <div class="chat-cards__viewport">
                      <div class="chat-cards__track" :style="{ '--card-count': blocksFor(t).peers.length }" @scroll="blocksFor(t).peers.length > 1 && syncScrollGroup(t, $event)">
                        <div v-for="(card, ci) in blocksFor(t).peers" :id="cardRef(t.id, ci)" :key="card.id" class="chat-card" :class="[isActive(t, card.id) ? 'is-on' : 'is-off', dirMark(enterDir(t, card.id))]" role="tabpanel" :aria-labelledby="tabRef(t.id, ci)" :inert="!isActive(t, card.id)">
                          <!-- 依据块：编号证据 + 来源；默认两条可见，其余"长出来"（不是替换掉已见的） -->
                          <template v-if="card.kind === 'evidence'">
                            <!--
                              依据块：**可见的展开控件**，不用裁剪隐藏绕过。
                              前两条默认就在页面上；第 3 条起挂在一个可见的按钮后面（aria-expanded +
                              被控制区域的 id），按钮本身 min-height 44px、有文字名字，
                              EvidenceList 不再自己承担那个会被 Tab 到的隐形 summary。
                            -->
                            <div class="chat-evidence">
                              <!-- 单卡（组内没有切换器）时，由 EvidenceList 自己给一个可见、有名字、≥44px 的摘要控件 -->
                              <EvidenceList :items="evidenceLines(card.items.slice(0, 2))" :title="blocksFor(t).peers.length > 1 ? '' : '支持依据'" />
                              <div v-if="evidenceRest(card.items.length)" :id="evidenceRestId(t.id)" class="chat-evidence__rest just-changed" :hidden="!evidenceOpen[t.id]">
                                <EvidenceList :items="evidenceLines(card.items.slice(2))" />
                              </div>
                              <button v-if="evidenceRest(card.items.length)" class="chat-block__more" type="button" :aria-expanded="!!evidenceOpen[t.id]" :aria-controls="evidenceRestId(t.id)" @click="toggleEvidence(t.id)"><UiIcon name="chevron" :size="15" /><span v-if="evidenceOpen[t.id]">收起，只看前两条</span><span v-else>展开其余 {{ evidenceRest(card.items.length) }} 条依据</span></button>
                            </div>
                          </template>
                          <!-- 数据块：后端契约 renderables 形状（kind=bars_chart），SVG 手绘，不引图表库 -->
                          <template v-else-if="card.kind === 'data'">
                            <div class="chat-bars">
                              <div class="chat-bars__head"><h3>{{ card.label }}</h3></div>
                              <p class="chat-bars__note">同一刻度比较各方向。展开来源与依据，核对评分支持哪些判断。</p>
                              <div class="chat-bars__plot" role="img" :aria-label="chartSummary(card.chart)">
                                <div class="chat-bars__grid" aria-hidden="true"><span v-for="tick in chartTicks(card.chart)" :key="tick" :style="{ left: (tick / Math.max(...card.chart.points.map(p => p.value), 1) * 100) + '%' }"><i>{{ tick }}</i></span></div>
                                <ul class="chat-bars__rows">
                                  <li v-for="p in chartPoints(card.chart)" :key="p.label">
                                    <span class="chat-bars__label">{{ p.label }}</span>
                                    <span class="chat-bars__track" aria-hidden="true"><i class="chat-bars__fill" :style="{ width: Math.max(4, p.ratio * 100) + '%' }" /></span>
                                    <span class="chat-bars__value">{{ p.value }}<small>{{ card.chart.unit }}</small></span>
                                  </li>
                                </ul>
                              </div>
                              <p class="chat-bars__foot">{{ chartSummary(card.chart) }}</p>
                            </div>
                          </template>
                          <!-- 方法块：这张判断依据的方法卡，同样带来源 -->
                          <template v-else>
                            <div class="chat-method">
                              <h3>{{ card.name }}</h3>
                              <p>{{ card.summary }}</p>
                              <p class="chat-method__source"><UiIcon name="info" :size="13" />{{ card.source }}</p>
                              <button class="chat-block__more" type="button" @click="theoryOpen = true">展开方法卡全文<UiIcon name="arrow" :size="15" /></button>
                            </div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <!-- 块三 · 说明：结论装不下的正文，跟在结论后面，不与主张争第一眼 -->
                <section v-if="ready(t) && blocksFor(t).detail" class="chat-block chat-block--detail" :style="blockDelay(2)" aria-label="补充说明">
                  <p>{{ blocksFor(t).detail }}</p>
                </section>
                <p v-else-if="liveDetail(t)" class="chat-block chat-block--transient" aria-hidden="true">{{ liveDetail(t) }}<span class="chat-caret" /></p>

                <!-- 块四 · 行动：要你做的事，别的块都不许长得像它 -->
                <RenderableBlock v-for="(block,bi) in t.renderables ?? []" :key="t.id+'-'+bi" :item="block" />
                <section v-if="ready(t) && t.guideTask" class="chat-block dialogue-action" aria-label="计划任务">
                  <h2>下一步行动</h2><p>{{t.guideTask.text}}</p><p v-if="t.guideTask.due_date" class="ws-muted">{{t.guideTask.due_date}}</p>
                  <button class="btn btn--primary" :disabled="!!guideSaving" :aria-pressed="guideDone.has(t.guideTask.task_id)" @click="completeGuide(t.guideTask.task_id)">{{guideSaving===t.guideTask.task_id?'正在保存…':guideDone.has(t.guideTask.task_id)?'恢复任务':'标记完成'}}</button>
                </section>
                <section v-if="ready(t) && t.reminder" class="chat-block"><p>{{t.reminder.title}} {{t.reminder.detail}}</p><RouterLink class="ws-text-link" to="/reminders">查看提醒</RouterLink></section>
                <section v-if="ready(t) && t.task" class="chat-block chat-block--action dialogue-action" :style="blockDelay(3)" :class="{ 'is-added': taskAdded(t.task.title) || taskAddedAt === t.task.title }" aria-label="行动建议">
                  <div class="dialogue-action__head"><UiIcon name="action" :size="18" /><h2>建议下一步</h2><span>约 {{ t.task.minutes }} 分钟</span></div>
                  <p class="dialogue-action__title">{{ t.task.title }}</p>
                  <div class="dialogue-action__footer"><RouterLink v-if="taskAdded(t.task.title)" class="btn btn--done" to="/home"><UiIcon name="check" :size="17" />已加入 · 查看行动</RouterLink><button v-else class="btn btn--primary" @click="demo.planChatTask(t.task.title, t.task.minutes); taskAddedAt = t.task.title">加入行动计划<UiIcon name="arrow" :size="17" /></button></div>
                </section>

                <!-- 块五 · 后续问题：你能怎么接下去（只在最后一条、输出结束后出现）。
                     条数不再是"有没有 options"的条件 —— 没有 options 时走兜底三句，
                     所以**每一条回答结束处都有一组可点的问题**（见 script 里的 followUpsOf）。 -->
                <div v-if="ready(t) && i === turns.length - 1" class="chat-block chat-block--follow dialogue-options" :style="blockDelay(4)" aria-label="后续问题">
                  <p>你可以这样继续</p><div class="ws-chat-options"><template v-for="option in followUpsOf(t)" :key="option"><RouterLink v-if="option === '比较方向方案' || option === '查看诊断报告'" class="btn" :to="option === '比较方向方案' ? '/directions' : '/report'">{{ option }}</RouterLink><button v-else type="button" :disabled="thinking || answered(t)" @click="send(option, blocksFor(t).optionRefs.find(item => item.label === option))">{{ option }}</button></template></div>
                </div>
              </div>

              <div v-if="t.materials?.length" class="desk-attachments"><span v-for="m in t.materials" :key="m.id" class="desk-attachment"><UiIcon name="attachment" :size="16" />{{ m.name }} · 附件记录</span></div>
              <footer v-if="t.from === 'host'" class="exp-message-tools dialogue-message__tools"><button class="exp-copy" :aria-label="copiedId === t.id ? copyStatus : '复制顾问回复'" :title="copiedId === t.id ? copyStatus : '复制顾问回复'" :disabled="isLive(t.id)" @click="copyReply(t.id, t.text)"><UiIcon name="copy" :size="16" />{{ copiedId === t.id ? copyLabel : '复制' }}</button></footer>
              <!-- 刷新态：Waiting 时用骨架盖住上一条回答（内容仍在 DOM 里，不是被摘掉）。
                   用 t.id 当 key 是为了让每次等待都从"透明"开始播一次淡入：换 key 会重建节点，
                   leave-transition 拿不到旧节点，于是留下的只有 enter（纯淡入，没有中间态）。 -->
              <SkeletonBlock v-if="isCovered(t.id)" :key="'sk-' + t.id" class="chat-skeleton-cover" variant="text" :lines="3" overlay />
            </div>
          </template>
        </article>
      </template>
      <!-- 失败态（另一条触发路径）：?demo-error=1 让本轮必然失败，可重试。界面上没有"错误状态预览"按钮。
           它是**流里的一条**，不是某条发言的一部分 —— 所以不要塞进上面那条 article 的 body，
           否则它会跑在"复制"工具条下面，读起来像那条回答的脚注。 -->
      <div v-if="errorVisible && !showFailure" class="chat-error" role="alert">
        <div class="chat-error__head"><UiIcon name="info" :size="18" /><strong>这次没有生成成功</strong></div>
        <p>{{ errorText }}你的上一条消息已保留，可以直接重试。</p>
        <div class="chat-error__actions"><button class="btn btn--primary" type="button" @click="retry">重试这一条<UiIcon name="arrow" :size="17" /></button><button class="btn" type="button" @click="errorVisible = false">先不用了</button></div>
      </div>
      <!-- 加载态：等待回复时是骨架，骨架的形状就是即将出现的块（结论 → 支撑 → 说明）。
           这一行现在也是「在场感」的主要落点之一：顶端身份牌删掉之后，
           "顾问正在想"必须在话语即将发生的位置被看见 —— 头像的 thinking 状态、
           名字旁边的状态词、以及骨架本身，三件事说的是同一句话。
           骨架走 SkeletonBlock（组件自己是 aria-hidden），加载状态由这一行的 role="status" 表达。
           首轮提问没有可盖的回答，这一份骨架就是普通形态（不 overlay）。 -->
      <div v-if="thinking" class="chat-turn chat-turn--host chat-turn--thinking" role="status">
        <!-- 状态不再写死：thinking 行与消息级头像、.chat-who__state 用的是同一个 hostState -->
        <AgentAvatar class="chat-turn__avatar" :agent="agentKeyOf(host)" :size="40" :state="hostState" />
        <div class="chat-turn__body">
          <p class="chat-who"><strong>{{ consultantLabel(host) }}</strong><span>{{ agentOf(agentKeyOf(host)).role }}</span><span class="chat-who__state">{{ presenceLabel }}</span></p>
          <!-- 首轮：没有内容可盖 → 普通骨架。已经有回答时这一份不渲染（那一条被 overlay 盖住），
               所以任何时刻屏幕上只有一份骨架 —— 这是 overlay 方案必须守住的唯一约束。 -->
          <template v-if="!coveredTurn">
            <div class="chat-skeleton-block">
              <SkeletonBlock variant="text" :lines="3" />
              <SkeletonBlock variant="card" :columns="2" />
            </div>
          </template>
          <p class="chat-skeleton__label">正在分析咨询内容…</p>
        </div>
      </div>
    </div></div>
    <button v-if="turns.length && !followTail" class="exp-latest" @click="goToLatest"><UiIcon name="down" :size="16" />回到最新消息</button></div>
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ announcement }} {{ copyStatus }}</p>
    <div class="ws-composer">
      <!-- 输入区的触控目标一律 ≥44px（附件移除、添加材料、发送、停止生成） -->
      <ul v-if="attached.length" class="composer-files" aria-label="待发送的附件">
        <li v-for="m in attached" :key="m.id" class="composer-file">
          <UiIcon name="attachment" :size="16" />
          <span class="composer-file__name">{{ m.name }}</span>
          <button type="button" class="composer-file__remove" :aria-label="'移除附件：' + m.name" @click="attached = attached.filter(item => item.id !== m.id)"><UiIcon name="close" :size="16" /></button>
        </li>
      </ul>
      <p v-if="attachmentError" class="ws-field-error" role="alert">{{ attachmentError }}</p>
      <div class="composer-field">
        <form @submit.prevent="send()">
          <textarea ref="input" v-model="draft" rows="1" aria-label="咨询内容" placeholder="说说最想解决的事…" @input="grow" @keydown="keydown" />
          <div class="composer-actions"><DetailPopover title="咨询与资料使用" label="查看咨询与资料使用说明"><p>Enter 发送，Shift + Enter 换行。</p><p>添加材料后会上传至系统，发送消息时一并交给顾问读取。</p></DetailPopover>
            <button type="button" class="composer-action desk-attachment-control" aria-label="添加材料" :disabled="thinking" @click="attachmentInput?.click()"><UiIcon name="attachment" :size="20" /></button>
            <input ref="attachmentInput" type="file" class="sr-only" tabindex="-1" accept=".txt,.csv,.json,.md,.pdf,.docx" @change="attach" />
            <button v-if="canStop" type="button" class="btn composer-stop" @click="stopGeneration"><span class="composer-stop__mark" aria-hidden="true" />停止生成</button>
            <button v-else class="btn btn--primary composer-send" :disabled="!draft.trim()" type="submit">发送<UiIcon name="arrow" :size="17" /></button>
          </div>
        </form>
      </div>
      <!-- 常驻提示改为聚焦时出现：键盘用法在最需要它的时刻才出现，不长期占一行 -->
      <p class="ws-composer__note"><span>Enter 发送 · Shift + Enter 换行</span></p>
      <p v-if="stalled" class="composer-stalled" role="status">已停止生成。已生成的内容保留在对话里，可以继续追问或重新发送。</p>
    </div>
    <!-- shape 显式写成 sheet：`inspector` 是 @deprecated 的旧 prop，而 InfoSheet.vue:54-58 的
         `resolvedShape` 让 `inspector` 的优先级**高于** `shape` —— 两个都传的话 shape 会被静默吃掉。
         所以这里只留 `shape`（实测计算样式见交付说明：类名里不再有 ws-sheet--inspector）。 -->
    <InfoSheet :shape="'sheet'" :open="panel !== null" :title="panel === 'profile' ? '个人画像' : panel === 'sessions' ? '历史对话' : '咨询成果'" @close="panel = null">
      <template v-if="panel === 'profile'"><StatTile label="已知信息" :value="progress.known" :denominator="progress.total" unit="条" :trend="{ label: '还有 ' + progress.gap + ' 项待补充' }" /><p class="ws-muted">可通过咨询继续完善。</p><dl class="ws-stack"><div v-for="f in known" :key="f.key"><dt class="ws-muted">{{ f.label }}</dt><dd>{{ demo.state.profileEdits[f.key] ?? (f.key === 'grade' ? demo.use.scenario.value.grade : f.value) }}</dd></div></dl><RouterLink class="ws-text-link" to="/profile">查看完整档案<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <template v-else-if="panel === 'sessions'"><section v-if="systemData.snapshot"><h3>{{systemData.snapshot.badge.name}} · 已保存的流程状态</h3><DetailPopover v-for="card in systemData.snapshot.pipeline_cards" :key="card.stage" :title="card.title" side="right"><template #trigger>{{card.title}} · {{card.status==='done'?'已完成':card.status==='in_progress'?'进行中':'尚未开始'}}</template><p v-for="theory in card.theory_models" :key="theory.theory_id">{{theory.name}}</p><p v-if="card.current_output">{{Object.values(card.current_output).filter(v=>typeof v==='string').join('；')}}</p></DetailPopover></section><p v-else class="ws-muted">这条旧会话未保存扩展快照；消息仍可查看，新回复会保存完整引导与流程状态。</p><p class="ws-muted">按咨询主题查找历史会话，原有对话内容会保留。</p><button v-for="s in backendDemo.state.sessions" :key="s.task_id" class="desk-session" :aria-pressed="demo.state.currentSessionId === s.task_id" :disabled="thinking" @click="selectSession(s.task_id)"><UiIcon name="chat" /><span><strong>{{ s.task_name }}</strong><small>{{ s.stage_label }} · {{ s.status === 'completed' ? '已结束' : s.status === 'paused' ? '已暂停' : '进行中' }}</small></span><UiIcon name="arrow" :size="16" /></button><p v-if="!backendDemo.state.sessions.length" class="ws-empty ws-muted">暂无历史会话。创建咨询后可在此查看。</p></template>
      <template v-else>
        <section class="ws-section"><h3>画像与相关成果</h3><StatTile label="已知信息" :value="progress.known" :denominator="progress.total" unit="条" /><nav class="ws-related"><RouterLink to="/profile" @click="panel=null">核对个人画像与来源</RouterLink><RouterLink to="/report" @click="panel=null">阅读诊断与依据</RouterLink><RouterLink to="/directions" @click="panel=null">比较方向方案</RouterLink></nav><AssetNotice/></section>
        <!-- 卡片头已经写着「已形成的行动建议」，这块只承担内容，避免重复一个标题 -->
        <StatTile label="已形成的行动建议" :value="planned.length" unit="条" />
        <ul class="ws-mini-list"><li v-for="t in planned" :key="t.id">{{ t.title }} · {{ t.minutes || 0 }} 分钟</li><li v-if="!planned.length">咨询形成具体行动后，将在此显示。</li></ul>
        <!-- 交接记录：DESIGN-LANGUAGE §8 写死"交接是默认展开的说明卡"，所以这里用 `static`
             （不是"记得加折叠"，而是明确它始终可见）。`v-if` 只决定有没有这段记录，不是开合。
             Foldable 的 static 头是 h3 + 面板留白，与这一栏别的小标题同档。 -->
        <Foldable v-if="handoffs.length" static variant="inline" title="顾问交接记录" :count="handoffs.length">
          <ul class="ws-mini-list"><li v-for="h in handoffs" :key="h.to + h.why"><strong>{{ consultantLabel(h.to) }}</strong><p>{{ h.why }}</p></li></ul>
        </Foldable>
        <button v-if="activeTheory" class="ws-text-button" @click="theoryOpen = true">方法依据：{{ activeTheory.name }}<UiIcon name="arrow" :size="16" /></button><RouterLink class="ws-text-link" to="/home">查看行动计划<UiIcon name="arrow" :size="16" /></RouterLink>
        <!-- 「导出记录」的退路：剪贴板不可用（或没权限）时，文本落在这里，用户自己选区复制。
             宁可多一块可选中的文本，也不能让那个按钮点了没反应。 -->
        <section v-if="exportText" class="ws-section">
          <h3>导出文本</h3>
          <p class="ws-muted">下面就是这段咨询的纯文本，可选中复制。</p>
          <pre class="dialogue-export">{{ exportText }}</pre>
        </section>
      </template>

    </InfoSheet>
    <InfoSheet :open="theoryOpen" :title="activeTheory?.name ?? '方法依据'" @close="theoryOpen = false"><p class="ws-muted">咨询使用的方法说明</p><p v-if="theoryError" class="ws-field-error">{{theoryError}}</p><p style="margin-top: var(--sp-4)">{{ activeTheory?.summary }}</p><h3 class="ws-section-title" style="margin-top: var(--sp-5)">应用说明</h3><p style="margin-top: var(--sp-3)">{{ activeTheory?.product_usage }}</p></InfoSheet>
  </section>
</template>
