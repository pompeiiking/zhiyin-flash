<script setup lang="ts">
import UiIcon from './UiIcon.vue'
defineProps<{ items: readonly string[] }>()
</script>
<template>
  <details class="exp-evidence"><summary><UiIcon name="report" :size="15" />支持依据<span>{{ items.length }}</span><UiIcon name="chevron" :size="14" /></summary><ol><li v-for="(item, index) in items" :key="index"><span>{{ index + 1 }}</span><p>{{ item }}</p></li></ol></details>
</template>
