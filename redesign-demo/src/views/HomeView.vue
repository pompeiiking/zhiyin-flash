<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import { GUIDES, EMPTY_COPY, partialCopy } from '../data/copy'
import GuideNote from '../components/GuideNote.vue'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import { useCountUp } from '../lib/motion'
import type { TaskItem } from '../data/types'

/**
 * 任务与计划 —— **账页版式**（2026-10-11 重做）。
 *
 * 上一版是"248px 左索引栏 + 主块 8 / 次块 4"。它把"一列等宽卡片"治好了，
 * 却换来两个新毛病：正文被目录挤窄 15%，而且每行还是几个同宽方块（模板感回来了）。
 *
 * 这一版把目录与内容合成一张**横贯的账页**：每行左边一小格写"这一行是什么 + 计数"，
 * 右边是内容。左边那一格就是索引 —— 所以本文件里**没有**独立的索引栏组件，
 * 也不再需要"点一条只看那一块"那套焦点状态：账页本来就是一眼看全的一份文件。
 * 版面基元在 base.css 的 `.ledger*` 里，五个内页共用。
 */

const scenario = computed(() => demo.use.scenario.value)
const now = computed(() => demo.use.now.value)
const waiting = computed(() => demo.use.waiting.value)
const done = computed(() => demo.use.done.value)
const progress = computed(() => demo.use.profileProgress.value)
const smallest = computed(() => demo.use.smallestNow.value)

const groups = computed(() => [
  { key: 'now', title: '现在要做的', items: now.value, hint: '每条都写清：做什么 + 多久 + 为什么是现在' },
  { key: 'waiting', title: '等着的', items: waiting.value, hint: '不用你动，但要让你看得见' },
  { key: 'done', title: '已经做完的', items: done.value, hint: '完成记录只由真实行为驱动 —— 点了才算' },
])

/** 条数滚动：切换年级或补画像时，让"这个数变了"被看见 */
const { shown: knownShown } = useCountUp(computed(() => progress.value.known))
const { shown: gapShown } = useCountUp(computed(() => progress.value.gap))

/** 学习链：因为做了什么，所以哪里变了 */
const learningChain = computed(() => {
  const last = demo.state.lastDoneId
  if (!last) return null
  const t = done.value.find((x) => x.id === last)
  if (!t) return null
  return t
})

function badgeClass(t: TaskItem) {
  return t.origin === '建议的' ? 'chip--attention' : t.origin === '关键节点' ? 'chip--primary' : ''
}
</script>

