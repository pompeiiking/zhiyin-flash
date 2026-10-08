<script setup lang="ts">
/**
 * 界面里那几枚"箭头 / 勾 / 叉" —— **画出来的线，不是字**。
 *
 * 以前它们直接写在模板里当文字：`→` `›` `✓` `×` `▾`。留着它们的代价很具体：
 *   · 形状随字体与字号变 —— `✓` 在 MiSans、宋体、Fraunces 下不是同一个勾；
 *   · 基线跟着行高飘 —— 行末的 `→` 会折到下一行（roomy 那档"看完整分析 →"断成两行，
 *     根因就是它；当时只治了折行的症状）；
 *   · 尺寸不受控 —— 字号一改，箭头跟着变胖变瘦。
 *
 * 这里统一成 16×16 的**描边 SVG**：`currentColor` 上色（所以自动跟随任何配色与状态色）、
 * 1.6 描边、圆头圆角，`width/height` 之外不写死尺寸。名字用**语义**
 * （arrow-right / check / close），不用形状（chevron / cross）：
 * 用哪一枚由"要表达什么"决定，换基础样式时只改这一个文件。
 */
type IconName =
  | 'arrow-right'
  | 'arrow-left'
  | 'arrow-up'
  | 'arrow-down'
  | 'chevron-right'
  | 'chevron-left'
  | 'close'
  | 'check'
  | 'caret-down'
  | 'external'

const PATHS: Record<IconName, string> = {
  'arrow-right': 'M2.8 8h9.4M8.6 4.2 12.4 8l-3.8 3.8',
  // 左向箭头与右向**必须成对**：日历的"上个月/下个月"、情报的"上一条/下一条"
  // 都是并排的两枚。只换右边那一枚，同一排就会出现"一个矢量箭头 + 一个字体箭头"
  // （同字号下形状与粗细都不一样），比两枚都不换更明显。
  'arrow-left': 'M13.2 8H3.8M7.4 4.2 3.6 8l3.8 3.8',
  'arrow-up': 'M8 13.2V3.8M4.2 7.6 8 3.8l3.8 3.8',
  'arrow-down': 'M8 2.8v9.4M4.2 8.4 8 12.2l3.8-3.8',
  'chevron-right': 'M6.2 3.6 10.6 8l-4.4 4.4',
  'chevron-left': 'M9.8 3.6 5.4 8l4.4 4.4',
  close: 'M4.2 4.2l7.6 7.6M11.8 4.2l-7.6 7.6',
  check: 'M3.4 8.6l3 3 6.2-6.8',
  'caret-down': 'M4.4 6.4 8 10l3.6-3.6',
  // 外链："往右上走、离开这一页"。不要用 arrow-right 顶替 —— 那会被读成"下一步"，
  // 而这一枚的含义是"点了会开新窗口、离开当前这屏"，两件事完全不同。
  external: 'M4.6 11.4 11.2 4.8M6.4 4.8h4.8v4.8',
}

withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 16 })

/*
 * 两条给后来人的说明（写在脚本里而不是模板里：模板里的注释会**跟着每个图标进 DOM**，
 * 全站四十多处，devtools 里就是四十多份重复的长注释）。
 *
 * 1. `aria-hidden`：这些线是**装饰**，旁边一定有一句人话或一个 aria-label 说明它是什么。
 *    给它们各自加 title 只会让读屏念出"箭头"，反而更吵。
 * 2. 垂直位置对齐**文字基线**（`.glyph` 的 `vertical-align`）而不是盒子中线：
 *    这些图标几乎都跟在文字前后，按中线对齐在中文行高下会明显偏高（中文字面比拉丁矮一截）。
 */
</script>

<template>
  <svg
    class="glyph"
    :width="size"
    :height="size"
    viewBox="0 0 16 16"
    aria-hidden="true"
    focusable="false"
  >
    <path
      :d="PATHS[name]"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>

<style scoped>
.glyph {
  display: inline-block;
  vertical-align: -0.18em;
  flex: 0 0 auto;
}
</style>
