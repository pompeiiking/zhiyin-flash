<script setup lang="ts">
import type {ActionTaskView} from '../api/backend-types'
import TaskEditor from './TaskEditor.vue'
import DetailPopover from './DetailPopover.vue'
import {dateKey,deadline} from '../lib/action-insights.mjs'

defineProps<{task:ActionTaskView;busy?:boolean;saving?:boolean}>()
defineEmits<{toggle:[task:ActionTaskView]}>()

function statusLabel(task:ActionTaskView){
  if(task.done)return '已完成'
  if(task.status==='waiting')return '等待中'
  if(task.status==='in_progress')return `进行中 · ${task.progress??0}%`
  return '待执行'
}
function closeMenu(event:MouseEvent){
  if(event.target instanceof Element&&event.target.closest('button,a'))(event.currentTarget as Element).closest('details')?.removeAttribute('open')
}
</script>

<template>
  <article class="restored-task" :class="{'is-done':task.done}" :aria-busy="saving">
    <button class="restored-check" :disabled="busy" :aria-label="(task.done?'恢复任务：':'完成任务：')+task.text" :aria-pressed="!!task.done" @click="$emit('toggle',task)">{{saving?'…':task.done?'✓':'○'}}</button>
    <div class="restored-task-content">
      <div class="restored-task-title"><h3>{{task.text}}</h3></div>
      <div class="restored-task-meta">
        <span class="restored-task-status" :class="{'is-waiting':task.status==='waiting','is-progress':task.status==='in_progress'}">{{saving?'正在保存':statusLabel(task)}}</span>
        <span>{{task.phase||'阶段任务'}}</span>
        <time v-if="task.due_date">{{dateKey(task.due_date)}}</time>
        <span v-if="!task.done" :class="{'ws-attention':deadline(task.due_date).overdue}">{{deadline(task.due_date).label}}</span>
        <span v-else-if="task.done_at">完成于 {{dateKey(task.done_at)}}</span>
        <span v-if="task.estimated_minutes">预计 {{task.estimated_minutes}} 分钟</span>
      </div>
    </div>
    <details class="restored-task-menu" name="task-actions">
      <summary :aria-label="'任务操作：'+task.text">更多</summary>
      <div class="restored-task-actions" @click="closeMenu">
        <DetailPopover :title="task.text" :label="'查看任务详情：'+task.text" side="right">
          <template #trigger>查看详情</template>
          <dl><dt>关联阶段</dt><dd>{{task.phase||'未提供'}}</dd><dt>截止日期</dt><dd>{{dateKey(task.due_date)||'未设定'}}</dd><dt>状态</dt><dd>{{statusLabel(task)}}</dd></dl>
          <p v-if="task.estimated_minutes">预计 {{task.estimated_minutes}} 分钟</p>
          <p v-if="task.scheduled_at">安排于 {{new Date(task.scheduled_at).toLocaleString()}}</p>
          <p v-if="task.waiting_reason">等待：{{task.waiting_reason}}</p>
          <RouterLink class="ws-text-link" :to="'/chat?question='+encodeURIComponent('请结合我的阶段计划解释这项任务的依据，并讨论执行方式：'+task.text+'；阶段：'+(task.phase||'未提供'))">带着这项任务咨询</RouterLink>
        </DetailPopover>
        <TaskEditor :task="task"/><TaskEditor :task="task" split/>
      </div>
    </details>
  </article>
</template>

<style scoped>
.restored-task{position:relative;display:grid;grid-template-columns:44px minmax(0,1fr) auto;align-items:start;gap:12px;padding:17px 0;border-bottom:1px solid var(--c-border)}.restored-task-content{min-width:0}.restored-check{display:grid;place-items:center;min-width:44px;min-height:44px;border:1px solid var(--c-border-strong);border-radius:50%;color:var(--c-primary);background:transparent;font-weight:var(--fw-bold)}.restored-check:hover{border-color:var(--c-primary);background:var(--c-primary-weak)}.restored-check[aria-pressed=true]{border-color:var(--c-primary);background:var(--c-primary);color:var(--c-on-primary)}.restored-task h3{min-width:0;margin:0;font-size:var(--fs-14);line-height:1.6;font-weight:var(--fw-medium);overflow-wrap:anywhere}.restored-task-meta{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:4px;color:var(--c-text-3);font-size:var(--fs-12)}.restored-task-status{display:inline-flex;align-items:center;gap:6px}.restored-task-status::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--c-border-strong)}.restored-task-status.is-waiting::before{background:var(--c-attention)}.restored-task-status.is-progress::before{background:var(--c-primary)}.is-done h3{color:var(--c-text-3)}.is-done .restored-task-status::before{background:var(--c-done)}.restored-task-menu{position:relative}.restored-task-menu>summary{display:grid;place-items:center;min-width:44px;min-height:44px;cursor:pointer;color:var(--c-text-3);font-size:var(--fs-12);list-style:none}.restored-task-menu>summary::-webkit-details-marker{display:none}.restored-task-menu[open]>summary{color:var(--c-primary)}.restored-task-actions{position:absolute;top:44px;right:0;z-index:5;display:flex;align-items:center;gap:16px;min-width:max-content;padding:8px 12px;border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-surface);box-shadow:var(--e-2)}.restored-task-actions :deep(.detail-trigger){min-height:36px;font-size:var(--fs-12)}
@media(max-width:600px){.restored-task{grid-template-columns:44px minmax(0,1fr) 44px;gap:10px;padding:16px 0}.restored-task-menu>summary{min-width:44px;min-height:44px}.restored-task-actions{gap:12px;max-width:calc(100vw - 32px);overflow-x:auto}.restored-task-actions :deep(.detail-trigger){min-height:44px}}
</style>
