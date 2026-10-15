<script setup lang="ts">
import { computed } from 'vue'
import UiIcon from './UiIcon.vue'
import type { TaskItem } from '../data/types'
const props=defineProps<{tasks:readonly TaskItem[]}>()
defineEmits<{inspect:[id:string]}>()
const done=computed(()=>props.tasks.filter(task=>task.bucket==='done').length)
const queue=computed(()=>[...props.tasks].filter(task=>task.bucket!=='done').slice(0,4))
</script>
<template><section class="plan-task-map"><div class="ws-section-head"><h2>待推进任务</h2><span>{{ tasks.length-done }} 件</span></div><div class="task-queue"><button v-for="task in queue" :key="task.id" @click="$emit('inspect',task.id)"><UiIcon :name="task.bucket==='waiting'?'review':'action'" :size="17"/><span><strong>{{ task.title }}</strong><small>{{ task.bucket==='waiting'?'等待中':'待执行' }}<template v-if="task.minutes!==null"> · {{ task.minutes }} 分钟</template></small></span><UiIcon name="arrow" :size="15"/></button></div><div class="task-queue__progress"><span>已完成 {{ done }} / {{ tasks.length }}</span><progress :value="done" :max="tasks.length||1" :aria-label="'已完成'+done+'件任务'"/></div></section></template>
