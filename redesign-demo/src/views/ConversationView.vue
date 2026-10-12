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
import { navigation } from '../lib/layout'
import { consultantLabel } from '../lib/consultant'
import EvidenceList from '../components/EvidenceList.vue'
import WorkspaceMotif from '../components/WorkspaceMotif.vue'
const route = useRoute()
const turns = computed(() => demo.state.chatTurns)
const draft = ref('')
const thinking = ref(false)
const flow = ref<HTMLElement | null>(null)
const input = ref<HTMLTextAreaElement | null>(null)
const panel = ref<'profile' | 'outcomes' | 'sessions' | null>(null)
const attachmentInput = ref<HTMLInputElement | null>(null)
const attachmentError = ref('')
const attached = ref<{ id: string; name: string }[]>([])
const theoryOpen = ref(false)
const activeTheory = computed(() => registry.theoryCards?.[0])
const followTail = ref(true)
const announcement = ref('')
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
const topicLabels: Record<string, { title: string; description: string; icon: string }> = { confused: { title: '兴趣与能力', description: '了解个人特点与适合的领域', icon: 'profile' }, undecided: { title: '方向选择', description: '比较备选方向与决策依据', icon: 'directions' }, how_to_act: { title: '行动规划', description: '将目标转化为具体行动', icon: 'action' }, stuck: { title: '执行调整', description: '分析执行障碍并调整方案', icon: 'review' } }
const starters = registry.taskEntries.filter(t => topicLabels[t.code]).map(t => ({ ...t, ...topicLabels[t.code] }))
const copyStatus = ref('')
const copiedId = ref('')
const copyLabel = ref('复制')
async function copyReply(id: string, text: string) {
  copiedId.value = id
  try { await navigator.clipboard.writeText(text); copyStatus.value = '回复已复制。'; copyLabel.value = '已复制' }
  catch { copyStatus.value = '未能复制，请选中正文手动复制。'; copyLabel.value = '复制失败' }
}
function goToLatest() { followTail.value = true; void scrollToEnd() }
function newSession() {
  if (demo.state.chatBusy) return
  backendDemo.newSession()
  demo.startChatSession([], backendDemo.state.currentSessionId)
  panel.value = null; attached.value = []; draft.value = ''; announcement.value = ''
}
function selectSession(id: string) {
  if (demo.state.chatBusy) return
  if (id !== demo.state.currentSessionId) demo.startChatSession(backendDemo.selectSession(id), id)
  panel.value = null; attached.value = []; draft.value = ''; announcement.value = ''
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
  const request: MessageRequest = { task_id: demo.state.currentSessionId, message: content, client_msg_id: crypto.randomUUID(), option_id: option?.option_id, option_value: option?.value, material_ids: attached.value.map(m => m.id) }
  backendDemo.recordMessage(request)
  append({ from: 'me', text: content, materials: attached.value.map(m => ({ ...m })) })
  attached.value = []
  draft.value = ''
  if (input.value) input.value.style.height = '48px'
  if (content !== '跳过这个问题') demo.noteCollected(2)
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
watch(() => demo.state.currentSessionId, () => {
  draft.value = ''; attached.value = []; attachmentError.value = ''; panel.value = null; announcement.value = ''
  followTail.value = true
  void scrollToEnd()
})
watch(thinking, value => demo.setChatBusy(value), { flush: 'sync' })
watch(() => {
  const last = turns.value[turns.value.length - 1]
  return last ? textOf(last.id, last.text) : ''
}, () => { if (followTail.value) void scrollToEnd() })
onMounted(() => {
  const n = Number(route.query.collected)
  if (Number.isFinite(n) && n > 0) demo.noteCollected(n)
  void scrollToEnd()
})
onUnmounted(() => {
  if (timer) clearTimeout(timer)
  if (pendingContent) reply(pendingContent, false)
  demo.setChatBusy(false)
})
</script>
<template>
  <section class="ws-conversation" aria-label="对话空间">
    <header class="ws-chat-head">
      <div><h1>咨询对话</h1><p>{{ consultantLabel(host) }} · 围绕当前问题开展咨询</p></div>
      <div class="ws-chat-head__tools"><button v-if="navigation.compact.value || navigation.mode.value === 'mobile'" :disabled="thinking" @click="newSession">新对话</button><button v-if="navigation.compact.value || navigation.mode.value === 'mobile'" :disabled="thinking" @click="panel = 'sessions'">历史会话</button><button @click="panel = 'outcomes'">咨询成果</button><button @click="panel = 'profile'">个人画像 {{ progress.known }}/{{ progress.total }}</button></div>
    </header>
    <div class="exp-conversation-body"><div ref="flow" class="ws-chat-flow" tabindex="0" role="log" aria-live="off" aria-label="对话记录" @scroll="followScroll">
      <div v-if="!turns.length" class="ws-chat-welcome">
        <div class="exp-intro"><div><span class="exp-eyebrow">生涯规划与就业指导</span><h2>选择咨询主题</h2><p>选择主题或输入问题，也可补充材料与个人信息。</p></div><WorkspaceMotif /></div>
        <div class="ws-chat-prompts"><button v-for="topic in starters" :key="topic.code" @click="send(topic.label)"><UiIcon :name="topic.icon" :size="22" /><span><strong>{{ topic.title }}</strong><small>{{ topic.description }}</small></span><UiIcon name="arrow" :size="16" /></button></div>
      </div>
      <template v-for="(t, i) in turns" :key="t.id">
        <article v-if="t.handoff" class="ws-handoff">
          <p class="ws-handoff__title">顾问交接 · <strong>{{ consultantLabel(t.handoff.to) }}</strong></p>
          <details class="ws-turn__details"><summary>交接说明</summary><dl><dt>接手顾问</dt><dd>{{ consultantLabel(t.handoff.to) }}</dd><dt>交接原因</dt><dd>{{ t.handoff.why }}</dd><dt>支持依据</dt><dd>{{ t.handoff.basedOn }}</dd></dl></details>
        </article>
        <article v-else class="ws-turn" :class="'ws-turn--' + t.from">
          <p v-if="t.from === 'host' && (i === 0 || turns[i - 1]?.from !== 'host' || turns[i - 1]?.speaker !== t.speaker)" class="ws-turn__speaker"><UiIcon name="chat" :size="18" />{{ consultantLabel(t.speaker) }}</p>
          <p>{{ t.from === 'host' ? textOf(t.id, t.text) : t.text }}</p>
          <div v-if="t.materials?.length" class="desk-attachments"><span v-for="m in t.materials" :key="m.id" class="desk-attachment"><UiIcon name="attachment" :size="16" />{{ m.name }} · 演示附件</span></div>
          <div v-if="t.from === 'host'" class="exp-message-tools"><EvidenceList v-if="t.citations?.length" :items="t.citations" /><button class="exp-copy" :aria-label="copiedId === t.id ? copyStatus : '复制顾问回复'" :title="copiedId === t.id ? copyStatus : '复制顾问回复'" :disabled="isStreaming(t.id)" @click="copyReply(t.id, t.text)"><UiIcon name="copy" :size="14" />{{ copiedId === t.id ? copyLabel : '复制' }}</button></div>
          <div v-if="t.task" class="ws-chat-task"><p>{{ t.task.title }}</p><div class="ws-chat-task__action"><span>约 {{ t.task.minutes }} 分钟</span><button class="btn btn--primary btn--sm" @click="demo.planChatTask(t.task.title, t.task.minutes)">加入行动计划</button></div></div>
          <div v-if="t.options?.length && i === turns.length - 1 && !isStreaming(t.id)" class="ws-chat-options">
            <template v-for="option in t.options" :key="option"><RouterLink v-if="option === '比较方向方案' || option === '查看诊断报告'" class="btn" :to="option === '比较方向方案' ? '/directions' : '/report'">{{ option }}</RouterLink><button v-else :disabled="thinking" @click="send(option, t.optionRefs?.find(item => item.label === option))">{{ option }}</button></template>
          </div>
        </article>
      </template>
      <p v-if="thinking" class="ws-chat-status" role="status">正在分析咨询内容…</p>
    </div>
    <button v-if="turns.length && !followTail" class="exp-latest" @click="goToLatest"><UiIcon name="down" :size="16" />回到最新消息</button></div>
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ announcement }} {{ copyStatus }}</p>
    <div class="ws-composer">
      <div v-if="attached.length" class="desk-attachments"><span v-for="m in attached" :key="m.id" class="desk-attachment"><UiIcon name="attachment" :size="16" />{{ m.name }}<button :aria-label="'移除附件：' + m.name" @click="attached = attached.filter(item => item.id !== m.id)"><UiIcon name="close" :size="14" /></button></span></div>
      <p v-if="attachmentError" class="ws-field-error" role="alert">{{ attachmentError }}</p>
      <form @submit.prevent="send()"><button type="button" class="ws-icon-button desk-attachment-control" aria-label="添加材料" :disabled="thinking" @click="attachmentInput?.click()"><UiIcon name="attachment" :size="20" /></button><input ref="attachmentInput" type="file" class="sr-only" tabindex="-1" accept=".txt,.csv,.json,.md,.pdf,.docx" @change="attach" /><textarea ref="input" v-model="draft" rows="1" aria-label="咨询内容" placeholder="输入咨询内容…" :disabled="thinking" @input="grow" @keydown="keydown" /><button class="btn btn--primary" :disabled="!draft.trim() || thinking" type="submit">{{ thinking ? '处理中' : '发送' }}</button></form>
      <p class="ws-composer__note"><span>演示对话 · 附件只记录名称，不上传</span><span>Enter 发送 · Shift + Enter 换行</span></p>
    </div>
    <InfoSheet inspector :open="panel !== null" :title="panel === 'profile' ? '个人画像' : panel === 'sessions' ? '历史对话' : '咨询成果'" @close="panel = null">
      <template v-if="panel === 'profile'"><p class="ws-muted">已有 {{ progress.known }} 条信息，待补充 {{ progress.gap }} 条。可通过咨询继续完善。</p><div class="ws-progress"><span :style="{ '--value': progress.known / progress.total }" /></div><dl class="ws-stack"><div v-for="f in known" :key="f.key"><dt class="ws-muted">{{ f.label }}</dt><dd>{{ demo.state.profileEdits[f.key] ?? (f.key === 'grade' ? demo.use.scenario.value.grade : f.value) }}</dd></div></dl><RouterLink class="ws-text-link" to="/profile">查看完整档案<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <template v-else-if="panel === 'sessions'"><p class="ws-muted">按咨询主题查找历史会话，原有对话内容会保留。</p><button v-for="s in backendDemo.state.sessions" :key="s.task_id" class="desk-session" :aria-pressed="demo.state.currentSessionId === s.task_id" :disabled="thinking" @click="selectSession(s.task_id)"><UiIcon name="chat" /><span><strong>{{ s.task_name }}</strong><small>{{ s.stage_label }} · {{ s.status === 'completed' ? '已结束' : s.status === 'paused' ? '已暂停' : '进行中' }}</small></span><UiIcon name="arrow" :size="16" /></button><p v-if="!backendDemo.state.sessions.length" class="ws-empty ws-muted">暂无历史会话。创建咨询后可在此查看。</p></template>
      <template v-else><h3 class="ws-section-title">已形成的行动建议</h3><ul class="ws-mini-list"><li v-for="t in planned" :key="t.id">{{ t.title }} · {{ t.minutes || 0 }} 分钟</li><li v-if="!planned.length">咨询形成具体行动后，将在此显示。</li></ul><details v-if="handoffs.length" class="ws-fold"><summary>顾问交接记录<UiIcon name="chevron" /></summary><ul class="ws-mini-list"><li v-for="h in handoffs" :key="h.to + h.why"><strong>{{ consultantLabel(h.to) }}</strong><p>{{ h.why }}</p></li></ul></details><button v-if="activeTheory" class="ws-text-button" @click="theoryOpen = true">方法依据：{{ activeTheory.name }}<UiIcon name="arrow" :size="16" /></button><RouterLink class="ws-text-link" to="/home">查看行动计划<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <p class="ws-demo-note">{{ STUDENT.name }}的预置示例，不代表你的真实档案。</p>
    </InfoSheet>
    <InfoSheet :open="theoryOpen" :title="activeTheory?.name ?? '方法依据'" @close="theoryOpen = false"><p class="ws-muted">方法卡示例 · 来自后端的理论卡配置</p><p style="margin-top: var(--sp-4)">{{ activeTheory?.summary }}</p><h3 class="ws-section-title" style="margin-top: var(--sp-5)">应用说明</h3><p style="margin-top: var(--sp-3)">{{ activeTheory?.product_usage }}</p></InfoSheet>
  </section>
</template>
