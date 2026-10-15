<script setup lang="ts">
import { computed } from 'vue'

/**
 * 能力雷达图。
 *
 * 刻意不引图表库：这份界面只有三支主色，
 * 图表也必须只用这三支 —— 手写 SVG 才能保证不出现库自带的第四种颜色。
 */
const props = withDefaults(
  defineProps<{
    axes: { label: string; value: number }[]
    size?: number
    /** 对比基准（可选）：上一条主线要求的分值 */
    baseline?: number
  }>(),
  { size: 260, baseline: 50 },
)

const R = computed(() => props.size / 2 - 34)
const C = computed(() => props.size / 2)

const angle = (i: number) => (Math.PI * 2 * i) / props.axes.length - Math.PI / 2

function point(i: number, ratio: number) {
  const a = angle(i)
  return [C.value + Math.cos(a) * R.value * ratio, C.value + Math.sin(a) * R.value * ratio]
}

const rings = [0.25, 0.5, 0.75, 1]

function ringPath(ratio: number) {
  return (
    props.axes
      .map((_, i) => {
        const [x, y] = point(i, ratio)
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ') + ' Z'
  )
}

const dataPath = computed(
  () =>
    props.axes
      .map((ax, i) => {
        const [x, y] = point(i, Math.max(0.05, Math.min(1, ax.value / 100)))
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ') + ' Z',
)

const baselinePath = computed(
  () =>
    props.axes
      .map((_, i) => {
        const [x, y] = point(i, props.baseline / 100)
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ') + ' Z',
)

const spokes = computed(() => props.axes.map((_, i) => point(i, 1)))

const labels = computed(() =>
  props.axes.map((ax, i) => {
    const [x, y] = point(i, 1.16)
    return { ...ax, x, y }
  }),
)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    role="img"
    :aria-label="`能力雷达图：${axes.map((a) => `${a.label} ${a.value} 分`).join('，')}`"
  >
    <!-- 网格 -->
    <path
      v-for="r in rings"
      :key="r"
      :d="ringPath(r)"
      fill="none"
      stroke="var(--chart-grid)"
      stroke-width="1"
    />
    <!-- 轴线 -->
    <line
      v-for="(p, i) in spokes"
      :key="`s${i}`"
      :x1="C"
      :y1="C"
      :x2="p[0]"
      :y2="p[1]"
      stroke="var(--chart-grid)"
      stroke-width="1"
    />
    <!-- 基准线：两条主攻方向要求的分值 -->
    <path
      :d="baselinePath"
      fill="none"
      stroke="var(--chart-2)"
      stroke-width="1"
      stroke-dasharray="3 3"
      opacity="0.55"
    />
    <!-- 数据 -->
    <path :d="dataPath" fill="var(--chart-1)" fill-opacity="0.14" stroke="var(--chart-1)" stroke-width="2" />
    <circle
      v-for="(ax, i) in axes"
      :key="`d${i}`"
      :cx="point(i, Math.max(0.05, Math.min(1, ax.value / 100)))[0]"
      :cy="point(i, Math.max(0.05, Math.min(1, ax.value / 100)))[1]"
      r="3"
      fill="var(--c-surface)"
      stroke="var(--chart-1)"
      stroke-width="2"
    />
    <!-- 轴名与分值 -->
    <text
      v-for="(l, i) in labels"
      :key="`l${i}`"
      :x="l.x"
      :y="l.y"
      text-anchor="middle"
      dominant-baseline="middle"
      style="font-size: var(--fs-12)"
      fill="var(--c-text-3)"
    >
      {{ l.label }} {{ l.value }}
    </text>
  </svg>
</template>
