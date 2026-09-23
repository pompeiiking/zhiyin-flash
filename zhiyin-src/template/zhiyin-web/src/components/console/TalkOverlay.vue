<script setup lang="ts">
/**
 * 业务对话 —— 五个主理真正说话的地方。
 *
 * 它从角落里搬了出来。理由不是"位置不好看"，而是三件事：
 *
 *   1. 对话是这套产品里**最需要专注**的动作之一，而左下角是边角料的位置；
 *   2. "谁在跟你说话"这件事需要被看见 —— 五个主理是轮班的，
 *      角落那个小窗只能塞下一行标题，交接根本演不出来；
 *   3. 它本来就该和画像、待办一样，是画布上**一块能点开的事**。
 *
 * 所以形态跟着其他模块走：画布上的一块 → 点开是这一层。
 * 左窄右宽两张薄片：左边交代"现在是谁、走到哪了、为什么换人"，
 * 右边才是说话。**五个主理在这边，不在左下角那张便签上。**
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Overlay from '@/components/console/Overlay.vue'
import RenderableBlock from '@/components/render/RenderableBlock.vue'
import { getTheoryCard, track, uploadMaterial } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import type { GuideOption } from '@/lib/asks'

const session = useSessionStore()
const router = useRouter()

const draft = ref('')
const thread = ref<HTMLElement | null>(null)
const box = ref<HTMLInputElement | null>(null)

/*
 * 别处（情报浮层）塞过来的那一句预填。
 *
 * 收到就写进输入框并聚焦 —— 用户可以改，也可以直接发。
 * **不自动发送**：替他按下发送键就是替他做了决定，而这一句是他自己要问的。
 * 用完立刻清掉：下一次进来不该看到上一次的残留。
 */
watch(
  () => session.chatDraft,
  async (text) => {
    if (!text) return
    draft.value = text
    session.chatDraft = ''
    await nextTick()
    box.value?.focus()
  },
  { immediate: true },
)

/**
 * 还没开口时的三句开场白。
 *
 * 空对话区原来是**一块纯白**：除了一行小字什么都没有，用户盯着它不知道该写什么 ——
 * "说一句就行"是一句安慰，不是一句提示。这三句是**动词级别**的提示，
 * 点一下填进输入框（不直接发出）：用户可以改，改的动作本身就是在组织语言。
 *
 * 为什么是三句而不是一堆示例：这一屏的对话是"说清楚一件事"，
 * 不是关键词搜索。示例多了就变成模板，用户会照着抄，反而说不出自己的话。
 */
const STARTERS = [
  '我不知道自己适合什么',
  '帮我看看这个专业能做什么',
  '我这学期还有多少时间能用',
]

function useStarter(text: string) {
  draft.value = text
  box.value?.focus()
}

/**
 * 这一屏是不是"还没开口"。
 *
 * 判据不能只看 `chatTurns.length > 0` —— 会话里天生带着一条占位（CHAT_SEED，
 * id 0 那句"登录后由 AI 主理"），所以登录用户一进来就已经有"一条消息"了。
 * 只看长度的话，开场白永远不出现，空对话区就还是一块白。
 * 真正的判据是：**除了那条占位，还有没有别人说过话**。
 */
const fresh = computed(
  () => !session.chatTurns.length || (session.chatTurns.length === 1 && session.chatTurns[0].id === 0),
)

const lead = computed(() => session.rail?.leadName ?? '')
const subtitle = computed(() =>
  lead.value ? `${lead.value} 在跟你说话 · 会随环节换人` : '还没开始 · 说一句就行，不用想好怎么问'
)

watch(
  () => session.chatTurns.length,
  async () => {
    await nextTick()
    if (thread.value) thread.value.scrollTop = thread.value.scrollHeight
  }
)

// 从别处点"下一步"进来：光标直接落在输入框里
watch(
  () => session.chatPrompt,
  async () => {
    await nextTick()
    box.value?.focus()
  },
  { immediate: true }
)

