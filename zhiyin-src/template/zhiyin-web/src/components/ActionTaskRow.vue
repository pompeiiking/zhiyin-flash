<script setup lang="ts">
import type {ActionTaskView} from '../api/backend-types'
import DetailPopover from './DetailPopover.vue'
import {dateKey,deadline} from '../lib/action-insights.mjs'
defineProps<{task:ActionTaskView;busy?:boolean}>()
defineEmits<{toggle:[task:ActionTaskView]}>()
</script>
<template><article class="restored-task" :class="{'is-done':task.done}">
<button class="restored-check" :disabled="busy" :aria-label="(task.done?'恢复任务：':'完成任务：')+task.text" :aria-pressed="!!task.done" @click="$emit('toggle',task)">{{task.done?'✓':'○'}}</button>
<div><h3>{{task.text}}</h3><div class="restored-task-meta"><span>{{task.phase||'阶段任务'}}</span><time v-if="task.due_date">{{dateKey(task.due_date)}}</time><span v-if="!task.done" :class="{'ws-attention':deadline(task.due_date).overdue}">{{deadline(task.due_date).label}}</span><span v-else-if="task.done_at">完成于 {{dateKey(task.done_at)}}</span></div></div>
<DetailPopover :title="task.text" :label="'查看任务详情：'+task.text" side="right"><template #trigger>依据与详情</template><dl><dt>关联阶段</dt><dd>{{task.phase||'未提供'}}</dd><dt>截止日期</dt><dd>{{dateKey(task.due_date)||'未设定'}}</dd><dt>状态</dt><dd>{{task.done?'已完成':'待执行'}}</dd></dl><p class="ws-muted">计划未提供单项预计用时和独立推荐理由。</p><RouterLink class="ws-text-link" :to="'/chat?question='+encodeURIComponent('请结合我的阶段计划解释这项任务的依据，并讨论执行方式：'+task.text+'；阶段：'+(task.phase||'未提供'))">带着这项任务咨询</RouterLink></DetailPopover>
</article></template>
<style scoped>
.restored-task{display:flex;align-items:center;gap:14px;padding:16px 0;border-bottom:1px solid var(--c-border)}.restored-task>div{flex:1;min-width:0}.restored-task h3{font-size:var(--fs-14);line-height:1.7;font-weight:var(--fw-medium);overflow-wrap:anywhere}.restored-task-meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--c-text-3);font-size:var(--fs-12);margin-top:5px}.restored-check{flex:none;min-width:40px;min-height:40px;border:1px solid var(--c-border);border-radius:50%;color:var(--c-primary);background:var(--c-surface)}.is-done h3{color:var(--c-text-3)}.restored-task :deep(.detail-trigger){flex:none;font-size:var(--fs-12)}@media(max-width:600px){.restored-task{flex-wrap:wrap}.restored-task>div{flex-basis:70%}.restored-task :deep(.detail-trigger){margin-left:54px}}
</style>
