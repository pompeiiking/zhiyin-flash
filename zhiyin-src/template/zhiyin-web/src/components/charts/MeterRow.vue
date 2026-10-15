<script lang="ts">
/* =============================================================================
 * MeterRow —— 一把尺子上并排表达「自身值 / 要求值 / 差距」
 * -----------------------------------------------------------------------------
 * 【为什么是两块 script】量纲守卫与格式化函数必须能被 StatTile / ConfidenceBadge
 * 复用（三者共用**唯一一把 0–1 的尺**，各写一份就等于又有了三把）。
 * 而 `<script setup>` **不允许出现 ES module 的 export**（@vue/compiler-sfc 会直接
 * 报错："<script setup> cannot contain ES module exports"）。
 * 所以导出物放在这块普通 `<script>` 里，`<script setup>` 负责组件本体。
 *
 * 【为什么要重做旧实现】旧实现把分值、门槛线、刻度三者当成三种独立画法：
 *   · 条长用 `transform: scaleX(score/100)`
 *   · 门槛线用 `left: ${requirement}%`
 *   · 0 刻度画在标签列上（`AssessmentView` 里那条轴根本不在条的那把尺上）
 * 结果就是审计说的"刻度轴与条长不是同一把尺"。
 * 现在只有**一个**定位坐标系：`.mtr__ruler` 这一列。条、缺口带、要求线、
 * 网格线、刻度签全部按它取百分比，谁也不可能跟别人错位。
 *
 * 【类名为什么是 mtr 而不是 meter】`base.css:834-856` 里已经有一个全局的
 * `.meter` / `.meter__fill` 零件（用法是 `<div class="meter"><div class="meter__fill"
 * :style="{'--meter': 0.46}"/>`），它的 `transform: scaleX(var(--meter, 0))`
 * 会把同名的条**静默压成 0 宽**——这正是本次实测抓到的 bug（条宽实测 0px，
 * 而 getComputedStyle 报 330px）。scoped 只改选择器优先级，改不了"别人也用这个名字"，
 * 所以本组件整体改名 `mtr__*`，彻底不与那个零件共享命名空间。
 *
 * 【量纲，写死在这里】本组件**只接受 0–1**。后端契约就是 0–1：
 *   backend-types.ts:364  `match_score?: (number | null)`
 *   backend-types.ts:99   `confidence?: number`（ProfileFieldView）
 *   backend-types.ts:468  `overall_confidence?: number`
 * 而演示数据用的是 0–100 整数，`validate-ai.ts` 只校验 `typeof === 'number'`，
 * 两种量纲可以在运行时同时存在 —— 所以**类型挡不住的那一半由运行时挡**：
 *   见 `normalize01()`，越界值一律换算/钳制并（开发态）报警，绝不照原样画出去。
 * 显示格式由调用方通过 `format` 决定 —— 组件**不**把 0–1 直接印成人话，
 * 因为"0.46 该印成 46 分还是 46%"是业务口径，不是组件口径。
 * ========================================================================== */

/**
 * 0–1 浮点的名义类型别名。
 * 用法：`const s: MeterValue01 = 0.46`。TS 上它仍是 number（结构化别名，
 * 不做 brand，避免调用方到处 `as`），它的作用是**在代码里留下唯一的量纲锚点**，
 * 顺带给 `format` 回调一个自解释的参数名。
 */
export type MeterValue01 = number

/** 0–1 → 文字。调用方通过它决定 0.46 是"46 分"还是"46%"。 */
export type MeterFormat = (value: MeterValue01) => string

/**
 * 判定"这看起来是百分制"的上界。定在 1.5 而不是 1：
 * 0–1 的浮点不会超过 1，所以 (1, 1.5] 这一段只可能是 0–100 的量纲
 * （或上游笔误），换算比钳制更接近调用方的本意。
 */
const PERCENT_CEILING = 1.5

const warned = new Set<string>()

function warnOnce(where: string, message: string) {
  if (!import.meta.env.DEV || warned.has(where)) return
  warned.add(where)
  console.warn(`[MeterRow/${where}] ${message}`)
}

