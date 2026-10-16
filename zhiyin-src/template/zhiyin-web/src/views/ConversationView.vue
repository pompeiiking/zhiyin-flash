<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { demo, toast } from '../store'
import { backendDemo } from '../lib/backend-demo'
import { auth } from '../lib/auth'
import { skin } from '../lib/theme'
import { navigation } from '../lib/layout'
import { consultantLabel, agentKeyOf } from '../lib/consultant'
import { newSession, openSession, loadShell, systemData } from '../lib/system-data'
import { replyTurns, answerParts } from '../lib/conversation-turns'
import { backendClient } from '../api/backend-client'
import { streamBackend } from '../api/backend-stream'
import type { ConversationTurnView, MessageRequest, TheoryCardView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'
import AgentAvatar from '../components/AgentAvatar.vue'
import UiIcon from '../components/UiIcon.vue'
import ReadableText from '../components/ReadableText.vue'
import DetailPopover from '../components/DetailPopover.vue'
import InfoSheet from '../components/InfoSheet.vue'
import RenderableBlock from '../components/RenderableBlock.vue'
import ConversationProfile from '../components/ConversationProfile.vue'
import '../styles/conversation.css'
const route = useRoute()
const turns = computed(() => demo.state.chatTurns)
const saved = backendDemo.getDraft(demo.state.currentSessionId)
const draft = ref(saved.text), attached = ref(saved.materials.map(m => ({ ...m })))
const selectedOption = ref<NonNullable<ChatTurn['optionRefs']>[number] | null>(null)
const flow = ref<HTMLElement | null>(null), input = ref<HTMLTextAreaElement | null>(null), fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false), thinking = ref(false), stopped = ref(false), followTail = ref(true)
const pending = ref<{ text: string; agent: string; note: string } | null>(null)
const requestError = ref(''), profileError = ref(''), guideSaving = ref('')
const profileOpen = ref(false), historyOpen = ref(false), profileLoading = ref(false)
const theoryCards = ref<Record<string, TheoryCardView>>({}), theoryErrors = ref<Record<string, string>>({})
const theoryLoading = ref<Record<string, boolean>>({})
const desktopProfile = computed(() => navigation.width.value >= 1180 && navigation.mode.value === 'desktop')
const sessions = computed(() => [...backendDemo.state.sessions].sort((a,b) => (b.last_active_at || '').localeCompare(a.last_active_at || '')))
const title = computed(() => backendDemo.currentSession.value?.task_name || '咨询对话')
const host = computed(() => systemData.snapshot?.badge.name || backendDemo.currentSession.value?.lead_agent_name || '咨询顾问')
const starters = computed(() => auth.state.bootstrap?.task_entries ?? [])
const doneTasks = computed(() => new Set((backendDemo.state.liveAction?.phases ?? []).flatMap(p => p.tasks ?? []).filter(t => t.done).map(t => t.task_id)))
let controller: AbortController | null = null, serial = 0, disposed = false
let failedRequest: MessageRequest | null = null
function remember() { backendDemo.saveDraft(demo.state.currentSessionId, draft.value, attached.value, flow.value?.scrollTop ?? null) }
function resizeInput() { if (input.value) { input.value.style.height = 'auto'; input.value.style.height = Math.min(input.value.scrollHeight, 144) + 'px' } }
async function bottom(force = false) { await nextTick(); if (flow.value && (force || followTail.value)) flow.value.scrollTop = flow.value.scrollHeight }
function onScroll() { const el = flow.value; if (el) followTail.value = el.scrollHeight - el.scrollTop - el.clientHeight < 90 }
function fill(text: string, option?: NonNullable<ChatTurn['optionRefs']>[number]) { draft.value = text; selectedOption.value = option ?? null; if (!desktopProfile.value) profileOpen.value = false; void nextTick(() => input.value?.focus()) }
function safeLink(url?: string | null) { try { const u = new URL(url || ''); return ['http:', 'https:'].includes(u.protocol) ? u.href : undefined } catch { return undefined } }
function displayDate(raw: string) { const date = new Date(raw); return Number.isNaN(date.getTime()) ? raw : date.toLocaleString('zh-CN', {month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'}) }
function evidenceCount(t: ChatTurn) { return (t.theory_refs?.length ?? 0) + (t.intel_refs?.length ?? 0) }
async function theory(id: string) { if (theoryCards.value[id] || theoryLoading.value[id]) return; theoryErrors.value[id] = ''; theoryLoading.value[id] = true; try { theoryCards.value[id] = await backendClient.theory(id) } catch (e) { theoryErrors.value[id] = (e as Error).message } finally { theoryLoading.value[id] = false } }
async function refreshProfile() { profileLoading.value = true; profileError.value = ''; try { const result = await backendClient.workspace(); if (!disposed) backendDemo.setWorkspace(result) } catch (e) { if (!disposed) profileError.value = (e as Error).message } finally { profileLoading.value = false } }
async function resume(id: string) { if (thinking.value) return; try { await openSession(id); historyOpen.value = false; pending.value = null; requestError.value = ''; await bottom(true) } catch (e) { requestError.value = (e as Error).message } }
async function create(code?: string) { if (thinking.value || systemData.busy) return; try { await newSession(code); pending.value = null; requestError.value = ''; await loadShell(); input.value?.focus() } catch (e) { requestError.value = (e as Error).message } }
async function start(code: string, label: string) { await create(code); if (!requestError.value) fill(label) }
async function upload(event: Event) {
 const files = Array.from((event.target as HTMLInputElement).files ?? []); uploading.value = true
 const sessionId = demo.state.currentSessionId
 try { for (const file of files) { const material = await backendClient.material(file); if (disposed || sessionId !== demo.state.currentSessionId) return; attached.value.push({ id: material.material_id, name: material.name || file.name }) } }
 catch (e) { requestError.value = (e as Error).message }
 finally { uploading.value = false; if (fileInput.value) fileInput.value.value = '' }
}
async function toggleTask(id: string) { guideSaving.value = id; try { backendDemo.setAction(await backendClient.actionDone({ task_id:id, done:!doneTasks.value.has(id) })) } catch (e) { toast((e as Error).message) } finally { guideSaving.value = '' } }
function stop() { stopped.value = true; controller?.abort() }
async function send(retry = false) {
 if (thinking.value || uploading.value || systemData.busy) return
 const text = retry ? failedRequest?.message : draft.value.trim() || (attached.value.length ? '请结合我上传的材料提供建议。' : '')
 if (!text) return
 const outgoingMaterials = attached.value.map(m => ({ ...m })), outgoingOption = selectedOption.value, outgoingDraft = draft.value
 if (!demo.state.currentSessionId) { await create(); if (!demo.state.currentSessionId || requestError.value) return }
 const sessionId = demo.state.currentSessionId
 const request: MessageRequest = retry && failedRequest ? failedRequest : { task_id:sessionId, message:text, client_msg_id:crypto.randomUUID(), material_ids:outgoingMaterials.map(m => m.id), ...(outgoingOption ? { option_id:outgoingOption.option_id, option_value:outgoingOption.value } : {}) }
 const run = ++serial
 failedRequest = request; requestError.value = ''; stopped.value = false
 controller = new AbortController(); thinking.value = true
 pending.value = { text:'', agent:host.value, note:'正在分析你的问题' }
 if (!retry) { demo.addChatTurn({ id:`${request.client_msg_id}-user`, from:'me', text, materials:outgoingMaterials }); if (draft.value === outgoingDraft) draft.value = ''; attached.value = attached.value.filter(m => !outgoingMaterials.some(s => s.id === m.id)); selectedOption.value = null; remember() }
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
  demo.setChatTurns([...turns.value, ...replyTurns(result, request.client_msg_id || crypto.randomUUID())], sessionId)
  systemData.snapshot = result; pending.value = null; failedRequest = null
  backendDemo.saveTurns(sessionId, demo.state.chatTurns)
  void loadShell(); void refreshProfile(); void bottom()
 } catch (e) { if (run === serial) requestError.value = stopped.value ? '已停止接收。已显示的内容尚未确认完成，可重新读取会话核对结果。' : (e as Error).message }
 finally { if (run === serial) { thinking.value = false; controller = null } }
}
async function copy(text: string) { try { await navigator.clipboard.writeText(text); toast('已复制') } catch { toast('复制失败，请手动选择文字复制。') } }
function keydown(e: KeyboardEvent) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && navigation.width.value > 760) { e.preventDefault(); void send() } }
watch(thinking, busy => demo.setChatBusy(busy), { flush:'sync' })
watch([draft, attached], () => { remember(); void nextTick(resizeInput) }, { deep:true })
watch(() => demo.state.currentSessionId, (_id, previous) => {
 backendDemo.saveDraft(previous, draft.value, attached.value, flow.value?.scrollTop ?? null)
 const data = backendDemo.getDraft(demo.state.currentSessionId); draft.value = data.text; attached.value = data.materials.map(m => ({ ...m }))
 selectedOption.value = null; failedRequest = null; pending.value = null; requestError.value = ''; stopped.value = false; followTail.value = true; void bottom(true)
}, { flush:'sync' })
onMounted(() => {
 if (demo.state.currentSessionId && !systemData.busy) void resume(demo.state.currentSessionId)
 void refreshProfile()
 if (typeof route.query.question === 'string') fill(route.query.question)
 else if (typeof route.query.topic === 'string') fill('我想讨论：' + route.query.topic)
 else if (typeof route.query.label === 'string') fill('我想补充' + route.query.label + '：')
 void bottom(true)
})
onUnmounted(() => { disposed = true; remember(); serial++; controller?.abort(); demo.setChatBusy(false) })
</script>
<template>
<section class="consultation-page" :class="{ 'consultation-page--profile': profileOpen && desktopProfile }" aria-label="咨询对话空间">
 <div class="consult-main">
  <header class="consult-header"><h1 :title="title">{{ title }}</h1><div class="consult-header__actions">
   <button class="consult-icon consult-brand" :aria-label="skin.state.accent === 'blue' ? '切换为校色红' : '切换为校徽蓝'" @click="skin.setAccent(skin.state.accent === 'blue' ? 'red' : 'blue')"><span />{{ skin.state.accent === 'blue' ? '蓝' : '红' }}</button>
   <button class="consult-icon consult-history-button" aria-label="历史会话" :disabled="thinking" @click="historyOpen = true"><UiIcon name="chat" :size="18" /></button>
   <button class="consult-icon" aria-label="新建咨询" :disabled="thinking || systemData.busy" @click="create()"><UiIcon name="plus" :size="19" /></button>
   <button class="consult-icon" aria-label="个人画像" :aria-expanded="profileOpen" @click="profileOpen = !profileOpen"><UiIcon name="profile" :size="19" /><span class="consult-header__label">个人画像</span></button>
  </div></header>
  <div ref="flow" class="consult-flow" @scroll.passive="onScroll">
   <div v-if="systemData.busy" class="consult-loading" role="status">正在读取会话…</div>
   <div v-else-if="!turns.length && !pending" class="consult-intro">
    <AgentAvatar agent="career" :size="64" /><h2>从你现在关心的事开始</h2><p>聊聊兴趣、方向，或一起梳理下一步。</p>
    <div class="consult-topics"><button v-for="(entry,i) in starters" :key="entry.code" @click="start(entry.code, entry.label)"><UiIcon :name="['profile','directions','action','review'][i % 4]" :size="21" /><span>{{ entry.label }}</span><UiIcon name="arrow" :size="17" /></button></div>
    <button v-if="sessions.length" class="consult-resume" @click="resume(sessions[0].task_id)">继续最近的咨询：{{ sessions[0].task_name }}</button>
   </div>
   <div v-else class="consult-messages" :aria-busy="thinking">
    <article v-for="turn in turns" :key="turn.id" class="consult-turn" :class="'consult-turn--' + turn.from">
     <div v-if="turn.from === 'me'" class="consult-user"><p>{{ turn.text }}</p><small v-for="m in turn.materials" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}</small></div>
     <p v-else-if="turn.from === 'system'" class="consult-system">{{ turn.text }}</p>
     <template v-else><AgentAvatar :agent="agentKeyOf(turn.speaker)" :size="38" /><div class="consult-answer">
      <span class="consult-speaker">{{ consultantLabel(turn.speaker || '咨询顾问') }}</span>
      <ReadableText v-if="answerParts(turn.text).lead" :text="answerParts(turn.text).lead" class="consult-prose consult-prose--lead" /><ReadableText v-if="answerParts(turn.text).body" :text="answerParts(turn.text).body" class="consult-prose" />
      <ReadableText v-if="turn.guideText" :text="turn.guideText" class="consult-guide" />
      <DetailPopover v-if="evidenceCount(turn)" title="本轮回复的依据" side="bottom" class="consult-evidence" @update:model-value="open => open && turn.theory_refs?.forEach(r => theory(r.theory_id))"><template #trigger><UiIcon name="shield" :size="15" /><span>查看依据</span><small>{{ evidenceCount(turn) }} 条线索</small></template>
       <div v-for="r in turn.intel_refs" :key="r.id" class="consult-source"><strong>{{ r.title || '资料来源' }}</strong><p v-if="r.source_name">{{ r.source_name }}</p><a v-if="safeLink(r.source_url)" :href="safeLink(r.source_url)" target="_blank" rel="noopener noreferrer">查看原始资料</a></div>
       <div v-for="r in turn.theory_refs" :key="r.theory_id" class="consult-source"><strong>{{ r.name }}</strong><p v-if="theoryCards[r.theory_id]">{{ theoryCards[r.theory_id].summary || '暂无详细方法说明。' }}</p><p v-else-if="theoryLoading[r.theory_id]" role="status">正在读取方法说明…</p><button v-else @click="theory(r.theory_id)">重新读取方法说明</button><p v-if="theoryErrors[r.theory_id]" role="alert">{{ theoryErrors[r.theory_id] }}</p></div>
      </DetailPopover>
      <div v-if="turn.renderables?.length" class="consult-renderables"><RenderableBlock v-for="(block,i) in turn.renderables" :key="i" :item="block" /></div>
      <div v-if="turn.guideTask" class="consult-task"><UiIcon name="action" :size="21" /><div><small>建议行动</small><p>{{ turn.guideTask.text }}</p><small v-if="turn.guideTask.due_date">{{ turn.guideTask.due_date }}</small></div><button :disabled="!!guideSaving" :aria-label="doneTasks.has(turn.guideTask.task_id) ? '恢复任务' : '完成任务'" @click="toggleTask(turn.guideTask.task_id)"><UiIcon :name="doneTasks.has(turn.guideTask.task_id) ? 'check' : 'plus'" :size="19" /></button></div>
      <div v-if="turn.reminder" class="consult-reminder"><UiIcon name="bell" :size="17" /><div><strong>{{ turn.reminder.title }}</strong><p v-if="turn.reminder.detail">{{ turn.reminder.detail }}</p><small v-if="turn.reminder.due_at">{{ displayDate(turn.reminder.due_at) }}</small></div></div>
      <p v-if="turn.question" class="consult-question">{{ turn.question }}</p>
      <div v-if="turn.optionRefs?.length" class="consult-options"><button v-for="option in turn.optionRefs" :key="option.option_id" :disabled="thinking" @click="fill(option.label, option)">{{ option.label }}<UiIcon name="plus" :size="14" /></button></div>
      <button class="consult-copy" aria-label="复制回复" @click="copy([turn.text, turn.guideText, turn.question].filter(Boolean).join('\n\n'))"><UiIcon name="copy" :size="15" /></button>
     </div></template>
    </article>
    <article v-if="pending" class="consult-turn consult-turn--host consult-pending" aria-label="当前回复"><AgentAvatar :agent="agentKeyOf(pending.agent)" :size="38" :state="thinking ? pending.text ? 'speaking' : 'thinking' : 'idle'" /><div class="consult-answer"><span class="consult-speaker">{{ consultantLabel(pending.agent) }}</span><ReadableText v-if="pending.text" :text="pending.text" class="consult-prose" /><p v-else-if="thinking" class="consult-wait"><span class="consult-pulse" />{{ pending.note }}</p><span v-if="thinking && pending.text" class="consult-cursor" aria-label="正在回复" /><small v-if="!thinking">{{ stopped ? '接收已停止' : '回复未完成' }}</small></div></article>
    <div v-if="requestError" class="consult-error" role="alert"><p>{{ requestError }}</p><button v-if="failedRequest && !stopped" @click="send(true)">重新尝试</button><button :disabled="thinking" @click="resume(demo.state.currentSessionId)">重新读取会话</button></div>
   </div>
  </div>
  <footer class="consult-compose-area">
   <button v-if="!followTail" class="consult-latest" @click="followTail = true; bottom(true)"><UiIcon name="down" :size="15" />回到最新消息</button>
   <p v-if="requestError && !turns.length && !pending" role="alert" class="consult-error">{{ requestError }}</p>
   <form class="consult-composer" @submit.prevent="send()">
    <div v-if="attached.length" class="consult-attachments"><span v-for="(m,i) in attached" :key="m.id"><UiIcon name="attachment" :size="14" />{{ m.name }}<button type="button" :aria-label="'移除' + m.name" @click="attached.splice(i,1)"><UiIcon name="close" :size="14" /></button></span></div>
    <textarea ref="input" v-model="draft" rows="1" aria-label="输入咨询内容" placeholder="写下你的想法，也可以补充一份材料…" @input="selectedOption?.label !== draft && (selectedOption = null)" @keydown="keydown" />
    <div class="consult-compose-tools"><input ref="fileInput" type="file" hidden multiple @change="upload" /><button type="button" class="consult-attach" :disabled="uploading || thinking" @click="fileInput?.click()"><UiIcon name="plus" :size="18" />{{ uploading ? '上传中…' : '添加材料' }}</button><span class="consult-send-hint">{{ thinking ? '回复生成中，可先准备下一条消息' : 'Enter 发送 · Shift + Enter 换行' }}</span><button v-if="thinking" type="button" class="consult-send consult-stop" aria-label="停止接收" @click="stop"><span /></button><button v-else type="submit" class="consult-send" aria-label="发送消息" :disabled="(!draft.trim() && !attached.length) || uploading || systemData.busy"><UiIcon name="arrow" :size="20" /></button></div>
   </form>
   <p class="consult-disclaimer">建议供参考，重要决定由你做出。<DetailPopover title="资料使用说明" side="top"><template #trigger><UiIcon name="info" :size="13" /></template><p>材料和对话将按你的资料偏好参与分析。你可以查看、更正个人画像，或调整资料使用范围。</p><RouterLink to="/settings">管理资料偏好</RouterLink></DetailPopover></p>
  </footer>
 </div>
 <ConversationProfile v-if="profileOpen && desktopProfile" :loading="profileLoading" :error="profileError" @close="profileOpen = false" @refresh="refreshProfile" @supplement="fill" />
 <InfoSheet :open="profileOpen && !desktopProfile" title="个人画像" shape="sheet" @close="profileOpen = false"><ConversationProfile :loading="profileLoading" :error="profileError" @close="profileOpen = false" @refresh="refreshProfile" @supplement="fill" /></InfoSheet>
 <InfoSheet :open="historyOpen" title="历史会话" shape="sheet" @close="historyOpen = false"><div class="consult-session-list"><button :disabled="!turns.length" @click="copy(turns.map(t => (t.from === 'me' ? '我' : t.speaker || '系统') + '：' + t.text).join('\n\n'))">复制当前会话记录</button><button v-for="session in sessions" :key="session.task_id" :disabled="thinking || systemData.busy" :aria-pressed="session.task_id === demo.state.currentSessionId" @click="resume(session.task_id)"><strong>{{ session.task_name }}</strong><small>{{ session.last_active_at ? new Date(session.last_active_at).toLocaleDateString('zh-CN') : '' }}</small></button><p v-if="!sessions.length">还没有历史会话。</p></div></InfoSheet>
</section>
</template>
