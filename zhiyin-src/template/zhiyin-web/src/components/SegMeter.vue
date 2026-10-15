<script setup lang="ts">
import { computed } from 'vue'

/* =============================================================================
 * SegMeter —— 「一条线走到哪了」的**分段**读数条
 * -----------------------------------------------------------------------------
 * 【为什么不是 StatTile 的 .tile__track】两者回答的问题不同：
 *   · `.tile__track` 是**连续比例**（5 / 8 → 62.5%），它回答"完成度是多少"；
 *   · 本组件是**离散分段**（8 段亮 3 段），它回答"这一批里还有几件没动"。
 * 靶子的 `.meter`（c2-hbu/_tools/c2.css：`display:flex;gap:3px` / `i{flex:1;height:5px;
 * border-radius:3px}`）就是后者：**一根条 = 一件可做的事**，勾掉一件亮一段。
 * 这也是 /home「今天这条线走到哪了」与 /plan 每段里程碑要的那种读数 ——
 * 段数就是件数，用户能对着列表一段一段数回来，比例条做不到这件事。
 *
 * 【段数不是装饰刻度】`total` 只接受**真实的件数**：
 *   · /home = 这一批任务的总件数（`demo.state.tasks.length`）
 *   · /plan 每段 = 这一段按 `DEMO_PHASE_TASK_IDS` 挂上的任务数
 * 不允许传一个为了好看取整的段数（例如"统一画 5 段"）—— 那会让条与列表对不上，
 * 是"数字不是真数据"的变体。
 *
 * 【没有动画】分段只由 `lit` 决定，宽度/颜色都是静态值：反例表点名的"图表生长"、
 * "数字滚动"在这里都不存在。所以本组件没有 @keyframes，也没有 transition ——
 * `scripts/check-design.mjs` 的 ANIM_ALLOWED 不需要为它登记任何东西。
 * ========================================================================== */

const props = withDefaults(
  defineProps<{
    /** 段数 = 这一批有多少件可做的事（真件数，不是装饰刻度） */
    total: number
    /** 亮着的段数 = 其中已经做完/已经走到的件数 */
    lit: number
    /** 读屏与悬停用的一句话（分段对读屏不可见，这句话是它唯一的等价物） */
    label: string
    /** 轨道高度：gauge 给"一屏只有一个读数"的位置，thin 给条目内 */
    height?: 'thin' | 'gauge'
  }>(),
  { height: 'thin' },
)

/** 段数取整并夹到非负；0 段时不渲染任何节点（而不是画一根空轨道） */
const segments = computed(() => Math.max(0, Math.round(props.total)))
const litCount = computed(() => Math.min(Math.max(0, Math.round(props.lit)), segments.value))
</script>

<template>
  <div class="seg" :class="`seg--${height}`" role="img" :aria-label="label">
    <i
      v-for="n in segments"
      :key="n"
      class="seg__i"
      :class="{ 'seg__i--on': n <= litCount }"
    />
  </div>
</template>

<style scoped>
/* 量值取自靶子的 .meter：gap 3px、高 5px、圆角 3px、底色 --c-done-weak、亮段主色 */
.seg {
  display: flex;
  gap: 3px;
  width: 100%;
  min-width: 0;
}

.seg__i {
  flex: 1 1 0;
  min-width: 2px;
  height: 5px;
  border-radius: 3px;
  background: var(--c-done-weak);
}

/* 亮段：实心主色。**不给渐变**——靶子那版用了 `linear-gradient(90deg,…)`，
   但那在灰度截图里与"深一点的实心"没有区别，却给同一个语义加了第二种画法。
   本项目颜色的口径是"一支令牌一个用途"，所以这里只用 --c-primary 实心。 */
.seg__i--on {
  background: var(--c-primary);
}

/* gauge：一屏只有一个读数时把轨道抬到 6px（与 StatTile 的 .tile__track 同高，
   两者并排时不会一粗一细） */
.seg--gauge .seg__i {
  height: 6px;
}
</style>
