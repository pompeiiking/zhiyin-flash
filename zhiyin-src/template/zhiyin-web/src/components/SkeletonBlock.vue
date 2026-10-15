<script lang="ts">
/**
 * 骨架屏 · 类型出口（审计 D7 / PLAN §4.2）
 *
 * `variant` 描述的是**将要出现什么**，不是"骨架长什么样"——
 * 因为加载态的任务是"预演真实内容的轮廓"，而不是先空一块再重建。
 * 用形状名（文本行 / 卡片 / 列表行 / 图表块 / 头像徽标）当枚举，
 * 调用方才能在写加载态时被迫先回答"这块内容到底是什么形状"。
 */
export type SkeletonVariant = 'text' | 'card' | 'list' | 'chart' | 'avatar'
export type SkeletonSize = 'sm' | 'md' | 'lg'
</script>

<script setup lang="ts">
import { computed } from 'vue'
import type { CSSProperties } from 'vue'
// SkeletonVariant / SkeletonSize 声明在本文件上方那个 <script> 块里（同一模块作用域）

/**
 * 骨架屏 · 三条设计决定
 *
 * 1. **它自己不摘内容。** 组件只画占位；内容是否让位由调用方决定。
 *    这是审计原话"取数时用 v-if 摘掉内容，而不是占位 —— 已有内容会消失变空白再重建"的落点：
 *    `overlay` 形态把骨架**盖在仍在 DOM 里的内容上**，于是没有布局跳动，也不需要清空已有信息。
 * 2. **骨架不是内容。** 整块 `aria-hidden="true"`，真正的加载状态由调用方用
 *    `aria-busy` / `role="status"` 表达。否则读屏会把一串灰条当成正文念出来。
 * 3. **动效只有一条信息：这里正在生成一块内容。** 静态底 + 一道扫过的高光，
 *    节奏与已有 `.chat-skeleton` 完全一致（1.4s），避免同屏出现两种骨架节拍。
 *    `prefers-reduced-motion` 下高光**静止成静态块**（不是 display:none —— 隐藏会让页面空掉）。
 */
const props = withDefaults(
  defineProps<{
    /** 预演哪一种内容的轮廓 */
    variant?: SkeletonVariant
    /** text / list：预演几行。调用方按"真实内容大概几行"给 */
    lines?: number
    /** card / chart / avatar：预演几列 */
    columns?: number
    /** card / chart：显式高度（px）。不给就按 variant 自己的节奏 */
    height?: number
    /** avatar：直径档位 */
    size?: SkeletonSize
    /** 放进一个已经在动的容器里时关掉扫光，避免同屏两种节奏 */
    animated?: boolean
    /** 盖在已有内容之上 —— 父元素需要 position: relative。刷新时"内容还在，只是暂时不可信" */
    overlay?: boolean
    /** 行内使用：跟在文字或标签后面（如"正在读取 …"），不占一整行 */
    inline?: boolean
    /**
     * 根元素标签。缺省 `div`（保持既有调用不变）。
     *
     * 【2026-10-14 · wave2】为什么需要它：`SkeletonBlock` 的根原来**写死**成 `<div>`，
     * 而 `<div>` 放进 `<button>` 是**非法 HTML**（button 的 content model 只允许 phrasing content，
     * 浏览器虽然会渲染，但 HTML 校验失败、无障碍树里那块内容会从按钮的可访问名里掉出来）。
     * 后果是实测的：一个 agent 需要"按钮里显示正在读取"这个形态（MIGRATION §4.1 的 8 处 P2
     * 行内用法就是这么写的：`读取中 <SkeletonBlock inline variant="text" :lines="1"/>`），
     * 发现根节点非法之后**放弃了那 8 处**。
     * 所以这不是"多个可选项"，是补上一种本来就该支持的用法：
     *   放进 <button> / <a> / <p> / <span> 里 → `as="span"`
     *   独立一块（默认用法）→ 不传
     * `span` 时 `.sk` 的 `display` 要跟着从 `flex` 变 `inline-flex`，
     * 否则一个块级流进行内上下文会让按钮的基线跳动（见 <style> 里的 `.sk--as-span`）。
     */
    as?: 'div' | 'span'
  }>(),
  {
    variant: 'text',
    lines: 3,
    columns: 1,
    size: 'md',
    animated: true,
    overlay: false,
    inline: false,
    as: 'div'
  }
)

