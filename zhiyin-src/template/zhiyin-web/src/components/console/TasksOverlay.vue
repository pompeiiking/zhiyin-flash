<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { useInkMark } from '@/composables/useInkMark'
import { todoTask, type TodoSuggestion } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'

/**
 * 待办 —— 三栏，但重点是**两个来源分得清**。
 *
 * 左：智能体建议（每条都写着"为什么、从哪来、建议放哪段时间"），可采纳、可直接否掉
 * 中：今天与待办（行动计划的 + 你自己写进去的），顶部一条输入框随手加
 * 右：已完成
 *
 * 为什么不做成一个混在一起的清单：混在一起，用户就分不清"这是我该做的"还是"AI 让我做的"。
 * 分开之后，采纳 / 否决本身就成了信息 —— 它回流进画像，下次推荐会更准。
 */
const session = useSessionStore()
const open = ref<string | null>(null)
const draft = ref('')

/**
 * 清单里的一行。
 *
 * 数据只有两个来源，**都在后端**：
 *   · 智能体建议：`POST /app/plan/todos/suggestions`（列在这里，采纳后才落库）
 *   · 你自己的待办：`GET/POST/PATCH /app/notes`（`session.customTodos` 就是它）
 *
 * 采纳一条建议 = 把它写成一条 note（走 addTodo）—— 这样它才真的进了后端，
 * 采集策略与 AI 下轮才读得到。此前"采纳"只往一个本地数组里塞个 id，
 * 界面上看着进了清单，后端一无所知。
 */
interface Row {
  id: string
  title: string
  due: string
  from: string
  detail: string
  /**
   * 这一条来自行动计划（而不是自建）。
   *
   * 勾选要回写**整版计划**（task_id 换一代就 404），那条写路径只有 ActionOverlay 一份，
   * 所以这里的计划任务只做展示与跳转，不复制一份勾选逻辑出来。
   */
  plan?: boolean
}

/*
 * 行动计划的待办也要进这一栏。
 *
 * 这一栏原来只列自建待办：一个有行动计划、一条自建都没写的账号，从主界面
 * 点「全部任务 →」进来看到的是一张空清单 —— 而主界面上明明写着"现在这一件"。
 * 来源仍然写在每一行上（"行动计划" / "你自己"），
 * "我该做的"与"AI 让我做的"照样分得清，这正是这一屏分两栏的理由。
 */
const planRows = computed<Row[]>(() =>
  (session.actionPlan?.phases ?? [])
    .flatMap((p) => p.tasks ?? [])
    .filter((t) => !t.done)
    .map((t) => ({
      id: `plan:${t.task_id}`,
      title: t.text,
      due: t.due_date ? `截止 ${t.due_date.slice(0, 10)}` : '计划没写截止',
      from: '行动计划',
      detail: `行动计划${t.phase ? `「${t.phase}」阶段` : ''}排的一条任务。`,
      plan: true,
    })),
)

const myRows = computed<Row[]>(() =>
  session.customTodos
    .filter((t) => !t.done)
    .map((t) => ({ id: t.id, title: t.label, due: '你写的', from: '你自己', detail: '' })),
)

/** 计划排的排前面 —— 与主界面"现在这一件"的取法一致 */
const today = computed<Row[]>(() => [...planRows.value, ...myRows.value])
const done = computed<Row[]>(() =>
  session.customTodos
    .filter((t) => t.done)
    .map((t) => ({ id: t.id, title: t.label, due: '你写的', from: '你自己', detail: '' })),
)

/*
 * ── 手绘：勾掉之后，在那一句上画一道 ────────────────────────────────
 *
 * 这一笔的含义完全来自它落在**哪一侧**：被划掉的东西是"不用再做了"。
 * 所以它只画在完成的那一侧 —— 同样的线画在还没做的事上，读出来是
 * "这条作废了"，正好是反的。
 *
 * 也不给整栏都描：已完成那一栏里每一条本来就有印刷体的删除线
 * （`.task.done .task__title`），整栏都加手绘就成了两套线互相压着。
 * 手绘留给"刚做成的那一下" —— 那是动作，不是状态。
 */
const struck = ref<string[]>([])
/** id → 已完成那一栏里的任务文字节点；节点卸载时被回填 null，顺手删掉 */
const doneTitles = new Map<string, HTMLElement>()

const ink = useInkMark({
  targets: () =>
    struck.value.map((id) => doneTitles.get(id)).filter((el): el is HTMLElement => !!el?.isConnected),
  shape: 'strike-through',
  // 与门户那个手绘圈同一支笔：记号笔绿
  token: '--mk-green',
  fallback: '#257040',
  strokeWidth: 2.2,
  iterations: 1, // 一笔划掉
  multiline: true, // 标题折行时一行一道，而不是横穿整块
  animationDuration: 560,
})

