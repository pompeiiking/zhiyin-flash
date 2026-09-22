<script setup lang="ts">
import { computed, ref } from 'vue'
import ChartFrame from './ChartFrame.vue'
import SketchPath from './SketchPath.vue'
import { sCircle, sPath, sPolyline, smoothPath } from '@/lib/sketch'
import type { TrendPoint } from '@/ai/registry'

/**
 * 把握度是怎么长起来的 —— 手绘版。
 * 每个拐点都点得开：那一刻具体发生了什么（包括把握度为什么反而掉了）。
 *
 * 线交给 rough 抖：这张图讲的是"一路长起来"，一笔画上去的线比规整折线更贴这件事。
 * 读数是兜底的：每个点上直接标数值，所以线画得再随意也不影响读数。
 */
const props = defineProps<{ points: TrendPoint[] }>()
const emit = defineEmits<{ (e: 'pick', index: number): void }>()

const active = ref(props.points.length - 1)

const W = 320
const H = 96
const PAD = 18
const TOP = 18
const BOTTOM = 78

const coords = computed(() =>
  props.points.map((p, i) => ({
    ...p,
    x: PAD + (i * (W - PAD * 2)) / Math.max(1, props.points.length - 1),
    y: BOTTOM - (BOTTOM - TOP) * p.v,
  })),
)

/** 线用自己的平滑路径，再交给 rough 抖一下 —— 比逐段画短线更像一笔 */
const lineOps = computed(() =>
  sPath(smoothPath(coords.value.map((c) => [c.x, c.y])), {
    seed: 21, stroke: 'var(--mk-green)', strokeWidth: 2.4, roughness: 0.7,
  }),
)
const areaOps = computed(() =>
  sPath(smoothPath(coords.value.map((c) => [c.x, c.y])) + ` L${coords.value[coords.value.length - 1].x},${BOTTOM} L${coords.value[0].x},${BOTTOM} Z`, {
    seed: 22, stroke: 'none', fill: 'var(--mk-green-soft)', roughness: 1.6,
  }),
)
const axisOps = computed(() => sPolyline([[PAD, TOP - 6], [PAD, BOTTOM], [W - PAD + 6, BOTTOM]], { seed: 31, stroke: 'var(--line-3)', strokeWidth: 1.3 }))
const dotOps = computed(() =>
  coords.value.map((c, i) =>
    sCircle(c.x, c.y, active.value === i ? 5.4 : 4, {
      seed: 40 + i,
      stroke: 'var(--mk-green)',
      strokeWidth: 2,
      fill: active.value === i ? 'var(--mk-green)' : '#ffffff',
    }),
  ),
)
const current = computed(() => coords.value[active.value])
</script>

<template>
  <ChartFrame title="把握度是怎么长起来的" :note="`${points[0].at} → ${current.at}`" tone="var(--mk-purple)">
    <svg class="plot" :viewBox="`0 0 ${W} ${H}`" role="img"
         :aria-label="`把握度从 ${points[0].v} 长到 ${points[points.length - 1].v}，共 ${points.length} 次变化`">
      <SketchPath :ops="axisOps" opacity="0.5" />
      <SketchPath :ops="areaOps" opacity="0.85" />
      <SketchPath :ops="lineOps" />

      <g
        v-for="(c, i) in coords"
        :key="c.at + i"
        class="pt"
        :class="{ on: active === i }"
        tabindex="0"
        role="button"
        :aria-label="`${c.at} 把握度 ${c.v}：${c.why}`"
        @mouseenter="active = i"
        @focus="active = i"
        @click="emit('pick', i)"
        @keydown.enter="emit('pick', i)"
      >
        <circle class="hit" :cx="c.x" :cy="c.y" r="13" />
        <SketchPath :ops="dotOps[i]" />
        <text class="val" :x="c.x" :y="c.y - 11">{{ c.v.toFixed(2) }}</text>
        <text class="at" :x="c.x" :y="BOTTOM + 14">{{ c.at }}</text>
      </g>
    </svg>

    <button class="why" type="button" @click="emit('pick', active)">
      <span class="mono why__at">{{ current.at }}</span>
      <span>{{ current.why }}</span>
    </button>
  </ChartFrame>
</template>

<style scoped>
.plot { width: 100%; max-width: 560px; height: auto; display: block; overflow: visible; margin-inline: auto; }
.pt { cursor: var(--cursor-dot); outline: none; }
.hit { fill: transparent; }
.pt:focus-visible .hit { fill: var(--accent-glow); }
.val { font-family: var(--font-sans); font-variant-numeric: tabular-nums; font-size: 10.5px; fill: var(--ink-3); text-anchor: middle; pointer-events: none; }
.pt.on .val { fill: var(--mk-green); }
.at { font-family: var(--font-sans); font-variant-numeric: tabular-nums; font-size: 10px; fill: var(--ink-3); text-anchor: middle; opacity: 0.75; }

.why {
  display: inline-flex; align-items: baseline; gap: var(--s3);
  font-size: var(--fs-small); color: var(--ink-2); text-align: left;
  transition: color var(--mo-fast) var(--mo-out);
}
.why:hover { color: var(--ink-1); }
.why__at { flex: 0 0 auto; color: var(--ink-3); }
</style>
