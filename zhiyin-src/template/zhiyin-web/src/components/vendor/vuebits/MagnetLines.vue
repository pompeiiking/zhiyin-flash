<!--
  vue-bits · MagnetLines  （DavidHDev/vue-bits, MIT）
  原件取自 https://vue-bits.dev/animations/MagnetLines
  本项目改动：去掉 Tailwind 类名（grid place-items-center / block origin-center），
  换成 scoped CSS；线宽线高与颜色按传入值走，可以直接吃本项目的令牌。
-->
<script setup lang="ts">
import { onMounted, onUnmounted, computed, useTemplateRef } from 'vue';

interface MagnetLinesProps {
  rows?: number;
  columns?: number;
  containerSize?: string;
  lineColor?: string;
  lineWidth?: string;
  lineHeight?: string;
  baseAngle?: number;
  className?: string;
  style?: Record<string, string | number>;
}

const props = withDefaults(defineProps<MagnetLinesProps>(), {
  rows: 9,
  columns: 9,
  containerSize: '80vmin',
  lineColor: '#efefef',
  lineWidth: '1vmin',
  lineHeight: '6vmin',
  baseAngle: -10,
  className: '',
  style: () => ({})
});

const containerRef = useTemplateRef<HTMLDivElement>('containerRef');

const total = computed(() => props.rows * props.columns);

/*
 * 本项目改动（性能）：原件每次 pointermove 都对**每一根线**调 getBoundingClientRect()
 * —— 126 根就是 126 次布局查询，鼠标一动整页都在抖。
 * 现在把每根线的中心点缓存起来（只有尺寸变化才会变），并且用 rAF 合帧。
 */
type LineItem = { el: HTMLSpanElement; cx: number; cy: number };
let lines: LineItem[] = [];
let frame = 0;
let pending: { x: number; y: number } | null = null;

const measure = () => {
  const container = containerRef.value;
  if (!container) return;
  lines = [...container.querySelectorAll<HTMLSpanElement>('span')].map(el => {
    const rect = el.getBoundingClientRect();
    return { el, cx: rect.x + rect.width / 2, cy: rect.y + rect.height / 2 };
  });
};

const onPointerMove = (pointer: { x: number; y: number }) => {
  for (const item of lines) {
    const b = pointer.x - item.cx;
    const a = pointer.y - item.cy;
    const c = Math.sqrt(a * a + b * b) || 1;
    const r = ((Math.acos(b / c) * 180) / Math.PI) * (pointer.y > item.cy ? 1 : -1);
    item.el.style.setProperty('--rotate', `${r}deg`);
  }
};

const flush = () => {
  frame = 0;
  const p = pending;
  pending = null;
  if (p) onPointerMove(p);
};

const handlePointerMove = (e: PointerEvent) => {
  pending = { x: e.x, y: e.y };
  if (!frame) frame = requestAnimationFrame(flush);
};

onMounted(() => {
  const container = containerRef.value;
  if (!container) return;

  window.addEventListener('pointermove', handlePointerMove);

  measure();
  if (lines.length) {
    const middle = lines[Math.floor(lines.length / 2)];
    onPointerMove({ x: middle.cx, y: middle.cy });
  }
});

onUnmounted(() => {
  window.removeEventListener('pointermove', handlePointerMove);
  if (frame) cancelAnimationFrame(frame);
});
</script>

<template>
  <div
    ref="containerRef"
    class="ml"
    :class="props.className"
    :style="{
      gridTemplateColumns: `repeat(${props.columns}, 1fr)`,
      gridTemplateRows: `repeat(${props.rows}, 1fr)`,
      width: props.containerSize,
      height: props.containerSize,
      ...props.style
    }"
  >
    <span
      v-for="i in total"
      :key="i"
      class="ml__line"
      :style="{
        backgroundColor: props.lineColor,
        width: props.lineWidth,
        height: props.lineHeight,
        '--rotate': `${props.baseAngle}deg`,
        transform: 'rotate(var(--rotate))',
        willChange: 'transform'
      }"
    />
  </div>
</template>

<style scoped>
/* 原件这里是 Tailwind 的 grid place-items-center */
.ml { display: grid; place-items: center; }
/* 原件这里是 block origin-center */
.ml__line { display: block; transform-origin: center; }
</style>

