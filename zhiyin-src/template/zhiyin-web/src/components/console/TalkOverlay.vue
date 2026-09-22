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
import { getTheoryCard, track } from '@/api/client'
import { useSessionStore } from '@/stores/session'

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

function send(text: string) {
  session.sendChat(text)
  draft.value = ''
}

/*
 * 交一份材料给他。
 *
 * 主理会说"把简历给我看看" —— 那时候**得有一个能交东西的地方**，否则用户只能
 * 把整份简历手打一遍（实测：这一步是整条链路里最容易卡死人的地方）。
 * 这里不做上传服务器：文件在浏览器里读成文本，作为这一轮的话发过去 ——
 * 与"他自己复制粘贴一段"走的是同一条路，链路不变。
 */
const attach = ref<HTMLInputElement | null>(null)
const attachError = ref('')
const attachName = ref('')

/** 只收能被模型读懂的纯文本形态；二进制（PDF/图片）如实说明，不假装读得懂 */
const TEXT_SUFFIX = /\.(txt|md|markdown|csv|tsv|json|html?|xml|ya?ml)$/i
const MAX_BYTES = 400 * 1024

function pickFile() {
  attachError.value = ''
  attach.value?.click()
}

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 同一个文件连选两次也要能触发
  if (!file) return
  if (!TEXT_SUFFIX.test(file.name)) {
    attachError.value = '这个格式我读不了，先导出成 Word / PDF 里的文字，或存成 txt 再传。'
    return
  }
  if (file.size > MAX_BYTES) {
    attachError.value = '文件太大了（超过 400KB），先截取和这次问题相关的那一段。'
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result ?? '').trim()
    if (!text) {
      attachError.value = '这个文件里没有文字。'
      return
    }
    attachName.value = file.name
    send(`【我传了一份材料：${file.name}】\n${text}`)
  }
  reader.onerror = () => {
    attachError.value = '文件读不出来，换一个试试。'
  }
  reader.readAsText(file, 'utf-8')
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
              主理顺手给的图。值来自服务端实测数据（画像各维把握、方案匹配度…），
              所以它不是"AI 画的示意图"，是这条结论的另一种写法。
            -->
            <figure v-if="turn.chart?.points?.length" class="chart">
              <figcaption class="label chart__k">{{ turn.chart.title || '这一轮的分布' }}</figcaption>
              <ul class="chart__rows">
                <li v-for="p in turn.chart.points" :key="p.label">
                  <span class="chart__label">{{ p.label }}</span>
                  <span class="chart__bar">
                    <i :style="{ width: `${Math.max(2, Math.min(100, p.value * 100))}%` }" />
                  </span>
                  <span class="mono chart__num">{{ p.value.toFixed(2) }}</span>
                </li>
              </ul>
            </figure>

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
                :key="opt"
                class="opt"
                type="button"
                :disabled="session.chatTyping"
                @click="send(opt)"
              >
                {{ opt }}
              </button>
            </div>
          </div>

          <div class="row">
            <!-- 主理要材料时得有地方交 —— 见 onFile 的说明 -->
            <button
              class="clip"
              type="button"
              :disabled="session.chatTyping"
              aria-label="上传一份材料（txt / md / csv / json / html）"
              title="上传一份材料（txt / md / csv / json / html）"
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
              :placeholder="session.chatPrompt ? '照上面那句答就行' : '直接说就行，不用想好怎么问'"
              aria-label="对话输入"
              @keydown.enter="send(draft)"
            >
            <button class="btn primary" type="button" :disabled="!draft.trim()" @click="send(draft)">
              发送
            </button>
          </div>

          <p v-if="attachError" class="label clip__err" role="alert">{{ attachError }}</p>
          <p v-else-if="attachName" class="label clip__ok">已把「{{ attachName }}」交给他了。</p>

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
.clip__ok { color: var(--accent); }

.tie { display: flex; align-items: center; justify-content: space-between; gap: var(--s4); }

/* 对话里那张图：横条 + 数值。窄也放得下，因为它本来就是"比较"用的 */
.chart { margin: 2px 0 6px; display: grid; gap: 6px; }
.chart__k { color: var(--ink-3); }
.chart__rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.chart__rows li { display: grid; grid-template-columns: minmax(3.5em, 6em) 1fr 3.2em; gap: var(--s2); align-items: center; }
.chart__label { font-size: var(--fs-small); color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chart__bar { height: 8px; border-radius: 999px; background: var(--fill-subtle); overflow: hidden; }
.chart__bar i { display: block; height: 100%; border-radius: inherit; background: var(--mk-green); }
.chart__num { font-size: var(--fs-small); color: var(--ink-3); text-align: right; }

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