/**
 * 把任意输入收进 0–1。返回 undefined 表示"没有值"（null / undefined / NaN / 非数字）。
 *
 * 【为什么选"换算 + 钳制 + 报警"而不是"抛错"】
 * 这段代码在渲染路径上。抛错会让整页白屏 —— 用户看到的是"页面坏了"，
 * 而不是"这个字段的量纲写错了"，故障反而更难定位；同时它也拦不住
 * "静默地画错"（有人 try/catch 掉就算了）。
 * 所以选：**保证画面始终可读**（越界值收进合法区间，缺值走缺依据形态），
 * **同时让写错的人当场听到**（开发态一次 warn，带具体数值与修法）。
 * 生产构建里 `import.meta.env.DEV` 为 false，warn 会被摇树掉，不留在包里。
 */
export function normalize01(input: unknown, where: string): MeterValue01 | undefined {
  if (typeof input !== 'number' || !Number.isFinite(input)) return undefined
  if (input >= 0 && input <= 1) return input

  const asPercent = input > 1 && input <= PERCENT_CEILING
  const fixed = Math.min(1, Math.max(0, asPercent ? input / 100 : input))
  warnOnce(
    where,
    asPercent
      ? `收到 ${input} —— 本组件只接受 0–1，已按 0–100 换算成 ${fixed}。` +
          `请在上游除以 100（或改用 0–100 的组件）。`
      : `收到越界的量 ${input} —— 本组件只接受 0–1，已钳制为 ${fixed}。`,
  )
  return fixed
}

/** 默认格式：0–1 → 百分数。调用方几乎总该覆盖它。 */
export function formatPercent01(v: MeterValue01): string {
  return `${Math.round(v * 100)}%`
}

/** 常用格式之一：0–1 → 整分（报告里的"46 分"）。 */
export function formatScore01(v: MeterValue01): string {
  return `${Math.round(v * 100)}`
}

/** 一条对照线：要求值 / 基准线 / 目标值 —— 都住在同一把尺上。 */
export interface MeterMark {
  /** 0–1（同样走 normalize01） */
  value: MeterValue01 | null | undefined
  /** floor = 至少要到这里（要求）；at = 就在这里（基准）；ceiling = 不能超过 */
  kind?: 'floor' | 'at' | 'ceiling'
  /** 文字标签，例如「主攻方向要求」。缺省时只画线不出文字 */
  label?: string
  /** 强调线（当前对照的那一条） */
  emphasis?: boolean
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 自身值，0–1。null = 没有依据（不是 0） */
    value?: MeterValue01 | null
    /**
     * 要求值 —— 最常用的一条对照线，直接给数就是 kind='floor'。
     * 与 `marks` 可以同时用，两条线都在同一把尺上。
     */
    requirement?: MeterValue01 | null
    /** 基准线（例如"全年级中位数"），kind='at' */
    baseline?: MeterValue01 | null
    /** 多条对照线，与 requirement / baseline 同一个坐标系 */
    marks?: MeterMark[]
    /** 刻度位置（0–1），必须含 0 与 1 才是一把完整的尺。传 [] 表示不画轴 */
    ticks?: MeterValue01[]
    /** 量纲换算与显示：调用方决定 0–1 印成什么 */
    format?: MeterFormat
    /** 只给读屏用：这一行是什么 */
    label?: string
    /** 行高，视用途 30 / 38 */
    height?: number
  }>(),
  {
    value: null,
    requirement: null,
    baseline: null,
    marks: () => [],
    ticks: () => [0, 0.5, 1],
    format: formatPercent01,
    label: '',
    height: 32,
  },
)

const self = computed(() => normalize01(props.value, 'value'))
const requirementMark = computed<MeterMark | null>(() =>
  props.requirement == null ? null : { value: props.requirement, kind: 'floor', label: '要求' },
)
const baselineMark = computed<MeterMark | null>(() =>
  props.baseline == null ? null : { value: props.baseline, kind: 'at', label: '基准' },
)

/** 全部对照线，收到同一把尺上 */
const allMarks = computed(() =>
  [requirementMark.value, baselineMark.value, ...props.marks]
    .filter((m): m is MeterMark => m != null)
    .map((m, index) => ({
      ...m,
      key: `${m.kind ?? 'floor'}-${index}-${m.value ?? 'x'}`,
      at: normalize01(m.value, 'mark'),
    }))
    .filter((m) => m.at != null),
)

/** 刻度：始终含 0 与 1，去重排序，保证"尺"是完整的 */
const axis = computed(() => {
  if (!props.ticks.length) return []
  const set = new Set([
    0,
    ...props.ticks.map((t) => normalize01(t, 'tick')).filter((t): t is number => t != null),
    1,
  ])
  return [...set].sort((a, b) => a - b)
})

