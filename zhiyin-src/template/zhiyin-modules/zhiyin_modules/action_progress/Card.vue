<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ result: { data: Record<string, any>; empty: boolean } }>()
const percent = computed(() => props.result.data.total ? Math.round(props.result.data.completed / props.result.data.total * 100) : 0)
</script>
<template>
  <div class="progress-card">
    <template v-if="result.data.has_plan">
      <p class="progress-count"><strong>{{ result.data.completed }}</strong> / {{ result.data.total }} 件</p>
      <progress :value="result.data.completed" :max="result.data.total || 1" :aria-label="`已完成 ${percent}%`" />
      <p>{{ result.empty ? '计划已建立，还没有可执行的任务。' : `已完成 ${percent}%，继续推进下一件事。` }}</p>
    </template>
    <p v-else>还没有行动计划。与主理聊聊，确定下一步。</p>
  </div>
</template>
<style scoped>
.progress-card { display:grid; gap:12px; padding:10px 0; }.progress-count { font-size:18px; }.progress-count strong { font-size:34px; color:var(--accent,#007a52); } progress { width:100%; height:10px; accent-color:#007a52; } p { margin:0; line-height:1.6; }
</style>
