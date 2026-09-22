<script setup lang="ts">
import { computed } from 'vue'
import SketchPath from '@/components/charts/SketchPath.vue'
import { sCircle, sLine } from '@/lib/sketch'
import type { PortalStop } from '@/data/portal'

/*
 * 一个站点（圈 + 一块批注）。
 *
 * 字的位置在上一版是错的，错的不是"左右交替"这个想法，是做法太机械：
 *   ① 时间与站名分居圈的两侧 —— 读一个点要在左右之间跳两次
 *   ② 偏移固定 52、两侧严格交替 —— 读起来是一排锯齿，不是一张画
 *   ③ 全部水平居中 —— 和曲线的走向没有任何关系
 *   ④ 八个圈一样大 —— 起点、终点和路过的点没有主次
 *
 * 现在：
 *   · 时间和站名合成**一块**批注（时间在名字上方，一小组，像图表的标注）
 *   · 偏移由数据给（off），按周围有什么东西定，不写死
 *   · 上线右对齐、下线左对齐 —— 字像挂在线上，而不是浮在真空里
 *   · 整块批注按曲线方向轻微倾斜（tilt，±5°），像手写在纸上
 *   · 圈按主次分三档：起点最重、终点次之、其余轻
 *   · 离得远的批注用一根极细的导线连回圈上
 */
const props = defineProps<{
  stop: PortalStop
  index: number
  active: boolean
  interactive: boolean
  /** 落在被擦掉的那一条里：看不见，所以只接焦点，不接鼠标 */
  erased?: boolean
  /** 这条线的法向单位向量：批注挂在这条线的垂直方向上 */
  nx?: number
  ny?: number
}>()

const emit = defineEmits<{ enter: []; leave: []; pick: [] }>()

const rank = computed(() => props.stop.rank ?? 'plain')
const R = computed(() => (rank.value === 'anchor' ? 25 : rank.value === 'end' ? 21 : 17))
const CORE = computed(() => (rank.value === 'anchor' ? 8.5 : rank.value === 'end' ? 7 : 6))

const nx = computed(() => props.nx ?? Math.SQRT1_2)
const ny = computed(() => props.ny ?? Math.SQRT1_2)
/** 上线（above）在轴的左上侧，下线（below）在右下侧 */
const side = computed(() => (props.stop.side === 'above' ? -1 : 1))
const off = computed(() => props.stop.off ?? 52)
const tilt = computed(() => props.stop.tilt ?? 0)

/** 批注落点：从圈心沿法向走 off */
const anchor = computed(() => ({
  x: props.stop.x + side.value * off.value * nx.value,
  y: props.stop.y + side.value * off.value * ny.value,
}))

/** 导线：从圈边拉到批注跟前，只在批注离得远的时候画 */
const leader = computed(() => {
  if (off.value < 48) return []
  const sx = props.stop.x + side.value * (R.value + 5) * nx.value
  const sy = props.stop.y + side.value * (R.value + 5) * ny.value
  return sLine(sx, sy, anchor.value.x - side.value * 7 * nx.value, anchor.value.y - side.value * 7 * ny.value, {
    seed: 2050 + props.index,
    stroke: 'var(--line-3)',
    strokeWidth: 1,
  })
})

const ring = computed(() =>
  sCircle(props.stop.x, props.stop.y, R.value, {
    seed: 2010 + props.index,
    stroke: props.stop.tone,
    strokeWidth: rank.value === 'plain' ? 2.6 : 3.1,
    fill: 'var(--n-1)',
  }),
)
const core = computed(() =>
  sCircle(props.stop.x, props.stop.y, CORE.value, { seed: 2020 + props.index, stroke: 'none', fill: props.stop.tone }),
)
</script>

