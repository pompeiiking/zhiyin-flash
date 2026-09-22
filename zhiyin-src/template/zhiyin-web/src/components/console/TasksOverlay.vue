<script setup lang="ts">
import { computed, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { todoTask, type TodoSuggestion } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'

/**
 * 待办 —— 三栏，但重点是**两个来源分得清**。
 *
 * 左：智能体建议（每条都写着"为什么、从哪来、建议放哪段时间"），可采纳、可直接否掉
 * 中：今天与待办（含你自己写进去的），顶部一条输入框随手加
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
}

const today = computed<Row[]>(() =>
  session.customTodos
    .filter((t) => !t.done)
    .map((t) => ({ id: t.id, title: t.label, due: '你写的', from: '你自己', detail: '' })),
)
const done = computed<Row[]>(() =>
  session.customTodos
    .filter((t) => t.done)
    .map((t) => ({ id: t.id, title: t.label, due: '你写的', from: '你自己', detail: '' })),
)

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
    subtitle="左边是智能体建议 · 中间是你自己的清单 · 两边分得清"
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

      <!-- 二、今天与待办（含自建） -->
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
              <p class="dim">{{ 'detail' in t && t.detail ? t.detail : '这一条是你自己加进来的。' }}</p>
              <div class="task__actions">
                <button class="btn primary" type="button" @click="complete(t)">勾掉</button>
                <button class="btn ghost" type="button" @click="openDetail(t as never)">看依据</button>
              </div>
            </div>
          </li>

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
            <span class="task__title">{{ t.title }}</span>
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
.task { border-bottom: 1px solid var(--line-1); }
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
