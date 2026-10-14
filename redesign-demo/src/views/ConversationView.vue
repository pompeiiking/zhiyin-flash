<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { demo } from '../store'
import { PROFILE_FIELDS, STUDENT } from '../data/student'
import { useStreaming } from '../lib/motion'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import type { ChatTurn } from '../data/types'
import { backendDemo } from '../lib/backend-demo'
import registry from '../data/backend-registry.json'
import type { GuideOptionView, MessageRequest } from '../api/backend-types'
import { consultantLabel, agentKeyOf } from '../lib/consultant'
import { navigation } from '../lib/layout'
import { agentOf } from '../lib/agents'
import AgentAvatar from '../components/AgentAvatar.vue'
import EvidenceList from '../components/EvidenceList.vue'
import ReadableText from '../components/ReadableText.vue'
import AssetNotice from '../components/AssetNotice.vue'
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
const activeTheory = computed(() => registry.theoryCards?.[0])
const followTail = ref(true)
const announcement = ref('')
/** 「演示数据说明」展开态：解释挂在输入区旁边，不占常驻空间，也不与主行动争位置 */
const composerNote = ref(false)
/**
 * 桌面（宽导航模式）才给右侧 rail 让出一列。
 * 用导航模式而不是纯 width 媒体查询：页面宽度与"壳层是不是窄导航"是一致的，
 * 两者用同一个判据，才不会出现"壳层已经收成窄导航、页面还留着一列 rail"的错位。
 */
const hasRail = computed(() => navigation.mode.value === 'desktop')

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
  return body.slice(0, 44) + '…'
}

/**
 * 数据块（演示）。
 *
 * 真实链路上 renderables 由后端投递；当前 demo 数据不投，所以这里按契约的
 * bars_chart 形状本地造一份，并在卡片上标注"演示数据"——不伪装成真实统计。
 * 只在两条真正谈"匹配 / 差距"的回答上挂，避免变成每句话都配一张图。
 */
