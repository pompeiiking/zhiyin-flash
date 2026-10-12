<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { demo } from '../store'
import { PROFILE_FIELDS } from '../data/student'

/**
 * 采集侧栏 —— 随对话同步推进的「我们了解到什么」。
 *
 * 对话页正文列是 760px 居中，在 1600 屏上两侧各空约 420px。这一栏放在右侧，
 * 把空的那边填成**有信息的一块**，而不是再摆一段装饰。
 *
 * 三条纪律：
 *  1. **表达事实，不表达要求**。列出来的只有"已经了解到的"；缺口只用一句话带过，
 *     不做成待办清单 —— 产品承诺"答不上来可以跳过"，把缺的逐条列出来就成了催办。
 *  2. **只动 transform / opacity**。逐段填充用每段自己的 `::after` 做 `scaleX`，
 *     新字段入场用位移 + 淡入；没有任何布局属性参与动画。
 *  3. **不新增颜色**。已填充 = 主色，未填充 = 描边色，文字走既有三档灰。
 *
 * 数据只有一个来源：store 的 `profileProgress`（年级基线 + 本次对话采集量）。
 * 导航底部那条进度线读的也是它，两处不会各说各话。
 */

const progress = computed(() => demo.use.profileProgress.value)

/** 只列已经了解到的那些 —— 缺的不列 */
const knownFields = computed(() => PROFILE_FIELDS.slice(0, progress.value.known))

/** 每一段的开关状态；index 也用来做错开的填充延迟 */
const segs = computed(() => PROFILE_FIELDS.map((_, i) => i < progress.value.known))

/*
 * 截图与评审用：`#/chat?collected=8` 直接把采集进度推进 8 条。
 * 真实产品里没有这个口子 —— 它是为了让"随对话推进"这件事能被一张静态图看见。
 */
onMounted(() => {
  const raw = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('collected')
  const n = Number(raw)
  if (Number.isFinite(n) && n > 0) demo.noteCollected(n)
})
</script>

<template>
  <aside class="collect" aria-label="学生档案">
    <header class="collect__head">
      <p class="collect__title">学生档案</p>
      <p class="collect__num">
        <span class="t-num">{{ progress.known }}</span>
        <span class="collect__of"> / {{ progress.total }} 条</span>
      </p>
    </header>

    <!-- 15 段：已了解的点亮，随对话一段段加上去 -->
    <div
      class="segs"
      role="img"
      :aria-label="`已经了解 ${progress.known} 条，共 ${progress.total} 条，随对话一条条加上去`"
    >
      <span
        v-for="(on, i) in segs"
        :key="i"
        class="seg"
        :class="{ 'seg--on': on }"
        :style="{ transitionDelay: `${i * 22}ms` }"
      />
    </div>

    <ul class="fields">
      <TransitionGroup name="field">
        <li v-for="f in knownFields" :key="f.key" class="collect__row">
          <span class="collect__key">{{ f.label }}</span>
          <span class="collect__val">{{ f.value }}</span>
        </li>
      </TransitionGroup>
    </ul>

    <p class="collect__gap">
      还有 {{ progress.gap }} 条会在后面聊到。答不上来可以跳过 ——
      <strong>跳过不会记成"缺失"</strong>。
    </p>

    <RouterLink class="collect__more" to="/profile">看完整的学生档案</RouterLink>
  </aside>
</template>

<style scoped>
/**
 * 它是**网格里的一栏**（对话页的第三列），不是浮在页面上的固定面板 ——
 * 上一版用 position: fixed，结果压住了对话页头部那个「看"对你的了解"」按钮：
 * 固定定位不受网格约束，谁在上面取决于谁后画。
 * 现在它回到文档流里，列位置由父级 `.chat` 的网格决定；柱内自己 sticky + 滚动。
 */
/* ⚠️ 这个类名**绝对不能**再叫 `.rail`。
   `base.css` 里的 `.rail` 已经是"内页索引式档案页"的版式容器
   （`display: grid; grid-template-columns: 248px minmax(0, 1fr)`）。
   两个含义撞在一起时，本组件 scoped 的 `.rail[data-v-*]` 只覆盖它自己声明过的属性，
   **没有声明 `display` 与 `grid-template-columns`**，于是这条 252px 宽的右栏被套上了
   两列网格：`.collect__head`/`.fields`/`.collect__more` 落在 248px 首列，
   而 **15 段进度条 `.segs` 与「还差几条」那段文字被塞进第二列、宽度压成 0**（等于看不见）。
   实测：内容 321px / 可视 250px，横向溢出 71px，右栏出现横向滚动条。
   2026-10-11 由客户报出（"右侧学生档案展示不全，需要左右滑动"）后改名为 `.collect`。
   守住它的是 `.tmp-research/lead-overflow.mjs`（任何元素 scrollWidth > clientWidth 即失败）。 */
.collect {
  grid-column: 3;
  grid-row: 1 / -1;
  align-self: start;
  position: sticky;
  top: var(--sp-4);
  max-height: calc(100vh - var(--w-topbar) - var(--sp-8));
  overflow-y: auto;
  padding: var(--sp-5);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
}

.collect__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
}

.collect__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
}

.collect__num {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  color: var(--c-primary);
  line-height: 1;
}

.collect__of {
  font-size: var(--fs-12);
  font-weight: 400;
  color: var(--c-text-3);
}

/* ---- 15 段进度 ---- */
.segs {
  display: flex;
  gap: 3px;
  margin-top: var(--sp-4);
  height: 6px;
}

.seg {
  position: relative;
  flex: 1;
  border-radius: var(--r-pill);
  background: var(--c-border);
  overflow: hidden;
}

/* 填充只用 scaleX —— 纯 transform，不碰宽度 */
.seg::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--c-primary);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform var(--dur-4) var(--ease-out);
}

.seg--on::after {
  transform: scaleX(1);
}

/* ---- 已了解到的字段 ---- */
.fields {
  margin-top: var(--sp-5);
  display: flex;
  flex-direction: column;
}

.collect__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  /* 11 行不画 11 条线：靠留白分组（GOV.UK：分隔线 opt-in、留白是默认）。 */
  padding: var(--sp-3) 0;
}

.collect__row:first-child {
  padding-top: 0;
}

.collect__row:last-child {
  padding-bottom: 0;
}

.collect__key {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  flex: none;
}

.collect__val {
  font-size: var(--fs-12);
  color: var(--c-text);
  text-align: right;
  /* 值长短不一：让它能折行，但不把标签挤走 */
  min-width: 0;
}

/* 新采集到的一条：淡入 + 上移 4px */
.field-enter-active {
  transition:
    opacity var(--dur-3) var(--ease-out),
    transform var(--dur-3) var(--ease-out);
}

.field-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.collect__gap {
  margin-top: var(--sp-4);
  padding-top: var(--sp-4);
  border-top: var(--bw-1) solid var(--c-border);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

.collect__gap strong {
  color: var(--c-text-2);
  font-weight: var(--fw-medium);
}

.collect__more {
  display: inline-block;
  margin-top: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--c-primary);
}

/* 减少动效：填充与入场都直接到位 */
@media (prefers-reduced-motion: reduce) {
  .seg::after,
  .field-enter-active {
    transition: none;
  }

  .field-enter-from {
    transform: none;
  }
}
</style>
