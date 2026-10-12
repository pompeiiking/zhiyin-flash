<script setup lang="ts">
import { computed } from 'vue'

/**
 * 四象限：把"要不要选它"摆到两个轴上，让取舍看得见。
 * 横轴 = 机会大小，纵轴 = 你现在够得着的程度。
 * 只允许用三支主色的深浅，不做彩色象限。
 */
const props = defineProps<{
  items: { id: string; label: string; x: number; y: number; role: string }[]
  selectedId?: string | null
}>()

const emit = defineEmits<{ pick: [id: string] }>()

void props

const W = 320
const H = 260
const PAD = 34

const zones = computed(() => [
  { key: 'q1', label: '机会大 · 够得着', x: PAD, y: PAD },
  { key: 'q2', label: '机会小 · 够得着', x: PAD, y: H / 2 + 6 },
  { key: 'q3', label: '机会小 · 要够一够', x: W / 2 + 6, y: H / 2 + 6 },
  { key: 'q4', label: '机会大 · 要够一够', x: W / 2 + 6, y: PAD },
])

function cx(v: number) {
  return PAD + (v / 100) * (W - PAD * 2)
}

function cy(v: number) {
  return H - PAD - (v / 100) * (H - PAD * 2)
}
</script>

<template>
  <div class="quad">
    <svg :width="W" :height="H" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="方向取舍四象限">
      <!-- 象限底 -->
      <rect
        :x="PAD"
        :y="PAD"
        :width="(W - PAD * 2) / 2"
        :height="(H - PAD * 2) / 2"
        fill="var(--c-primary-weak)"
        opacity="0.5"
      />
      <rect
        :x="PAD"
        :y="PAD"
        :width="W - PAD * 2"
        :height="H - PAD * 2"
        fill="none"
        stroke="var(--chart-grid)"
        stroke-width="1"
      />
      <!-- 十字 -->
      <line
        :x1="W / 2"
        :y1="PAD"
        :x2="W / 2"
        :y2="H - PAD"
        stroke="var(--chart-grid)"
        stroke-width="1"
      />
      <line
        :x1="PAD"
        :y1="H / 2"
        :x2="W - PAD"
        :y2="H / 2"
        stroke="var(--chart-grid)"
        stroke-width="1"
      />

      <!-- 象限名 -->
      <text
        v-for="z in zones"
        :key="z.key"
        :x="z.x"
        :y="z.y"
        style="font-size: var(--fs-12)"
        fill="var(--c-text-3)"
      >
        {{ z.label }}
      </text>

      <!-- 轴名 -->
      <text :x="W / 2" :y="H - 10" text-anchor="middle" style="font-size: var(--fs-12)" fill="var(--c-text-3)">
        机会大小 →
      </text>
      <text
        :x="12"
        :y="H / 2"
        text-anchor="middle"
        style="font-size: var(--fs-12)"
        fill="var(--c-text-3)"
        :transform="`rotate(-90 12 ${H / 2})`"
      >
        够得着的程度 →
      </text>

      <!-- 点 -->
      <g v-for="it in items" :key="it.id" class="quad__dot" @click="emit('pick', it.id)">
        <circle
          :cx="cx(it.x)"
          :cy="cy(it.y)"
          :r="selectedId === it.id ? 9 : 7"
          :fill="selectedId === it.id ? 'var(--c-primary)' : 'var(--c-surface)'"
          :stroke="it.role === '主攻' ? 'var(--chart-1)' : it.role === '平行' ? 'var(--chart-2)' : 'var(--chart-3)'"
          stroke-width="2"
        />
        <text
          :x="cx(it.x)"
          :y="cy(it.y) + 22"
          text-anchor="middle"
          style="font-size: var(--fs-12)"
          fill="var(--c-text-2)"
        >
          {{ it.label }}
        </text>
      </g>
    </svg>

    <ul class="quad__legend">
      <li v-for="it in items" :key="`k${it.id}`" class="quad__legend-item">
        <span class="quad__legend-role">{{ it.role }}</span>
        <button class="quad__legend-btn" @click="emit('pick', it.id)">{{ it.label }}</button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.quad {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  align-items: center;
}

.quad__dot {
  cursor: pointer;
}

.quad__legend {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.quad__legend-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-12);
}

.quad__legend-role {
  flex: none;
  width: 32px;
  color: var(--c-text-3);
}

.quad__legend-btn {
  color: var(--c-text-2);
  text-align: left;
}

.quad__legend-btn:hover {
  color: var(--c-primary);
  text-decoration: underline;
}
</style>
