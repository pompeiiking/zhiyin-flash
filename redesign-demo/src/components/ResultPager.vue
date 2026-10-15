<script setup lang="ts">
import { computed } from 'vue'
import UiIcon from './UiIcon.vue'
const props = withDefaults(defineProps<{ page: number; total: number; size?: number; label: string }>(), { size: 6 })
const emit = defineEmits<{ 'update:page': [value: number] }>()
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.size)))
</script>
<template>
  <div v-if="total > size" class="result-pager" :aria-label="label + '分页'">
    <span role="status">第 {{ (page - 1) * size + 1 }}–{{ Math.min(page * size, total) }} 条，共 {{ total }} 条</span>
    <div><button class="ws-icon-button" :aria-label="label + '上一页'" :disabled="page <= 1" @click="emit('update:page',page - 1)"><UiIcon name="back" :size="18"/></button><span>{{ page }} / {{ pages }}</span><button class="ws-icon-button" :aria-label="label + '下一页'" :disabled="page >= pages" @click="emit('update:page',page + 1)"><UiIcon name="arrow" :size="18"/></button></div>
  </div>
</template>
<style scoped>
.result-pager { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 20px; padding-block: 16px; border-top: 1px solid var(--c-border); color: var(--c-text-2); font-size: 13px; font-variant-numeric: tabular-nums; }
.result-pager > div { display: flex; align-items: center; gap: 10px; }
@media print { .result-pager { display: none; } }
</style>
