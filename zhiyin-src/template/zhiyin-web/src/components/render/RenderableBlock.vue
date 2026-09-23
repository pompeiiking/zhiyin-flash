<script setup lang="ts">
/**
 * 可视件的**前端分发点**：拿到一块 `Renderable`，按 `kind` 选组件画。
 *
 * 为什么要有这一层（而不是在对话气泡里直接画一张图）：
 * 产品会不断做出新的"功能模块" —— 后端一段取数逻辑 + 前端一整套渲染效果。
 * 分发写在这里，新模块就只做一件事：加一个 `kind` 分支（服务端那边注册同名的
 * 校验函数、把工具挂给该挂的角色），**契约不用动**。
 *
 * 两条纪律：
 *   · 数值一律只读 `payload`，不在前端算、更不猜 —— 点位是服务端从库里读的；
 *   · 认不出的 `kind` **什么都不画**（只留一行控制台日志）。
 *     摆一块空白比不摆更坏：用户会以为"这里本来就该有东西，只是没加载出来"。
 */
import { computed } from 'vue'
import type { RenderableView } from '@/api/client'

const props = defineProps<{ item: RenderableView }>()

interface BarsPoint {
  label: string
  value: number
}

/**
 * 柱状图的点位：一律是 **0–1 的比值**（注册表里那几种都从库里的
 * 把握度 / 匹配度 / 完成率读出来），所以条宽直接按它画。
 */
const bars = computed<{ title: string; unit: string; points: BarsPoint[] } | null>(() => {
  if (props.item.kind !== 'bars_chart') return null
  const payload = (props.item.payload ?? {}) as { unit?: unknown; points?: unknown }
  const raw = Array.isArray(payload.points) ? payload.points : []
  const points = raw
    .map((point) => {
      const row = point as { label?: unknown; value?: unknown }
      const label = String(row.label ?? '').trim()
      const value = Number(row.value)
      return { label, value: Number.isFinite(value) ? value : NaN }
    })
    .filter((point) => point.label && Number.isFinite(point.value))
  if (points.length < 2) return null
  return {
    title: props.item.title || '这一轮的分布',
    unit: String(payload.unit ?? ''),
    points,
  }
})

/** 条宽：0–1 的比值直接换算，最小留 2% 让"很小"也看得见 */
const width = (value: number) => `${Math.max(2, Math.min(100, value * 100))}%`

/**
 * 数值怎么写给人看。
 *
 * 这里是 0–1 的比值，写 `0.95` 或 `95.00` 都要用户自己换算一遍 ——
 * 直接把同一套刻度写成百分数，后面跟上这一件自己的单位（`%` / `分`）。
 */
const numberText = (value: number, unit: string) => `${Math.round(value * 100)}${unit || '%'}`
</script>

<template>
  <figure v-if="bars" class="rb">
    <figcaption class="label rb__k">{{ bars.title }}</figcaption>
    <ul class="rb__rows">
      <li v-for="point in bars.points" :key="point.label">
        <span class="rb__label">{{ point.label }}</span>
        <span class="rb__bar"><i :style="{ width: width(point.value) }" /></span>
        <span class="mono rb__num">{{ numberText(point.value, bars.unit) }}</span>
      </li>
    </ul>
  </figure>
</template>

<style scoped>
/* 横条 + 数值：窄也放得下，因为它本来就是"比较"用的 */
.rb { margin: 2px 0 6px; display: grid; gap: 6px; }
.rb__k { color: var(--ink-3); }
.rb__rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.rb__rows li { display: grid; grid-template-columns: minmax(3.5em, 6em) 1fr 3.4em; gap: var(--s2); align-items: center; }
.rb__label { font-size: var(--fs-small); color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rb__bar { height: 8px; border-radius: 999px; background: var(--fill-subtle); overflow: hidden; }
.rb__bar i { display: block; height: 100%; border-radius: inherit; background: var(--mk-green); }
.rb__num { font-size: var(--fs-small); color: var(--ink-3); text-align: right; }
</style>
