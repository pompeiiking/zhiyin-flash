<script setup lang="ts">
import { computed } from 'vue'
import { normalize01, formatPercent01, type MeterFormat } from './charts/MeterRow.vue'

/* =============================================================================
 * StatTile —— 「读数瓦片」
 * -----------------------------------------------------------------------------
 * 【为什么要它】审计原话（COVERAGE.md:159）：
 *   "**零进度图形**——只有『5 件待推进 · 3 件已完成』这样的分母文案；
 *    三个时间窗（9/20、10/31、11/30）只是三行 14px 灰字，时间关系完全不可见。"
 * 这句话拆开是两个欠账：
 *   ① 进度只剩分母文字 → 需要一个"数值 + 分母 + 同名图形"的固定形状
 *   ② 数字没有被当读数对待 → 需要 tabular-nums + 右对齐 + 单位降一档
 * 本组件一次补齐这两条，并且**顺带承载 `needs_recompute`**：
 * 状态与数值住在同一格里，用户读到 5/8 的同时就看到"这版要重算"，
 * 而不是把状态甩到页面另一头的一句灰字里（COVERAGE.md:180 的第三种印法）。
 *
 * 【量纲】分数与比例一律 0–1（与 MeterRow 同源，`progress` 直接喂给 MeterRow）。
 * 计数值（件、条、天）**不是比例**，走 `value` 的裸数字路径，不做 0–1 收束 ——
 * 但也就**不能**参与 `progress`（那样会把 8 件画成满格）。
 * ========================================================================== */

const props = withDefaults(
  defineProps<{
    /** 主数值。数字 = 读数；null / undefined = 还没有这条读数（不是 0） */
    value?: number | null
    /** 0–1 的分数或比例。给了它就按分数渲染：先测一次量纲，再交给 format */
    score?: number | null
    /** 0–1 → 文字。缺省按 score 印百分数 */
    format?: MeterFormat
    /** 单位，降一档显示（"分" / "%" / "件"） */
    unit?: string
    label: string
    /** 分母：印成 "5 / 8" 并画进度；只给 denominator 时自动算 progress */
    denominator?: number | null
    /** 0–1 进度。给了它就画进度条（与 MeterRow 同一把 0–1 的尺） */
    progress?: number | null
    /** 状态标记：需要重算 / 已完成 / 需要你注意（后者用红，配额 ≤1%） */
    state?: 'none' | 'recompute' | 'done' | 'attention'
    /** 趋势：只表达方向，tone 由调用方定（组件不替业务判断好坏） */
    trend?: { label: string; tone?: 'flat' | 'attention' } | null
    /** 大字档：给"一屏只有一个读数"的位置用 */
    emphasis?: boolean
  }>(),
  {
    value: null,
    score: null,
    format: formatPercent01,
    unit: '',
    denominator: null,
    progress: null,
    state: 'none',
    trend: null,
    emphasis: false,
  },
)

/** 计数路径：只有真数字才算数，null/undefined/NaN 一律是"缺读数" */
const count = computed(() =>
  typeof props.value === 'number' && Number.isFinite(props.value) ? props.value : undefined,
)

/** 分数路径：唯一的 0–1 入口，越界值在这里被换算/钳制并报警 */
const ratioScore = computed(() => normalize01(props.score, 'StatTile.score'))

/** 进度：显式 progress 优先，其次由分母推算。两者都是 0–1 */
const ratio = computed(() => {
  const explicit = normalize01(props.progress, 'StatTile.progress')
  if (explicit != null) return explicit
  if (count.value == null || props.denominator == null || props.denominator <= 0) return undefined
  return Math.min(1, Math.max(0, count.value / props.denominator))
})

/** 主数值的文字形态（分数 → format；计数 → 原样） */
const display = computed(() => {
  if (ratioScore.value != null) return props.format(ratioScore.value)
  if (count.value != null) return String(count.value)
  return null
})

/** 单位：分数路径下由 format 决定（通常已带 % 或 分），不再重复印 */
const shownUnit = computed(() => (ratioScore.value != null ? '' : props.unit))

const hasDenominator = computed(
  () => count.value != null && props.denominator != null && props.denominator > 0,
)

const stateMeta = computed(() => {
  switch (props.state) {
    case 'recompute':
      return { text: '需要重算', tone: 'attention' as const, why: '依据变过，这个读数还是上一版的' }
    case 'done':
      return { text: '已完成', tone: 'done' as const, why: '这项已经结束' }
    case 'attention':
      return { text: '需要你注意', tone: 'attention' as const, why: '这里有一件事等你处理' }
    default:
      return null
  }
})