function chartFor(text: string, speaker: string | undefined): BarsChart | null {
  if (speaker !== '帮你判断方向的人' && speaker !== '陪你推进的人') return null
  if (/匹配|日常/.test(text)) {
    return {
      unit: '分',
      points: [
        { label: '半导体工艺', value: 72 },
        { label: '新能源材料', value: 61 },
        { label: '材料检测', value: 54 },
      ],
    }
  }
  if (/差距|门槛|够不够|多少/.test(text)) {
    return {
      unit: '分',
      points: [
        { label: '当前水平', value: 46 },
        { label: '方向要求', value: 50 },
      ],
    }
  }
  return null
}

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
  if (!chart && activeTheory.value) {
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
  '演示数据 · ' + chart.points.map(p => `${p.label} ${p.value}${chart.unit}`).join('，')

const { stream, textOf, isStreaming } = useStreaming((_id, text) => {
  announcement.value = consultantLabel(host.value) + '：' + text
})
let timer: ReturnType<typeof setTimeout> | null = null
let pendingContent = ''
let seq = Date.now()
const progress = computed(() => demo.use.profileProgress.value)
const known = computed(() => PROFILE_FIELDS.slice(0, progress.value.known))
const planned = computed(() => [...demo.use.now.value, ...demo.use.waiting.value])
const handoffs = computed(() => turns.value.filter((t) => t.handoff).map((t) => t.handoff!))
const host = computed(() => [...turns.value].reverse().find((t) => t.from === 'host' && t.speaker)?.speaker ?? '了解你情况的人')
const taskAdded = (title: string) => demo.state.tasks.some(task => task.title === title)
const taskAddedAt = ref('')
const topicLabels: Record<string, { title: string; description: string; icon: string }> = { confused: { title: '兴趣与能力', description: '了解个人特点与适合的领域', icon: 'profile' }, undecided: { title: '方向选择', description: '比较备选方向与决策依据', icon: 'directions' }, how_to_act: { title: '行动规划', description: '将目标转化为具体行动', icon: 'action' }, stuck: { title: '执行调整', description: '分析执行障碍并调整方案', icon: 'review' } }
const starters = registry.taskEntries.filter(t => topicLabels[t.code]).map(t => ({ ...t, ...topicLabels[t.code] }))
const copyStatus = ref('')
const copiedId = ref('')
const copyLabel = ref('复制')

/* ---- 错误态：demo 里没有真实失败，但必须可触发、可操作 ----
 * 触发口子只有查询参数 `?demo-error=1`——它**不是产品功能**，界面上不留按钮。
 * 所以这里用一次性快照而不是 computed：进页面时带上参数，这一次咨询就会走失败分支，
 * 之后即使用户把地址栏里的参数删掉，本轮错误态也不会凭空消失。 */
const routeError = ref(false)
/** demo 数据里那条"未能生成"的系统消息：它本身就是可触发的一次真实失败 */
const failureTurn = computed(() => turns.value.find(t => t.from === 'system' && /未能生成/.test(t.text)) ?? null)
const errorVisible = ref(false)
/** 重试之后这条失败记录就不再占位（不改 store，只在本地隐去） */
const retriedIds = ref<string[]>([])
const showFailure = computed(() => !!failureTurn.value && !retriedIds.value.includes(failureTurn.value.id))
const errorText = computed(() => (failureTurn.value?.text ?? '本次未能生成内容。').trim())
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
  const current = streamingTurn.value
  if (current) stopped.value = [...stopped.value, current.id]
  if (thinking.value) { stalled.value = true; thinking.value = false }
  if (timer) { clearTimeout(timer); timer = null }
  announcement.value = '已停止生成。已生成的内容保留，可以继续追问或重新发送。'
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
watch(() => demo.state.currentSessionId, () => { cardGroups.value = {}; stopped.value = []; stalled.value = false; errorVisible.value = false })

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
  return turns.value.some((t) => isStreaming(t.id)) ? 'speaking' : 'idle'
})
/** 状态词：只说"此刻在干什么"，不给角色名（角色名就在同一行的 .chat-who 上） */
const presenceLabel = computed(() =>
  hostState.value === 'thinking' ? '正在分析你的问题' : hostState.value === 'speaking' ? '正在回答' : '在线，等你开口',
)
/** 头部那一行左侧的会话名（可截断；完整名字走 title） */
const sessionName = computed(() => backendDemo.currentSession.value?.task_name || '围绕当前问题开展咨询')
async function copyReply(id: string, text: string) {
  copiedId.value = id
  try { await navigator.clipboard.writeText(text); copyStatus.value = '回复已复制。'; copyLabel.value = '已复制' }
  catch { copyStatus.value = '未能复制，请选中正文手动复制。'; copyLabel.value = '复制失败' }
}
function goToLatest() { followTail.value = true; void scrollToEnd() }
function newSession() {
  if (demo.state.chatBusy) return
  rememberDraft()
  backendDemo.newSession()
  demo.startChatSession([], backendDemo.state.currentSessionId)
  panel.value = null; announcement.value = ''
}
function selectSession(id: string) {
  if (demo.state.chatBusy) return
  rememberDraft()
  if (id !== demo.state.currentSessionId) demo.startChatSession(backendDemo.selectSession(id), id)
  panel.value = null; announcement.value = ''
}
function attach(event: Event) {
  attachmentError.value = ''
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    if (attached.value.length >= 5) throw new Error('每轮最多添加 5 份材料。')
    const receipt = backendDemo.recordMaterial(file)
    attached.value.push({ id: receipt.material_id, name: receipt.name ?? file.name })
  } catch (error) { attachmentError.value = (error as Error).message }
  ;(event.target as HTMLInputElement).value = ''
}
async function scrollToEnd() {
  await nextTick()
  if (flow.value) flow.value.scrollTop = turns.value.length ? flow.value.scrollHeight : 0
}
function followScroll() {
  if (flow.value) followTail.value = flow.value.scrollHeight - flow.value.scrollTop - flow.value.clientHeight < 64
}
function append(turn: Omit<ChatTurn, 'id'>, animate = true) {
  const complete = { ...turn, id: 'turn-' + (++seq), optionRefs: turn.options?.map((label, index) => ({ option_id: 'option-' + seq + '-' + index, label, value: label })) }
  demo.addChatTurn(complete)
  if (animate && turn.from === 'host' && !turn.handoff) {
    announcement.value = ''
    stream(complete.id, complete.text)
  }
  if (followTail.value) void scrollToEnd()
}
function reply(content: string, animate = true) {
  let response: Omit<ChatTurn, 'id'>
  let why = '继续了解你的情况'
  if (/卡住|做不动|坚持不了|忘了/.test(content)) {
    why = '你需要先把行动负担降下来'
    response = { from: 'host', speaker: '陪你推进的人', text: '建议先将当前任务拆分为 5 分钟可完成的步骤，再根据执行结果调整计划。', task: { title: '先投 1 家半导体方向的工艺岗', minutes: 5 } }
  } else if (/差多少|行不行|够不够/.test(content)) {
    why = '你想了解能力和方向门槛之间的差距'
    response = { from: 'host', speaker: '帮你判断方向的人', text: '示例报告里，呈现能力是 46 分，主攻方向要求 50 分。差 4 分，这是可以先补的一项。可在诊断报告中查看具体差距与支持依据。', options: ['查看诊断报告', '制定 5 分钟行动任务'] }
  } else if (/怎么动|下一步|开始做|先动|5 分钟|一直没有开始/.test(content)) {
    why = '你已经开始关心具体怎么行动'
    response = { from: 'host', speaker: '帮你排计划的人', text: '建议联系一位相关专业的学长，了解目标方向的日常工作与岗位要求。可先将访谈作为当前行动任务。', task: { title: '给上一届学长发一条消息，问一句半导体岗日常', minutes: 5 } }
  } else if (/拿不准|选哪个|怎么选|纠结|方向|选错/.test(content)) {
    why = '你开始关心方向之间的差别'
    response = { from: 'host', speaker: '帮你判断方向的人', text: '当前示例包含半导体工艺、新能源与材料检测三个方向。建议比较匹配依据、能力差距及主要风险后进行选择。', options: ['比较方向方案', '制定 5 分钟行动任务'] }
  } else {
    response = { from: 'host', speaker: '了解你情况的人', text: content === '跳过这个问题' ? '已跳过当前问题。近期哪些活动是你愿意主动投入时间的？' : '已记录。对于方向选择，你更关注选择风险，还是执行进度？', options: ['更怕选错', '更怕一直没有开始', '跳过这个问题'] }
  }
  if (host.value !== response.speaker) append({ from: 'host', speaker: response.speaker, text: '将由对应顾问继续处理当前咨询。', handoff: { to: response.speaker!, why, basedOn: '你刚才的回答与已有档案' } })
  append(response, animate)
}
function send(text?: string, option?: GuideOptionView) {
  const content = (text ?? draft.value).trim()
  if (!content || thinking.value) return
  followTail.value = true
  stalled.value = false
  const request: MessageRequest = { task_id: demo.state.currentSessionId, message: content, client_msg_id: crypto.randomUUID(), option_id: option?.option_id, option_value: option?.value, material_ids: attached.value.map(m => m.id) }
  backendDemo.recordMessage(request)
  append({ from: 'me', text: content, materials: attached.value.map(m => ({ ...m })) })
  attached.value = []
  draft.value = ''
  if (input.value) input.value.style.height = '48px'
  if (content !== '跳过这个问题') demo.noteCollected(2)
  if (routeError.value) { errorVisible.value = true; return }
  thinking.value = true
  pendingContent = content
  timer = setTimeout(() => {
    thinking.value = false
    reply(content)
    pendingContent = ''
    timer = null
  }, 520)
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
function rememberDraft() { if (demo.state.authed) backendDemo.saveDraft(demo.state.currentSessionId, draft.value, attached.value, flow.value?.scrollTop ?? null) }
watch(() => demo.state.currentSessionId, (_id, previousId) => {
  if (demo.state.authed) backendDemo.saveDraft(previousId, draft.value, attached.value, flow.value?.scrollTop ?? null)
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
  const question = typeof route.query.question === 'string' ? route.query.question : ''
  if (question && !draft.value) draft.value = question
  const topic = typeof route.query.topic === 'string' ? route.query.topic : ''
  if (topic && !draft.value) draft.value = '我想讨论：' + topic
  const gap = PROFILE_FIELDS.find(f => f.key === route.query.gap)
  const gapLabel = gap?.label || backendDemo.state.liveWorkspace?.profile_panel?.gaps?.find(g=>g.key===route.query.gap)?.label || (typeof route.query.label==='string'?route.query.label:'')
  if (gapLabel && !draft.value) draft.value = '我想补充' + gapLabel + '：'
  const n = Number(route.query.collected)
  if (Number.isFinite(n) && n > 0) demo.noteCollected(n)
  /* 错误态只由查询参数触发（界面上没有按钮）：?demo-error=1 */
  if (route.query['demo-error'] === '1') { routeError.value = true; errorVisible.value = true }
  if (restoredDraft.scroll !== null) void nextTick(() => { if (flow.value) { flow.value.scrollTop = restoredDraft.scroll!; followScroll() } })
  else void scrollToEnd()
})
onUnmounted(() => {
  rememberDraft()
  if (timer) clearTimeout(timer)
  /* 停止生成之后离开页面：那条回复按"已停止"落在原地，不再补一次完整回答 */
  if (pendingContent && !stalled.value) reply(pendingContent, false)
  demo.setChatBusy(false)
})
</script>
<template>
  <section class="ws-conversation dialogue-page" :class="{ 'has-rail': hasRail }" aria-label="对话空间">
    <!--
      头部只有**一行**：会话名 + 演示标识 + 4 个入口。
      「错误态演示」是调试口子 → 只由 ?demo-error=1 触发，界面上不留按钮。
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
    <header class="ws-chat-head">
      <p class="ws-chat-head__session" :title="sessionName">{{ sessionName }}</p>
      <!-- 演示/真实数据的区分不能丢，但留在**这同一行**里，不另起一块 -->
      <span v-if="backendDemo.state.dataMode === 'demo'" class="ws-chat-head__demo" title="本地演示数据：虚构人物与预设结果，不代表真实档案">演示数据</span>
      <nav v-if="!hasRail" class="ws-chat-head__flow" aria-label="这次咨询的产出与依据">
        <button type="button" aria-label="咨询成果" title="咨询成果" @click="panel = 'outcomes'"><UiIcon name="report" :size="18" /><span class="ws-chat-head__label">咨询成果</span></button>
        <button type="button" aria-label="个人画像" title="个人画像" @click="panel = 'profile'"><UiIcon name="profile" :size="18" /><span class="ws-chat-head__label">个人画像</span></button>
      </nav>
      <div class="ws-chat-head__tools">
        <button type="button" :disabled="demo.state.chatBusy" aria-label="新对话" title="新对话" @click="newSession"><UiIcon name="plus" :size="18" /><span class="ws-chat-head__label">新对话</span></button>
        <button type="button" :disabled="demo.state.chatBusy" aria-label="历史会话" title="历史会话" @click="panel = 'sessions'"><UiIcon name="chat" :size="18" /><span class="ws-chat-head__label">历史会话</span></button>
      </div>
    </header>
    <!-- 桌面右侧 rail：产物与依据常驻在旁边，窄屏收起（见 dialogue.css） -->
    <aside class="dialogue-rail" aria-label="这次咨询的产出与依据">
      <button type="button" class="dialogue-rail__item" @click="panel = 'outcomes'">
        <UiIcon name="report" :size="18" />
        <span><strong>咨询成果</strong><small>{{ planned.length ? planned.length + ' 条行动建议' : '还没有形成建议' }}</small></span>
      </button>
      <button type="button" class="dialogue-rail__item" @click="panel = 'profile'">
        <UiIcon name="profile" :size="18" />
        <span><strong>个人画像</strong><small>{{ progress.known }} 项已知 · {{ progress.gap }} 项待补充</small></span>
      </button>
      <p class="dialogue-rail__note">这两项是这次咨询的产出与依据，会话本身只有「新对话 / 历史会话」。</p>
    </aside>
    <div class="exp-conversation-body"><div ref="flow" class="ws-chat-flow" tabindex="0" role="log" aria-live="off" aria-label="对话记录" @scroll="followScroll"><div class="dialogue-thread">
      <div v-if="!turns.length" class="ws-chat-welcome">
        <!--
          【2026-10-14 · P0-3】空态是整页最贵的一屏，原来只有一句标题与四张起步卡：
          "这里有一个顾问"完全没被看见。顶端常驻身份牌删掉之后，第一屏就不该再有
          第二块身份牌 —— 所以这里放的是**这一次咨询的在席者**（会随主理切换而换人），
          而且用的是刚进页时的 idle 形态：睁着眼睛在等你开口。
          它不是被删掉的那块牌的翻版：那块牌是"常驻页头"，首屏过后还在；
          这一块是空态的一部分，消息一出现就被对话本身替代。
        -->
        <div class="dialogue-presence">
          <AgentAvatar :agent="agentKeyOf(host)" :size="96" :state="hostState" />
          <div class="dialogue-presence__intro">
            <p class="dialogue-presence__who">
              <strong>{{ consultantLabel(host) }}</strong>
              <span class="dialogue-presence__state">{{ presenceLabel }}</span>
            </p>
            <p class="dialogue-presence__role">{{ agentOf(agentKeyOf(host)).role }}</p>
          </div>
        </div>
        <div class="exp-intro"><div><h2>从你正在想的事聊起</h2><p>方向还没想清楚也没关系。选一句最像你的，或者直接说说现在的困惑。</p></div></div>
        <div class="ws-chat-prompts"><button v-for="topic in starters" :key="topic.code" @click="send(topic.label)"><UiIcon :name="topic.icon" :size="22" /><span><strong>{{ topic.title }}</strong><small>{{ topic.description }}</small></span><UiIcon name="arrow" :size="16" /></button></div>
      </div>
      <template v-for="(t, i) in turns" :key="t.id">
        <section v-if="t.handoff" class="chat-handoff" aria-label="顾问交接">
          <div class="chat-handoff__flow">
            <!-- 交接卡里的两张脸也是 40px：它是同一种"人"，不该在别处缩成 34px ——
                 一屏里同一个主理出现两种尺寸，读起来是两套头像而不是一个角色 -->
            <AgentAvatar :agent="agentKeyOf(speakerBefore(i))" :size="40" />
            <span class="chat-handoff__arrow" aria-hidden="true"><UiIcon name="arrow" :size="15" /></span>
            <AgentAvatar :agent="agentKeyOf(t.handoff.to)" :size="40" state="speaking" />
          </div>
          <div class="chat-handoff__said">
            <strong>{{ consultantLabel(t.handoff.to) }}接手</strong>
            <p>{{ t.handoff.why }}</p>
            <p class="chat-handoff__basis"><UiIcon name="info" :size="13" />依据：{{ t.handoff.basedOn }}</p>
          </div>
        </section>
        <article v-else class="chat-turn" :class="['chat-turn--' + t.from, { 'chat-turn--cont': !isGroupStart(i) }]" :aria-label="t.from === 'me' ? '你的消息' : consultantLabel(t.speaker) + '的回复'">
          <template v-if="t.from === 'me'">
            <div class="chat-turn__body">
              <div class="chat-bubble chat-bubble--me"><ReadableText :text="t.text" /></div>
              <div v-if="t.materials?.length" class="desk-attachments"><span v-for="m in t.materials" :key="m.id" class="desk-attachment"><UiIcon name="attachment" :size="16" />{{ m.name }} · 演示附件</span></div>
            </div>
          </template>
          <template v-else>
            <AgentAvatar v-if="isGroupStart(i)" class="chat-turn__avatar" :agent="turnAgent(t)" :size="40" :state="isSpeaking(t.id) ? 'speaking' : 'idle'" />
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
                <!-- 块一 · 结论：一句话主张，大字，不等用户去段落里找。
                     层级**只用排印手段**做（字号 + 字重 + 下边缘收束线），不新增"结论"这类
                     结构自述词 —— 用户不需要被告知"这是一条判断"，他需要一眼看出来。 -->
                <section v-if="leadText(t)" class="chat-block chat-block--lead" :style="blockDelay(0)" aria-label="结论">
                  <ReadableText :text="leadText(t)" />
                  <span v-if="isLive(t.id) && !liveDetail(t)" class="chat-caret" aria-hidden="true" />
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
                              <div class="chat-bars__head"><h3>{{ card.label }}</h3><span v-if="card.demo" class="chat-bars__demo">演示数据</span></div>
                              <p class="chat-bars__note">按后端 renderables 契约（kind = bars_chart）绘制；当前示例后端未投递，此处为本地演示数据。</p>
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
                <section v-if="ready(t) && t.task" class="chat-block chat-block--action dialogue-action" :style="blockDelay(3)" :class="{ 'is-added': taskAdded(t.task.title) || taskAddedAt === t.task.title }" aria-label="行动建议">
                  <div class="dialogue-action__head"><UiIcon name="action" :size="18" /><h2>建议下一步</h2><span>约 {{ t.task.minutes }} 分钟</span></div>
                  <p class="dialogue-action__title">{{ t.task.title }}</p>
                  <div class="dialogue-action__footer"><RouterLink v-if="taskAdded(t.task.title)" class="btn btn--done" to="/home"><UiIcon name="check" :size="17" />已加入 · 查看行动</RouterLink><button v-else class="btn btn--primary" @click="demo.planChatTask(t.task.title, t.task.minutes); taskAddedAt = t.task.title"><span class="btn__fx" aria-hidden="true" />加入行动计划<UiIcon name="arrow" :size="17" /></button></div>
                </section>

                <!-- 块五 · 后续问题：你能怎么接下去（只在最后一条、输出结束后出现） -->
                <div v-if="ready(t) && blocksFor(t).options.length && i === turns.length - 1" class="chat-block chat-block--follow dialogue-options" :style="blockDelay(4)" aria-label="回复选项">
                  <p>你可以这样继续</p><div class="ws-chat-options"><template v-for="option in blocksFor(t).options" :key="option"><RouterLink v-if="option === '比较方向方案' || option === '查看诊断报告'" class="btn" :to="option === '比较方向方案' ? '/directions' : '/report'">{{ option }}</RouterLink><button v-else :disabled="thinking" @click="send(option, blocksFor(t).optionRefs.find(item => item.label === option))">{{ option }}</button></template></div>
                </div>
              </div>

              <div v-if="t.materials?.length" class="desk-attachments"><span v-for="m in t.materials" :key="m.id" class="desk-attachment"><UiIcon name="attachment" :size="16" />{{ m.name }} · 演示附件</span></div>
              <footer v-if="t.from === 'host'" class="exp-message-tools dialogue-message__tools"><button class="exp-copy" :aria-label="copiedId === t.id ? copyStatus : '复制顾问回复'" :title="copiedId === t.id ? copyStatus : '复制顾问回复'" :disabled="isLive(t.id)" @click="copyReply(t.id, t.text)"><UiIcon name="copy" :size="16" />{{ copiedId === t.id ? copyLabel : '复制' }}</button></footer>
            </div>
          </template>
        </article>
      </template>
      <!-- 加载态：等待回复时是骨架，骨架的形状就是即将出现的块（结论 → 支撑 → 说明）。
           这一行现在也是「在场感」的主要落点之一：顶端身份牌删掉之后，
           "顾问正在想"必须在话语即将发生的位置被看见 —— 头像的 thinking 状态、
           名字旁边的状态词、以及骨架本身，三件事说的是同一句话。 -->
      <div v-if="thinking" class="chat-turn chat-turn--host chat-turn--thinking" role="status">
        <!-- 状态不再写死：thinking 行与消息级头像、.chat-who__state 用的是同一个 hostState -->
        <AgentAvatar class="chat-turn__avatar" :agent="agentKeyOf(host)" :size="40" :state="hostState" />
        <div class="chat-turn__body">
          <p class="chat-who"><strong>{{ consultantLabel(host) }}</strong><span>{{ agentOf(agentKeyOf(host)).role }}</span><span class="chat-who__state">{{ presenceLabel }}</span></p>
          <div class="chat-skeleton" aria-hidden="true">
            <span class="chat-skeleton__lead" />
            <span class="chat-skeleton__line" />
            <span class="chat-skeleton__line chat-skeleton__line--short" />
            <span class="chat-skeleton__cards"><i /><i /></span>
          </div>
          <p class="chat-skeleton__label">正在分析咨询内容…（回答会分成结论、依据与行动几块，逐块落位）</p>
        </div>
      </div>
      <!-- 错误态（另一条触发路径）：?demo-error=1 让本轮必然失败，可重试。界面上没有"错误态演示"按钮 -->
      <div v-if="errorVisible && !showFailure" class="chat-error" role="alert">
        <div class="chat-error__head"><UiIcon name="info" :size="18" /><strong>这次没有生成成功</strong></div>
        <p>{{ errorText }}你的上一条消息已保留，可以直接重试。</p>
        <div class="chat-error__actions"><button class="btn btn--primary" type="button" @click="retry">重试这一条<UiIcon name="arrow" :size="17" /></button><button class="btn" type="button" @click="errorVisible = false">先不用了</button></div>
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
        <button type="button" class="composer-info" :class="{ 'is-on': composerNote }" :aria-expanded="composerNote" aria-controls="composer-note" :aria-label="composerNote ? '收起演示数据说明' : '演示数据说明'" @click="composerNote = !composerNote"><UiIcon name="info" :size="17" /></button>
        <form @submit.prevent="send()">
          <textarea ref="input" v-model="draft" rows="1" aria-label="咨询内容" placeholder="说说最想解决的事…" @input="grow" @keydown="keydown" />
          <div class="composer-actions">
            <button type="button" class="composer-action desk-attachment-control" aria-label="添加材料" :disabled="thinking" @click="attachmentInput?.click()"><UiIcon name="attachment" :size="20" /></button>
            <input ref="attachmentInput" type="file" class="sr-only" tabindex="-1" accept=".txt,.csv,.json,.md,.pdf,.docx" @change="attach" />
            <button v-if="canStop" type="button" class="btn composer-stop" @click="stopGeneration"><span class="composer-stop__mark" aria-hidden="true" />停止生成</button>
            <button v-else class="btn btn--primary composer-send" :disabled="!draft.trim()" type="submit">发送<UiIcon name="arrow" :size="17" /></button>
          </div>
        </form>
      </div>
      <!-- 常驻提示改为聚焦时出现：键盘用法在最需要它的时刻才出现，不长期占一行 -->
      <p class="ws-composer__note"><span>Enter 发送 · Shift + Enter 换行</span></p>
      <p v-if="composerNote" id="composer-note" class="composer-note">演示对话 · 附件只记录名称，不上传；对话内容是虚构的演示数据，不代表真实档案。</p>
      <p v-if="stalled" class="composer-stalled" role="status">已停止生成。已生成的内容保留在对话里，可以继续追问或重新发送。</p>
    </div>
    <InfoSheet inspector :open="panel !== null" :title="panel === 'profile' ? '个人画像' : panel === 'sessions' ? '历史对话' : '咨询成果'" @close="panel = null">
      <template v-if="panel === 'profile'"><p class="ws-muted">已有 {{ progress.known }} 条信息，待补充 {{ progress.gap }} 条。可通过咨询继续完善。</p><div class="ws-progress"><span :style="{ '--value': progress.known / progress.total }" /></div><dl class="ws-stack"><div v-for="f in known" :key="f.key"><dt class="ws-muted">{{ f.label }}</dt><dd>{{ demo.state.profileEdits[f.key] ?? (f.key === 'grade' ? demo.use.scenario.value.grade : f.value) }}</dd></div></dl><RouterLink class="ws-text-link" to="/profile">查看完整档案<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <template v-else-if="panel === 'sessions'"><p class="ws-muted">按咨询主题查找历史会话，原有对话内容会保留。</p><button v-for="s in backendDemo.state.sessions" :key="s.task_id" class="desk-session" :aria-pressed="demo.state.currentSessionId === s.task_id" :disabled="thinking" @click="selectSession(s.task_id)"><UiIcon name="chat" /><span><strong>{{ s.task_name }}</strong><small>{{ s.stage_label }} · {{ s.status === 'completed' ? '已结束' : s.status === 'paused' ? '已暂停' : '进行中' }}</small></span><UiIcon name="arrow" :size="16" /></button><p v-if="!backendDemo.state.sessions.length" class="ws-empty ws-muted">暂无历史会话。创建咨询后可在此查看。</p></template>
      <template v-else><section class="ws-section"><h3>画像与相关成果</h3><p class="ws-muted">{{ progress.known }} 项已知信息 · {{ progress.gap }} 项待补充</p><nav class="ws-related"><RouterLink to="/profile" @click="panel=null">核对个人画像与来源</RouterLink><RouterLink to="/report" @click="panel=null">阅读诊断与依据</RouterLink><RouterLink to="/directions" @click="panel=null">比较方向方案</RouterLink></nav><AssetNotice/></section><h3 class="ws-section-title">已形成的行动建议</h3><ul class="ws-mini-list"><li v-for="t in planned" :key="t.id">{{ t.title }} · {{ t.minutes || 0 }} 分钟</li><li v-if="!planned.length">咨询形成具体行动后，将在此显示。</li></ul><details v-if="handoffs.length" class="ws-fold"><summary>顾问交接记录<UiIcon name="chevron" /></summary><ul class="ws-mini-list"><li v-for="h in handoffs" :key="h.to + h.why"><strong>{{ consultantLabel(h.to) }}</strong><p>{{ h.why }}</p></li></ul></details><button v-if="activeTheory" class="ws-text-button" @click="theoryOpen = true">方法依据：{{ activeTheory.name }}<UiIcon name="arrow" :size="16" /></button><RouterLink class="ws-text-link" to="/home">查看行动计划<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <p class="ws-demo-note">{{ STUDENT.name }}的预置示例，不代表你的真实档案。</p>
    </InfoSheet>
    <InfoSheet :open="theoryOpen" :title="activeTheory?.name ?? '方法依据'" @close="theoryOpen = false"><p class="ws-muted">方法卡示例 · 来自后端的理论卡配置</p><p style="margin-top: var(--sp-4)">{{ activeTheory?.summary }}</p><h3 class="ws-section-title" style="margin-top: var(--sp-5)">应用说明</h3><p style="margin-top: var(--sp-3)">{{ activeTheory?.product_usage }}</p></InfoSheet>
  </section>
</template>