/**
 * 发一轮话。
 *
 * `option` 只在**点选项**时给：它带着那条选项的身份（option_id / value），
 * 让后端知道"用户选的是上一轮的那一条"。只发 label 的话，这一轮就退化成自由文本，
 * 同一个问题可能又被问一遍（见 session store 的 chatOptions）。
 */
/**
 * 发一轮。
 *
 * **待发的材料跟着这一轮走**：用户传完材料再打字，那一句和材料本来就是一件事
 * （"简历在这，你看看"）。分开成两次发送，模型会先看到一份没有上下文材料、
 * 再看到一句不知道在说谁的话 —— 而用户以为自己只做了一次动作。
 */
function send(text: string, option?: GuideOption) {
  const material = pending.value
  pending.value = null
  attachError.value = ''
  session.sendChat(text, option, material ? [material] : [])
  draft.value = ''
}

/** 这一轮刚点过的那一条：它要显示成"已答"，不能再让人点第三次 */
const answeredId = computed(() => session.chatAnswered?.optionId ?? '')
const isAnswered = (opt: GuideOption) => (opt.option_id ?? opt.label) === answeredId.value

/**
 * 行动阶段的"这一件具体是什么"。
 *
 * 后端给的是 `guide.kind = 'task'`（含任务正文与截止），而之前前端只把它当成
 * 一句普通回复：输入框仍写着"直接说就行"，页面上也没有可以点的下一步 ——
 * 用户不知道要回什么，也不知道回完了会发生什么。这里把它摊开成三件事：
 * **做什么、回什么、做不动怎么办**。
 */
const task = computed(() => (session.guide?.kind === 'task' ? session.guide.task : null))

/** 行动阶段回话的两种模板：一个"做完了"，一个"卡住了"（后者命中 stuck 意图 → 复盘环节给最小动作） */
const TASK_DONE = '做完了，我来说说结果'
const TASK_BLOCKED = '这件事我卡住了，帮我拆小一点'

function openAction() {
  session.closeOverlay()
  session.openOverlay('action')
}

/*
 * 交一份材料给他。
 *
 * 主理会说"把简历给我看看" —— 那时候**得有一个能交东西的地方**，否则用户只能
 * 把整份简历手打一遍（实测：这一步是整条链路里最容易卡死人的地方）。
 *
 * 这一版改的是**交的方式**：文件真的传上去，正文留在服务端，对话框里只有一枚
 * 材料卡（名字 + 读到多少字）。此前是把文件读成一大段文本直接发成一条消息 ——
 * 一份简历几百行当场铺满对话框，用户要读的是主理的回话，不是自己刚交的原文。
 * 顺带解决了两件事：GBK 导出的文本不再变成乱码（编码识别在服务端），
 * 体积上限也不再由浏览器那一侧的两行判断决定。
 */
const attach = ref<HTMLInputElement | null>(null)
const attachError = ref('')
const attaching = ref(false)

/** 已经传上去、等着随下一句一起发出的材料（**上传完成 ≠ 已经给他**，所以下面那条卡写"这一轮一起发"） */
const pending = ref<{ material_id: string; name: string; chars: number } | null>(null)

function pickFile() {
  attachError.value = ''
  attach.value?.click()
}

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 同一个文件连选两次也要能触发
  if (!file) return
  attaching.value = true
  try {
    const material = await uploadMaterial(file)
    // 后端字段是可选的（契约里默认空），这里补齐成本地形状：
    // 少一个字段就少一处 `?? ''` —— 材料卡上有名字与字数才算"读到了"
    pending.value = {
      material_id: material.material_id,
      name: material.name ?? file.name,
      chars: material.chars ?? 0,
    }
  } catch (cause) {
    // 读不出来的原因由服务端说清（Excel 先另存为 CSV / 文件是空的 / 超了 2MB），原样显示
    attachError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    attaching.value = false
  }
}

function dropMaterial() {
  pending.value = null
}

/** 字数：给"我读到了"一个可见的把握（不是精确报告，量级对就够） */
function charsLabel(chars: number): string {
  return chars >= 1000 ? `约 ${(chars / 1000).toFixed(1)} 千字` : `${chars} 字`
}

