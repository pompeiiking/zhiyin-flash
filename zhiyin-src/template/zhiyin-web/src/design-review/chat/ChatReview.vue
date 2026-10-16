<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AgentAvatar from '../../components/AgentAvatar.vue'
import UiIcon from '../../components/UiIcon.vue'
import { WORKSPACE_GROUPS } from '../../lib/workspace-nav'

// An isolated, local design review. No auth, store, API or personal-data writes.
type Scene = 'intro' | 'conversation' | 'evidence'
const params = new URLSearchParams(location.search)
const embedded = params.get('surface') === '1'
const initial = params.get('state') || location.hash.slice(1)
const scenes: { id: Scene; label: string }[] = [
  { id: 'intro', label: '刚进入' }, { id: 'conversation', label: '咨询进行中' }, { id: 'evidence', label: '查看依据' },
]
const scene = ref<Scene>(scenes.some(s => s.id === initial) ? initial as Scene : 'intro')
const device = ref<'desktop' | 'mobile'>('desktop')
const brand = ref(params.get('brand') === 'red' ? 'red' : 'blue')
const preview = ref<HTMLIFrameElement | null>(null)
const reviewStage = ref<HTMLElement | null>(null)
const previewScale = ref(1)
let previewObserver: ResizeObserver | undefined
function fitPreview() { if (reviewStage.value) previewScale.value = Math.min(1, (reviewStage.value.clientWidth - 32) / (device.value === 'desktop' ? 1280 : 390), (reviewStage.value.clientHeight - 32) / (device.value === 'desktop' ? 800 : 844)) }
watch(device, () => void nextTick(fitPreview))
const previewUrl = computed(() => `./chat-review.html?surface=1&state=${scene.value}&brand=${brand.value}`)
const menu = ref<HTMLDialogElement | null>(null)
const entry = ref<HTMLTextAreaElement | null>(null)
const scrollArea = ref<HTMLElement | null>(null)
const sourceButton = ref<HTMLButtonElement | null>(null)
const sourceCard = ref<HTMLElement | null>(null)
const attachmentButton = ref<HTMLButtonElement | null>(null)
const draft = ref('')
const sourceOpen = ref(scene.value === 'evidence')
const attachmentOpen = ref(false)
const attachment = ref(false)
const selectedTopic = ref('方向选择')
const status = ref<'idle' | 'waiting' | 'reading' | 'done' | 'stopped' | 'error'>('idle')
const selectedHistory = ref('direction')
const loadingHistory = ref('')
const done = ref(false)
const preferred = ref('数据分析')
const notice = ref('')
const question = ref('想试数据分析，也在考虑读研。每周只有 10 小时，先做哪件事？')
const previousRounds = ref<{ question: string; lead: string; summary: string; compared: boolean; done: boolean; preferred: string; evidence: boolean }[]>([])
const isWaiting = computed(() => ['waiting', 'reading'].includes(status.value))
const showReply = computed(() => scene.value !== 'intro' && !isWaiting.value && !['stopped','error'].includes(status.value))
const title = computed(() => scene.value === 'intro' ? '新的咨询' : selectedHistory.value === 'project' ? '把项目经历整理成案例' : '数据分析与读研，如何安排')
const histories = [ { id: 'direction', title: '数据分析与读研，如何安排', time: '今天' }, { id: 'project', title: '把项目经历整理成案例', time: '昨天' } ]
const topics = [ { title: '了解自己', icon: 'profile', prompt: '我想从做过的事情里了解自己的兴趣和能力。' }, { title: '比较方向', icon: 'directions', prompt: '想试数据分析，也在考虑读研。每周只有 10 小时，先做哪件事？' }, { title: '制定行动', icon: 'action', prompt: '我想把数据分析的准备工作拆成这周能做的小步骤。' }, { title: '调整节奏', icon: 'review', prompt: '计划有些推进不动，我想找出卡住的原因。' } ]
let timers: ReturnType<typeof setTimeout>[] = []
let announcementTimer: ReturnType<typeof setTimeout> | undefined
function cancelTimers() { timers.forEach(clearTimeout); timers = [] }
function announce(text: string) { notice.value = text; clearTimeout(announcementTimer); announcementTimer = setTimeout(() => notice.value = '', 4000) }
function chooseScene(value: Scene) { scene.value = value; location.hash = value }
function ask(prompt: string) { draft.value = prompt; void nextTick(() => { entry.value?.focus(); resize() }) }
function resize() { if (entry.value) { entry.value.style.height = 'auto'; entry.value.style.height = Math.min(140, entry.value.scrollHeight) + 'px' } }
async function latest() { await nextTick(); scrollArea.value?.scrollTo({ top: scrollArea.value.scrollHeight, behavior: 'auto' }) }
function startReply(text?: string, replay = false) {
  if (isWaiting.value) return
  if (!replay && showReply.value) previousRounds.value.push({question: question.value, lead: selectedHistory.value === 'project' ? '先把一段经历写清楚，再扩展作品集。' : '先完成分析案例，再判断发展方向。', summary: selectedHistory.value === 'project' ? '从校园调研开始，保留问题、过程和结果三个部分。' : '从已有调研经历开始，把每周 10 小时集中到一个小案例。', compared: scene.value === 'evidence' && selectedHistory.value !== 'project', done: done.value, preferred: preferred.value, evidence: false})
  cancelTimers(); loadingHistory.value = ''; sourceOpen.value = false; attachmentOpen.value = false
  question.value = text || draft.value.trim() || question.value
  draft.value = ''; scene.value = 'conversation'; status.value = 'waiting'; done.value = false
  void nextTick(resize); void latest()
  timers.push(setTimeout(() => { status.value = 'reading' }, 1500))
  timers.push(setTimeout(() => { status.value = 'done'; void latest() }, 4200))
}
function stop() { cancelTimers(); status.value = 'stopped'; announce('已停止本次演示，问题已保留。') }
function send() { if (draft.value.trim()) startReply() }
function keyboard(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && matchMedia('(pointer:fine)').matches) { event.preventDefault(); send() }
}
function openHistory(id: string) {
  cancelTimers(); menu.value?.close(); loadingHistory.value = id; sourceOpen.value = false; status.value = 'idle'; previousRounds.value = []
  timers.push(setTimeout(() => {
    selectedHistory.value = id; loadingHistory.value = ''; scene.value = 'conversation'; done.value = false
    question.value = id === 'project' ? '校园调研里，我做了问卷清洗和结果说明。怎样把它整理成一份分析案例？' : '想试数据分析，也在考虑读研。每周只有 10 小时，先做哪件事？'
    void nextTick(() => scrollArea.value?.scrollTo({ top: 0 }))
  }, 400))
}
function fresh() { cancelTimers(); scene.value = 'intro'; status.value = 'idle'; sourceOpen.value = false; draft.value = ''; attachment.value = false; previousRounds.value = []; menu.value?.close() }
async function revealSource() { await nextTick(); sourceCard.value?.scrollIntoView({block:'nearest'}); sourceCard.value?.focus({ preventScroll: true }) }
async function toggleSource() { sourceOpen.value = !sourceOpen.value; if (sourceOpen.value) await revealSource() }
function closeSource() { sourceOpen.value = false; sourceButton.value?.focus({ preventScroll: true }) }
function outside(event: PointerEvent) {
  const target = event.target as Node
  if (sourceOpen.value && !sourceCard.value?.contains(target) && !sourceButton.value?.contains(target)) sourceOpen.value = false
}
function escape(event: KeyboardEvent) { if (event.key === 'Escape') { if (sourceOpen.value) closeSource(); attachmentOpen.value = false } }
function receive(event: MessageEvent) {
  if (event.origin !== location.origin || event.source !== window.parent) return
  if (event.data?.type === 'chat-review-replay') startReply(undefined, true)
  if (event.data?.type === 'chat-review-error') { cancelTimers(); scene.value = 'conversation'; status.value = 'error'; sourceOpen.value = false }
}
function replay() { preview.value?.contentWindow?.postMessage({type:'chat-review-replay'},location.origin) }
function fail() { preview.value?.contentWindow?.postMessage({type:'chat-review-error'},location.origin) }
onMounted(() => { document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape); window.addEventListener('message', receive); if (sourceOpen.value) void revealSource(); if (reviewStage.value) { previewObserver = new ResizeObserver(fitPreview); previewObserver.observe(reviewStage.value); fitPreview() } })
onBeforeUnmount(() => { cancelTimers(); clearTimeout(announcementTimer); previewObserver?.disconnect(); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); window.removeEventListener('message', receive) })
</script>

