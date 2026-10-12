<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { demo } from '../store'
import { GUIDES, FALLBACK_COPY, EMPTY_COPY } from '../data/copy'
import { CHAT_TURNS, STUDENT } from '../data/student'
import GuideNote from '../components/GuideNote.vue'
import CollectRail from '../components/CollectRail.vue'
import ChatOutline from '../components/ChatOutline.vue'
import { useStreaming } from '../lib/motion'
import type { ChatTurn } from '../data/types'

/**
 * 对话。
 *
 * 这里最要紧的两条产品口径：
 *   1. 一次只问一个问题，能用点选项就不要让人打字（7.4）
 *   2. 换主理必须有一张交接卡：谁接手、凭什么、为什么 —— 三件事齐全（7.4）
 *
 * 另外把文档 14.2 的「话术表」做成了真的规则：
 * 关键词命中就换环节、换主理，且这一步不调模型（产品原文如此）。
 */

const turns = ref<ChatTurn[]>(CHAT_TURNS.map((t) => ({ ...t })))
const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
let seq = 100

/**
 * 动效取向：
 *   · 主理的回答**逐字出来**（不是整段"啪"地出现）—— 这不是装饰，是把"系统在生成"变得可理解。
 *   · 生成中显示三点脉冲（CSS 动画，跑在主线程之外，加载时也不掉帧）。
 *   · 用户自己的消息**不做入场动画** —— 那是他自己刚打的，早就在屏幕上了。
 */
const { stream, textOf, isStreaming } = useStreaming()
const thinking = ref(false)

/** 文档 14.2 的话术表：命中哪一类词，就进哪一环、换哪一位主理 */
const RULES: { kw: string[]; host: string; why: string; text: string; options?: string[] }[] = [
  {
    kw: ['不知道', '迷茫', '不清楚', '说不上', '不确定'],
    host: '了解你情况的人',
    why: '你还在"我是谁"这一步，不是"选哪个"',
    text: '那先把"你是谁"立起来。我问你一个问题就够 —— 你更怕选错，还是更怕一直不定？',
    options: ['更怕选错', '更怕一直不定'],
  },
  {
    kw: ['行不行', '差多少', '够不够', '有没有希望'],
    host: '帮你判断方向的人',
    why: '你在问"差距"，这属于判断，不属于采集',
    text: '差距能算出来。你现在的呈现能力是 46 分，两条主攻方向都要求 50 分以上 —— 差 4 分，是补起来最快的一个。',
  },
  {
    kw: ['拿不准', '选哪个', '怎么选', '犹豫', '纠结'],
    host: '帮你判断方向的人',
    why: '你已经有选项了，缺的是比对',
    text: '我不替你选。我把三条方向的差别和风险摆出来：半导体工艺这条专业与兴趣都对得上，但缺一段产线经历；新能源在扩招，研发岗多数要研究生；国企检测岗稳，但和你"想做东西"的兴趣相反。',
    options: ['看三条方向的差别', '先做一件 5 分钟的事'],
  },
  {
    kw: ['怎么动', '从哪下手', '下一步', '开始做', '怎么办'],
    host: '帮你排计划的人',
    why: '你的问题已经不是"选哪个"，而是"先做什么"',
    text: '先做一件 15 分钟能做完的：把简历第一页的封面表述改成"工艺方向"。你前 5 家都会先看这一页。',
  },
  {
    kw: ['卡住', '没进展', '做不动', '坚持不了', '忘了'],
    host: '陪你推进的人',
    why: '停滞的问题不该继续加计划，该往回看',
    text: '那就别加新任务了。上次那条"投 3 家"确实太大 —— 我把它拆成"先投 1 家"，5 分钟。做不动通常不是你的问题，是任务太大。',
  },
]

const currentHost = computed(() => {
  for (let i = turns.value.length - 1; i >= 0; i -= 1) {
    const t = turns.value[i]
    if (t.from === 'host' && t.speaker) return t.speaker
  }
  return STUDENT.currentHost
})