/** v-for 里没法给"某一条"起名字，所以用函数 ref 把落点收进这张表 */
function trackDoneTitle(id: string, el: HTMLElement | null) {
  if (el) doneTitles.set(id, el)
  else doneTitles.delete(id)
}

function add() {
  session.addTodo(draft.value)
  draft.value = ''
}

/** 采纳一条建议：写进后端（note），再把它从"待处理建议"里划掉 */
async function adopt(s: TodoSuggestion) {
  await session.addTodo(s.label)
  session.acceptSuggestion(s.id)
}

function complete(t: Row) {
  session.toggleCustomTodo(t.id)
  /*
   * 勾掉之后这一行会从中间那一栏挪到右边（store 立刻翻 done，v-for 跟着重排），
   * 所以要等这一轮渲染落定再去拿它的节点 —— 拿早了拿到的是已经不在文档里的旧节点，
   * 那种节点上画不出记号（见 composable）。
   *
   * 只往里加、不清空：一口气勾掉几条时，先画的那几道不该跟着消失 ——
   * 一笔划掉的东西又变回没划，读出来是"我又没做完"。
   */
  if (!struck.value.includes(t.id)) struck.value = [...struck.value, t.id]
  void nextTick(() => ink.redraw())
}

function openDetail(t: Row) {
  session.openDrawer(t.title, `来自 ${t.from}`, [
    { source: t.from, detail: t.detail || '这一条是你自己加进来的。', confidence: 0.8, at: t.due },
  ])
}
</script>

<template>
  <Overlay
    title="待办"
    subtitle="左边是智能体建议 · 中间是计划与你自己的清单 · 两边分得清"
    from="todo"
    @close="session.closeOverlay()"
  >
    <div class="board">
      <!-- 一、智能体建议 -->
      <section class="col sheet sheet--quiet">
        <header class="col__head">
          <span class="col__pip" style="background: var(--mk-purple)" aria-hidden="true" />
          <span class="label">智能体建议</span>
        </header>

        <AiFrame :task="() => todoTask() as never" :compact="true">
          <template #default="{ data }">
            <ul v-if="data" class="sug">
              <li
                v-for="s in (data as TodoSuggestion[]).filter((x) => !session.acceptedSuggestions.includes(x.id) && !session.dismissedSuggestions.includes(x.id))"
                :key="s.id"
              >
                <p class="sug__label">{{ s.label }}</p>
                <p class="sug__why">{{ s.why }}</p>
                <p class="label sug__meta">{{ s.from }} · 建议 {{ s.when }}</p>
                <div class="sug__acts">
                  <button class="btn primary" type="button" @click="adopt(s)">采纳</button>
                  <button class="btn ghost" type="button" @click="session.dismissSuggestion(s.id)">不用</button>
                </div>
              </li>
              <li v-if="!(data as TodoSuggestion[]).some((x) => !session.acceptedSuggestions.includes(x.id) && !session.dismissedSuggestions.includes(x.id))" class="label col__empty">
                这批建议都处理完了
              </li>
            </ul>
          </template>
        </AiFrame>
      </section>

      <!-- 二、今天与待办（计划排的 + 自建） -->
      <section class="col sheet">
        <header class="col__head">
          <span class="col__pip" style="background: var(--mk-green)" aria-hidden="true" />
          <span class="label">今天与待办</span>
          <span class="mono col__count">{{ today.length }}</span>
        </header>

        <form class="add" @submit.prevent="add">
          <input v-model="draft" type="text" placeholder="自己加一条…" aria-label="自己加一条待办">
          <button class="add__go" type="submit" :disabled="!draft.trim()" aria-label="加入待办">＋</button>
        </form>

        <!--
          没存下来这件事必须说出来。
          存不下来，AI 就读不到你写的话，也就没法把它当依据 ——
          那正是"因为你写了…"说不出口的原因。
          静默地只存在本地，用户会以为系统知道，而系统其实什么也没看见。
        -->
        <p v-if="!session.todoSynced" class="label add__warn">
          这条还没保存成功 —— AI 暂时读不到它，也就没法把它当依据。
        </p>

        <ul class="list">
          <li v-for="t in today" :key="t.id" class="task now">
            <button class="task__head" type="button" :aria-expanded="open === t.id" @click="open = open === t.id ? null : t.id">
              <span class="task__title">{{ t.title }}</span>
              <span class="label task__due">{{ t.due }}</span>
              <span class="label task__from">{{ t.from }}</span>
            </button>
            <div v-if="open === t.id" class="task__detail">
              <p class="dim">{{ t.detail || '这一条是你自己加进来的。' }}</p>
              <div class="task__actions">
                <!-- 计划任务：勾选要改整版计划，这里只把人送到那个唯一能改它的地方 -->
                <button
                  v-if="t.plan"
                  class="btn primary"
                  type="button"
                  @click="session.openOverlay('action')"
                >
                  去行动计划里勾
                </button>
                <template v-else>
                  <button class="btn primary" type="button" @click="complete(t)">勾掉</button>
                  <button class="btn ghost" type="button" @click="openDetail(t)">看依据</button>
                </template>
              </div>
            </div>
          </li>

          <li v-if="!today.length" class="label col__empty">现在还没有要做的事</li>
        </ul>
      </section>

      <!-- 三、已完成 -->
      <section class="col sheet sheet--quiet">
        <header class="col__head">
          <span class="col__pip" aria-hidden="true" />
          <span class="label">已完成</span>
          <span class="mono col__count">{{ done.length }}</span>
        </header>
        <p v-if="!done.length" class="label col__empty">还没勾掉过什么</p>
        <ul class="list">
          <li v-for="t in done" :key="t.id" class="task done">
            <span :ref="(el) => trackDoneTitle(t.id, el as HTMLElement | null)" class="task__title">{{ t.title }}</span>
            <span class="label task__from">{{ t.from }}</span>
          </li>
        </ul>
      </section>
    </div>
  </Overlay>
