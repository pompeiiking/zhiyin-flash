<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {backendClient} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import AssetNotice from '../components/AssetNotice.vue'
import TaskBrief from '../components/TaskBrief.vue'
import DetailPopover from '../components/DetailPopover.vue'
import StatusBanner from '../components/StatusBanner.vue'
import EmptyState from '../components/EmptyState.vue'
import type {ActionTaskView} from '../api/backend-types'
const plan=computed(()=>backendDemo.state.liveAction)
const tasks=computed(()=>plan.value?.phases?.flatMap(p=>p.tasks??[])??[])
const doneCount=computed(()=>tasks.value.filter(t=>t.done).length)
const pending=computed(()=>tasks.value.filter(t=>!t.done))
const next=computed(()=>plan.value?.next_task??pending.value[0])
const busy=ref(false),error=ref('')
async function load(){busy.value=true;error.value='';try{backendDemo.setAction(await backendClient.action())}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function finish(task:ActionTaskView){if(busy.value)return;busy.value=true;try{backendDemo.setAction(await backendClient.actionDone({task_id:task.task_id,done:!task.done}))}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
onMounted(load)
</script>
<template><div class="ws-page journey-page">
<PageHeading title="今日行动" description="从当前优先任务开始，完成状态与阶段计划同步。"><template #meta><span class="tag">{{new Date().toLocaleDateString('zh-CN')}}</span><span class="tag">待执行 {{pending.length}} 件</span><span class="tag">已完成 {{doneCount}} / {{tasks.length}}</span></template><RouterLink class="btn" to="/plan">看阶段计划</RouterLink></PageHeading>
<AssetNotice/><StatusBanner v-if="error" tone="error" :message="error" retry-label="重新读取" @retry="load"/>
<div class="journey-action-grid"><main class="journey-action-main">
<section v-if="next" class="c2-today-task"><header class="c2-today-task-head"><h2>当前优先任务</h2><span v-if="next.due_date">{{next.due_date}}</span></header><div class="journey-focus"><div class="journey-focus__copy"><h2>{{next.text}}</h2><DetailPopover title="关联阶段" label="查看关联阶段"><template #trigger>任务依据</template><p>{{next.phase||'阶段计划'}}</p><RouterLink to="/plan">查看完整计划</RouterLink></DetailPopover><div class="journey-focus__actions"><button class="btn btn--primary" :disabled="busy" @click="finish(next)">{{busy?'正在保存…':next.done?'恢复任务':'标记完成'}}</button><RouterLink class="btn" :to="'/chat?question='+encodeURIComponent('我想讨论这项任务：'+next.text)">咨询此任务</RouterLink></div></div></div></section>
<EmptyState v-else-if="!busy" kind="notes" :title="tasks.length?'当前计划任务已完成':'暂无行动任务'" description="通过咨询明确方向后，安排具体行动。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink></EmptyState><p v-else role="status">正在读取行动计划…</p>
<section class="hm-live"><div class="hm-live__head"><h2>任务完成情况</h2><span>{{doneCount}} / {{tasks.length}}</span></div><progress v-if="tasks.length" :value="doneCount" :max="tasks.length" aria-label="任务完成情况"/></section>
<ul class="ws-mini-list"><li v-for="task in pending.filter(t=>t.task_id!==next?.task_id)" :key="task.task_id"><strong>{{task.text}}</strong><span v-if="task.due_date"> · {{task.due_date}}</span><button class="ws-text-button" :disabled="busy" @click="finish(task)">完成任务</button></li></ul>
</main><aside class="journey-action-aside"><TaskBrief/><RouterLink class="ws-text-link" to="/schedule">核对课程与截止日期</RouterLink><RouterLink class="ws-text-link" to="/notes">查看个人待办</RouterLink></aside></div>
<section class="c2-plan-tools"><RouterLink class="btn" to="/notes">添加个人待办</RouterLink><button class="ws-text-button" :disabled="busy" @click="load">刷新行动计划</button></section>
</div></template>
