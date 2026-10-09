<script setup lang="ts">
defineProps<{ result: { data: Record<string, any> } }>()
</script>
<template>
  <p v-if="!result.data.items?.length" class="empty-records" role="status">暂无完成记录</p>
  <ul v-else class="records"><li v-for="item in result.data.items" :key="item.key">
    <span>{{ item.label || item.key }}</span><span>{{ item.unlocked ? '已完成' : '待完成' }}</span>
  </li></ul>
</template>
<style scoped>
.records { padding:0; list-style:none; }.records li { display:flex; justify-content:space-between; gap:20px; padding:16px 0; border-bottom:1px solid #dedbd3; }
.empty-records { margin:0; padding:16px 0; line-height:1.6; }
</style>