<template>
  <div v-if="!embedded" class="review-board">
    <header class="review-toolbar">
      <div class="review-name"><strong>对话页方案</strong><span>示例内容 · 不连接个人数据</span></div>
      <div class="scene-tabs" aria-label="设计状态"><button v-for="s in scenes" :key="s.id" :aria-pressed="scene === s.id" @click="chooseScene(s.id)">{{ s.label }}</button></div>
      <div class="review-controls">
        <div class="device-tabs" aria-label="预览尺寸"><button :aria-pressed="device === 'desktop'" @click="device = 'desktop'">桌面</button><button :aria-pressed="device === 'mobile'" @click="device = 'mobile'">手机</button></div>
        <button class="brand-switch" @click="brand = brand === 'blue' ? 'red' : 'blue'">{{ brand === 'blue' ? '切换河大红' : '切换校徽蓝' }}</button>
      </div>
    </header>
    <div class="review-help"><span>{{ scene === 'intro' ? '选择话题填入输入框，再发送；左侧历史可切换。' : scene === 'conversation' ? '体验一轮等待、回复与卡片出现；可停止，也可操作行动卡。' : '点击“查看依据”展开或关闭小卡片；手机在消息附近展开。' }}</span><div><button @click="replay">体验等待与生成</button><button @click="fail">查看失败态</button><a href="/#/chat">返回正式对话</a></div></div>
    <div ref="reviewStage" class="review-stage" :class="'review-stage--' + device" :style="{'--preview-scale': previewScale}"><iframe :key="device" ref="preview" :src="previewUrl" title="对话页交互方案" /></div>
  </div>
  <div v-else class="chat-design" :data-brand="brand">
    <aside class="design-sidebar" aria-label="功能导航与历史会话">
      <div class="design-brand"><span>职</span><strong>职引</strong><small>河北大学</small></div>
      <button class="new-chat" @click="fresh"><UiIcon name="plus" :size="18" />新建咨询</button>
      <div class="sidebar-nav">
        <div class="nav-current"><UiIcon name="chat" :size="19" />咨询对话</div>
        <section v-for="group in WORKSPACE_GROUPS" :key="group.key"><h2>{{ group.label }}</h2><a v-for="item in group.items" :key="item.key" :href="'/#' + item.to" target="_top"><UiIcon :name="item.icon" :size="17" />{{ item.label }}</a></section>
      </div>
      <section class="history-list" aria-label="历史会话"><h2>历史会话 <span>2</span></h2><button v-for="h in histories" :key="h.id" :aria-pressed="scene !== 'intro' && selectedHistory === h.id" @click="openHistory(h.id)"><span>{{ h.title }}</span><small>{{ loadingHistory === h.id ? '读取中…' : h.time }}</small></button></section>
      <div class="sidebar-person"><span>林</span><div><strong>林知夏</strong><small>应用统计学 · 大三</small></div><button aria-label="切换红蓝品牌色" @click="brand = brand === 'blue' ? 'red' : 'blue'"><UiIcon name="settings" :size="19" /></button></div>
    </aside>

    <main class="consultation">
      <header class="conversation-header"><button class="mobile-menu icon-button" aria-label="打开导航与历史会话" @click="menu?.showModal()"><UiIcon name="menu" /></button><div class="conversation-heading"><small>咨询对话</small><h1>{{ title }}</h1></div><div class="header-actions"><button class="theme-button" @click="brand = brand === 'blue' ? 'red' : 'blue'"><i />{{ brand === 'blue' ? '校徽蓝' : '河大红' }}</button><button class="mobile-new icon-button" aria-label="新建咨询" @click="fresh"><UiIcon name="plus" /></button></div></header>
      <div ref="scrollArea" class="conversation-scroll" :class="{ 'is-intro': scene === 'intro' }" :aria-busy="!!loadingHistory">
        <div v-if="loadingHistory" class="history-loading" role="status"><span class="activity-dot" />正在读取这段咨询…</div>
        <section v-else-if="scene === 'intro'" class="opening">
          <div class="opening-identity"><AgentAvatar agent="profile_analyst" :size="64" /><span>信息采集顾问</span></div>
          <h2>从你想解决的问题开始</h2>
          <p class="opening-subtitle">可以先聊一件事，也可以从下面选一个方向。</p>
          <div class="topic-choices"><button v-for="topic in topics" :key="topic.title" @click="selectedTopic = topic.title; ask(topic.prompt)"><UiIcon :name="topic.icon" :size="23" /><span>{{ topic.title }}</span><UiIcon name="arrow" :size="17" /></button></div>
          <div class="resume-line"><UiIcon name="review" :size="18" /><div><span>继续上次的咨询</span><button @click="openHistory('direction')">数据分析与读研，如何安排 <UiIcon name="arrow" :size="15" /></button></div></div>
        </section>
        <section v-else class="message-thread" aria-label="对话消息">
          <div class="session-date">{{ selectedHistory === 'project' ? '昨天' : '今天' }}</div>
          <div v-for="(round,index) in previousRounds" :key="index" class="previous-round"><article class="user-message"><p>{{ round.question }}</p></article><div class="previous-reply"><AgentAvatar agent="career_advisor" :size="38" /><div class="previous-body"><div class="reply-identity"><strong>职业分析顾问</strong><span>与你一起梳理</span></div><p class="reply-lead">{{ round.lead }}</p><p class="reply-summary">{{ round.summary }}</p><button class="source-trigger" :aria-expanded="round.evidence" @click="round.evidence = !round.evidence"><UiIcon name="shield" :size="15" />查看依据 <span>2 条线索</span></button><div v-if="round.evidence" class="previous-evidence"><strong>这条建议的依据</strong><p>校园调研经历；每周可投入 10 小时。岗位适配性仍需结合实际案例核对。</p><button @click="round.evidence = false">关闭依据</button></div><div v-if="round.compared" class="direction-comparison"><button v-for="direction in ['数据分析','统计学读研']" :key="direction" :aria-pressed="round.preferred === direction" @click="round.preferred = direction; ask('我想继续讨论' + direction)"><div class="direction-title"><strong>{{ direction }}</strong></div><p>{{ direction === '数据分析' ? '验证：能否用数据解释业务问题' : '验证：是否喜欢深入研究问题' }}</p><span class="direction-detail">{{ direction === '数据分析' ? '用一份完整案例检验' : '从一篇论文和导师交流开始' }}</span></button></div><div v-else class="action-object" :class="{'is-done':round.done}"><div class="action-top"><span><UiIcon name="action" :size="16" />下一步行动</span><small>{{ round.done ? '已完成' : '待完成' }}</small></div><strong>梳理一段项目经历</strong><p>写清问题、处理过程和结果，各用一句话。</p><div class="action-bottom"><span><UiIcon name="calendar" :size="15" />本周</span><button :aria-pressed="round.done" @click="round.done = !round.done">{{ round.done ? '已完成 · 撤销' : '标记完成' }}</button></div></div><p class="next-question">哪一段经历最适合先整理？</p><div class="reply-options"><button @click="ask('先从校园调研开始梳理。')">校园调研</button><button @click="ask('先从课程项目开始梳理。')">课程项目</button><button @click="ask('我想先说明另一个情况：')">补充其他情况</button></div></div></div></div>
          <article class="user-message" aria-label="你的消息"><p>{{ question }}</p><span v-if="attachment" class="attached-message"><UiIcon name="attachment" :size="14" />项目记录.pdf</span></article>
          <article class="assistant-message" aria-label="本轮顾问回复">
            <AgentAvatar class="message-avatar" :agent="selectedHistory === 'project' ? 'path_planner' : 'career_advisor'" :state="isWaiting ? 'thinking' : status === 'done' ? 'done' : 'idle'" :size="38" />
            <div class="reply-body">
              <div class="reply-identity"><strong>{{ selectedHistory === 'project' ? '行动规划顾问' : '职业分析顾问' }}</strong><span v-if="isWaiting">正在回复</span><span v-else>与你一起梳理</span></div>
              <div v-if="isWaiting" class="reply-progress" role="status" aria-live="polite"><div class="progress-line"><span class="activity-dot" /><strong>{{ status === 'waiting' ? '已收到，正在整理你的问题' : '正在整理回复与下一步建议' }}</strong></div><p>回复会在这里出现，你仍可回看之前的内容。</p><div class="progress-trace"><span>问题已收到</span><i /><span>等待回复</span></div></div>
              <div v-else-if="status === 'stopped'" class="reply-stopped" role="status"><p>已停止回复，问题已保留。</p><button @click="startReply()">重新生成 <UiIcon name="arrow" :size="16" /></button></div>
              <div v-else-if="status === 'error'" class="reply-stopped reply-error" role="alert"><strong>暂时未收到回复</strong><p>你的问题已保留，可以重试这一轮。</p><button @click="startReply()">重试这一轮 <UiIcon name="arrow" :size="16" /></button></div>
              <div v-else-if="showReply" class="reply-content">
                <p class="reply-lead">{{ selectedHistory === 'project' ? '先把一段经历写清楚，再扩展作品集。' : '先完成分析案例，再判断发展方向。' }}</p>
                <p class="reply-summary">{{ selectedHistory === 'project' ? '从校园调研开始，保留问题、过程和结果三个部分。' : '从已有调研经历开始，把每周 10 小时集中到一个小案例。' }}</p>
                <div class="source-anchor">
                  <button ref="sourceButton" class="source-trigger" :aria-expanded="sourceOpen" aria-controls="source-card" @click="toggleSource"><span class="source-symbol"><UiIcon name="shield" :size="15" /></span>查看依据 <span>2 条线索</span><UiIcon :name="sourceOpen ? 'close' : 'chevron'" :size="14" /></button>
                  <aside v-if="sourceOpen" id="source-card" ref="sourceCard" class="source-card" tabindex="-1" role="region" aria-label="这条建议的依据">
                    <header><div><span>对应这条建议</span><h3>为什么先做分析案例</h3></div><button class="icon-button" aria-label="关闭依据" @click="closeSource"><UiIcon name="close" :size="18" /></button></header>
                    <div class="source-item"><div><UiIcon name="chat" :size="16" /><strong>已有经历</strong></div><blockquote>“校园调研中，我负责问卷清洗和结果说明。”</blockquote><small>前次咨询 · 你提供的经历</small></div>
                    <div class="source-item"><div><UiIcon name="calendar" :size="16" /><strong>可投入时间</strong></div><p>每周可投入 10 小时。</p><small>本次提问</small></div>
                    <div class="source-uncertainty"><span>尚待验证</span><p>岗位适配性仍需结合实际案例与岗位信息核对。</p></div>
                    <button class="correct-source" @click="closeSource(); ask('我想更正用于这条建议的信息：')">补充或更正信息 <UiIcon name="arrow" :size="16" /></button>
                  </aside>
                </div>

                <div v-if="scene === 'evidence' && selectedHistory !== 'project'" class="direction-comparison" aria-label="选择继续讨论的方向">
                  <button v-for="direction in ['数据分析','统计学读研']" :key="direction" :aria-pressed="preferred === direction" @click="preferred = direction"><div class="direction-title"><strong>{{ direction }}</strong><span class="selection-mark"><UiIcon v-if="preferred === direction" name="check" :size="12" /></span></div><p>{{ direction === '数据分析' ? '验证：能否用数据解释业务问题' : '验证：是否喜欢深入研究问题' }}</p><span class="direction-detail">{{ direction === '数据分析' ? '用一份完整案例检验' : '从一篇论文和导师交流开始' }}</span></button>
                </div>
                <div v-else class="action-object" :class="{ 'is-done': done }" aria-label="下一步行动">
                  <div class="action-top"><span><UiIcon name="action" :size="16" />{{ preferred === '统计学读研' && selectedHistory !== 'project' ? '继续讨论：统计学读研' : '下一步行动' }}</span><small>{{ done ? '已完成' : '待完成' }}</small></div>
                  <strong>{{ preferred === '统计学读研' && selectedHistory !== 'project' ? '选一篇感兴趣的论文，记录一个想深入的问题' : '梳理一段项目经历' }}</strong>
                  <p>{{ preferred === '统计学读研' && selectedHistory !== 'project' ? '先明确研究兴趣，再与导师讨论适合的准备路径。' : '写清问题、处理过程和结果，各用一句话。' }}</p>
                  <div class="action-bottom"><span><UiIcon name="calendar" :size="15" />本周</span><button :aria-pressed="done" @click="done = !done; announce(done ? '演示：已标记完成，未写入实际计划。' : '演示：已恢复为待完成。')"><UiIcon :name="done ? 'check' : 'plus'" :size="16" />{{ done ? '已完成 · 撤销' : '标记完成' }}</button></div>
                </div>
                <p class="next-question">{{ preferred === '统计学读研' ? '你有特别想继续研究的问题吗？' : '哪一段经历最适合先整理？' }}</p>
                <div class="reply-options"><button @click="ask('先从校园调研开始梳理。')">校园调研</button><button @click="ask('先从课程项目开始梳理。')">课程项目</button><button @click="ask('我想先说明另一个情况：')">补充其他情况</button></div>
              </div>
            </div>
          </article>
        </section>
      </div>

      <footer class="composer-dock">
        <div class="composer" :class="{ 'has-focus': !!draft }">
          <div v-if="attachment" class="file-pill"><UiIcon name="attachment" :size="16" /><span>项目记录.pdf</span><button aria-label="移除示例附件" @click="attachment = false"><UiIcon name="close" :size="15" /></button></div>
          <label class="sr-only" for="consultation-draft">咨询内容</label><textarea id="consultation-draft" ref="entry" v-model="draft" rows="1" :placeholder="scene === 'intro' ? '说说你正在考虑的事…' : '继续聊聊，或补充你的想法…'" @input="resize" @keydown="keyboard" />
          <div class="composer-bottom"><div class="composer-left"><div class="attachment-anchor"><button ref="attachmentButton" class="add-material" :aria-expanded="attachmentOpen" @click="attachmentOpen = !attachmentOpen"><UiIcon name="plus" :size="19" /><span>补充材料</span></button><div v-if="attachmentOpen" class="attachment-menu"><strong>体验材料展示</strong><p>使用示例附件，不上传文件。</p><button @click="attachment = true; attachmentOpen = false; attachmentButton?.focus()"><UiIcon name="attachment" :size="17" />添加项目记录.pdf</button></div></div><span v-if="scene === 'intro'" class="composer-topic">{{ selectedTopic }}</span></div><button v-if="isWaiting" class="stop-button" @click="stop"><span />停止回复</button><button v-else class="send-button" :disabled="!draft.trim() || !!loadingHistory" @click="send"><span>发送</span><UiIcon name="arrow" :size="18" /></button></div>
        </div>
        <div class="composer-caption"><span>个人信息按需补充，重要建议请结合实际核对</span><span class="desktop-hint">Enter 发送 · Shift + Enter 换行</span></div>
      </footer>
    </main>
    <div class="preview-toast" role="status" aria-live="polite" v-if="notice">{{ notice }}</div>
    <dialog ref="menu" class="navigation-drawer" @click="event => { if (event.target === menu) menu?.close() }">
      <header><strong>职引 · 咨询空间</strong><button class="icon-button" aria-label="关闭导航" @click="menu?.close()"><UiIcon name="close" /></button></header>
      <button class="new-chat" @click="fresh"><UiIcon name="plus" :size="18" />新建咨询</button>
      <nav aria-label="手机功能导航"><div class="nav-current"><UiIcon name="chat" :size="18" />咨询对话</div><section v-for="group in WORKSPACE_GROUPS" :key="group.key"><h2>{{ group.label }}</h2><div><a v-for="item in group.items" :key="item.key" :href="'/#'+item.to" target="_top">{{ item.label }}</a></div></section></nav>
      <section class="history-list" aria-label="手机历史会话"><h2>历史会话</h2><button v-for="h in histories" :key="h.id" @click="openHistory(h.id)"><span>{{ h.title }}</span><small>{{ h.time }}</small></button></section>
    </dialog>
  </div>
</template>