<template>
  <div class="page">
    <header class="page__head">
      <div class="hstack hstack-3 between wrap">
        <div>
          <h1 class="page__title">任务与计划</h1>
          <p class="page__sub">
            你现在是{{ scenario.grade }}：{{ scenario.situation }}。这一年真正要解决的是 ——
            {{ scenario.focus }}。
          </p>
        </div>
        <RouterLink class="btn btn--primary" to="/chat">和主理聊聊</RouterLink>
      </div>
    </header>

    <div class="ledger">
      <!-- 紧凑统计条（2026-10-12 新加）：这一屏"有几个什么"摊在一条线上，一眼看完，
           不用往下滚。它刻意不做成"大数字 + 强调色"的 hero metric ——
           数字与正文同级、无强调色、无独立卡片。 -->
      <section class="ledger__row">
        <p class="ledger__label">这一屏</p>
        <div class="ledger__body">
          <div class="tally">
            <div class="tally__item">
              <span class="tally__n">{{ now.length }}</span><span class="tally__k">现在要做的</span>
            </div>
            <div class="tally__item">
              <span class="tally__n">{{ waiting.length }}</span><span class="tally__k">等着的</span>
            </div>
            <div class="tally__item">
              <span class="tally__n">{{ done.length }}</span><span class="tally__k">已经做完的</span>
            </div>
            <div class="tally__item">
              <span class="tally__n">{{ progress.known }}/{{ progress.total }}</span><span class="tally__k">学生档案</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 第一行＝这一屏唯一"今天要做的事"。焦点靠字号与留白当，不加彩色竖规。 -->
      <section v-if="smallest" class="ledger__row">
        <p class="ledger__label">今天这一件</p>
        <div class="ledger__body">
          <h2 class="today__title">{{ smallest.title }}</h2>
          <p class="today__why">{{ smallest.why }}</p>
          <div class="today__meta">
            <span class="chip">约 {{ smallest.minutes }} 分钟</span>
            <span class="chip chip--outline">{{ smallest.origin }}</span>
          </div>
        </div>
        <div class="ledger__aside">
          <button class="btn btn--primary" @click="demo.completeTask(smallest.id)">勾掉它</button>
          <button class="btn btn--ghost btn--sm" @click="demo.shrinkTask(smallest.id)">
            太大，改小
          </button>
        </div>
      </section>

      <!-- 三组任务：一组建一行。左边那格既是索引又是计数（不再另占一栏目录）。 -->
      <section v-for="g in groups" :key="g.key" class="ledger__row">
        <p class="ledger__label">{{ g.title }} · {{ g.items.length }}</p>
        <div class="ledger__body">
          <p class="ledger__hint">{{ g.hint }}</p>

          <ul v-if="g.items.length" class="tasks stagger">
            <li
              v-for="t in g.items"
              :key="t.id"
              class="task"
              :class="{ 'task--done': g.key === 'done', 'task--waiting': g.key === 'waiting' }"
            >
              <!-- 「现在要做的 / 已经做完的」：勾选区与标题都可点 —— 整行可点的第一步。
                   「等着的」按 GOV.UK 的 cannot-start-yet 语法：灰字，而且**行不链接**
                   （用户会去点不该点的东西，他们因此重新设计过这一处）。 -->
              <button
                v-if="g.key !== 'waiting'"
                class="task__check"
                :aria-label="g.key === 'done' ? `把「${t.title}」放回现在要做的` : `完成「${t.title}」`"
                @click="g.key === 'done' ? demo.reopenTask(t.id) : demo.completeTask(t.id)"
              >
                {{ g.key === 'done' ? '✓' : '' }}
              </button>
              <span v-else class="task__check task__check--off" aria-hidden="true" />

              <div class="task__main">
                <button
                  v-if="g.key !== 'waiting'"
                  class="task__title task__title--hit"
                  @click="g.key === 'done' ? demo.reopenTask(t.id) : demo.completeTask(t.id)"
                >
                  {{ t.title }}
                </button>
                <p v-else class="task__title">{{ t.title }}</p>
                <p v-if="t.why" class="task__why">{{ t.why }}</p>
                <div class="task__meta">
                  <span v-if="t.minutes" class="chip">约 {{ t.minutes }} 分钟</span>
                  <span class="chip chip--outline" :class="badgeClass(t)">{{ t.origin }}</span>
                  <span v-if="t.due" class="chip chip--attention">{{ t.due }}</span>
                  <span v-if="t.doneAt" class="t-note">{{ t.doneAt }} 完成</span>
                </div>
              </div>

              <div class="task__side">
                <button
                  v-if="t.origin === '建议的'"
                  class="btn btn--sm"
                  @click="demo.acceptSuggestion(t.id)"
                >
                  采纳
                </button>
                <button
                  v-if="t.origin === '建议的'"
                  class="btn btn--sm btn--ghost"
                  @click="demo.rejectSuggestion(t.id)"
                >
                  不适合
                </button>
                <button
                  v-if="g.key === 'now' && t.minutes > 5"
                  class="btn btn--sm btn--ghost"
                  @click="demo.shrinkTask(t.id)"
                >
                  改小
                </button>
              </div>
            </li>
          </ul>

          <div v-else class="empty">
            <p class="empty__title">{{ EMPTY_COPY.workbenchTitle }}</p>
            <p class="empty__body">{{ EMPTY_COPY.workbenchBody }}</p>
            <RouterLink class="btn btn--sm" to="/path">选一个方向</RouterLink>
          </div>
        </div>
      </section>

      <!-- 学生档案：进度不再是"第二列的一张卡"，而是账页里的一行 -->
      <section class="ledger__row">
        <p class="ledger__label">学生档案 · {{ progress.known }}/{{ progress.total }}</p>
        <div class="ledger__body">
          <p class="progress__text">{{ partialCopy(progress.known, progress.gap) }}</p>
          <div class="meter" style="margin-top: var(--sp-3); max-width: 420px">
            <div class="meter__fill" :style="{ '--meter': progress.known / progress.total }" />
          </div>
          <dl class="mini">
            <div class="mini__row">
              <dt>已经了解</dt>
              <dd class="t-num">{{ Math.round(knownShown) }} 条</dd>
            </div>
            <div class="mini__row">
              <dt>还差</dt>
              <dd class="t-num">{{ Math.round(gapShown) }} 条</dd>
            </div>
          </dl>
          <RouterLink class="btn btn--sm" to="/profile" style="margin-top: var(--sp-4)">
            补齐还差的 {{ progress.gap }} 条
          </RouterLink>
        </div>
      </section>

      <!-- 最后一行：两件"说明"并排。它们本来就不必各占一整行。 -->
      <section class="ledger__row">
        <p class="ledger__label">变化与支持</p>
        <div class="ledger__body ledger__body--pair">
          <div>
            <h3 class="ledger__title">因为做了什么，所以哪里变了</h3>
            <div v-if="learningChain" class="callout callout--done" style="margin-top: var(--sp-3)">
              <div>
                <p class="t-strong">「{{ learningChain.title }}」已记入完成记录</p>
                <p class="t-note" style="margin-top: var(--sp-1)">
                  画像里的"节奏"跟着变了一条 —— 完成记录只看真实行为，不看计划里写了什么。
                </p>
              </div>
            </div>
            <p v-else class="t-note" style="margin-top: var(--sp-3)">
              勾掉一件事，这里会告诉你"哪里跟着变了"。没勾过，这里就空着 —— 空着也是真的。
            </p>
          </div>

          <div>
            <h3 class="ledger__title">现在是谁在帮你</h3>
            <p class="t-note" style="margin-top: var(--sp-2)">
              同一时刻只有一个主理。换人时会有一张交接卡：谁接手、凭什么、为什么。
            </p>
            <div class="hstack hstack-2" style="margin-top: var(--sp-4)">
              <ConfidenceBadge :value="{ level: 'high', label: '比较确定', bars: 3 }" />
              <span class="t-note">这位主理对你当前情况的把握</span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <GuideNote gkey="home" :text="GUIDES.home" to="/plan" to-label="看完整计划" />
  </div>