</template>

<style scoped>
.board { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr) minmax(0, 0.9fr); gap: var(--s3); padding: var(--s4) var(--s5) var(--s5); }
.col { padding: var(--s4); overflow: auto; display: flex; flex-direction: column; gap: var(--s3); }
.col__head { display: flex; align-items: center; gap: var(--s2); }
.col__pip { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-4); flex: 0 0 auto; }
.col__count { margin-left: auto; color: var(--ink-3); }
.col__empty { padding: var(--s3) 0; color: var(--ink-3); }

.sug { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.sug li { display: grid; gap: 3px; padding: var(--s3) var(--s3) var(--s3) var(--s4); border-left: 3px solid var(--mk-purple); border-radius: 0 var(--r-sm) var(--r-sm) 0; }
.sug li:nth-child(even) { background: var(--fill-subtle); }
.sug__label { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.sug__why { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.6; }
.sug__meta { color: var(--ink-3); }
.sug__acts { display: flex; gap: 6px; padding-top: 4px; }
.sug__acts .btn { height: 28px; padding: 0 12px; font-size: var(--fs-small); }

.add { display: flex; gap: 6px; }
.add input {
  flex: 1; height: 34px; padding: 0 var(--s3);
  border: 2px solid var(--line-2); border-radius: var(--r-pill);
  background: var(--n-0); color: var(--ink-1);
}
.add input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.add__go {
  width: 34px; height: 34px; border-radius: 50%;
  border: 2px solid var(--accent); color: var(--accent); font-size: 17px; line-height: 1;
  transition: background var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.add__go:hover:not(:disabled) { background: var(--accent); color: var(--accent-ink); }
.add__go:disabled { opacity: 0.35; }
.add__warn { margin: 6px 0 0; color: var(--warn, var(--accent)); line-height: 1.6; }

.list { list-style: none; margin: 0; padding: 0; }
/*
 * 每一行自己当定位祖先。
 *
 * 手绘那一笔是 rough-notation 插在元素**旁边**的一层绝对定位 SVG，它的坐标系是
 * 最近的那个定位祖先。不设在这里，坐标系就落到整块纸上 —— 而这张纸打开时是带缩放
 * 动画的，坐标系越大，落笔的位置偏得越明显（同一行自己当坐标系时，偏差不到一个像素）。
 */
.task { position: relative; border-bottom: 1px solid var(--line-1); }
.task:last-child { border-bottom: 0; }
.task.now { box-shadow: inset 2px 0 0 var(--accent); }
.task.done { opacity: 0.55; }
.task__head {
  width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: baseline;
  gap: 2px var(--s3); padding: var(--s3) var(--s2) var(--s3) var(--s3);
  border-radius: var(--r-sm); text-align: left;
  transition: background var(--mo-fast) var(--mo-out);
}
.task__head:hover { background: var(--fill-hover); }
.task__title { grid-column: 1 / -1; font-size: var(--fs-body); color: var(--ink-1); }
.task.done .task__title { text-decoration: line-through; color: var(--ink-3); }
.task__due { color: var(--ink-2); }
.task__from { text-align: right; color: var(--ink-3); }
.task__detail { padding: 0 var(--s2) var(--s4) var(--s3); display: grid; gap: var(--s3); }
.task__actions { display: flex; gap: var(--s2); }

@media (max-width: 980px) {
  .board { grid-template-columns: minmax(0, 1fr); }
}
</style>
