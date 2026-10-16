<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {backendClient} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import {actionRows,dateKey,deadline,taskGroup} from '../lib/action-insights.mjs'
import {usePagedItems} from '../lib/paged-items'
import type {ActionTaskView} from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import AssetNotice from '../components/AssetNotice.vue'
import TaskBrief from '../components/TaskBrief.vue'
import DetailPopover from '../components/DetailPopover.vue'
import CapabilityGap from '../components/CapabilityGap.vue'
import StatusBanner from '../components/StatusBanner.vue'
import ActionTaskRow from '../components/ActionTaskRow.vue'
import ResultPager from '../components/ResultPager.vue'
import InfoSheet from '../components/InfoSheet.vue'
const plan=computed(()=>backendDemo.state.liveAction),tasks=computed(()=>actionRows(plan.value))
const doneCount=computed(()=>tasks.value.filter(t=>t.done).length)
const pending=computed(()=>tasks.value.filter(t=>!t.done))
const next=computed(()=>tasks.value.find(t=>t.task_id===plan.value?.next_task?.task_id&&!t.done)??pending.value[0])
const busy=ref(false),saving=ref(false),error=ref(''),status=ref(''),lastDone=ref<ActionTaskView|null>(null),query=ref(''),group=ref('pending')
const groups=[{key:'pending',label:'待执行'},{key:'today',label:'今天截止'},{key:'overdue',label:'已过截止日'},{key:'upcoming',label:'后续安排'},{key:'undated',label:'未设日期'},{key:'done',label:'已完成'}]
const matches=(t:ActionTaskView,key:string)=>key==='pending'?!t.done:taskGroup(t)===key
const filtered=computed(()=>tasks.value.filter(t=>matches(t,group.value)&&[t.text,t.phase,t.due_date].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,5)
const addOpen=ref(false),note=ref(''),noteBusy=ref(false),noteError=ref('')
const timeFact=computed(()=>backendDemo.state.liveWorkspace?.profile_panel?.fields?.find(f=>f.key==='time'||f.key==='weekly_hours'))
async function load(){if(busy.value)return;busy.value=true;error.value='';try{const [action,workspace]=await Promise.all([backendClient.action(),backendClient.workspace()]);backendDemo.setAction(action);backendDemo.setWorkspace(workspace)}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function finish(task:ActionTaskView){if(busy.value)return;busy.value=true;saving.value=true;error.value='';try{backendDemo.setAction(await backendClient.actionDone({task_id:task.task_id,done:!task.done}));lastDone.value=task.done?null:{...task,done:true};status.value=task.done?'任务已恢复。':'完成状态已保存。'}catch(e){error.value=(e as Error).message}finally{busy.value=false;saving.value=false}}
async function addNote(){if(noteBusy.value||!note.value.trim())return;noteBusy.value=true;noteError.value='';try{backendDemo.upsertNote(await backendClient.addNote({kind:'todo',text:note.value.trim()}));note.value='';addOpen.value=false;status.value='个人待办已保存到账号；尚未排入行动计划。'}catch(e){noteError.value=(e as Error).message}finally{noteBusy.value=false}}
onMounted(load)
</script>
<template><div class="ws-page journey-page">
<PageHeading title="今日行动" description="从一件具体的小事开始，让想好的方向往前走。"><template #meta><span class="tag">{{new Date().toLocaleDateString('zh-CN')}}</span><span class="tag">待执行 {{pending.length}} 件</span><span class="tag">已完成 {{doneCount}} / {{tasks.length}}</span></template><RouterLink class="btn" to="/plan">看阶段计划</RouterLink></PageHeading>
<AssetNotice/><StatusBanner v-if="error" tone="error" :message="error" retry-label="重新读取" @retry="load"/><p v-if="status" class="desk-status" role="status">{{status}}</p>
<section v-if="lastDone" class="journey-complete"><div><h2>刚刚完成</h2><p>{{lastDone.text}}</p></div><button class="btn" :disabled="busy" @click="finish(lastDone)">恢复任务</button></section>
<div class="journey-action-grid"><main class="journey-action-main">
<section v-if="next" class="c2-today-task"><header class="c2-today-task-head"><h2>当前优先任务</h2><span :class="{'ws-attention':deadline(next.due_date).overdue}">{{deadline(next.due_date).label}}</span></header><div class="journey-focus"><div class="journey-focus__copy"><p class="ws-muted">{{next.phase}}<span v-if="next.due_date"> · {{dateKey(next.due_date)}}</span></p><h2>{{next.text}}</h2><DetailPopover title="任务依据与关联计划" label="查看任务依据与关联计划" side="right"><template #trigger>为什么是这项任务</template><p>{{plan?.next_task?.task_id===next.task_id?'来自当前计划的优先任务。':'当前计划没有指定优先项，先展示第一项未完成任务。'}}</p><p>关联阶段：{{next.phase}}</p><p class="ws-muted">该任务尚未提供独立的推荐理由。</p><RouterLink to="/plan">查看完整阶段路径</RouterLink></DetailPopover><div class="journey-focus__actions"><button class="btn btn--primary" :disabled="busy" @click="finish(next)">{{busy?(saving?'正在保存…':'正在读取…'):'标记完成'}}</button><RouterLink class="btn" :to="'/chat?question='+encodeURIComponent('我想讨论这项任务：'+next.text+'；所属阶段：'+next.phase)">咨询此任务</RouterLink></div></div></div></section>
<p v-else class="ws-empty">{{busy?'正在读取行动计划…':tasks.length?'当前计划任务已完成。':'暂无行动任务，请通过咨询安排计划。'}}</p>
<section class="hm-live"><div class="hm-live__head"><h2>任务完成情况</h2><span>{{doneCount}} / {{tasks.length}}</span></div><progress v-if="tasks.length" :value="doneCount" :max="tasks.length" aria-label="任务完成情况"/></section>
<section><div class="ws-inline-actions task-group-filter"><button v-for="g in groups" :key="g.key" class="btn" :aria-pressed="group===g.key" @click="group=g.key">{{g.label}} {{tasks.filter(t=>matches(t,g.key)).length}}</button><CapabilityGap title="等待中" reason="任务目前只有完成与未完成状态，尚不能记录等待外部反馈，也不能把未来截止的任务自动视为等待中。"/></div><label class="information-search">查找任务<input v-model="query" type="search" placeholder="任务、阶段或日期"/></label><ActionTaskRow v-for="task in paged" :key="task.task_id" :task="task" :busy="busy" @toggle="finish"/><p v-if="!filtered.length&&!busy" class="ws-empty">当前分组没有符合条件的任务。</p><ResultPager v-model:page="page" :total="filtered.length" :size="5" label="行动任务"/></section>
</main><aside class="journey-action-aside"><section><h2>时间与安排依据</h2><p v-if="timeFact">{{timeFact.label||'可投入时间'}}：{{timeFact.value}}</p><p v-else class="ws-muted">当前画像未提供可投入时间。</p><CapabilityGap title="任务预计用时" reason="当前任务没有预计分钟数，不能计算今天所需时长或把空课节次当作可用小时。"/><RouterLink class="ws-text-link" to="/schedule">核对课程与截止日期</RouterLink><RouterLink class="ws-text-link" to="/profile">补充可投入时间</RouterLink></section><TaskBrief/><section><h2>执行记录</h2><p>已完成 {{doneCount}} 件任务。</p><RouterLink class="ws-text-link" to="/review">查看复盘与执行记录</RouterLink></section></aside></div>
<section class="c2-plan-tools"><button class="btn" @click="addOpen=true">添加个人待办</button><button class="ws-text-button" :disabled="busy" @click="load">刷新行动计划</button></section>
<InfoSheet :open="addOpen" title="记一件准备做的事" @close="!noteBusy&&(addOpen=false)"><form @submit.prevent="addNote"><label class="ws-field">做什么<textarea v-model="note" maxlength="200" required placeholder="例如：整理项目经历与成果"/></label><p class="ws-muted">保存到个人待办，可在「待办与目标」继续管理。</p><CapabilityGap title="排进今天与设置用时" reason="现有个人待办接口没有日期或用时字段，行动计划也没有手动新增任务接口。可在咨询中安排，但本次保存不会替你排期。"/><p v-if="noteError" role="alert" class="ws-field-error">{{noteError}}</p><button class="btn btn--primary" :disabled="noteBusy||!note.trim()">{{noteBusy?'正在保存…':'保存个人待办'}}</button></form></InfoSheet>
</div></template>
<style scoped>.task-group-filter{gap:8px;margin-bottom:16px}.task-group-filter [aria-pressed=true]{background:var(--c-primary-weak);color:var(--c-primary);border-color:var(--c-primary)}progress{width:100%;accent-color:var(--c-primary)}.c2-plan-tools{display:flex;flex-wrap:wrap;gap:16px}form>.btn{margin-top:20px}</style>
