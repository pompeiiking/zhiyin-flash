<script setup lang="ts">
import type { Confidence } from '../data/types'

/**
 * 把握度：L1 不给数字，只给三档文字 + 三格点（文档 7.3）。
 * 小数与分值只在点开依据之后才出现 —— 所以组件本身不接收数值。
 */
defineProps<{ value: Confidence }>()
</script>

<template>
  <span class="confidence" :title="`把握度：${value.label}`">
    <span class="confidence__bars" aria-hidden="true">
      <i
        v-for="n in 3"
        :key="n"
        class="confidence__bar"
        :class="{ 'confidence__bar--on': n <= value.bars }"
      />
    </span>
    <span>{{ value.label }}</span>
  </span>
</template>