function goReport() {
  session.closeOverlay()
  router.push('/report')
}

/** 点开对话里引用的那条外部信息：来源与原文都在抽屉里，网址可点回原页面。 */
/**
 * 回复下面挂着的那条"依据的外部信息"—— 点开去哪？
 *
 * 从抽屉改成**情报浮层，并停在这一条上**。理由：同一批外部事实现在有一个
 * 正经的阅读界面（一页一条、来源可点），再开一个抽屉把同一段话换个壳说一遍，
 * 就是"两个地方都能看情报"而不是"打通"。
 *
 * 引用里带着 id（`IntelRefView.id`），浮层按 id 定位 ——
 * 用户看到的是**主理刚刚引用的那一条**，不是从头开始翻。
 * id 对不上（这批情报已经换过一轮）时浮层从头开始，不会给人停在一个错误的条目上。
 */
function openIntelRef(ref: { id?: string }) {
  session.openIntelAt(ref.id ?? '')
}

/**
 * 这一轮主理踩着哪些理论。
 *
 * 回包里的 `badge.theory_refs` 只有 id 与展示名 —— 正文按需取
 * （`GET /app/theory-cards/{id}`，内容在动态资源里，改它不发版）。
 * 标签放在对话旁边而不是轨道面板里：轨道那片平时是收起的，
 * 而"这句话凭什么"要在读到那句话的地方就能点开。
 */
async function openTheory(id: string) {
  try {
    const card = await getTheoryCard(id)
    // 只有真的写了内容的那几块才摆出来 —— 空块配一句"还没写"是给开发看的，
    // 不是给读这张卡的人看的。
    const rows = [
      card.summary && { source: '它是什么', detail: card.summary, confidence: 1, at: card.school || '理论' },
      card.product_usage && {
        source: '在这个产品里怎么用',
        detail: card.product_usage,
        confidence: 1,
        at: card.school || '理论',
      },
    ].filter(Boolean) as { source: string; detail: string; confidence: number; at: string }[]
    session.openDrawer(card.name, card.school || '这一轮判断用到的理论', rows)
  } catch (cause) {
    session.openDrawer('这张理论卡打不开', cause instanceof Error ? cause.message : String(cause), [])
  }
}

/** 点开交接说明：为什么换人 / 换理论 / 结论变了（注册表里的 conv_disclosure_open）。 */
function openDisclosure() {
  const rail = session.rail
  if (!rail) return
  track('conv_disclosure_open', { stage: rail.stage })
  session.openDrawer(
    `为什么现在是「${rail.leadName}」`,
    rail.disclosure || '这一轮没有换人，也没有换依据。',
    [
      { source: '显式告知', detail: rail.disclosure || '这一轮没有需要告知的变更。', confidence: 1, at: '这一轮' },
      ...(rail.theories ?? []).map((t) => ({
        source: '这一轮的依据',
        detail: t.name,
        confidence: 1,
        at: t.stage || '—',
      })),
    ],
  )
}
</script>