/** 读屏一句话：瓦片是给眼睛的，读屏需要把形状翻译回句子 */
const ariaText = computed(() => {
  const parts: string[] = [props.label]
  parts.push(display.value == null ? '当前没有读数' : `当前 ${display.value}${shownUnit.value}`)
  if (hasDenominator.value) parts.push(`共 ${props.denominator}`)
  if (stateMeta.value) parts.push(stateMeta.value.text)
  if (props.trend) parts.push(props.trend.label)
  return parts.join('，')
})
</script>

<template>
  <div class="tile" :class="{ 'tile--emphasis': emphasis, 'tile--empty': display == null }" role="group" :aria-label="ariaText">
    <!-- ① 标签行（含状态标记）：状态与数值同格，不甩到页面另一头 -->
    <div class="tile__top">
      <span class="tile__label">{{ label }}</span>
      <span
        v-if="stateMeta"
        class="tile__state"
        :class="[`tile__state--${stateMeta.tone}`]"
        :title="stateMeta.why"
      >
        <i class="tile__state-dot" aria-hidden="true" />
        {{ stateMeta.text }}
      </span>
    </div>

    <!-- ② 读数行：数值 + 单位 + 分母。整行右对齐，数字等宽 -->
    <div class="tile__readout">
      <span class="tile__value t-num">{{ display ?? '—' }}</span>
      <span v-if="shownUnit" class="tile__unit">{{ shownUnit }}</span>
      <span v-if="hasDenominator" class="tile__denom t-num">
        <span class="tile__slash" aria-hidden="true">/</span>{{ denominator }}
      </span>
    </div>

    <!-- ③ 进度：只有真有一条 0–1 的进度时才画。计数没有分母就不画 ——
           画一根 100% 的条比不画更糟（它会在说"这件事做完了"） -->
    <div v-if="ratio != null" class="tile__track" aria-hidden="true">
      <span class="tile__fill" :style="{ width: `${ratio * 100}%` }" />
    </div>

    <!-- ④ 趋势 / 脚注 -->
    <p v-if="trend" class="tile__foot" :class="{ 'tile__foot--attention': trend.tone === 'attention' }">
      {{ trend.label }}
    </p>
  </div>
</template>

<style scoped>
.tile {
  /* ① 标签 ② 读数 ③ 进度 ④ 脚注 —— 单列，标签与读数**不可能**被排版拉开 */
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  justify-items: end;
  gap: var(--sp-1);
  min-width: 0;
}

/* ---------- ① 标签 + 状态 ---------- */
.tile__top {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  min-width: 0;
}

.tile__label {
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-snug);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tile__state {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  margin-left: auto;
  font-size: var(--fs-12);
  line-height: 1.6;
  white-space: nowrap;
}

.tile__state-dot {
  display: block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

/* 需要重算 / 需要你注意：红。形态也一起变（实心点 + 加字重），不只靠颜色 */
.tile__state--attention {
  color: var(--c-attention);
  font-weight: var(--fw-medium);
}

/* 已完成：中性灰。完成不给颜色奖励（tokens.css 的口径） */
.tile__state--done {
  color: var(--c-done);
}

/* ---------- ② 读数 ---------- */
.tile__readout {
  display: flex;
  align-items: baseline;
  justify-content: flex-end; /* 数字当读数对待：右对齐 */
  gap: 3px;
}

.tile__value {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: var(--c-text);
}

.tile--emphasis .tile__value {
  font-size: var(--fs-30);
  line-height: 1.15;
}

/* 没有读数时不能和真读数同重 —— 否则"—"会被读成"0" */
.tile--empty .tile__value {
  font-weight: var(--fw-regular);
  color: var(--c-text-3);
}

.tile__unit {
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  color: var(--c-text-3);
}

.tile__denom {
  font-size: var(--fs-14);
  font-weight: var(--fw-regular);
  color: var(--c-text-3);
  margin-left: 2px;
}

.tile__slash {
  margin-right: 1px;
  color: var(--c-text-4);
}

/* ---------- ③ 进度 ---------- */
.tile__track {
  position: relative;
  width: 100%;
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--c-surface-3);
  overflow: hidden;
}

.tile__fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-primary);
  /* 宽度变化 = "进度推进了"这件事被看见（CRAFT-BRIEF §5.1 第 7 条） */
  transition: width var(--dur-4) var(--ease-out);
}

/* ---------- ④ 脚注 ---------- */
.tile__foot {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: var(--lh-snug);
  text-align: right;
}

.tile__foot--attention {
  color: var(--c-attention);
  font-weight: var(--fw-medium);
}

@media (prefers-reduced-motion: reduce) {
  .tile__fill {
    transition: none;
  }
}
</style>