async function scrollToEnd() {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

function pushSystem(text: string) {
  turns.value.push({ id: `s${(seq += 1)}`, from: 'system', text })
}

/** 把一条主理消息推上去，并让它逐字出来 */
function pushHost(turn: Omit<ChatTurn, 'id'>): ChatTurn {
  const id = `h${(seq += 1)}`
  const full = { ...turn, id } as ChatTurn
  turns.value.push(full)
  void scrollToEnd()
  stream(id, full.text)
  return full
}

function reply(input: string) {
  const rule = RULES.find((r) => r.kw.some((k) => input.includes(k)))
  if (!rule) {
    pushSystem(FALLBACK_COPY.noExternalFact)
    pushHost({
      from: 'host',
      speaker: currentHost.value,
      text: '我先把这句记下来。为了不给你一个空泛的结论，我想先确认一件事：你现在最想解决的是"选哪个"，还是"先动起来"？',
      options: ['选哪个', '先动起来'],
    })
    return
  }

  if (rule.host !== currentHost.value) {
    pushHost({
      from: 'host',
      speaker: rule.host,
      text: '接下来由我接手。',
      handoff: { to: rule.host, why: rule.why, basedOn: '你刚说的这句话 + 已有的 12 条了解' },
    })
  }

  pushHost({
    from: 'host',
    speaker: rule.host,
    text: rule.text,
    options: rule.options,
  })
}

function send(text?: string) {
  const content = (text ?? draft.value).trim()
  if (!content) return
  turns.value.push({ id: `m${(seq += 1)}`, from: 'me', text: content })
  draft.value = ''
  resetComposer()
  void scrollToEnd()

  // 答一轮 = 画像多两条：这是"随信息采集同步推进"的推进点。
  // 导航底部那条进度线与右侧栏读的是同一个 store 值，所以三处同时动。
  demo.noteCollected(2)

  // 不假装秒回：先给三点脉冲，再出结果
  thinking.value = true
  setTimeout(() => {
    thinking.value = false
    reply(content)
  }, 520)
}

/**
 * 输入框自动增高（上限 240px）：
 * 生涯规划的追问经常要写两三句，一个单行框会把人的话截断。
 * Enter 发送、Shift+Enter 换行 —— 这两条是国内用户最习惯的一版。
 */
const composerEl = ref<HTMLTextAreaElement | null>(null)
const COMPOSER_MAX = 240

function resetComposer() {
  const el = composerEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = '44px'
}

function autoGrow() {
  const el = composerEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX)}px`
}

function onComposerKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="chat">
    <header class="chat__head">
      <div>
        <h1 class="page__title" style="font-size: var(--fs-20)">对话</h1>
        <p class="chat__host">
          现在是谁在帮你 ·
          <strong>{{ currentHost }}</strong>
          <span v-if="demo.state.grade !== 'junior'" class="chat__grade">
            这段对话是「大三」那次聊的 —— 切年级只换工作台与计划，不重放对话
          </span>
        </p>
      </div>
      <RouterLink class="btn btn--sm" to="/profile">看学生档案</RouterLink>
    </header>

    <!--
      两侧栏：左边是"这次聊出来的"（谁接过手、产出了什么），右边是"对你的了解"。
      一进一出，两边都有真事做 —— 而不是拿装饰去填那几百像素的空白。
    -->
    <ChatOutline :turns="turns" />
    <CollectRail />

    <div class="chat__guide">
      <GuideNote gkey="chat" :text="GUIDES.chat" to="/report" to-label="去评估报告" />
    </div>

    <div ref="scroller" class="chat__scroll">
      <div class="chat__list">
        <div v-if="!turns.length" class="empty">
          <p class="empty__title">{{ EMPTY_COPY.chatTitle }}</p>
          <p class="empty__body">{{ EMPTY_COPY.chatBody }}</p>
        </div>

        <article
          v-for="t in turns"
          :key="t.id"
          class="turn"
          :class="[`turn--${t.from}`]"
        >
          <!-- 系统说状态：与主理说内容分开（7.4） -->
          <p v-if="t.from === 'system'" class="turn__system">{{ t.text }}</p>

          <template v-else>
            <div v-if="t.speaker" class="turn__speaker">{{ t.speaker }}</div>

            <div class="turn__bubble">
              <p class="turn__text">
                {{ t.from === 'host' ? textOf(t.id, t.text) : t.text
                }}<span v-if="isStreaming(t.id)" class="caret" aria-hidden="true" />
              </p>

              <!-- 交接卡：谁、凭什么、为什么 -->
              <div v-if="t.handoff" class="handoff">
                <p class="handoff__title">换人接手了</p>
                <dl class="handoff__list">
                  <div class="handoff__row">
                    <dt>谁接手</dt>
                    <dd>{{ t.handoff.to }}</dd>
                  </div>
                  <div class="handoff__row">
                    <dt>为什么</dt>
                    <dd>{{ t.handoff.why }}</dd>
                  </div>
                  <div class="handoff__row">
                    <dt>凭什么</dt>
                    <dd>{{ t.handoff.basedOn }}</dd>
                  </div>
                </dl>
              </div>

              <!-- 依据：点开可见 -->
              <div v-if="t.citations?.length" class="cites">
                <span class="cites__label">依据</span>
                <ul>
                  <li v-for="c in t.citations" :key="c">{{ c }}</li>
                </ul>
              </div>

              <!-- 带时长的任务 -->
              <div v-if="t.task" class="taskcard">
                <span class="chip chip--primary">下一步</span>
                <span class="taskcard__text">{{ t.task.title }}</span>
                <span class="chip">约 {{ t.task.minutes }} 分钟</span>
                <button
                  class="btn btn--sm"
                  @click="demo.planChatTask(t.task.title, t.task.minutes)"
                >
                  排进今天
                </button>
              </div>
            </div>

            <!-- 可点选项：能用点就不要让人打字。正在逐字输出时先不给，免得抢话 -->
            <div v-if="t.options?.length && !isStreaming(t.id)" class="opts">
              <button
                v-for="o in t.options"
                :key="o"
                class="opt"
                :disabled="t.id !== turns[turns.length - 1].id"
                @click="send(o)"
              >
                {{ o }}
              </button>
            </div>
          </template>
        </article>

        <!-- 生成中：三点脉冲（CSS 动画，跑在合成层上） -->
        <div v-if="thinking" class="thinking" role="status" aria-label="正在生成">
          <span class="thinking__dot" />
          <span class="thinking__dot" />
          <span class="thinking__dot" />
        </div>
      </div>
    </div>

    <!-- 输入区：固定在底部，不发散 -->
    <div class="composer">
      <div class="composer__inner">
        <textarea
          ref="composerEl"
          v-model="draft"
          class="field__input composer__input"
          rows="1"
          placeholder="说一句就行。试试：我不知道自己适合什么 / 投了几家没回音 / 卡住了"
          aria-label="给主理发一句话"
          @input="autoGrow"
          @keydown="onComposerKeydown"
        />
        <button class="btn btn--primary composer__send" :disabled="!draft.trim()" @click="send()">
          发送
        </button>
      </div>
      <p class="composer__note">
        一次只问一个问题 · 答不上来可以跳过 · 不用先填简历 · Enter 发送，Shift + Enter 换行
      </p>
    </div>
  </div>
</template>

<style scoped>
/**
 * 三栏：左「这次聊出来的」· 中对话 · 右「对你的了解」。
 *
 * 定高与滚动行为一个字没改（第 3 行仍是 minmax(0,1fr)，滚动仍由 .chat__scroll 自己 overflow-y），
 * 只是把"中间那一列的宽度"从内层 760px 限宽升级成显式的 760px 列 ——
 * 这样两侧栏才有确定的位置。上一版用 position: fixed 把右栏浮在页面上，
 * 结果压住了头部那个「看学生档案」按钮：固定定位不受网格约束，谁在上面只看谁后画。
 */
.chat {
  display: grid;
  /* 三栏**必须对称**（252 / 760 / 252）：原来左 232、右 272 是不对称的，
     中栏因此整体偏右 28px —— 结果上方的进度条（全页居中）会两边凸出，左右还不一样多。
     对称之后中栏真正居中，进度条才能与它对齐。 */
  grid-template-columns: 252px 760px 252px;
  /* 三栏合计 1312px，容器是 1328px —— 不写这句，多出的 16px 全落在右侧，
     中栏中心会比页面中心偏右 8px，上方进度条就还是对不齐。 */
  justify-content: center;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  column-gap: var(--sp-5);
  max-width: 1328px;
  margin: 0 auto;
  height: calc(100vh - var(--w-topbar));
  min-height: 520px;
}

/* 中间四块各占一行，都在第 2 列 */
.chat__head {
  grid-column: 2;
  grid-row: 1;
}

.chat__guide {
  grid-column: 2;
  grid-row: 2;
}

.chat__scroll {
  grid-column: 2;
  grid-row: 3;
  min-height: 0;
}

.composer {
  grid-column: 2;
  grid-row: 4;
}

/* 窗口不够宽就把两侧栏收起、回到单列 —— 三栏挤在一起两边都难读。
   用 :deep() 关掉的是子组件（左栏/右栏）的根元素。 */
@media (max-width: 1360px) {
  .chat {
    grid-template-columns: minmax(0, 1fr);
    max-width: 900px;
  }

  .chat :deep(.outline),
  .chat :deep(.collect) {
    display: none;
  }

  .chat__head,
  .chat__guide,
  .chat__scroll,
  .composer {
    grid-column: 1;
  }
}

/*
 * 对话头：**做成卡片，不做通栏白条**。
 * 原来这里是 border-bottom + 不透明底色，横贯整列、两端硬切；而全站其余部分
 * （包括左右两栏）都是"暖底 + 圆角 + 发丝边"的卡片 —— 于是这两条白带成了版面里
 * 唯一的外来件。评审的原话是"白色背景一个方块，有点和别的不搭"。
 * 现在与消息列同宽、同圆角、同边框，读起来是一条连续的中间栏。
 */
.chat__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-4) var(--sp-5);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  /* 与中栏**齐栏**（不内缩）：上方的进度条按中栏 760px 对齐，
     头部卡片若内缩 24px 就变成 712px，进度条又会两侧各凸出 24px。
     关系应当是"面板齐栏、面板里的内容内缩"——内缩由各卡自己的 padding 负责。 */
  margin: 0;
}

.chat__host {
  margin-top: 2px;
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.chat__grade {
  margin-left: var(--sp-2);
  padding: 1px var(--sp-2);
  border-radius: var(--r-sm);
  background: var(--c-surface-3);
  color: var(--c-text-3);
}

.chat__host strong {
  color: var(--c-text);
  font-weight: var(--fw-medium);
}

.chat__guide {
  padding: var(--sp-3) var(--sp-6) 0;
}

.chat__scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-4) var(--sp-6);
}

.chat__list {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.turn {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.turn--me {
  align-items: flex-end;
}

.turn__speaker {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.turn--me .turn__speaker {
  text-align: right;
}

.turn__bubble {
  max-width: 80%;
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
}

/* 主理说内容：不用气泡，纯文本。
   这是 ChatGPT / Claude 的做法，也是 shadcn v4 里的 ghost 变体 ——
   一屏里空气泡越少，"哪一句是结论"越清楚。 */
.turn--host .turn__bubble {
  padding: 0;
  background: transparent;
  border: none;
}

/* 用户说的话才用气泡：浅底 + 同色系描边，不引第三种颜色 */
.turn--me .turn__bubble {
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-lg);
  background: var(--c-primary-weak);
  border: var(--bw-1) solid var(--c-primary-border);
}

.turn__system {
  align-self: center;
  padding: 2px var(--sp-3);
  border-radius: var(--r-pill);
  background: var(--c-surface-3);
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

/* 逐字输出时的光标：2px 竖条，1s 闪烁 */
.caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--c-primary);
  animation: caret-blink 1s steps(2, start) infinite;
}

@keyframes caret-blink {
  to {
    opacity: 0;
  }
}

/* 三点脉冲 */
.thinking {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: var(--sp-2) 0;
}

.thinking__dot {
  width: 6px;
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--c-text-4);
  animation: thinking-pulse 1.1s var(--ease-in-out) infinite;
}

.thinking__dot:nth-child(2) {
  animation-delay: 0.14s;
}

.thinking__dot:nth-child(3) {
  animation-delay: 0.28s;
}

@keyframes thinking-pulse {
  0%,
  60%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .caret {
    animation: none;
  }

  .thinking__dot {
    animation: none;
    opacity: 0.6;
  }
}

/* 交接卡 */
.handoff {
  margin-top: var(--sp-3);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  border-left: 3px solid var(--c-attention);
}

.handoff__title {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--c-attention);
}

.handoff__list {
  margin: var(--sp-2) 0 0;
}

.handoff__row {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: var(--sp-2);
  padding: 3px 0;
  font-size: var(--fs-12);
}

.handoff__row dt {
  color: var(--c-text-3);
}

.handoff__row dd {
  margin: 0;
  color: var(--c-text-2);
}

/* 依据 */
.cites {
  margin-top: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) dashed var(--c-border-strong);
}

.cites__label {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  letter-spacing: 0.04em;
}

.cites ul {
  margin-top: var(--sp-1);
}

.cites li {
  position: relative;
  padding-left: var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: 1.6;
}

.cites li::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 9px;
  width: 4px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--c-border-strong);
}

/* 任务卡 */
.taskcard {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
  flex-wrap: wrap;
}

.taskcard__text {
  flex: 1;
  min-width: 140px;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

/* 选项 */
.opts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.opt {
  height: 32px;
  padding: 0 var(--sp-4);
  border-radius: var(--r-pill);
  border: var(--bw-1) solid var(--c-primary-border);
  background: var(--c-surface);
  color: var(--c-primary);
  font-size: var(--fs-14);
}

.opt:hover:not(:disabled) {
  background: var(--c-primary-weak);
  border-color: var(--c-primary);
}

.opt:disabled {
  opacity: 0.4;
  cursor: default;
}

/* 输入区 */
/* 输入区：同上，卡片而不是通栏白条（border-top 换成卡片整圈边）。
   分隔靠"它是一块独立面板"来表达，不靠一条横贯的硬线。 */
.composer {
  flex: none;
  padding: var(--sp-3) var(--sp-4);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  /* 同上：齐栏（水平不内缩），只与上方消息区留出间距 */
  margin: var(--sp-3) 0 0;
}

.composer__inner {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: var(--sp-2);
}

.composer__input {
  height: 44px;
  min-height: 44px;
  max-height: 240px;
  padding: 12px var(--sp-4);
  line-height: 1.5;
  resize: none;
  overflow-y: auto;
}

.composer__send {
  height: 44px;
  flex: none;
}

.composer__note {
  max-width: 760px;
  margin: var(--sp-2) auto 0;
  font-size: var(--fs-12);
  color: var(--c-text-3);
}
</style>