<template>
  <Overlay
    title="和主理聊聊"
    :subtitle="subtitle"
    from="talk"
    size="wide"
    @close="session.closeOverlay()"
  >
    <div class="wrap">
      <!-- 左片：谁在说、走到哪了、为什么换人 —— 五个主理只在里头出现 -->
      <aside class="speaker sheet sheet--quiet">
        <span class="label speaker__k">现在是谁</span>
        <template v-if="lead">
          <h3 class="speaker__name">{{ lead }}</h3>
          <!--
            交接说明可点开：点它是"我想知道为什么换人"这个动作本身，
            顺手记一条 conv_disclosure_open（注册表里声明过、此前没人发）。
          -->
          <button class="speaker__say speaker__say--link" type="button" @click="openDisclosure">
            {{ session.rail?.disclosure || '按你这一轮说的话接手。' }}
          </button>

          <ol v-if="session.railCards.length" class="stages">
            <li
              v-for="card in session.railCards"
              :key="card.stage"
              :class="{ now: card.active, done: card.status === 'done' }"
            >
              <span class="stages__dot" aria-hidden="true" />
              <span class="stages__t">{{ card.title }}</span>
              <span class="label stages__s">{{ card.active ? '进行中' : card.status === 'done' ? '已完成' : '待接手' }}</span>
            </li>
          </ol>
        </template>

        <!-- 还没开口：别演一个"正在服务中"的假状态 -->
        <template v-else>
          <h3 class="speaker__name">还没人接手</h3>
          <p class="speaker__say">
            说一句就行 —— 一句话就够系统判环节、派主理。不用先想好怎么问。
          </p>
        </template>

        <!-- 这一轮的依据：点开就是那张理论卡的正文 -->
        <div v-if="session.rail?.theories?.length" class="basis">
          <span class="label speaker__k">这一轮的依据</span>
          <div class="basis__list">
            <button
              v-for="t in session.rail.theories"
              :key="t.theory_id"
              class="theory"
              type="button"
              @click="openTheory(t.theory_id)"
            >
              {{ t.name }}
            </button>
          </div>
        </div>

        <p class="label speaker__foot">
          五个主理轮班：谁也接、为什么换人，都会在这里写出来。
        </p>
      </aside>

      <!-- 右片：说话的地方 -->
      <section class="talk sheet">
        <div ref="thread" class="thread">
          <!--
            还没开口：不是一块白，而是三句"可以照着说、也可以改"的开场白。
            空白不是留白，是让人卡住的地方。
          -->
          <!--
            已经替他写好一句（比如从情报浮层"拿这条去问主理"过来）时，不再摆开场白：
            输入框里有字，旁边还挂三句示例，读起来像"你到底想让我说什么"。
          -->
          <div v-if="fresh && !draft" class="starter">
            <p class="starter__t">第一句不用想好，随便挑一句开始：</p>
            <ul class="starter__list">
              <li v-for="s in STARTERS" :key="s">
                <button class="starter__b" type="button" @click="useStarter(s)">
                  {{ s }}
                </button>
              </li>
            </ul>
            <p class="starter__d">
              说错也没关系 —— 我会记下"你说了什么"和"我凭什么这么理解"，
              两条都能随时回来看。
            </p>
          </div>

          <!-- 占位那一句在"还没开口"时不出场：开场白已经把话说清楚了 -->
          <template v-for="turn in (fresh ? [] : session.chatTurns)" :key="turn.id">
            <p class="line" :class="turn.role">
              <span v-if="turn.role === 'ai' && turn.actor" class="label line__who">{{ turn.actor }}</span>
              {{ turn.text }}
            </p>

            <!--
              这一轮交上去的材料：**只显示"它是什么"**，不摊开正文。
              正文在服务端，主理读得到；摆在这里的几百行只会把对话挤没，
              而用户要读的是主理的回话。
            -->
            <div v-if="turn.material" class="material">
              <svg width="15" height="17" viewBox="0 0 34 40" aria-hidden="true">
                <path
                  d="M3 3.6h19l9 9v23.8a1.6 1.6 0 0 1-1.6 1.6H3a1.6 1.6 0 0 1-1.6-1.6V5.2A1.6 1.6 0 0 1 3 3.6Z"
                  fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"
                />
                <path
                  d="M22 3.6v9h9M9 23h16M9 29h11" fill="none" stroke="currentColor"
                  stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                />
              </svg>
              <span class="material__name mono">{{ turn.material.name }}</span>
              <span class="label material__meta">
                已交给主理 · {{ charsLabel(turn.material.chars) }}
              </span>
            </div>

            <!--
              这一轮摆在回复里的**可视件**（图 / 时间线 / 对比表…）。
              值来自服务端实测数据（画像各维把握、方案匹配度…），
              所以它不是"AI 画的示意图"，是这条结论的另一种写法。
              按 kind 分发在 `RenderableBlock` 里 —— 加一种新的可视件，
              这里是零改动。
            -->
            <RenderableBlock
              v-for="(item, index) in turn.renderables ?? []"
              :key="`${item.kind}-${index}`"
              :item="item"
            />

            <!-- 这一轮用到的外部情报：点开就是来源与原文 -->
            <div v-if="turn.intelRefs?.length" class="refs">
              <span class="label refs__k">依据的外部信息</span>
              <button
                v-for="ref in turn.intelRefs"
                :key="ref.id"
                class="ref"
                type="button"
                @click="openIntelRef(ref)"
              >
                <span class="label ref__kind">{{ ref.kind_label || '公开信息' }}</span>
                <span class="ref__t">{{ ref.title }}</span>
                <span class="label ref__src">{{ ref.source_name }}</span>
              </button>
            </div>
          </template>

          <div v-if="session.chatTyping" class="line ai typing">
            <span class="typing__dot" aria-hidden="true" />
            正在回你…
          </div>
        </div>

        <div class="compose">
          <!-- 在等用户回答的那一句：给它自己的位置，而不是塞进输入框占位符 -->
          <div v-if="session.chatPrompt" class="prompt">
            <span class="label prompt__k">在等你回答</span>
            <p class="prompt__q">{{ session.chatPrompt }}</p>
            <div v-if="session.chatOptions.length" class="prompt__opts">
              <button
                v-for="opt in session.chatOptions"
                :key="opt.option_id ?? opt.label"
                class="opt"
                :class="{ 'opt--used': isAnswered(opt) }"
                type="button"
                :disabled="session.chatTyping"
                @click="send(opt.label, opt)"
              >
                {{ opt.label }}
              </button>
            </div>
            <!--
              点了选项但这一轮没往前走时，必须**说出来**。
              不说的话，用户看到的是"一模一样的问题又回来了"，只能认为点了没用。
            -->
            <p v-if="session.chatClarify" class="prompt__note" role="status">
              {{ session.chatClarify }}
            </p>
          </div>

          <!--
            行动阶段：把"现在这一件"摊开 —— 做什么、回什么、做不动怎么办。
            没有这一段，输入框那句"直接说就行"等于没给任何可执行的动作。
          -->
          <div v-if="task" class="task">
            <span class="label task__k">现在做这一件</span>
            <p class="task__t">{{ task.text }}</p>
            <p class="label task__d">
              做完回来说一句就行；做不动也说一声 —— 卡住不是失败，是这条任务拆得还不够小。
            </p>
            <div class="task__acts">
              <button class="opt" type="button" :disabled="session.chatTyping" @click="send(TASK_DONE)">
                做完了
              </button>
              <button class="opt" type="button" :disabled="session.chatTyping" @click="send(TASK_BLOCKED)">
                做不到，拆小一点
              </button>
              <button class="opt opt--quiet" type="button" @click="openAction">去行动计划勾掉</button>
            </div>
          </div>

          <div class="row">
            <!-- 主理要材料时得有地方交 —— 见 onFile 的说明 -->
            <button
              class="clip"
              type="button"
                :disabled="session.chatTyping"
              aria-label="上传一份材料（txt / csv / json / html）"
              title="上传一份材料（txt / csv / json / html；Excel 请先另存为 CSV）"
              @click="pickFile"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 7v9a4 4 0 0 0 8 0V6a2.5 2.5 0 0 0-5 0v10"
                      fill="none" stroke="currentColor" stroke-width="1.7"
                      stroke-linecap="round" />
              </svg>
            </button>
            <input
              ref="attach"
              class="clip__input"
              type="file"
              accept=".txt,.md,.markdown,.csv,.tsv,.json,.html,.htm,.xml,.yml,.yaml"
              @change="onFile"
            >
            <input
              ref="box"
              v-model="draft"
              type="text"
              :placeholder="
                pending
                  ? '要补一句就说；不补也行，直接交上去'
                  : session.chatPrompt
                  ? '照上面那句答就行'
                  : task
                    ? '做完就说一句；做不动也说一声'
                    : '直接说就行，不用想好怎么问'
              "
              aria-label="对话输入"
              @keydown.enter="send(draft)"
            >
            <button
              class="btn primary"
              type="button"
              :disabled="(!draft.trim() && !pending) || session.chatTyping"
              @click="send(draft)"
            >
              {{ pending && !draft.trim() ? '交上去' : '发送' }}
            </button>
          </div>

          <p v-if="attachError" class="label clip__err" role="alert">{{ attachError }}</p>
          <p v-else-if="attaching" class="label clip__busy">正在读你传的材料…</p>

          <!--
            待发的材料：一栏薄卡，带"移除"。
            它还没发出去，所以不能装成已经交上去了 —— 文案是"这一轮一起发"，
            不是"已交给主理"（后者是发出去之后气泡上那枚卡的说法）。
          -->
          <div v-else-if="pending" class="hold">
            <span class="label hold__k">这一轮一起发</span>
            <span class="hold__name mono">{{ pending.name }}</span>
            <span class="label hold__meta">{{ charsLabel(pending.chars) }}</span>
            <button class="label hold__x" type="button" @click="dropMaterial">移除</button>
          </div>

          <div class="tie">
            <span class="label">聊完它会接着往下做 —— 不用你回头找路。</span>
            <button class="label tie__go" type="button" @click="goReport">看完整报告 →</button>
          </div>
        </div>
      </section>
    </div>
  </Overlay>
