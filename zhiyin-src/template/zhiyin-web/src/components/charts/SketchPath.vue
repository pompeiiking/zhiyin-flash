<script setup lang="ts">
import type { SketchOp } from '@/lib/sketch'

/** 一条手绘 path。图表组件都靠它把 rough 算出来的形状画出来 */
defineProps<{ ops: SketchOp[]; opacity?: number | string }>()
</script>

<template>
  <g :opacity="opacity">
    <path
      v-for="(o, i) in ops"
      :key="i"
      :d="o.d"
      :fill="o.fill"
      :stroke="o.stroke"
      :stroke-width="o.strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
      vector-effect="non-scaling-stroke"
    />
  </g>
</template>