<template>
  <g
    class="stop"
    :class="{ on: active }"
    :data-erased="erased ? '' : undefined"
    :data-rank="rank"
    :style="{ color: stop.tone, animationDelay: `${0.2 + index * 0.14}s` }"
    :tabindex="interactive ? 0 : -1"
    :aria-hidden="interactive ? undefined : 'true'"
    role="button"
    :aria-label="`${stop.at}：${stop.label}`"
    @mouseenter="emit('enter')"
    @mouseleave="emit('leave')"
    @focus="emit('enter')"
    @blur="emit('leave')"
    @click="emit('pick')"
    @keydown.enter="emit('pick')"
  >
    <circle class="stop__hit" :cx="stop.x" :cy="stop.y" :r="R + 20" />
    <SketchPath v-if="leader.length" :ops="leader" class="stop__leader" />
    <SketchPath :ops="ring" />
    <SketchPath :ops="core" />

    <!--
      一块批注而不是两行散字：时间在名字上方，同一侧、同一对齐方向。
      上线右对齐（字的右端贴着导线），下线左对齐 —— 字从线上长出来。
    -->
    <g class="block" :transform="`rotate(${tilt} ${anchor.x} ${anchor.y})`">
      <text
        class="stop__at"
        :x="anchor.x"
        :y="anchor.y - 23"
        :text-anchor="side < 0 ? 'end' : 'start'"
      >{{ stop.at }}</text>
      <text
        class="stop__label"
        :x="anchor.x"
        :y="anchor.y"
        :text-anchor="side < 0 ? 'end' : 'start'"
      >{{ stop.label }}</text>
    </g>
  </g>
</template>

<style scoped>
.stop { cursor: var(--cursor-dot); outline: none; opacity: 0; animation: stop-in 620ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
@keyframes stop-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }

/*
 * 被擦掉的站：形状还在，但墨已经没了。
 * 鼠标掠过它不该有反应（看不见的东西不该能悬停），
 * 但键盘聚焦要有反应 —— 所以只关掉 pointer-events，不关掉焦点。
 */
.stop[data-erased] { pointer-events: none; }

.stop__hit { fill: transparent; }
.stop__leader { opacity: 0.75; }
/*
 * 时间标记（"现在""08:40""周三"）。
 *
 * 它原来吃 --font-mono：等宽字体没有中文字形，中文那几站（现在 / 周三 / 下周一）
 * 就落到了**新宋体**上，11.5px 的新宋体在这个尺度下几乎是一条灰线 ——
 * 同一块批注里，数字是等宽、中文是另一个字体，还更细。
 * 现在字体交给 --font-mono 里排在泛型 monospace 前面的中文字族（数字仍等宽），
 * 尺寸跟站名拉开一档、字重实一档，并且不再拉 0.06em 的字距（中文不吃字距）。
 */
.stop__at {
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 500;
  fill: var(--ink-3);
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
}
/*
 * 站名：批注里真正要读的那一行。
 * 16px 对中文偏小（中文的字面比拉丁大，同字号下更"挤"），提到 17px 并给一点字重，
 * 压线的那一圈颜色就压不住字了。
 */
.stop__label {
  font-family: var(--font-sans);
  font-size: 17px;
  font-weight: 500;
  letter-spacing: 0.005em;
  fill: var(--ink-2);
}
/* 起点那一站最重：名字加粗，时间也跟着实一点 */
.stop[data-rank="anchor"] .stop__label { font-size: 19px; fill: var(--ink-1); font-weight: 600; }
.stop[data-rank="anchor"] .stop__at { fill: var(--ink-2); }
.stop[data-rank="end"] .stop__label { fill: var(--ink-1); font-weight: 600; }

.stop.on .stop__at { fill: currentColor; }
.stop.on .stop__label { fill: var(--ink-1); font-weight: 600; }
.stop.on .stop__leader { opacity: 1; }
.stop:focus-visible .stop__hit { fill: color-mix(in srgb, currentColor 12%, transparent); }

@media (prefers-reduced-motion: reduce) {
  .stop { animation: none; opacity: 1; }
}
</style>
