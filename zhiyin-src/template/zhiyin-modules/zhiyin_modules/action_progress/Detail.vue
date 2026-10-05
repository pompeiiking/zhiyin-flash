<script setup lang="ts">
defineProps<{ result: { data: Record<string, any> }; readonly?: boolean; busy?: boolean }>()
const emit = defineEmits<{ action: [name: string, payload: Record<string, unknown>] }>()
</script>
<template>
  <div>
    <p v-if="!result.data.tasks?.length">暂无任务，先完成一份行动计划。</p>
    <label v-for="task in result.data.tasks" :key="task.task_id" class="task-row">
      <input type="checkbox" :checked="task.done" :disabled="readonly || busy"
        @change="emit('action', 'plan.task.set_done', { task_id: task.task_id, done: !task.done })" />
      <span :class="{ done: task.done }">{{ task.text }}<small>{{ task.phase }}</small></span>
    </label>
  </div>
</template>
<style scoped>
.task-row { display:flex; gap:14px; padding:16px 0; border-bottom:1px solid #dedbd3; align-items:center; } input { width:18px; height:18px; accent-color:#007a52; } small { display:block; color:#777; margin-top:5px; }.done { text-decoration:line-through; color:#777; }
</style>