</template>

<style scoped>
.wrap {
  height: 100%; min-height: 0;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr);
  gap: var(--s3);
}

/* 左片：和其他浮层一样，上下各缩一截，两张片子轮廓不同 */
.speaker {
  padding: var(--s4) var(--s4) var(--s5);
  margin: 28px 0 72px;
  display: flex; flex-direction: column; gap: var(--s3);
  overflow: auto;
  animation: sheet-in-left 520ms var(--ease-expo) 60ms both;
}
.speaker__k { color: var(--ink-3); }
.speaker__name { font-size: var(--t-h4); letter-spacing: var(--track-h); }
.speaker__say { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.75; }
/* 可点开的那一句：平时长得像正文，悬停才提示"能点" —— 它不是按钮，是一句话 */
.speaker__say--link { width: 100%; text-align: left; }
.speaker__say--link:hover { color: var(--ink-1); text-decoration: underline dotted var(--accent); }

.stages { list-style: none; margin: var(--s2) 0 0; padding: 0; display: grid; gap: 1px; }
.stages li {
  display: grid; grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center; gap: var(--s2);
  padding: 6px var(--s2); border-radius: var(--r-sm);
}
.stages li.now { background: var(--fill-subtle); }
.stages__dot { width: 7px; height: 7px; border-radius: 50%; background: var(--line-3); }
.stages li.done .stages__dot { background: var(--mk-green); }
.stages li.now .stages__dot { background: var(--mk-purple); animation: mo-breathe 2.4s var(--ease-out) infinite; }
.stages__t { font-size: var(--fs-small); color: var(--ink-2); }
.stages li.now .stages__t { color: var(--ink-1); font-weight: 600; }
.stages__s { color: var(--ink-3); }
.speaker__foot { margin-top: auto; color: var(--ink-faint); line-height: 1.65; }

