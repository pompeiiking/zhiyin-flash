<script setup lang="ts">
import { computed } from 'vue'

/**
 * 趋势线：只画一条，只标一个变化点。
 * 报告里的"第 1 版 → 这一版"用的就是它。
 */
const props = defineProps<{
  points: { label: string; value: number }[]
  /** 高亮的那个点（例如"这一版"） */
  highlightIndex?: number
  height?: number
}>()

const W = 420
const H = computed(() => props.height ?? 132)
const PAD_X = 28
const PAD_Y = 22

const min = computed(() => Math.min(...props.points.map((p) => p.value)) - 6)
const max = computed(() => Math.max(...props.points.map((p) => p.value)) + 6)

function px(i: number) {
  const n = props.points.length
  return n <= 1 ? W / 2 : PAD_X + (i / (n - 1)) * (W - PAD_X * 2)
}

function py(v: number) {
  const span = max.value - min.value || 1
  return H.value - PAD_Y - ((v - min.value) / span) * (H.value - PAD_Y * 2)
}

const line = computed(() =>
  props.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${px(i).toFixed(1)},${py(p.value).toFixed(1)}`).join(' '),
)

const area = computed(
  () => `${line.value} L${px(props.points.length - 1).toFixed(1)},${H.value - PAD_Y} L${px(0).toFixed(1)},${H.value - PAD_Y} Z`,
)
</script>

<template>
  <svg
    :width="W"
    :height="H"
    :viewBox="`0 0 ${W} ${H}`"
    role="img"
    :aria-label="`趋势：${points.map((p) => `${p.label} ${p.value}`).join('，')}`"
    class="trend"
  >
    <line
      :x1="PAD_X"
      :y1="H - PAD_Y"
      :x2="W - PAD_X"
      :y2="H - PAD_Y"
      stroke="var(--chart-axis)"
      stroke-width="1"
    />
    <path :d="area" fill="var(--chart-1)" fill-opacity="0.08" />
    <path :d="line" fill="none" stroke="var(--chart-1)" stroke-width="2" />

    <g v-for="(p, i) in points" :key="p.label">
      <circle
        :cx="px(i)"
        :cy="py(p.value)"
        :r="highlightIndex === i ? 5 : 3.5"
        fill="var(--c-surface)"
        :stroke="highlightIndex === i ? 'var(--chart-2)' : 'var(--chart-1)'"
        stroke-width="2"
      />
      <text
        :x="px(i)"
        :y="H - 6"
        text-anchor="middle"
        style="font-size: var(--fs-12)"
        fill="var(--c-text-3)"
      >
        {{ p.label }}
      </text>
      <text
        :x="px(i)"
        :y="py(p.value) - 10"
        text-anchor="middle"
        style="font-size: var(--fs-12)"
        :fill="highlightIndex === i ? 'var(--c-text)' : 'var(--c-text-3)'"
      >
        {{ p.value }}
      </text>
    </g>
  </svg>
</template>

<style scoped>
.trend {
  width: 100%;
  height: auto;
}
</style>