</template>

<style scoped>
/* 任务行：靠留白分组，不逐行画线（与其余四页同一套语法） */
.tasks {
  display: flex;
  flex-direction: column;
}

.task {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-4) 0;
}

.task:first-child {
  padding-top: 0;
}

.task:last-child {
  padding-bottom: 0;
}

.task__check {
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 2px;
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  font-size: var(--fs-12);
  color: var(--c-on-primary);
  display: grid;
  place-items: center;
}

.task__check:hover {
  border-color: var(--c-primary);
}

.task--done .task__check {
  background: var(--c-done);
  border-color: var(--c-done);
}

.task--done .task__title {
  color: var(--c-text-3);
  text-decoration: line-through;
}

.task__main {
  flex: 1;
  min-width: 0;
}

.task__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  text-align: left;
  color: var(--c-text);
}

/* 标题本身也能点 —— "整行可点"的第一步（勾选区之外再给一个大目标） */
.task__title--hit:hover {
  color: var(--c-primary);
}

/* 「等着的」：灰字，而且行不链接（GOV.UK 的 cannot-start-yet 语法：
   用户会去点不该点的东西，所以他们把这一档重新设计过） */
.task--waiting .task__title {
  color: var(--c-text-3);
}

.task__check--off {
  background: transparent;
  border-style: dashed;
  opacity: 0.55;
}

.task__why {
  margin-top: 2px;
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: var(--lh-snug);
  max-width: 34em;
}

.task__meta {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
  flex-wrap: wrap;
}

.task__side {
  display: flex;
  gap: var(--sp-1);
  flex: none;
}

.progress__text {
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.mini {
  margin: var(--sp-4) 0 0;
  max-width: 420px;
}

.mini__row {
  display: flex;
  justify-content: space-between;
  padding: var(--sp-2) 0;
  font-size: var(--fs-14);
}

.mini__row dt {
  color: var(--c-text-3);
}

.mini__row dd {
  margin: 0;
  font-weight: var(--fw-medium);
}
</style>