/**
 * 差距带：从自身值到"最近的那条要求线"之间。**不上红** ——
 * 红色在本产品专用于"需要你注意"，而"差距"是常态、是需要被读出来的量，
 * 不是警报。所以差距用**形态**表达：中性斜纹带，长度就是差距本身。
 */
const gapBand = computed(() => {
  const from = self.value
  if (from == null) return null
  const floors = allMarks.value.filter((m) => (m.kind ?? 'floor') === 'floor' && m.at != null)
  if (!floors.length) return null
  // 最近的一条：取与自身值差最小的一条，避免多目标线时空隙乱画
  const nearest = floors.reduce((a, b) => (Math.abs(b.at! - from) < Math.abs(a.at! - from) ? b : a))
  if (nearest.at === from) return null
  const left = Math.min(from, nearest.at!)
  const width = Math.abs(nearest.at! - from)
  return { left, width, to: nearest.at! }
})

/** 差距的一句话（人话部分由文字标签承担，这里只给数值） */
const gapText = computed(() => {
  const band = gapBand.value
  if (!band || self.value == null) return ''
  const diff = Math.abs(band.to - self.value)
  const short = self.value < band.to
  return short ? `还差 ${props.format(diff)}` : `已高出 ${props.format(diff)}`
})

/** 读屏一句话：把图上的形状翻译成句子 */
const ariaText = computed(() => {
  const parts: string[] = []
  parts.push(self.value == null ? '自身值：暂无依据' : `自身值：${props.format(self.value)}`)
  for (const m of allMarks.value) if (m.at != null) parts.push(`${m.label ?? '对照'}：${props.format(m.at)}`)
  if (gapText.value) parts.push(gapText.value)
  return (props.label ? `${props.label}，` : '') + parts.join('；')
})

const selfText = computed(() => (self.value == null ? '暂无依据' : props.format(self.value)))
</script>

<template>
  <div class="mtr" :class="{ 'mtr--empty': self == null }" role="img" :aria-label="ariaText">
    <!-- 行标 + 值 一直排在尺子左边，不参与尺子的坐标系 -->
    <div class="mtr__head">
      <span class="mtr__name">
        <slot name="name">{{ label }}</slot>
      </span>
      <span class="mtr__value t-num">{{ selfText }}</span>
    </div>

    <!-- ── 唯一坐标系：ruler ─────────────────────────────────────────── -->
    <div class="mtr__ruler" :style="{ '--meter-h': `${height}px` }">
      <!-- 网格线：0 / 中点 / 1，位置与刻度签、条长同源 -->
      <span
        v-for="t in axis"
        :key="`grid-${t}`"
        class="mtr__grid"
        :style="{ left: `${t * 100}%` }"
        aria-hidden="true"
      />

      <!-- 轨道：缺依据时不是"空条"，而是虚线描出来的"这里本该有一条" -->
      <span class="mtr__track" aria-hidden="true" />

      <!-- 差距带：中性斜纹，长度 = 差距本身 -->
      <span
        v-if="gapBand"
        class="mtr__gap"
        :style="{ left: `${gapBand.left * 100}%`, width: `${gapBand.width * 100}%` }"
        aria-hidden="true"
      />

      <!-- 自身值 -->
      <span v-if="self != null" class="mtr__fill" :style="{ width: `${self * 100}%` }" aria-hidden="true" />

      <!-- 对照线：floor 是"至少要到这里"，用向上三角 + 实线；
           at 是"基准在这儿"，用一条短帽；ceiling 是"不能超过"，用向下三角 -->
      <span
        v-for="m in allMarks"
        :key="m.key"
        class="mtr__mark"
        :class="[`mtr__mark--${m.kind ?? 'floor'}`, { 'mtr__mark--emphasis': m.emphasis }]"
        :style="{ left: `${(m.at as number) * 100}%` }"
        aria-hidden="true"
      >
        <i class="mtr__mark-glyph" />
        <i class="mtr__mark-line" />
      </span>
    </div>

    <!-- 轴：与 ruler 同列同宽，所以 0 永远压在条的起点上。
         每个刻度是宽度为 0 的锚点，刻度线用 translateX(-50%) 精确压在锚点上 ——
         这样"刻度线的几何位置"与网格线、条长是同一套百分比算出来的，可逐像素断言。 -->
    <div v-if="axis.length" class="mtr__axis" aria-hidden="true">
      <span
        v-for="(t, i) in axis"
        :key="`tick-${t}`"
        class="mtr__tick"
        :class="{ 'mtr__tick--first': i === 0, 'mtr__tick--last': i === axis.length - 1 }"
        :style="{ left: `${t * 100}%` }"
      >
        <i class="mtr__tick-mark" />
        <b class="mtr__tick-text t-num">{{ format(t) }}</b>
      </span>
    </div>

    <!-- 图例：把图上的形状写成字（形状是给眼睛的，文字是给读屏与色觉障碍的） -->
    <p v-if="allMarks.length || gapBand" class="mtr__legend">
      <span v-for="m in allMarks" :key="`lg-${m.key}`" class="mtr__legend-item">
        <i class="mtr__legend-glyph" :class="`mtr__legend-glyph--${m.kind ?? 'floor'}`" aria-hidden="true" />
        {{ m.label ?? '对照' }} {{ m.at != null ? format(m.at) : '' }}
      </span>
      <span v-if="gapText" class="mtr__legend-item">
        <i class="mtr__legend-glyph mtr__legend-glyph--gap" aria-hidden="true" />
        {{ gapText }}
      </span>
    </p>
  </div>
