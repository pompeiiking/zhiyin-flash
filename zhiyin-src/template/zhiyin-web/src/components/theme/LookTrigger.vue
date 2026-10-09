<script setup lang="ts">
/**
 * 「外观台」三个字 —— 开那块面板的唯一入口（三处各挂一个）。
 *
 * 【为什么是三个字，不是一颗图标或浮片】
 *
 * 外观台是一件"当面配给人看"的工具：它得先被看见，才谈得上点。所以这里就是一个
 * 明写的文字按钮，跟着真正的界面走 —— 控制台里坐在账号那颗的右边、报告页顶栏、
 * 门户页右上角。之前那一版挂在右下角当浮片，那是"工具"的位置；现在是"台子"，
 * 台子该摆在人看得见的地方。
 *
 * 三个字的位置自己说清了它是什么，所以不再画图标、不再加边框：它旁边的东西
 * （账号、面包屑、主张）都比它重要，它不该跟它们抢。悬停才出现下划线。
 */
import { toggleLookPanel } from '@/composables/useLookPanel'

const props = withDefaults(defineProps<{ anchor?: 'left' | 'right' }>(), { anchor: 'left' })
</script>

<template>
  <button
    class="look-trigger label"
    type="button"
    aria-haspopup="dialog"
    title="打开外观台：七条轴，自己配一套"
    @click="toggleLookPanel(props.anchor)"
  >
    外观台
  </button>
</template>

<style scoped>
.look-trigger {
  flex: 0 0 auto;
  padding: 2px 2px;
  color: var(--ink-3);
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 4px;
  transition: color var(--dur-micro) var(--ease-out),
              text-decoration-color var(--dur-micro) var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
.look-trigger:hover {
  color: var(--accent);
  text-decoration-color: currentColor;
}
}
</style>
