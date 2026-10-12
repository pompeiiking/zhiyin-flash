<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { demo } from '../store'
import { PROFILE_FIELDS, STUDENT } from '../data/student'
import { useStreaming } from '../lib/motion'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import type { ChatTurn } from '../data/types'
const route = useRoute()
const turns = computed(() => demo.state.chatTurns)
const draft = ref('')
const thinking = ref(false)
const flow = ref<HTMLElement | null>(null)
const input = ref<HTMLTextAreaElement | null>(null)
const panel = ref<'profile' | 'outcomes' | null>(null)
const followTail = ref(true)
const announcement = ref('')
const { stream, textOf, isStreaming } = useStreaming((_id, text) => {
  announcement.value = host.value + '：' + text
})
let timer: ReturnType<typeof setTimeout> | null = null
let pendingContent = ''
let seq = Date.now()
const progress = computed(() => demo.use.profileProgress.value)
const known = computed(() => PROFILE_FIELDS.slice(0, progress.value.known))
const planned = computed(() => [...demo.use.now.value, ...demo.use.waiting.value])
const handoffs = computed(() => turns.value.filter((t) => t.handoff).map((t) => t.handoff!))
const host = computed(() => [...turns.value].reverse().find((t) => t.from === 'host' && t.speaker)?.speaker ?? '了解你情况的人')
const starters = ['还不清楚自己适合什么', '几个方向拿不准', '定了方向，不知道怎么动', '最近有点做不动']
async function scrollToEnd() {
  await nextTick()
  if (flow.value) flow.value.scrollTop = flow.value.scrollHeight
}
function followScroll() {
  if (flow.value) followTail.value = flow.value.scrollHeight - flow.value.scrollTop - flow.value.clientHeight < 64
}
function append(turn: Omit<ChatTurn, 'id'>, animate = true) {
  const complete = { ...turn, id: 'turn-' + (++seq) }
  demo.addChatTurn(complete)
  if (animate && turn.from === 'host' && !turn.handoff) {
    announcement.value = ''
    stream(complete.id, complete.text)
  }
  void scrollToEnd()
}
function reply(content: string, animate = true) {
  let response: Omit<ChatTurn, 'id'>
  let why = '继续了解你的情况'
  if (/卡住|做不动|坚持不了|忘了/.test(content)) {
    why = '你需要先把行动负担降下来'
    response = { from: 'host', speaker: '陪你推进的人', text: '先不用加新任务。把眼前这一件拆到 5 分钟，做完一个最小步骤就算推进了。', task: { title: '先投 1 家半导体方向的工艺岗', minutes: 5 } }
  } else if (/差多少|行不行|够不够/.test(content)) {
    why = '你想了解能力和方向门槛之间的差距'
    response = { from: 'host', speaker: '帮你判断方向的人', text: '示例报告里，呈现能力是 46 分，主攻方向要求 50 分。差 4 分，这是可以先补的一项。完整差距和依据在评估报告里。', options: ['打开评估报告', '先做一件 5 分钟的事'] }
  } else if (/怎么动|下一步|开始做|先动|5 分钟|一直没有开始/.test(content)) {
    why = '你已经开始关心具体怎么行动'
    response = { from: 'host', speaker: '帮你排计划的人', text: '先找一个你信得过的学长，问问这个方向的日常工作。只要发出一条消息，就能完成今天的一小步。', task: { title: '给上一届学长发一条消息，问一句半导体岗日常', minutes: 5 } }
  } else if (/拿不准|选哪个|怎么选|纠结|方向|选错/.test(content)) {
    why = '你开始关心方向之间的差别'
    response = { from: 'host', speaker: '帮你判断方向的人', text: '半导体工艺、新能源和国企检测，这三条路各有长处，也有不同的门槛。先看看各自需要补什么，选哪条由你决定。', options: ['看三条方向的差别', '先做一件 5 分钟的事'] }
  } else {
    response = { from: 'host', speaker: '了解你情况的人', text: content === '跳过这个问题' ? '可以，我们换一个容易回答的。最近有哪件事是你愿意主动花时间做的？' : '我记下了。先不急着下结论：你更怕选错，还是更怕一直没有开始？', options: ['更怕选错', '更怕一直没有开始', '跳过这个问题'] }
  }
  if (host.value !== response.speaker) append({ from: 'host', speaker: response.speaker, text: '接下来由我来接手。', handoff: { to: response.speaker!, why, basedOn: '你刚才的回答与已有档案' } })
  append(response, animate)
}
function send(text?: string) {
  const content = (text ?? draft.value).trim()
  if (!content || thinking.value) return
  followTail.value = true
  append({ from: 'me', text: content })
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
watch(() => turns.value.length, scrollToEnd)
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
})
</script>
<template>
  <section class="ws-conversation" aria-label="对话空间">
    <header class="ws-chat-head">
      <div><h1>对话</h1><p>{{ host }} · 一次只问一个问题</p></div>
      <div class="ws-chat-head__tools"><button @click="panel = 'outcomes'">这次聊出的事</button><button @click="panel = 'profile'">学生档案 {{ progress.known }}/{{ progress.total }}</button></div>
    </header>
    <div ref="flow" class="ws-chat-flow" tabindex="0" role="log" aria-live="off" aria-label="对话记录" @scroll="followScroll">
      <div v-if="!turns.length" class="ws-chat-welcome">
        <h2>先聊聊，你现在最想解决什么？</h2>
        <p>不用先想好答案，也不用准备简历。选一句接近你现在的情况，我们从那里开始。</p>
        <div class="ws-chat-prompts"><button v-for="s in starters" :key="s" @click="send(s)">{{ s }}</button></div>
      </div>
      <template v-for="(t, i) in turns" :key="t.id">
        <article v-if="t.handoff" class="ws-handoff">
          <p class="ws-handoff__title">换人接手了 · <strong>{{ t.handoff.to }}</strong></p>
          <details class="ws-turn__details"><summary>为什么换人</summary><dl><dt>谁接手</dt><dd>{{ t.handoff.to }}</dd><dt>为什么</dt><dd>{{ t.handoff.why }}</dd><dt>凭什么</dt><dd>{{ t.handoff.basedOn }}</dd></dl></details>
        </article>
        <article v-else class="ws-turn" :class="'ws-turn--' + t.from">
          <p v-if="t.from === 'host' && (i === 0 || turns[i - 1]?.from !== 'host' || turns[i - 1]?.speaker !== t.speaker)" class="ws-turn__speaker"><UiIcon name="chat" :size="18" />{{ t.speaker }}</p>
          <p>{{ t.from === 'host' ? textOf(t.id, t.text) : t.text }}</p>
          <details v-if="t.citations?.length" class="ws-turn__details"><summary>查看这条判断的依据</summary><ul><li v-for="c in t.citations" :key="c">{{ c }}</li></ul></details>
          <div v-if="t.task" class="ws-chat-task"><p>{{ t.task.title }}</p><div class="ws-chat-task__action"><span>约 {{ t.task.minutes }} 分钟</span><button class="btn btn--primary btn--sm" @click="demo.planChatTask(t.task.title, t.task.minutes)">排进今天</button></div></div>
          <div v-if="t.options?.length && i === turns.length - 1 && !isStreaming(t.id)" class="ws-chat-options">
            <template v-for="option in t.options" :key="option"><RouterLink v-if="option === '看三条方向的差别' || option === '打开评估报告'" class="btn" :to="option === '看三条方向的差别' ? '/report?focus=choose' : '/report'">{{ option }}</RouterLink><button v-else :disabled="thinking" @click="send(option)">{{ option }}</button></template>
          </div>
        </article>
      </template>
      <p v-if="thinking" class="ws-chat-status" role="status">正在看你的情况…</p>
    </div>
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ announcement }}</p>
    <div class="ws-composer">
      <form @submit.prevent="send()"><textarea ref="input" v-model="draft" rows="1" aria-label="给主理发一句话" placeholder="说说你现在的想法…" :disabled="thinking" @input="grow" @keydown="keydown" /><button class="btn btn--primary" :disabled="!draft.trim() || thinking" type="submit">{{ thinking ? '稍等' : '发送' }}</button></form>
      <p class="ws-composer__note"><span>示例对话 · 答不上来可以跳过</span><span>Enter 发送 · Shift + Enter 换行</span></p>
    </div>
    <InfoSheet :open="panel !== null" :title="panel === 'profile' ? '学生档案' : '这次聊出的事'" @close="panel = null">
      <template v-if="panel === 'profile'"><p class="ws-muted">已了解 {{ progress.known }} 条，还差 {{ progress.gap }} 条。可在后面的对话里慢慢补充。</p><div class="ws-progress"><span :style="{ '--value': progress.known / progress.total }" /></div><dl class="ws-stack"><div v-for="f in known" :key="f.key"><dt class="ws-muted">{{ f.label }}</dt><dd>{{ demo.state.profileEdits[f.key] ?? (f.key === 'grade' ? demo.use.scenario.value.grade : f.value) }}</dd></div></dl><RouterLink class="ws-text-link" to="/profile">查看完整档案<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <template v-else><h3 class="ws-section-title">已有的下一步</h3><ul class="ws-mini-list"><li v-for="t in planned" :key="t.id">{{ t.title }} · {{ t.minutes || 0 }} 分钟</li><li v-if="!planned.length">聊到下一步时，一件具体的事会出现在这里。</li></ul><details v-if="handoffs.length" class="ws-fold"><summary>谁接过手<UiIcon name="chevron" /></summary><ul class="ws-mini-list"><li v-for="h in handoffs" :key="h.to + h.why"><strong>{{ h.to }}</strong><p>{{ h.why }}</p></li></ul></details><RouterLink class="ws-text-link" to="/home">去任务与计划<UiIcon name="arrow" :size="16" /></RouterLink></template>
      <p class="ws-demo-note">{{ STUDENT.name }}的预置示例，不代表你的真实档案。</p>
    </InfoSheet>
  </section>
</template>
