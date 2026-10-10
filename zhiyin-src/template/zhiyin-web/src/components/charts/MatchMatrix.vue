<script setup lang="ts">
import { computed } from 'vue'
import type { MatchResult } from '@/ai/registry'

type MatchCell = MatchResult['cells'][number]
const props = defineProps<{ cells: MatchCell[]; tracks: string[] }>()
const emit = defineEmits<{ (e: 'pick', track: string, skill: string): void }>()
const labels = { reported: '有材料', studied: '课程线索', unknown: '待补材料' }
const skills = computed(() => [...new Set(props.cells.map((c) => c.skill))])
const COLS = computed(() => skills.value.length)
const ROW_LABEL = 100
const CELL = 76
const grid = computed(() => props.tracks.map((track) => skills.value.map((skill) => ({
  track, skill, cell: props.cells.find((c) => c.track === track && c.skill === skill),
}))))
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
        :disabled="!c.cell"
        :aria-label="`${c.track} 的 ${c.skill}：${c.cell ? labels[c.cell.status] : '未核对'}`"
        @click="emit('pick', c.track, c.skill)"
      >
        <span class="mx__need">{{ c.cell ? labels[c.cell.status] : '未核对' }}</span>
        <span class="mx__have">{{ c.cell ? '点击看依据' : '—' }}</span>
      </button>
    </div>
    <p class="mx__foot label">有材料也需要核验；课程只代表学习线索，缺材料不代表没有能力。</p>
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
@media (hover: hover) and (pointer: fine) {
.mx__cell:hover { transform: translateY(-2px); } }
.mx__need { font-family: var(--font-sans); font-size: 13px; font-weight: 600; color: var(--ink-1); font-variant-numeric: tabular-nums; }
.mx__have { font-family: var(--font-sans); font-size: 10px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.mx__have.short { color: var(--warn); font-weight: 600; }
.mx__foot { color: var(--ink-3); padding-top: 4px; }
</style>