/* 这一轮的依据：理论标签。样式与轨道面板里那份一致（同一个东西，长一样） */
.basis { display: flex; flex-direction: column; gap: 6px; margin-top: var(--s3); }
.basis__list { display: flex; flex-wrap: wrap; gap: 6px; }
.theory {
  padding: 3px 10px; border-radius: var(--r-pill);
  border: 1px solid var(--line-2); color: var(--mk-purple); font-size: var(--fs-small);
  transition: border-color var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.theory:hover { border-color: var(--mk-purple); color: var(--ink-1); }

/* 右片：说话的地方 */
.talk {
  padding: 0;
  margin-bottom: 40px;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  overflow: hidden;
  animation: sheet-in 460ms var(--ease-expo) both;
}
.thread {
  min-height: 0; overflow-y: auto;
  padding: var(--s5) var(--s6);
  display: flex; flex-direction: column; gap: var(--s3);
}

/*
 * 开场白区：三颗可点的句子 + 一句说明。
 * 它是**纸上的铅笔批注**的样子（左侧一道墨线），不是又一张卡 ——
 * 对话区里再套卡，读起来就分不清哪句是系统说的、哪句是你说过的。
 */
.starter { display: grid; gap: var(--s3); padding-left: var(--s4); border-left: 2px solid var(--line-2); }
.starter__t { font-family: var(--font-display); font-size: var(--t-h3); line-height: 1.4; color: var(--ink-1); }
.starter__list { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--s2); }
.starter__b {
  min-height: 32px; padding: 6px 13px;
  border: var(--bw) solid var(--line-3); border-radius: var(--r-pill);
  background: var(--n-1);
  font-size: var(--fs-small); color: var(--ink-2); line-height: 1.3;
  transform: rotate(-0.5deg);
  transition: border-color var(--dur-micro) var(--ease-out),
              color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out),
              transform var(--dur-micro) var(--ease-out);
}
.starter__list li:nth-child(2) .starter__b { transform: rotate(0.6deg); }
.starter__list li:nth-child(3) .starter__b { transform: rotate(-0.3deg); }
.starter__b:hover {
  border-color: var(--accent); color: var(--accent); background: var(--accent-soft);
  transform: rotate(0) translateY(-1px);
}
.starter__d { font-size: var(--fs-small); color: var(--ink-3); line-height: 1.75; max-width: 52ch; }

