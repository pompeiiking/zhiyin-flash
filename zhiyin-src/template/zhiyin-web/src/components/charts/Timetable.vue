<script setup lang="ts">
import { computed, ref } from 'vue'
import SketchPath from './SketchPath.vue'
import { sLine, sRect } from '@/lib/sketch'
import { PERIODS, WEEKDAYS, type Course } from '@/data/student'

/**
 * 自动课表 —— 手绘周历。
 *
 * 它不只是"把课摆到格子里"。真正的产出是**空档**：哪几段没课、能把事情放进去。
 * 所以没课的格子也得画出来（虚线），并且可点 —— 点开就是"这段能干什么"。
 * 每门课同样可点：它撑起画像里的哪一条、和目标岗位是什么关系。
 */
/**
 * 课表由**外面给**，不再自己读那份演示数据。
 *
 * 原因很直接：这份课表以前写死在前端，界面上却写着"从学信网导入"：
 * 学信网根本没有课程表。真数据来自教务系统（见 BindOverlay 那条线），
 * 没授权时这张图就该是空的 —— 空图配上"还没授权"是一句实话，
 * 画满假课再配一句"已导入"是一句假话。
 */
const props = withDefaults(
  defineProps<{ compact?: boolean; courses?: Course[] }>(),
  { compact: false, courses: () => [] },
)
const emit = defineEmits<{ (e: 'pick-course', course: Course): void; (e: 'pick-gap', day: number, period: number): void }>()

const COLS = WEEKDAYS.length
const ROWS = PERIODS.length
const CELL = 64
const LABEL_W = 50
const HEAD_H = 26
const W = LABEL_W + COLS * CELL
const H = HEAD_H + ROWS * CELL

const active = ref<string | null>(null)

/** 课程按 day(1-7) / start(节) 落到格子上 */
const placed = computed(() =>
  (props.courses ?? []).filter((c) => c.day <= COLS)
    .map((c) => ({ course: c, col: c.day - 1, row: Math.max(0, Math.ceil(c.start / 2) - 1), span: Math.max(1, Math.ceil(c.span / 2)) }))
    .filter((p) => p.row < ROWS),
)

const gridOps = computed(() => {
  const ops = []
  for (let r = 0; r <= ROWS; r++) ops.push(...sLine(LABEL_W, HEAD_H + r * CELL, W, HEAD_H + r * CELL, { seed: 200 + r, stroke: 'var(--line-2)', strokeWidth: r === 0 ? 1.6 : 1 }))
  for (let c = 0; c <= COLS; c++) ops.push(...sLine(LABEL_W + c * CELL, HEAD_H, LABEL_W + c * CELL, H, { seed: 260 + c, stroke: 'var(--line-2)', strokeWidth: c === 0 ? 1.6 : 1 }))
  return ops
})

const courseOps = computed(() =>
  placed.value.map((p, i) => {
    const x = LABEL_W + p.col * CELL + 4
    const y = HEAD_H + p.row * CELL + 4
    const w = CELL - 8
    const h = p.span * CELL - 8
    const tone = p.course.type === '实践' ? 'var(--mk-purple)' : p.course.type === '选修' ? 'var(--mk-blue)' : 'var(--mk-green)'
    const soft = p.course.type === '实践' ? 'var(--mk-purple-soft)' : p.course.type === '选修' ? 'var(--mk-blue-soft)' : 'var(--mk-green-soft)'
    return { ...p, x, y, w, h, tone, ops: sRect(x, y, w, h, { seed: 300 + i * 5, stroke: tone, strokeWidth: 2, fill: soft }) }
  }),
)

/** 没被课占掉的格子 = 可投入窗口 */
const gaps = computed(() => {
  const taken = new Set<string>()
  for (const p of placed.value) for (let k = 0; k < p.span; k++) taken.add(`${p.col}:${p.row + k}`)
  const out: { col: number; row: number }[] = []
  for (let c = 0; c < COLS; c++) for (let r = 0; r < ROWS; r++) if (!taken.has(`${c}:${r}`)) out.push({ col: c, row: r })
  return out
})
</script>

<template>
  <svg class="tt" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="本周课表与可投入的空档">
    <!-- 表头 -->
    <text v-for="(d, c) in WEEKDAYS" :key="d" class="hd" :x="LABEL_W + c * CELL + CELL / 2" :y="16" text-anchor="middle">{{ d }}</text>
    <text v-for="(p, r) in PERIODS" :key="p" class="hd" :x="LABEL_W - 8" :y="HEAD_H + r * CELL + CELL / 2 + 3" text-anchor="end">{{ p }}</text>

    <SketchPath :ops="gridOps" opacity="0.7" />

    <!-- 空档：虚线框，点开看这段能干什么 -->
    <g v-for="g in gaps" :key="`g${g.col}-${g.row}`" class="gap" tabindex="0" role="button"
       :aria-label="`${WEEKDAYS[g.col]} ${PERIODS[g.row]} 没课`"
       @click="emit('pick-gap', g.col + 1, g.row + 1)" @keydown.enter="emit('pick-gap', g.col + 1, g.row + 1)">
      <rect class="hit" :x="LABEL_W + g.col * CELL" :y="HEAD_H + g.row * CELL" :width="CELL" :height="CELL" />
    </g>

    <!-- 课程 -->
    <g v-for="p in courseOps" :key="p.course.id" class="crs" :class="{ on: active === p.course.id }"
       tabindex="0" role="button"
       :aria-label="`${p.course.name}，${p.course.teacher}，${p.course.place}`"
       @mouseenter="active = p.course.id" @focus="active = p.course.id"
       @click="emit('pick-course', p.course)" @keydown.enter="emit('pick-course', p.course)">
      <SketchPath :ops="p.ops" />
      <text class="nm" :x="p.x + 7" :y="p.y + 15">{{ p.course.name.length > 6 ? p.course.name.slice(0, 6) : p.course.name }}</text>
      <text v-if="p.h > 60" class="mt" :x="p.x + 7" :y="p.y + 30">{{ p.course.place }}</text>
      <text v-if="p.h > 90" class="mt" :x="p.x + 7" :y="p.y + 44">{{ p.course.credit }} 学分 · {{ p.course.type }}</text>
    </g>
  </svg>
</template>

<style scoped>
.tt { width: 100%; height: auto; display: block; overflow: visible; }
.hd { font-family: var(--font-sans); font-size: 10px; fill: var(--ink-3); }
.gap { cursor: var(--cursor-dot); outline: none; }
.gap .hit { fill: transparent; }
.gap:hover .hit, .gap:focus-visible .hit { fill: var(--fill-subtle); }
.crs { cursor: var(--cursor-dot); outline: none; }
.crs .nm { font-family: var(--font-sans); font-size: 10px; font-weight: 600; fill: var(--ink-1); pointer-events: none; }
.crs .mt { font-family: var(--font-sans); font-size: 9px; fill: var(--ink-3); pointer-events: none; }
.crs:focus-visible { filter: drop-shadow(0 0 0.35rem rgba(15, 122, 88, 0.5)); }
</style>
