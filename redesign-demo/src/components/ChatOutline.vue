<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import type { ChatTurn } from '../data/types'

/**
 * 左栏 ·「这次聊出来的」。
 *
 * 对话页正文列 760px，两侧各空着几百像素。右侧栏（CollectRail）放的是**输入**：
 * 我们了解到什么。左边这一栏放**输出**：这次对话聊出了什么 ——
 * 谁接过手、产出了哪些待办。一进一出，两边都有真事做，不是拿装饰填空。
 *
 * 数据全部来自已经在跑的东西：交接链取 `turns` 里的 handoff 字段（产品要求交接卡三件事齐全：
 * 谁接手／凭什么／为什么），产出的待办取 store 里 origin 为"计划拆下来的"那些任务。
 * 一栏里不新造任何数据。
 */

const props = defineProps<{ turns: ChatTurn[] }>()

/** 交接链：谁接过手、为什么。产品口径里这是一次"环节切换"，必须留痕 */
const chain = computed(() =>
  props.turns
    .filter((t) => t.handoff)
    .map((t) => t.handoff!)
    .slice(-2),
)

/** 这次对话真正产出的待办：只有 origin 是"计划拆下来的"才算 —— 系统建议的不算产出 */
const planned = computed(() =>
  [...demo.use.now.value, ...demo.use.waiting.value].filter((t) => t.origin === '计划拆下来的'),
)
</script>

<template>
  <aside class="outline" aria-label="这次聊出来的">
    <header class="outline__head">
      <p class="outline__title">这次聊出来的</p>
    </header>

    <!-- 交接链 -->
    <section v-if="chain.length" class="part">
      <p class="part__label">谁接过手</p>
      <ol class="chain">
        <li v-for="h in chain" :key="h.to" class="chain__item">
          <span class="chain__to">{{ h.to }}</span>
          <span class="chain__why">{{ h.why }}</span>
        </li>
      </ol>
    </section>

    <!-- 产出的待办 -->
    <section class="part">
      <p class="part__label">已经产出</p>
      <ul v-if="planned.length" class="made">
        <li v-for="t in planned.slice(0, 4)" :key="t.id" class="made__item">
          <span class="made__title">{{ t.title }}</span>
          <span class="made__min t-num">{{ t.minutes }} 分钟</span>
        </li>
      </ul>
      <!--
        还没产出时不写"暂无数据"，而是说清**什么时候才会有** ——
        空状态要交代条件，不能让用户以为界面坏了。
      -->
      <p v-else class="outline__quiet">
        还没产出待办。聊到"要动起来"的时候，这里会出现一件具体的事。
      </p>
    </section>

    <RouterLink class="outline__more" to="/plan">去计划与行动</RouterLink>
  </aside>
</template>

<style scoped>
/* 网格第一栏（对话页最左）。与右栏同一种卡片语言，但更轻 ——
   它是"脉络"，不是要读细的正文。 */
.outline {
  grid-column: 1;
  grid-row: 1 / -1;
  align-self: start;
  position: sticky;
  top: var(--sp-4);
  padding: var(--sp-5);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
}

.outline__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
}

.part {
  margin-top: var(--sp-5);
}

.part__label {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* ---- 交接链：一条细线串起环节，节点是主色圆点 ---- */
.chain {
  margin-top: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.chain__item {
  position: relative;
  padding-left: var(--sp-4);
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
}

/* 节点：用 ::before 画，不额外加 DOM */
.chain__item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 5px;
  width: 6px;
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--c-primary);
}

/* 连线：除最后一项都往下拉一根发丝线 */
.chain__item:not(:last-child)::after {
  content: '';
  position: absolute;
  left: 2px;
  top: 14px;
  bottom: calc(-1 * var(--sp-3));
  width: 1px;
  background: var(--c-border);
}

.chain__to {
  color: var(--c-text);
  font-weight: var(--fw-medium);
  display: block;
}

.chain__why {
  color: var(--c-text-3);
}

/* ---- 产出的待办 ---- */
.made {
  margin-top: var(--sp-3);
  display: flex;
  flex-direction: column;
}

.made__item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: var(--sp-2) 0;
  border-bottom: var(--bw-1) solid var(--c-border);
  font-size: var(--fs-12);
}

.made__item:last-child {
  border-bottom: none;
}

.made__title {
  color: var(--c-text);
  min-width: 0;
}

.made__min {
  color: var(--c-text-3);
  flex: none;
}

.outline__quiet {
  margin-top: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

.outline__more {
  display: inline-block;
  margin-top: var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-primary);
}
</style>
