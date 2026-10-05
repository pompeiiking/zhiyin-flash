<script setup lang="ts">
defineProps<{ result: { data: Record<string, any> } }>()
</script>
<template>
  <div class="achievement-card"><strong>{{ result.data.unlocked }} / {{ result.data.total }}</strong>
    <p>{{ result.data.unlocked ? '这些是你真正完成过的事。' : '完成一件事，这里就会留下记录。' }}</p>
  </div>
</template>
<style scoped>
.achievement-card { padding:10px 0; } strong { font-size:28px; color:var(--accent,#007a52); } p { margin-top:12px; line-height:1.6; }
</style>
