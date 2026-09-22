<script setup lang="ts">
/**
 * 所有图表共用的外壳：标题 + 一句说明 + 画布。
 *
 * 图表是手绘的，所以外壳不给"卡片 + 阴影"那种规整的盒子：一条虚线边框、
 * 四个角不完全一样的圆角、左上角一撇起笔。它是**一页纸上的画**，不是一块面板。
 * （中途改成过规整的实线框 + 小圆点，读起来更"产品"，但那一版整屏失去了手作感 ——
 * 用户的原话是"没有质感"。这一版的取舍：外壳保持手绘，层次交给它下面那张纸。）
 */
defineProps<{ title: string; note?: string; tone?: string; wide?: boolean }>()
</script>

<template>
  <figure class="cf" :class="{ 'cf--wide': wide }" :style="tone ? { '--cf-tone': tone } : undefined">
    <figcaption class="cf__head">
      <span class="cf__title">{{ title }}</span>
      <span v-if="note" class="label cf__note">{{ note }}</span>
    </figcaption>
    <slot />
  </figure>
</template>

<style scoped>
.cf {
  --cf-tone: var(--mk-green);
  position: relative;
  display: flex; flex-direction: column; gap: var(--s2);
  padding: var(--s4) var(--s4) var(--s3);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-md) var(--r-lg) var(--r-md) var(--r-lg);
  background: var(--paper-lit-soft);
  box-shadow: var(--e-1), var(--inner-hi);
}
.cf--wide { grid-column: 1 / -1; }

/* 角上那一小笔画：手绘的东西总有起笔 */
.cf::after {
  content: "";
  position: absolute; left: 14px; top: -2px;
  width: 38px; height: 4px;
  background: var(--cf-tone);
  border-radius: 3px;
  transform: rotate(-0.8deg);
}
.cf__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.cf__title { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.cf__note { color: var(--ink-3); }
</style>