</template>

<style scoped>
.mtr {
  --meter-value-w: 56px;
}

/* ---------- 行标 + 值 ---------- */
.mtr__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--meter-value-w);
  align-items: baseline;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}

.mtr__name {
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-snug);
}

.mtr__value {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text);
  text-align: right; /* 数字当读数对待：右对齐 + 等宽 */
  white-space: nowrap;
}

/* 没有依据时，值本身也要"轻"下来，不能和真读数同重 */
.mtr--empty .mtr__value {
  font-weight: var(--fw-regular);
  color: var(--c-text-3);
}

/* ---------- 尺子（唯一坐标系） ---------- */
.mtr__ruler {
  position: relative;
  height: var(--meter-h);
}

.mtr__grid {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--chart-grid);
  pointer-events: none;
}

/* 轨道：整条 = 完整的尺。缺依据时它变成虚线框（"这里本该有一条"），
   而**不是**三根空刻度那种"已知但很低"的误读 */
.mtr__track {
  position: absolute;
  inset: 0;
  border-radius: var(--r-pill);
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
}

.mtr--empty .mtr__track {
  background: transparent;
  border-style: dashed;
  border-color: var(--c-border-strong);
}

/* 自身值：从 0 起画，宽度就是数值 —— 与刻度同源。
   显式写 transform: none 是第二道保险：全局零件 `.meter__fill` 用
   `scaleX(var(--meter, 0))` 画条，一旦选择器撞名就会把条压成 0 宽
   （本次实测抓到的就是这个：条宽 0px 而 computed width 330px）。 */
.mtr__fill {
  position: absolute;
  top: var(--meter-inset);
  bottom: var(--meter-inset);
  left: var(--meter-inset);
  transform: none;
  border-radius: var(--r-pill);
  background: var(--c-primary);
  /* 入场：条长出来，回答"这里刚算出一个判断"（CRAFT-BRIEF §5.1 第 7 条）。
     用 width 而不是 scaleX —— scaleX 会把圆角与内部纹理一起压扁。 */
  transition: width var(--dur-4) var(--ease-out);
}

/* 差距带：中性斜纹。不是红的 —— 差距是常态量，不是警报。
   高度必须与轨道一致（不能跟着对照线的 ±2px 长），否则带子会变成梯形。

   【2026-10-14 · check-contrast 门禁】这里的 `color` **不是文字色**，它是斜纹的填充源：
   `--meter-gap-pattern` 是一段 repeating-linear-gradient，里面用的是 currentColor
   （tokens.css:395）。元素本身是空 span + aria-hidden，带子里一个字符都没有 ——
   差距的数值由旁边的图例文字（"还差 8 分"）与 role="img" 的 aria-label 承担。
   与 base.css:658 的 `.dot`（color 只喂 background: currentColor）是同一个机制，
   所以保留 --c-text-4 并在 scripts/check-contrast.mjs 的 DECORATIVE_ALLOWED 里登记。 */
