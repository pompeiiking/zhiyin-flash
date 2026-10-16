<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {backendClient} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import {actionRows,dateKey,deadline} from '../lib/action-insights.mjs'
import type {ActionTaskView} from '../api/backend-types'
import {usePagedItems} from '../lib/paged-items'
import TaskEditor from './TaskEditor.vue'
import PhaseEditor from './PhaseEditor.vue'
import ActionTaskRow from './ActionTaskRow.vue'
import DetailPopover from './DetailPopover.vue'
import ResultPager from './ResultPager.vue'
import ReportHistory from './ReportHistory.vue'
import StatusBanner from './StatusBanner.vue'
import Foldable from './Foldable.vue'
defineProps<{today?:boolean}>()
const plan=computed(()=>backendDemo.state.liveAction),tasks=computed(()=>actionRows(plan.value))
const busy=ref(false),saving=ref(false),error=ref(''),status=ref(''),selected=ref(-1),query=ref(''),filter=ref('all')
const doneCount=computed(()=>tasks.value.filter(t=>t.done).length)
const phases=computed(()=>(plan.value?.phases??[]).map((p,index)=>{
 const items=tasks.value.filter(t=>t.phaseIndex===index),pending=items.filter(t=>!t.done)
 const nearest=pending.map(t=>dateKey(t.due_date)).filter(Boolean).sort()[0]
 return {...p,index,items,done:items.filter(t=>t.done).length,nearest}
}))
const current=computed(()=>phases.value.find(p=>p.items.some(t=>!t.done)))
const filtered=computed(()=>tasks.value.filter(t=>(selected.value<0||t.phaseIndex===selected.value)&&(filter.value==='all'||(filter.value==='done'?t.done:filter.value==='pending'?!t.done:!t.done&&t.status===filter.value))&&[t.text,t.phase,dateKey(t.due_date)].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,6)
const workspace=computed(()=>backendDemo.state.liveWorkspace)
const timeFact=computed(()=>workspace.value?.profile_panel?.fields?.find(f=>f.key==='time'||f.key==='weekly_hours'))
async function load(){if(busy.value||saving.value)return;busy.value=true;error.value='';try{const results=await Promise.allSettled([backendClient.action(),backendClient.workspace()]);if(results[0].status==='fulfilled')backendDemo.setAction(results[0].value);if(results[1].status==='fulfilled')backendDemo.setWorkspace(results[1].value);const failed=results.find(r=>r.status==='rejected');if(failed?.status==='rejected')throw failed.reason}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function toggle(task:ActionTaskView){if(saving.value||busy.value)return;saving.value=true;error.value='';try{backendDemo.setAction(await backendClient.actionDone({task_id:task.task_id,done:!task.done}));status.value=task.done?'任务已恢复。':'任务已完成，阶段进度已同步。'}catch(e){error.value=(e as Error).message}finally{saving.value=false}}
onMounted(load)
</script>
<template><section class="restored-plan" :aria-busy="busy">
<StatusBanner v-if="error" tone="error" :message="error" retry-label="重新读取" @retry="load"/><p v-if="status" role="status" class="desk-status">{{status}}</p>
<div class="ws-section-head"><div><h2>{{current?'当前阶段 · '+current.name:tasks.length?'计划已完成':'阶段路径'}}</h2><p class="ws-muted">{{doneCount}} / {{tasks.length}} 项完成 · {{phases.length}} 个阶段</p></div><button class="btn" :disabled="busy||saving" @click="load">{{busy?'正在读取…':'刷新计划'}}</button></div>
<nav v-if="phases.length" class="restored-phase-path" aria-label="按阶段查看任务"><button v-for="p in phases" :key="p.index" :aria-pressed="selected===p.index" @click="selected=selected===p.index?-1:p.index"><span class="restored-phase-number">{{p.items.length&&p.done===p.items.length?'✓':p.index+1}}</span><strong>{{p.name}}</strong><small>{{p.starts_at||p.ends_at?(dateKey(p.starts_at)||'未定')+' — '+(dateKey(p.ends_at)||'未定'):p.date_range||'时间范围待补充'}}</small><progress :value="p.done" :max="Math.max(1,p.items.length)" :aria-label="p.name+'完成进度'"/><small>{{p.done}} / {{p.items.length}} 项完成</small></button></nav>
<div class="journey-action-grid"><main class="journey-action-main">
<div class="ws-section-head plan-task-heading"><h2>{{selected>=0?phases[selected]?.name:'全部阶段任务'}}</h2><div class="ws-inline-actions plan-create-actions"><PhaseEditor/><TaskEditor/></div></div><div class="restore-toolbar"><label class="information-search">查找任务<input v-model="query" type="search" placeholder="任务、阶段或截止日期"/></label><label class="ws-field">状态<select v-model="filter"><option value="all">全部任务</option><option value="pending">待执行</option><option value="done">已完成</option><option value="waiting">等待中</option><option value="in_progress">进行中</option></select></label></div>
<div v-if="selected>=0"><button class="ws-text-button" @click="selected=-1">查看全部阶段</button></div>
<ActionTaskRow v-for="task in paged" :key="task.task_id" :task="task" :busy="saving||busy" @toggle="toggle"/><ResultPager v-model:page="page" :total="filtered.length" :size="6" label="阶段任务"/>
<p v-if="!filtered.length&&!busy" class="ws-empty">{{tasks.length?'没有符合当前条件的任务。':'尚未形成计划，可通过咨询安排阶段任务。'}}</p>
</main><aside class="journey-action-aside">
<section><h2>各阶段的进度与时间</h2><div v-for="p in phases" :key="p.index" class="restored-stage-summary"><button class="ws-text-button" @click="selected=p.index">{{p.name}} · {{p.done}} / {{p.items.length}}</button><span v-if="p.nearest" :class="{'ws-attention':deadline(p.nearest).overdue}">{{deadline(p.nearest).label}}</span><DetailPopover :title="p.name+' · 阶段详情'" :label="'查看'+p.name+'阶段详情'" side="right"><template #trigger>阶段详情</template><p>{{p.starts_at?dateKey(p.starts_at):p.date_range||'未设阶段开始时间'}} — {{p.ends_at?dateKey(p.ends_at):'未设结束时间'}}</p><p v-if="p.blocked_by?.length" class="ws-attention">前置阶段尚未完成：{{p.blocked_by.map(id=>phases.find(x=>x.id===id)?.name||id).join('、')}}</p><p v-if="p.depends_on?.length">依赖：{{p.depends_on.map(id=>phases.find(x=>x.id===id)?.name||id).join('、')}}</p><p v-for="condition in p.blocking_conditions" :key="condition">阻塞条件：{{condition}}</p><p v-for="requirement in p.handoff_requirements" :key="requirement">交接要求：{{requirement}}</p><p v-if="p.tag">{{p.tag}}</p><p>已完成 {{p.done}} 项，待执行 {{p.items.length-p.done}} 项。</p><p v-if="p.nearest">最近任务截止：{{p.nearest}}。这是任务日期，不代表整个阶段的截止日期。</p><RouterLink class="ws-text-link" :to="'/chat?question='+encodeURIComponent('请一起核对阶段「'+p.name+'」的安排、前置条件与交接要求')">讨论这个阶段</RouterLink></DetailPopover><PhaseEditor :phase-id="p.id"/></div></section>
<section><h2>安排依据</h2><p v-if="timeFact">{{timeFact.label||'每周可投入'}}：{{timeFact.value}}</p><p v-if="workspace?.plan_panel?.evaluation">{{workspace.plan_panel.evaluation}}</p><DetailPopover title="计划与资料的关系" label="查看计划与资料的关系" side="right"><template #trigger>资料关联</template><ul class="ws-mini-list"><li v-for="edge in workspace?.dependencies" :key="edge.from_asset+edge.to_asset">{{edge.from_asset}} → {{edge.to_asset}}<p>{{edge.via_profile_keys?.map(key=>workspace?.profile_panel?.fields?.find(f=>f.key===key)?.label||key).join('、')}}</p></li></ul><p v-if="!workspace?.dependencies?.length">当前没有返回资料关联关系。</p></DetailPopover><RouterLink class="ws-text-link" to="/profile">核对个人资料</RouterLink><RouterLink class="ws-text-link" to="/schedule">结合课表查看时间</RouterLink></section>
<section><h2>任务进度图</h2><div class="restored-task-map"><DetailPopover v-for="t in tasks" :key="t.task_id" :title="t.text" :label="t.text+'：'+(t.done?'已完成':t.status==='waiting'?'等待中':t.status==='in_progress'?'进行中 '+t.progress+'%':'待执行')" side="right"><template #trigger>{{t.done?'✓':'○'}}</template><p>{{t.phase}}</p><p>{{dateKey(t.due_date)||'未设日期'}}</p><button class="btn" :disabled="saving||busy" @click="toggle(t)">{{t.done?'恢复任务':'标记完成'}}</button></DetailPopover></div></section>
</aside></div>
<Foldable title="行动计划版本" :default-open="false"><ReportHistory asset-type="action_plan"/></Foldable>
</section></template>
<style scoped>
.plan-create-actions{margin:0;gap:12px}.plan-task-heading{flex-wrap:wrap;gap:8px}.restored-plan .restore-toolbar .ws-field{flex:none;flex-direction:row;align-items:center;gap:10px;white-space:nowrap}.restore-toolbar .ws-field select{width:auto;min-width:120px}.restore-toolbar .ws-field,.restore-toolbar .information-search{margin:0}.restore-toolbar{margin-bottom:0}.restored-plan .restored-phase-path{margin:16px 0 20px}

.restored-phase-path{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0 30px}.restored-phase-path>button{display:grid;grid-template-columns:24px minmax(0,1fr);gap:6px;text-align:left;padding:14px;border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-surface);color:var(--c-text)}.restored-phase-path>button[aria-pressed=true]{border-color:var(--c-primary);background:var(--c-primary-weak)}.restored-phase-path small{color:var(--c-text-3);line-height:1.6}.restored-phase-path>button>strong,.restored-phase-path>button>small{grid-column:2}.restored-phase-path>button>progress{grid-column:1/-1}.restored-phase-number{grid-row:1/3;align-self:center;font-size:20px;color:var(--c-primary);font-variant-numeric:tabular-nums}progress{accent-color:var(--c-primary);width:100%;height:5px}.restore-toolbar{display:flex;flex-wrap:wrap;gap:16px;align-items:end;margin-bottom:0}.restore-toolbar .information-search{flex:1;min-width:180px}.restored-stage-summary{display:grid;grid-template-columns:1fr auto;gap:8px;padding:12px 0;border-bottom:1px solid var(--c-border);font-size:var(--fs-12)}.restored-stage-summary>button:first-child{grid-column:1/-1;text-align:left}.restored-task-map{display:flex;flex-wrap:wrap;gap:8px}.restored-task-map :deep(.detail-trigger){width:32px;height:32px;border:1px solid var(--c-border);border-radius:50%;justify-content:center}.restored-plan>.journey-action-grid{margin-bottom:28px}@media(max-width:600px){.restored-phase-path{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:18px 0 24px}.restored-phase-path>button{padding:12px;min-width:0}.restored-phase-path>button>strong{font-size:13px}.restored-phase-path small{font-size:11px}.restore-toolbar{gap:10px}}@media print{.restore-toolbar,.restored-plan button{display:none}}
</style>