.line { font-size: var(--t-body); line-height: 1.72; max-width: 62ch; }
.line.me {
  align-self: flex-end;
  padding: 9px var(--s4);
  border-radius: var(--r-md) var(--r-md) var(--r-xs) var(--r-md);
  background: var(--accent); color: var(--accent-ink);
  max-width: 52ch;
}
.line.ai { color: var(--ink-1); }
.line__who { display: block; margin-bottom: 2px; color: var(--mk-purple); }
.typing { display: flex; align-items: center; gap: var(--s2); color: var(--ink-3); }
.typing__dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--mk-purple);
  animation: mo-breathe 1.6s var(--ease-out) infinite;
}

.compose {
  display: flex; flex-direction: column; gap: var(--s3);
  padding: var(--s4) var(--s5) var(--s5);
  border-top: 1px solid var(--line-1);
  background: var(--n-0);
}
.prompt {
  display: flex; flex-direction: column; gap: 5px;
  padding: var(--s3) var(--s4);
  border: var(--bw) solid var(--accent);
  border-radius: var(--r-sm);
  background: var(--accent-soft);
}
.prompt__k { color: var(--accent); }
.prompt__q { font-size: var(--fs-small); color: var(--ink-1); line-height: 1.65; max-width: 62ch; }
.prompt__opts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.prompt__opts .opt {
  padding: 5px 12px; border-radius: var(--r-pill);
  border: 1px solid var(--accent); background: var(--n-1);
  font-size: var(--t-xs); color: var(--accent);
  transition: background var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out);
}
.prompt__opts .opt:hover { background: var(--accent); color: var(--accent-ink); }
.prompt__opts .opt:disabled { opacity: 0.5; cursor: not-allowed; }
/*
 * 已经点过的那一条：划掉 + 降一级 —— 它就是"这一条答过了"的样子，
 * 而不是一个还能再点的按钮（再点一次只会把同一个状态又走一遍）。
 */
.prompt__opts .opt--used {
  border-style: dashed; color: var(--ink-3); text-decoration: line-through;
}
.prompt__opts .opt--used:disabled { opacity: 0.75; }
.prompt__note { font-size: var(--fs-small); color: var(--warn); line-height: 1.7; max-width: 62ch; }

/* 行动阶段那一块：和"在等你回答"同一个位置、同一套材质，只是内容是任务不是问题 */
.task {
  display: flex; flex-direction: column; gap: 5px;
  padding: var(--s3) var(--s4);
  border: var(--bw) solid var(--line-3);
  border-left: 3px solid var(--mk-green);
  border-radius: var(--r-sm);
  background: var(--fill-subtle);
}
.task__k { color: var(--mk-green); }
.task__t { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); line-height: 1.6; max-width: 62ch; }
.task__d { color: var(--ink-3); line-height: 1.7; max-width: 62ch; }
.task__acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.task__acts .opt {
  padding: 5px 12px; border-radius: var(--r-pill);
  border: 1px solid var(--mk-green); background: var(--n-1);
  font-size: var(--t-xs); color: var(--ink-1);
  transition: background var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out);
}
.task__acts .opt:hover { background: var(--mk-green); color: var(--n-0); }
.task__acts .opt:disabled { opacity: 0.5; cursor: not-allowed; }
.task__acts .opt--quiet { border-color: var(--line-2); color: var(--ink-2); }
.task__acts .opt--quiet:hover { background: var(--n-1); color: var(--ink-1); border-color: var(--line-4); }

