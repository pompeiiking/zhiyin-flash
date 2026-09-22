<script setup lang="ts">
import { computed } from 'vue'
import SketchPath from '@/components/charts/SketchPath.vue'
import { sCircle, sRect } from '@/lib/sketch'

/**
 * 一笔画出来的按钮。
 *
 * 为什么不用 `.btn`：圆角矩形本身就是一个"框"。这一版门户里所有可点的东西
 * 都不该长成框 —— 它是**纸上画的一圈线**，鼠标上去，圈里的墨填满。
 *
 * 结构上仍然是一个原生 button（键盘、焦点、语义都不丢），
 * 那圈线只是它背后的 SVG。
 */
const props = withDefaults(defineProps<{ label: string; tone?: string; big?: boolean; kind?: 'blob' | 'pill' }>(), {
  tone: 'var(--accent)',
  big: false,
  kind: 'pill',
})
const emit = defineEmits<{ (e: 'click'): void }>()

/** 椭圆更像"手画的圈"；pill 用来放稍长的文字 */
const ops = computed(() =>
  props.kind === 'blob'
    ? sCircle(90, 26, 24, { seed: 601, stroke: 'currentColor', strokeWidth: 2.4, roughness: 1.5 })
    : sRect(2, 3, 176, 46, { seed: 602, stroke: 'currentColor', strokeWidth: 2.4, roughness: 1.6 }),
)
</script>

<template>
  <button class="ib" :class="{ 'ib--big': props.big }" type="button" :style="{ '--tone': props.tone }" @click="emit('click')">
    <svg class="ib__ring" viewBox="0 0 180 52" fill="none" aria-hidden="true">
      <SketchPath :ops="ops" />
    </svg>
    <span class="ib__label">{{ props.label }}</span>
  </button>
</template>

<style scoped>
.ib {
  position: relative;
  display: inline-flex; align-items: center; justify-content: center;
  height: 52px; padding: 0 var(--s5);
  color: var(--tone);
  transition: color 260ms var(--mo-out);
}
.ib--big { height: 62px; padding: 0 var(--s6); }

.ib__ring { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.ib__ring :deep(path) {
  stroke-dasharray: 1; stroke-dashoffset: 1;
  transition: stroke-dashoffset 900ms cubic-bezier(0.16, 1, 0.3, 1), fill 300ms var(--mo-out), stroke-width 200ms var(--mo-out);
}
/* 圈自己画出来 */
.ib :deep(path) { animation: ib-draw 900ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
@keyframes ib-draw { to { stroke-dashoffset: 0; } }

.ib__label { position: relative; font-size: var(--fs-body); font-weight: 600; letter-spacing: 0.02em; }

/* 悬停：圈里进墨，字反白 —— 一笔画的按钮最自然的状态变化 */
.ib:hover { color: var(--accent-ink); }
.ib:hover .ib__ring :deep(path) { fill: var(--tone); stroke-width: 2.8; }

/*
 * 焦点环不省：手绘的圈太细，键盘用户需要一个一眼能看见的指示。
 * 用实心描边 + 6px 间距，和那圈手绘线并列存在，互不干扰。
 */
.ib:focus-visible {
  outline: 3px solid var(--tone);
  outline-offset: 6px;
  border-radius: var(--r-pill);
}
.ib:focus-visible .ib__ring :deep(path) { stroke-width: 3.4; }

@media (prefers-reduced-motion: reduce) {
  .ib__ring :deep(path) { animation: none; stroke-dashoffset: 0; }
}
</style>
