<script setup lang="ts">
import { computed } from 'vue'
import type { MatchResult } from '@/ai/registry'

/** 矩阵的一格：学职网要多少、你有多少 */
type MatchCell = MatchResult['cells'][number]

/**
 * 专业 ↔ 职业 匹配矩阵 —— 手绘方格。
 *
 * 行是学职网给的职业方向，列是能力项。每格两个数：要多少（学职网）、你有多少（从课程与成绩折出来）。
 * 差得越多，格子越"空"（虚线）。所以扫一眼就能看出：你在哪一行是够的，缺的是哪一格。
 * 每一格都能点开 —— 它会说清楚"这个要求从哪来、你这个分数是怎么算出来的"。
 */
const props = defineProps<{ cells: MatchCell[]; tracks: string[] }>()
const emit = defineEmits<{ (e: 'pick', track: string, skill: string): void }>()

const skills = computed(() => [...new Set(props.cells.map((c) => c.skill))])
const COLS = computed(() => skills.value.length)
const ROW_LABEL = 78
const CELL = 62

const grid = computed(() =>
  props.tracks.map((track) =>
    skills.value.map((skill) => {
      const cell = props.cells.find((c) => c.track === track && c.skill === skill)
      const need = cell?.need ?? 0
      const have = cell?.have ?? 0
      return { track, skill, need, have, gap: Math.max(0, need - have) }
    }),
  ),
)
/** 缺口决定"这格有多空"：够 = 实心格；差一点 = 半格；差很多 = 虚线空心 */
const fillOf = (gap: number) => (gap < 0.05 ? 'rgba(15,122,88,0.18)' : gap < 0.15 ? 'rgba(15,122,88,0.10)' : 'none')
const strokeOf = (gap: number) => (gap < 0.05 ? 'var(--mk-green)' : gap < 0.15 ? 'var(--mk-green)' : gap < 0.35 ? 'var(--mk-orange)' : 'var(--warn)')
const dashOf = (gap: number) => (gap >= 0.15 ? '4 4' : 'none')
</script>

<template>
  <div class="mx" :style="{ '--cols': COLS, '--cell': CELL + 'px', '--row-label': ROW_LABEL + 'px' }">
    <div class="mx__head">
      <span />
      <span v-for="s in skills" :key="s" class="mx__skill mono">{{ s }}</span>
    </div>
    <div v-for="(row, r) in grid" :key="r" class="mx__row">
      <span class="mx__track">{{ props.tracks[r] }}</span>
      <button
        v-for="c in row"
        :key="c.skill"
        class="mx__cell"
        type="button"
        :style="{ borderColor: strokeOf(c.gap), borderStyle: dashOf(c.gap) === 'none' ? 'solid' : 'dashed', background: fillOf(c.gap) }"
        :aria-label="`${c.track} 的 ${c.skill}：要求 ${c.need}，你 ${c.have}`"
        @click="emit('pick', c.track, c.skill)"
      >
        <span class="mx__need">{{ Math.round(c.need * 100) }}</span>
        <span class="mx__have" :class="{ short: c.gap >= 0.15 }">{{ Math.round(c.have * 100) }}</span>
      </button>
    </div>
    <p class="mx__foot label">上：职业要求 · 下：你的现状 · 虚线＝还差这一格</p>
  </div>
</template>

<style scoped>
.mx { display: flex; flex-direction: column; gap: 4px; }
.mx__head, .mx__row { display: grid; grid-template-columns: var(--row-label) repeat(var(--cols), var(--cell)); gap: 4px; align-items: center; }
.mx__skill { text-align: center; text-transform: none; letter-spacing: 0.02em; }
.mx__track { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.mx__cell {
  height: 46px; border: var(--bw) solid var(--line-2); border-radius: 10px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0;
  transition: transform var(--mo-fast) var(--mo-out), border-color var(--mo-fast) var(--mo-out);
}
.mx__cell:hover { transform: translateY(-2px); }
.mx__need { font-family: var(--font-sans); font-size: 13px; font-weight: 600; color: var(--ink-1); font-variant-numeric: tabular-nums; }
.mx__have { font-family: var(--font-sans); font-size: 10px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.mx__have.short { color: var(--warn); font-weight: 600; }
.mx__foot { color: var(--ink-3); padding-top: 4px; }
</style>