.row { display: flex; gap: var(--s2); }
.row input {
  flex: 1; min-width: 0; height: 42px; padding: 0 var(--s4);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-pill);
  background: var(--n-1); color: var(--ink-1);
  font-size: var(--t-sm);
  transition: border-color var(--dur-micro) var(--ease-out), box-shadow var(--dur-micro) var(--ease-out);
}
.row input:hover { border-color: var(--line-3); }
.row input:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.row .btn { height: 42px; }

/* 交材料那个回形针：和输入框同高，安静地待在左边 */
.clip {
  flex: 0 0 auto; width: 42px; height: 42px;
  display: grid; place-items: center;
  border: var(--bw) solid var(--line-2); border-radius: var(--r-pill);
  background: var(--n-1); color: var(--ink-2);
  transition: border-color var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out);
}
.clip:hover { border-color: var(--line-3); color: var(--accent); }
.clip:disabled { opacity: 0.5; cursor: default; }
.clip__input { display: none; }
.clip__err { color: var(--warn); }
.clip__busy { color: var(--accent); }

/* 已交上去的材料（气泡下面那枚卡）：名字 + 一句话，**没有正文** */
.material {
  align-self: flex-end;
  display: inline-flex; align-items: center; gap: var(--s2);
  max-width: 100%;
  padding: 7px var(--s3);
  border: var(--bw) solid var(--accent); border-radius: var(--r-sm);
  background: var(--accent-soft); color: var(--accent-deep);
}
.material__name { font-size: var(--t-xs); color: var(--ink-1); overflow-wrap: anywhere; }
.material__meta { color: var(--accent-deep); white-space: nowrap; }

/* 待发的材料（输入框下面那条）：虚线 = 还没发出去 */
.hold {
  display: flex; align-items: center; gap: var(--s2);
  padding: 6px var(--s3);
  border: 1px dashed var(--line-3); border-radius: var(--r-sm);
  background: var(--fill-subtle);
}
.hold__k { color: var(--ink-3); white-space: nowrap; }
.hold__name { font-size: var(--t-xs); color: var(--ink-1); overflow-wrap: anywhere; }
.hold__meta { color: var(--ink-faint); white-space: nowrap; }
.hold__x { margin-left: auto; color: var(--ink-3); white-space: nowrap; }
.hold__x:hover { color: var(--warn); text-decoration: underline; }

.tie { display: flex; align-items: center; justify-content: space-between; gap: var(--s4); }

/* 引用的外部信息：一行一条，点开是来源与原文 */
.refs { display: grid; gap: 4px; margin: 2px 0 6px; }
.refs__k { color: var(--ink-3); }
.ref {
  display: grid; grid-template-columns: auto 1fr auto; gap: var(--s2);
  align-items: baseline; text-align: left;
  padding: 6px 10px; border-radius: var(--r-sm);
  border: var(--bw) solid var(--line-1); background: var(--n-1);
}
.ref:hover { border-color: var(--line-3); }
.ref__kind { color: var(--mk-orange); }
.ref__t { font-size: var(--fs-small); color: var(--ink-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ref__src { color: var(--ink-faint); }
.tie .label { color: var(--ink-3); }
.tie__go { color: var(--accent); }
.tie__go:hover { text-decoration: underline; }

@media (max-width: 900px) {
  .wrap { grid-template-columns: minmax(0, 1fr); height: auto; }
  .speaker { margin: 0 0 var(--s3); }
  .talk { margin-bottom: 0; }
}
</style>