/** 行数/列数兜底：0 或负数会渲染出"什么都没有的骨架"，那和不做骨架一样 */
const rows = computed(() => Math.max(1, Math.round(props.lines)))
const cols = computed(() => Math.max(1, Math.round(props.columns)))

const rootStyle = computed<CSSProperties | undefined>(() =>
  props.height ? { height: `${props.height}px` } : undefined
)

const gridStyle = computed<CSSProperties>(() => ({
  gridTemplateColumns: `repeat(${cols.value}, minmax(0, 1fr))`
}))

/** 段落最后一行在真实文本里是断的；等宽的灰条会被读成表格而不是一段话 */
function lineWidth(index: number): string {
  if (rows.value === 1) return '72%'
  if (index === rows.value) return '58%'
  return index % 4 === 3 ? '86%' : '100%'
}

/**
 * 行内形态不能用百分比宽度：`.sk--inline` 是 shrink-to-fit 的 inline-flex 容器，
 * 百分比在里面解不出参照宽度，灰条会直接塌成 0 宽（看不见）。
 * 所以行内改为由 CSS 给 em 宽度，这里返回 undefined。
 */
function lineStyle(index: number): CSSProperties | undefined {
  return props.inline ? undefined : { width: lineWidth(index) }
}

/** 图表块的高度节奏：真实条形图高低不一，等高的柱子会读成"表格的列" */
const COL_HEIGHTS = [68, 44, 88, 56, 76, 38, 92, 62]
function colHeight(index: number): string {
  return `${COL_HEIGHTS[(index - 1) % COL_HEIGHTS.length]}%`
}
</script>

<template>
  <component
    :is="as"
    class="sk"
    :class="[`sk--${variant}`, `sk--${size}`, `sk--as-${as}`, { 'sk--overlay': overlay, 'sk--inline': inline, 'sk--static': !animated }]"
    :style="rootStyle"
    aria-hidden="true"
  >
    <!-- 文本行 -->
    <template v-if="variant === 'text'">
      <span v-for="n in rows" :key="n" class="sk__bar sk__line" :style="lineStyle(n)" />
    </template>

    <!-- 列表行：头像位 + 两行字，预演"一条记录"而不是三根横线 -->
    <template v-else-if="variant === 'list'">
      <span v-for="n in rows" :key="n" class="sk__row">
        <span class="sk__bar sk__dot" />
        <span class="sk__row-body">
          <span class="sk__bar sk__line" style="width: 42%" />
          <span class="sk__bar sk__line" style="width: 76%" />
        </span>
      </span>
    </template>

    <!-- 卡片：一次预演 N 张同级卡片的骨架 -->
    <template v-else-if="variant === 'card'">
      <span class="sk__grid" :style="gridStyle">
        <span v-for="n in cols" :key="n" class="sk__card">
          <span class="sk__bar" style="width: 52%; height: 14px" />
          <span class="sk__bar" style="width: 100%" />
          <span class="sk__bar" style="width: 82%" />
        </span>
      </span>
    </template>

    <!-- 图表块：基线 + N 根不等高的柱子，预演的是"读数"不是"盒子" -->
    <template v-else-if="variant === 'chart'">
      <span class="sk__chart">
        <span v-for="n in cols" :key="n" class="sk__bar sk__col" :style="{ height: colHeight(n) }" />
      </span>
      <span class="sk__axis" />
    </template>

    <!-- 头像 / 徽标 -->
    <template v-else>
      <span class="sk__grid" :style="gridStyle">
        <span v-for="n in cols" :key="n" class="sk__bar sk__avatar" />
      </span>
    </template>
  </component>
</template>

<style scoped>
/* ============================================================================
 * 骨架屏
 * 静态底走 --sk-base（= 交互态表面那一档），扫光走 --sk-sheen。
 * 高光必须比"底"更亮，所以不能复用 --c-primary-weak：
 * 深色主题下 --c-primary-weak(#1d2137) 比骨架底(#2c2c2e)**更暗**，
 * 用它会扫出一道黑带（现有 .chat-skeleton 在深色下就是这个症状）。
 * ========================================================================= */
.sk {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
}

