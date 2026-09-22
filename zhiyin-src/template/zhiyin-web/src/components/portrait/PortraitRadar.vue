<script setup lang="ts">
import { computed } from 'vue'
import { sLine, sPath, sPolyline } from '@/lib/sketch'

/**
 * 画像雷达 —— 维度把握的一张手绘蛛网图。
 *
 * 用 rough.js 直接把"网、轴、数据多边形"画成铅笔线（seed 固定，不抖）：
 * 网是淡墨的三层蛛网，数据多边形用签名绿描边 + 排线填充（hachure），
 * 看上去是"有人拿绿铅笔在坐标纸上涂了一块"。
 * 每个顶点有一片透明的热区，点它 = 选中那个维度（右栏跟着切）。
 */
export interface RadarDim {
  id: string
  name: string
  value: number
}

const props = defineProps<{ dims: RadarDim[]; selected?: string | null }>()
const emit = defineEmits<{ (e: 'select', id: string): void }>()

/* 画布与几何：中心、半径、从正上方起，顺时针均分 */
const W = 340
const H = 280
const CX = W / 2
const CY = H / 2 + 4
const R = 96

const n = computed(() => Math.max(3, Math.min(8, props.dims.length)))

const angleOf = (i: number) => (Math.PI * 2 * i) / n.value - Math.PI / 2
const pointAt = (i: number, r: number): [number, number] => [
  CX + Math.cos(angleOf(i)) * r,
  CY + Math.sin(angleOf(i)) * r,
]

/** 三层蛛网（25 / 55 / 100%）+ 辐条，全部淡墨 */
const web = computed(() => {
  const rings = [0.28, 0.6, 1].map((f) =>
    sPolyline(
      Array.from({ length: n.value }, (_, i) => pointAt(i, R * f)).concat([
        pointAt(0, R * f),
      ]),
      { stroke: 'currentColor', strokeWidth: 1, roughness: 0.9, bowing: 0.6 },
    ),
  )
  const spokes = Array.from({ length: n.value }, (_, i) =>
    sLine(CX, CY, ...pointAt(i, R), { stroke: 'currentColor', strokeWidth: 1, roughness: 0.8, bowing: 0.5 }),
  ).flat()
  return { rings, spokes }
})

/** 数据多边形：闭合手绘线 + 绿排线填充 */
const data = computed(() => {
  if (!props.dims.length) return null
  const pts = props.dims.map((d, i) => pointAt(i, R * Math.min(1, Math.max(0.04, d.value))))
  const dPath =
    pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ') + ' Z'
  return sPath(dPath, {
    stroke: 'var(--radar-accent, #257040)',
    strokeWidth: 2.2,
    roughness: 1.15,
    bowing: 1.2,
    fill: 'var(--radar-accent, #257040)',
    fillStyle: 'hachure',
    hachureGap: 7,
    fillWeight: 1.3,
    seed: 11,
  })
})

/** 顶点标签的落位：按角度决定对齐，保证不出画布 */
function labelPos(i: number) {
  const [x, y] = pointAt(i, R + 18)
  const rad = angleOf(i)
  const anchor = Math.abs(Math.cos(rad)) < 0.3 ? 'middle' : Math.cos(rad) > 0 ? 'start' : 'end'
  const dy = Math.abs(Math.sin(rad)) < 0.3 ? 4 : Math.sin(rad) < 0 ? 0 : 10
  return { x, y, anchor, dy }
}

const pick = (id: string) => emit('select', id)
</script>

<template>
  <figure
    class="radar"
    role="img"
    :aria-label="`各维度把握雷达图，共 ${dims.length} 个维度`"
  >
    <svg :viewBox="`0 0 ${W} ${H}`" class="radar__ink">
      <g class="radar__web">
        <template v-for="(ring, ri) in web.rings" :key="`r${ri}`">
          <path
            v-for="(op, oi) in ring"
            :key="`${ri}-${oi}`"
            :d="op.d"
            :stroke="op.stroke"
            :fill="op.fill"
            :stroke-width="op.strokeWidth"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </template>
        <template v-for="op in web.spokes" :key="op[0].d.slice(0, 24)">
          <path
            :d="op.d"
            :stroke="op.stroke"
            :fill="op.fill"
            :stroke-width="op.strokeWidth"
            stroke-linecap="round"
          />
        </template>
      </g>

      <g v-if="data" class="radar__data">
        <path
          v-for="(op, i) in data"
          :key="i"
          :d="op.d"
          :stroke="op.stroke"
          :fill="op.fill"
          :stroke-width="op.strokeWidth"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </g>

      <!-- 标签 + 热区 -->
      <g v-for="(d, i) in dims.slice(0, 8)" :key="d.id" class="radar__lab" @click="pick(d.id)">
        <text
          :x="labelPos(i).x"
          :y="labelPos(i).y + labelPos(i).dy"
          :text-anchor="labelPos(i).anchor"
          :class="{ on: d.id === selected }"
        >{{ d.name }}</text>
        <circle :cx="pointAt(i, R * Math.min(1, Math.max(0.04, d.value)))[0]"
                :cy="pointAt(i, R * Math.min(1, Math.max(0.04, d.value)))[1]" r="13" fill="transparent" />
      </g>
    </svg>
    <figcaption class="radar__cap label">点维度名，右边看它的明细</figcaption>
  </figure>
</template>

<style scoped>
.radar { margin: 0; display: grid; gap: 2px; justify-items: center; min-width: 0; }
.radar__ink {
  width: 100%; max-width: 360px; height: auto;
  color: var(--line-3);           /* 网与轴走淡墨（currentColor） */
  overflow: visible;
}
.radar__data { color: var(--mk-green); }
.radar__lab { cursor: pointer; }
.radar__lab text {
  font-family: var(--font-sans);
  font-size: 12px;
  fill: var(--ink-3);
  transition: fill var(--dur-fast) var(--ease-out);
}
.radar__lab:hover text { fill: var(--ink-1); }
.radar__lab text.on { fill: var(--accent); font-weight: 600; }
.radar__cap { color: var(--ink-4); }
</style>