.mtr__gap {
  position: absolute;
  top: 0;
  bottom: 0;
  color: var(--c-text-4);
  background-image: var(--meter-gap-pattern);
  pointer-events: none;
}

/* ---------- 对照线 ---------- */
.mtr__mark {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 0;
}

.mtr__mark-line {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -1px;
  width: var(--bw-2);
  border-radius: 1px;
  background: var(--c-text-2);
}

.mtr__mark-glyph {
  position: absolute;
  top: -7px;
  left: 0;
  display: block;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
}

/* floor：至少要到这里 → 实线 + 向上三角 */
.mtr__mark--floor .mtr__mark-glyph {
  border-bottom: 5px solid var(--c-text-2);
}

/* at：基准就在这里 → 一条短帽，没有三角（它不是"要求"，不该长得像要求） */
.mtr__mark--at .mtr__mark-line {
  top: 50%;
  bottom: auto;
  left: -4px;
  width: 9px;
  height: var(--bw-2);
  background: var(--c-text-3);
}
.mtr__mark--at .mtr__mark-glyph {
  display: none;
}

/* ceiling：不能超过 → 虚线 + 向下三角 */
.mtr__mark--ceiling .mtr__mark-line {
  background: repeating-linear-gradient(to bottom, var(--c-text-2) 0 3px, transparent 3px 6px);
}
.mtr__mark--ceiling .mtr__mark-glyph {
  border-bottom: 0;
  border-top: 5px solid var(--c-text-2);
}

/* 强调的那一条：加粗，不换色（色相配额只有三支） */
.mtr__mark--emphasis .mtr__mark-line {
  left: -1.5px;
  width: 3px;
  background: var(--c-text);
}
.mtr__mark--emphasis.mtr__mark--floor .mtr__mark-glyph {
  border-bottom-color: var(--c-text);
}

/* ---------- 轴 ---------- */
.mtr__axis {
  position: relative;
  height: 20px;
  margin-top: var(--sp-1);
}

.mtr__tick {
  position: absolute;
  top: 0;
  left: 0;
  display: block;
  width: 0;
}

.mtr__tick-mark {
  position: absolute;
  top: 0;
  left: 0;
  display: block;
  width: 1px;
  height: 4px;
  background: var(--chart-axis);
  transform: translateX(-50%);
}

.mtr__tick-text {
  position: absolute;
  top: 6px;
  left: 0;
  display: block;
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  color: var(--c-text-3);
  white-space: nowrap;
  transform: translateX(-50%);
}

/* 首尾两档：刻度线仍钉在 0 / 1 上，只把文字挪回尺内，避免溢出 */
.mtr__tick--first .mtr__tick-text {
  transform: none;
}
.mtr__tick--last .mtr__tick-text {
  transform: translateX(-100%);
}

/* ---------- 图例 ---------- */
.mtr__legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-3);
  margin-top: var(--sp-1);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.mtr__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.mtr__legend-glyph {
  display: inline-block;
  width: 10px;
  height: 8px;
  flex: 0 0 auto;
}

.mtr__legend-glyph--floor {
  width: 0;
  height: 0;
  margin-left: 4px;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-bottom: 5px solid var(--c-text-2);
}

.mtr__legend-glyph--at {
  width: 10px;
  height: 2px;
  background: var(--c-text-3);
}

.mtr__legend-glyph--ceiling {
  width: 0;
  height: 0;
  margin-left: 4px;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid var(--c-text-2);
}

/* 图例里那枚 10×8 的小方块：与 .mtr__gap 同一条斜纹、同一个机制，
   它的说明文字就在同一个 .mtr__legend-item 里（"还差 8 分"），方块本身 aria-hidden。
   同样保留 --c-text-4 并登记在 check-contrast 的 DECORATIVE_ALLOWED。 */
.mtr__legend-glyph--gap {
  height: 8px;
  color: var(--c-text-4);
  background-image: var(--meter-gap-pattern);
}

/* reduced-motion：条不生长，直接落位。信息（长度与刻度）原样保留 ——
   降级的是"长出来"这个过程，不是"多长"这个结论。 */
@media (prefers-reduced-motion: reduce) {
  .mtr__fill {
    transition: none;
  }
}

/* 窄屏：值列收窄（数字右对齐的那条边要稳），标签列靠 1fr 自适应 */
@media (max-width: 480px) {
  .mtr {
    --meter-value-w: 48px;
  }
}
</style>