/* `as="span"`：根的 display 必须跟着切成行内级。
   为什么不能只换标签：`span` 默认是 inline，而 `.sk` 上写着 `display: flex`，
   在 `<button>` 里一个 flex 块会让按钮的内容盒按块级重新布局（按钮高度、基线都会跳）。
   `inline-flex` 才与"这是按钮里的一个小占位"这个用法相符。
   两条都写全（base 与 inline 的组合），这样**不依赖规则顺序** —— `.sk--inline` 与
   `.sk--as-span` 特异度相同，谁在后面谁赢，是个会随重构静默翻转的坑。 */
.sk--as-span {
  display: inline-flex;
  flex-direction: column;
  vertical-align: middle;
}

.sk--as-span.sk--inline {
  display: inline-flex;
  flex-direction: row;
}

.sk--inline {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  vertical-align: middle;
  gap: var(--sp-2);
}

/* 盖在内容之上：内容没有被摘掉，只是暂时不可信 —— 刷新时页面不会先空一块 */
.sk--overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  padding: var(--sp-4);
  background: var(--c-surface);
  overflow: hidden;
}

.sk__bar {
  position: relative;
  display: block;
  overflow: hidden;
  min-width: 0;
  height: 12px;
  border-radius: var(--r-sm);
  background: var(--sk-base);
}

/* 一道扫过的高光：传达"这一块正在生成"，三条共用同一节奏（与 .chat-skeleton 一致） */
.sk__bar::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, var(--sk-sheen), transparent);
  transform: translateX(-100%);
  animation: sk-sweep var(--sk-sweep) var(--ease-in-out) infinite;
}

@keyframes sk-sweep {
  to {
    transform: translateX(100%);
  }
}

/* 逐行错开 ≤ 0.36s：同一节奏、不同相位 = "从上往下长出来"；
   再大就变成"好几块各自在闪"（CRAFT-BRIEF §5.1 第 5 条） */
.sk__line:nth-child(2)::after,
.sk__row:nth-child(2) .sk__bar::after {
  animation-delay: 0.12s;
}
.sk__line:nth-child(3)::after,
.sk__row:nth-child(3) .sk__bar::after {
  animation-delay: 0.24s;
}
.sk__line:nth-child(4)::after,
.sk__row:nth-child(4) .sk__bar::after {
  animation-delay: 0.36s;
}

/* ---- 列表行 ---- */
.sk__row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-width: 0;
}

/* 行内：跟着文字后面的一小段灰条（宽度用 em，理由见 lineStyle 的注释） */
.sk--inline .sk__line {
  width: 6em;
  height: 10px;
}

.sk__row-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  flex: 1;
  min-width: 0;
}

.sk__dot {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: var(--r-pill);
}

/* ---- 卡片 / 头像 ---- */
.sk__grid {
  display: grid;
  gap: var(--sp-3);
  min-width: 0;
}

.sk__card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}

/* ---- 图表块 ---- */
.sk--chart {
  gap: var(--sp-2);
}

.sk__chart {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-2);
  height: 96px;
  min-width: 0;
}

.sk__col {
  flex: 1;
  height: 100%;
  border-radius: var(--r-sm) var(--r-sm) 0 0;
}

.sk__axis {
  display: block;
  height: var(--bw-1);
  background: var(--c-border);
}

/* ---- 头像 / 徽标 ---- */
.sk__avatar {
  width: 100%;
  /* 必须显式 height:auto：.sk__bar 上那条 12px 的行高会压过 aspect-ratio，
     否则头像是扁椭圆而不是圆 */
  height: auto;
  aspect-ratio: 1;
  border-radius: var(--r-pill);
}

.sk--sm .sk__avatar {
  max-width: 28px;
}

.sk--md .sk__avatar {
  max-width: 40px;
}

.sk--lg .sk__avatar {
  max-width: 64px;
}

/* 调用方已经在一个动效容器里：只留静态轮廓 */
.sk--static .sk__bar::after {
  animation: none;
  background: none;
}

/* reduced-motion：**降级到可用形态**，不是隐藏。
   高光停住，灰块还在 —— 用户仍然看到"这里将会有一块内容" */
@media (prefers-reduced-motion: reduce) {
  .sk__bar::after {
    animation: none;
    background: none;
  }
}
</style>
