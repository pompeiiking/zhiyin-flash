<script setup lang="ts">
import type {ActionTaskView} from '../api/backend-types'
import TaskEditor from './TaskEditor.vue'
import DetailPopover from './DetailPopover.vue'
import {dateKey,deadline} from '../lib/action-insights.mjs'
defineProps<{task:ActionTaskView;busy?:boolean}>()
defineEmits<{toggle:[task:ActionTaskView]}>()
</script>
<template><article class="restored-task" :class="{'is-done':task.done}">
<button class="restored-check" :disabled="busy" :aria-label="(task.done?'恢复任务：':'完成任务：')+task.text" :aria-pressed="!!task.done" @click="$emit('toggle',task)">{{task.done?'✓':'○'}}</button>
<div class="restored-task-content"><h3>{{task.text}}</h3><div class="restored-task-meta"><span v-if="!task.done&&task.status==='in_progress'">进行中 · {{task.progress}}%</span><span v-if="!task.done&&task.status==='waiting'">等待中</span><span>{{task.phase||'阶段任务'}}</span><time v-if="task.due_date">{{dateKey(task.due_date)}}</time><span v-if="!task.done" :class="{'ws-attention':deadline(task.due_date).overdue}">{{deadline(task.due_date).label}}</span><span v-else-if="task.done_at">完成于 {{dateKey(task.done_at)}}</span></div></div>
<div class="restored-task-actions"><DetailPopover :title="task.text" :label="'查看任务详情：'+task.text" side="right"><template #trigger>依据与详情</template><dl><dt>关联阶段</dt><dd>{{task.phase||'未提供'}}</dd><dt>截止日期</dt><dd>{{dateKey(task.due_date)||'未设定'}}</dd><dt>状态</dt><dd>{{task.done?'已完成':task.status==='waiting'?'等待中':task.status==='in_progress'?'进行中 · '+task.progress+'%':'待执行'}}</dd></dl><p v-if="task.estimated_minutes">预计 {{task.estimated_minutes}} 分钟</p><p v-if="task.scheduled_at">安排于 {{new Date(task.scheduled_at).toLocaleString()}}</p><p v-if="task.waiting_reason">等待：{{task.waiting_reason}}</p><RouterLink class="ws-text-link" :to="'/chat?question='+encodeURIComponent('请结合我的阶段计划解释这项任务的依据，并讨论执行方式：'+task.text+'；阶段：'+(task.phase||'未提供'))">带着这项任务咨询</RouterLink></DetailPopover>
<TaskEditor :task="task"/><TaskEditor :task="task" split/></div></article></template>
<style scoped>
.restored-task{display:grid;grid-template-columns:40px minmax(0,1fr);align-items:start;gap:8px 14px;padding:16px 0;border-bottom:1px solid var(--c-border)}.restored-task-content{min-width:0}.restored-check{grid-row:1/3}.restored-task-actions{grid-column:2;display:flex;flex-wrap:wrap;gap:4px 18px;min-width:0}.restored-task-actions :deep(.detail-trigger){min-height:36px}.restored-task h3{font-size:var(--fs-14);line-height:1.7;font-weight:var(--fw-medium);overflow-wrap:anywhere}.restored-task-meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--c-text-3);font-size:var(--fs-12);margin-top:5px}.restored-check{flex:none;min-width:40px;min-height:40px;border:1px solid var(--c-border);border-radius:50%;color:var(--c-primary);background:var(--c-surface)}.is-done h3{color:var(--c-text-3)}.restored-task :deep(.detail-trigger){flex:none;font-size:var(--fs-12)}@media(max-width:600px){.restored-task-actions{gap:4px 12px}.restored-task-actions :deep(.detail-trigger){min-height:44px}}
</style>
