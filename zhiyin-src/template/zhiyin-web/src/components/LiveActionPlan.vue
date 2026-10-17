<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import {backendClient} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import {actionRows,actionStatusMatches,dateKey,deadline} from '../lib/action-insights.mjs'
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

const plan=computed(()=>backendDemo.state.liveAction)
const tasks=computed(()=>actionRows(plan.value))
const workspace=computed(()=>backendDemo.state.liveWorkspace)
const directions=computed(()=>backendDemo.state.liveDirections)
const busy=ref(false),savingTask=ref(''),error=ref(''),status=ref('')
const selected=ref(-1),selectionTouched=ref(false),query=ref(''),filter=ref('pending')
let statusTimer:ReturnType<typeof setTimeout>|undefined

const doneCount=computed(()=>tasks.value.filter(task=>task.done).length)
const phases=computed(()=>(plan.value?.phases??[]).map((phase,index)=>{
  const items=tasks.value.filter(task=>task.phaseIndex===index)
  const pending=items.filter(task=>!task.done)
  const nearest=pending.map(task=>dateKey(task.due_date)).filter(Boolean).sort()[0]
  return {...phase,index,items,done:items.filter(task=>task.done).length,nearest}
}))
const currentPhase=computed(()=>{
  const taskId=plan.value?.next_task?.task_id
  const byNext=taskId?phases.value.find(phase=>phase.items.some(task=>task.task_id===taskId)):undefined
  return byNext??phases.value.find(phase=>!phase.blocked_by?.length&&phase.items.some(task=>!task.done&&task.status!=='waiting'))
})
const inspectedPhase=computed(()=>phases.value.find(phase=>phase.index===selected.value)??currentPhase.value??phases.value[0])
const nextTask=computed(()=>plan.value?.next_task??currentPhase.value?.items.find(task=>!task.done&&task.status!=='waiting'))
const selectedDirection=computed(()=>directions.value?.plans?.find(item=>item.id===directions.value?.selected_id||item.selected))
const overallPercent=computed(()=>tasks.value.length?Math.round(doneCount.value/tasks.value.length*100):0)
const allDone=computed(()=>tasks.value.length>0&&doneCount.value===tasks.value.length)
const timeFact=computed(()=>workspace.value?.profile_panel?.fields?.find(field=>field.key==='time'||field.key==='weekly_hours'))
const filtered=computed(()=>tasks.value.filter(task=>(selected.value<0||task.phaseIndex===selected.value)
  &&actionStatusMatches(task,filter.value)
  &&[task.text,task.phase,dateKey(task.due_date)].join(' ').toLowerCase().includes(query.value.trim().toLowerCase())))
const {page,paged}=usePagedItems(filtered,6,()=>[selected.value,query.value,filter.value])

const filters=[
  {id:'pending',label:'待执行'},
  {id:'in_progress',label:'进行中'},
  {id:'waiting',label:'等待中'},
  {id:'done',label:'已完成'},
  {id:'all',label:'全部'},
]
const assetLabels:Record<string,string>={
  portrait:'生涯画像',profile:'个人资料',academic:'学业分析',report:'分析报告',direction_plan:'方向计划',action_plan:'行动计划',schedule:'课表',review:'复盘记录',
}

function phaseState(phase:(typeof phases.value)[number]){
  if(phase.items.length&&phase.done===phase.items.length)return 'done'
  if(phase.blocked_by?.length)return 'blocked'
  if(phase.index===currentPhase.value?.index)return 'current'
  if(phase.items.some(task=>!task.done)&&phase.items.filter(task=>!task.done).every(task=>task.status==='waiting'))return 'waiting'
  return 'upcoming'
}
function phaseStateLabel(phase:(typeof phases.value)[number]){
  return {done:'已完成',blocked:'前置阻塞',current:'当前阶段',waiting:'等待中',upcoming:'待开始'}[phaseState(phase)]
}
function phasePeriod(phase:(typeof phases.value)[number]){
  const start=dateKey(phase.starts_at),end=dateKey(phase.ends_at)
  if(start&&end)return `${start} 至 ${end}`
  if(phase.date_range)return phase.date_range
  if(start)return `${start} 开始`
  if(end)return `${end} 前完成`
  return '时间待定'
}
function selectPhase(index:number){
  selectionTouched.value=true
  selected.value=index
  const phase=phases.value.find(item=>item.index===selected.value)
  query.value=''
  if(phase?.items.length&&phase.done===phase.items.length)filter.value='done'
  else if(phase?.items.some(task=>!task.done&&(!task.status||task.status==='pending')))filter.value='pending'
  else if(phase?.items.some(task=>!task.done&&task.status==='in_progress'))filter.value='in_progress'
  else if(phase?.items.some(task=>!task.done&&task.status==='waiting'))filter.value='waiting'
  else filter.value='all'
}
function selectAll(){
  selectionTouched.value=true
  selected.value=-1
  query.value=''
  filter.value='pending'
}
function closeStageMenu(event:MouseEvent){
  if(event.target instanceof Element&&event.target.closest('button,a')&&!event.target.closest('[aria-haspopup="dialog"]')){
    (event.currentTarget as Element).closest('details')?.removeAttribute('open')
  }
}
function initializeSelection(){
  if(!selectionTouched.value&&currentPhase.value)selected.value=currentPhase.value.index
}
function showStatus(message:string){
  status.value=message
  if(statusTimer)clearTimeout(statusTimer)
  statusTimer=setTimeout(()=>{status.value=''},4200)
}
async function load(){
  if(busy.value||savingTask.value)return
  busy.value=true;error.value='';status.value=''
  try{
    const results=await Promise.allSettled([backendClient.action(),backendClient.workspace(),backendClient.directions()])
    if(results[0].status==='fulfilled')backendDemo.setAction(results[0].value)
    if(results[1].status==='fulfilled')backendDemo.setWorkspace(results[1].value)
    if(results[2].status==='fulfilled')backendDemo.setLiveDirections(results[2].value)
    if(results[0].status==='fulfilled')initializeSelection()
    const failed=results.find(result=>result.status==='rejected')
    if(failed?.status==='rejected')throw failed.reason
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function toggle(task:ActionTaskView){
  if(savingTask.value||busy.value)return
  savingTask.value=task.task_id;error.value=''
  try{
    backendDemo.setAction(await backendClient.actionDone({task_id:task.task_id,done:!task.done}))
    showStatus(task.done?'任务已恢复。':'任务已完成，阶段进度已同步。')
  }catch(e){error.value=(e as Error).message}
  finally{savingTask.value=''}
}
onMounted(load)
onBeforeUnmount(()=>{if(statusTimer)clearTimeout(statusTimer)})
</script>

<template>
  <section class="restored-plan" :aria-busy="busy">
    <StatusBanner v-if="error" tone="error" :message="error" retry-label="重新读取" @retry="load"/>
    <p v-if="status" role="status" class="plan-toast">{{status}}</p>

    <section v-if="!busy&&plan?.has_plan===false" class="plan-empty-path">
      <header><div><p>还没有阶段计划</p><h2>把方向、时间和第一步连起来</h2></div><RouterLink class="btn btn--primary" :to="'/chat?question='+encodeURIComponent('请根据我的资料和可投入时间，一起建立阶段行动计划')">开始规划</RouterLink></header>
      <ol><li><span>方向</span><strong>确定这轮要靠近什么</strong><RouterLink to="/directions">查看方向方案</RouterLink></li><li><span>时间</span><strong>确认每周能投入多少</strong><RouterLink to="/schedule">核对课表与时间</RouterLink></li><li><span>第一步</span><strong>安排一件现在能开始的事</strong><RouterLink to="/notes">查看待办与目标</RouterLink></li></ol>
    </section>

    <template v-else-if="plan&&plan.has_plan!==false">
      <section class="plan-overview">
        <div class="plan-goal">
          <div class="plan-goal-copy">
            <span>{{selectedDirection?'已确认方向':'行动方向'}}</span>
            <h2>{{selectedDirection?.name||'方向尚未确认'}}</h2>
            <p>{{selectedDirection?.target_desc||selectedDirection?.fit_reason||'先核对方向方案，再让行动计划围绕一个清晰目标展开。'}}</p>
          </div>
          <div class="plan-progress">
            <strong>{{doneCount}} / {{tasks.length}}</strong><span>项已完成</span>
            <div role="progressbar" aria-label="整份行动计划进度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="overallPercent"><i :style="{width:overallPercent+'%'}"></i></div>
          </div>
        </div>
        <div class="plan-goal-actions">
          <RouterLink to="/directions">{{selectedDirection?'查看方向方案':'去确认方向'}}</RouterLink>
          <DetailPopover v-if="selectedDirection?.fit_reason||selectedDirection?.main_risk" :title="selectedDirection.name+' · 方向依据'" label="查看方向依据">
            <template #trigger>方向依据</template>
            <p v-if="selectedDirection.fit_reason">{{selectedDirection.fit_reason}}</p>
            <p v-if="selectedDirection.main_risk" class="ws-attention">主要风险：{{selectedDirection.main_risk}}</p>
          </DetailPopover>
          <button class="plan-refresh" :disabled="busy||!!savingTask" @click="load">{{busy?'正在读取…':'刷新'}}</button>
        </div>
        <div class="plan-focus">
          <div class="plan-focus-label"><span>现在做</span><p v-if="nextTask">{{dateKey(nextTask.due_date)||'未设截止日期'}}，{{deadline(nextTask.due_date).label}}</p></div>
          <strong v-if="nextTask">{{nextTask.text}}</strong>
          <strong v-else>{{allDone?'这一轮已经完成':'下一项任务待安排'}}</strong>
          <RouterLink v-if="nextTask" to="/home">开始行动</RouterLink>
        </div>
      </section>

      <section v-if="!busy&&!phases.length" class="plan-state">
        <div><h2>方向有了，接下来搭出行动路线</h2><p>先建立第一个阶段，再放入一件可以立即开始的任务。</p></div>
        <PhaseEditor/>
      </section>

      <div v-else-if="phases.length" class="plan-work">
        <section class="plan-route">
          <header><h2>行动路线</h2><div class="plan-route-actions"><button :aria-pressed="selected<0" @click="selectAll">全部阶段</button><PhaseEditor/></div></header>
          <nav aria-label="按阶段查看任务">
            <ol :style="{gridTemplateColumns:'repeat('+phases.length+', minmax(170px, 1fr))'}">
              <li v-for="phase in phases" :key="phase.id||phase.index" :class="'is-'+phaseState(phase)">
                <button :aria-pressed="selected===phase.index" @click="selectPhase(phase.index)">
                  <span class="plan-route-index" aria-hidden="true">{{phaseState(phase)==='done'?'✓':phase.index+1}}</span>
                  <span class="plan-route-copy"><strong>{{phase.name}}</strong><small>{{phaseStateLabel(phase)}}，{{phase.done}} / {{phase.items.length}} 项</small><i><b :style="{width:(phase.items.length?phase.done/phase.items.length*100:0)+'%'}"></b></i></span>
                </button>
              </li>
            </ol>
          </nav>
        </section>

        <section class="plan-checklist" aria-labelledby="plan-stage-title">
          <header class="plan-stage-head">
            <div>
              <p>{{selected>=0&&inspectedPhase?phaseStateLabel(inspectedPhase):'整份计划'}}</p>
              <h2 id="plan-stage-title">{{selected>=0&&inspectedPhase?inspectedPhase.name:'全部任务'}}</h2>
              <span v-if="selected>=0&&inspectedPhase">{{phasePeriod(inspectedPhase)}}</span>
              <span v-else>{{doneCount}} 项已完成，还有 {{tasks.length-doneCount}} 项待推进</span>
            </div>
            <div class="plan-stage-actions">
              <TaskEditor :phase-id="selected>=0 ? inspectedPhase?.id : undefined"/>
              <details v-if="selected>=0&&inspectedPhase" class="plan-stage-menu" name="stage-actions">
                <summary>阶段操作</summary>
                <div class="plan-stage-menu-panel" @click="closeStageMenu">
                  <PhaseEditor :phase-id="inspectedPhase.id"/>
                  <DetailPopover title="这份计划怎样形成" label="查看计划依据"><template #trigger>查看计划依据</template><p v-if="timeFact">{{timeFact.label||'每周可投入'}}：{{timeFact.value}}</p><p v-if="workspace?.plan_panel?.evaluation">{{workspace.plan_panel.evaluation}}</p><ul v-if="workspace?.dependencies?.length" class="ws-mini-list"><li v-for="edge in workspace.dependencies" :key="edge.from_asset+edge.to_asset">{{assetLabels[edge.from_asset]||edge.from_asset}} → {{assetLabels[edge.to_asset]||edge.to_asset}}<p v-if="edge.via_profile_keys?.length">参考：{{edge.via_profile_keys.map(key=>workspace?.profile_panel?.fields?.find(field=>field.key===key)?.label||key).join('、')}}</p></li></ul><p v-else>当前没有返回资料关联关系。</p></DetailPopover>
                  <RouterLink to="/schedule">{{plan?.reminders_synced?'查看课表安排':'结合课表安排'}}</RouterLink>
                  <RouterLink :to="'/chat?question='+encodeURIComponent('请一起核对阶段「'+inspectedPhase.name+'」的安排、前置条件与完成标志')">讨论这一阶段</RouterLink>
                </div>
              </details>
            </div>
          </header>

          <details v-if="selected>=0&&inspectedPhase&&(inspectedPhase.blocked_by?.length||inspectedPhase.blocking_conditions?.length||inspectedPhase.handoff_requirements?.length)" class="plan-context">
            <summary>阶段条件与完成标志</summary>
            <div class="plan-context-body">
              <section v-if="inspectedPhase.blocked_by?.length" class="is-attention"><h3>先完成</h3><p>{{inspectedPhase.blocked_by.map(id=>phases.find(phase=>phase.id===id)?.name||id).join('、')}}</p></section>
              <section v-if="inspectedPhase.blocking_conditions?.length"><h3>进入条件</h3><ul><li v-for="condition in inspectedPhase.blocking_conditions" :key="condition">{{condition}}</li></ul></section>
              <section v-if="inspectedPhase.handoff_requirements?.length"><h3>完成标志</h3><ul><li v-for="requirement in inspectedPhase.handoff_requirements" :key="requirement">{{requirement}}</li></ul></section>
            </div>
          </details>

          <div class="plan-task-tools">
            <label class="information-search"><span class="sr-only">查找任务</span><input v-model="query" type="search" placeholder="查找任务或截止日期"/></label>
            <div class="plan-filters" role="group" aria-label="按状态筛选"><button v-for="item in filters" :key="item.id" :aria-pressed="filter===item.id" @click="filter=item.id">{{item.label}}</button></div>
          </div>
          <div class="plan-task-list">
            <ActionTaskRow v-for="task in paged" :key="task.task_id" :task="task" :busy="!!savingTask||busy" :saving="savingTask===task.task_id" @toggle="toggle"/>
          </div>
          <ResultPager v-model:page="page" :total="filtered.length" :size="6" label="阶段任务"/>
          <p v-if="!filtered.length&&!busy" class="ws-empty">{{tasks.length?(filter==='pending'?'当前范围没有待执行任务，可切换状态查看其他任务。':'没有符合当前条件的任务。'):'这个计划还没有任务，请添加任务或通过咨询完善安排。'}}</p>
        </section>
      </div>
    </template>

    <Foldable title="行动计划版本" :default-open="false"><ReportHistory asset-type="action_plan"/></Foldable>
  </section>
</template>

<style scoped>
.plan-toast{position:fixed;right:24px;bottom:24px;z-index:40;max-width:min(360px,calc(100vw - 32px));margin:0;padding:12px 16px;border:1px solid var(--c-primary);border-radius:var(--r-sm);background:var(--c-surface);box-shadow:var(--e-2);color:var(--c-text);font-size:var(--fs-14)}
.plan-state{display:flex;align-items:center;justify-content:space-between;gap:24px;margin:12px 0 32px;padding:28px 0;border-top:1px solid var(--c-border);border-bottom:1px solid var(--c-border)}.plan-state h2{margin:0 0 6px;font-size:var(--fs-20)}.plan-state p{max-width:620px;margin:0;color:var(--c-text-2)}
.plan-empty-path{margin:12px 0 32px;padding:28px 0;border-top:3px solid var(--c-primary);border-bottom:1px solid var(--c-border)}.plan-empty-path>header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.plan-empty-path>header p{color:var(--c-primary);font-size:12px;font-weight:600}.plan-empty-path>header h2{margin-top:5px;font-size:26px}.plan-empty-path ol{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin:26px 0 0;padding:0;border-top:1px solid var(--c-border);list-style:none}.plan-empty-path li{display:grid;gap:7px;padding:18px 20px 18px 0}.plan-empty-path li+li{padding-left:20px;border-left:1px solid var(--c-border)}.plan-empty-path li>span{color:var(--c-text-3);font-size:11px}.plan-empty-path li strong{font-size:15px}.plan-empty-path li a{width:max-content;min-height:36px;color:var(--c-primary);font-size:12px}
.plan-overview{margin:8px 0 34px;padding-top:18px;border-top:3px solid var(--c-primary);border-bottom:1px solid var(--c-border)}.plan-goal{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;padding:0 4px}.plan-goal-copy{min-width:0}.plan-goal-copy>span{color:var(--c-primary);font-size:var(--fs-12)}.plan-goal h2{margin:4px 0 6px;font-size:24px;line-height:1.35;letter-spacing:-.015em}.plan-goal p{max-width:62ch;margin:0;color:var(--c-text-2);font-size:var(--fs-14);line-height:1.7}.plan-progress{display:grid;grid-template-columns:auto auto;gap:2px 7px;align-items:baseline;flex:0 0 190px;color:var(--c-text-3);font-size:var(--fs-12)}.plan-progress strong{color:var(--c-text);font-size:var(--fs-16);font-variant-numeric:tabular-nums}.plan-progress>div{grid-column:1/-1;height:4px;overflow:hidden;margin-top:5px;border-radius:var(--r-pill);background:var(--c-border)}.plan-progress i{display:block;height:100%;background:var(--c-primary)}.plan-goal-actions{display:flex;align-items:center;gap:16px;padding:9px 4px 15px}.plan-goal-actions>a,.plan-goal-actions :deep(.detail-trigger),.plan-refresh{min-height:34px;border:0;background:transparent;color:var(--c-primary);font-size:var(--fs-12)}.plan-refresh{margin-left:auto;padding:0}.plan-focus{display:grid;grid-template-columns:120px minmax(0,1fr) auto;gap:18px;align-items:center;margin-bottom:22px;padding:16px 18px;border-left:3px solid var(--c-primary);border-radius:0 var(--r-sm) var(--r-sm) 0;background:var(--c-surface)}.plan-focus-label span{color:var(--c-primary);font-size:var(--fs-12);font-weight:var(--fw-medium)}.plan-focus-label p{margin:3px 0 0;color:var(--c-text-3);font-size:11px}.plan-focus>strong{font-size:var(--fs-16);line-height:1.55}.plan-focus>a{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 14px;border:1px solid var(--c-primary);border-radius:var(--r-sm);color:var(--c-primary);font-size:var(--fs-12);font-weight:var(--fw-medium)}
.plan-work{margin-bottom:34px}.plan-route{padding-bottom:22px;border-bottom:1px solid var(--c-border)}.plan-route>header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px}.plan-route h2{margin:0;font-size:var(--fs-16)}.plan-route-actions{display:flex;align-items:center;gap:16px}.plan-route-actions>button,.plan-route-actions :deep(.ws-text-button){min-height:38px;border:0;background:transparent;color:var(--c-primary);font-size:var(--fs-12)}.plan-route-actions>button[aria-pressed=true]{font-weight:var(--fw-medium)}.plan-route nav{overflow-x:auto;scrollbar-width:thin}.plan-route ol{display:grid;min-width:100%;margin:0;padding:0;list-style:none}.plan-route li{position:relative;min-width:0}.plan-route li:not(:last-child)::before{content:"";position:absolute;top:15px;left:30px;width:calc(100% - 30px);height:1px;background:var(--c-border-strong)}.plan-route li>button{position:relative;z-index:1;display:grid;grid-template-columns:30px minmax(0,1fr);gap:10px;width:100%;min-height:66px;padding:0 18px 0 0;border:0;background:transparent;color:var(--c-text);text-align:left}.plan-route-index{display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--c-border-strong);border-radius:50%;background:var(--c-bg);color:var(--c-text-3);font-size:11px;font-variant-numeric:tabular-nums}.plan-route li>button[aria-pressed=true] .plan-route-index{border-color:var(--c-primary);background:var(--c-primary);color:var(--c-on-primary)}.plan-route .is-current .plan-route-index{border-color:var(--c-primary);color:var(--c-primary)}.plan-route .is-done .plan-route-index{border-color:var(--c-done);color:var(--c-done)}.plan-route .is-done>button[aria-pressed=true] .plan-route-index{background:var(--c-done);color:var(--c-on-primary)}.plan-route .is-blocked .plan-route-index{border-color:var(--c-attention);color:var(--c-attention)}.plan-route-copy{display:grid;gap:2px;min-width:0;padding-top:4px}.plan-route-copy strong{justify-self:start;width:max-content;max-width:100%;padding-right:10px;overflow:hidden;background:var(--c-bg);text-overflow:ellipsis;white-space:nowrap;font-size:var(--fs-14);font-weight:var(--fw-medium)}.plan-route-copy small{color:var(--c-text-3);font-size:11px}.plan-route-copy>i{display:none}
.plan-checklist{min-width:0;margin-top:26px}.plan-stage-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding-bottom:16px;border-bottom:1px solid var(--c-border)}.plan-stage-head p{margin:0 0 3px;color:var(--c-primary);font-size:var(--fs-12)}.plan-stage-head h2{margin:0;font-size:var(--fs-20)}.plan-stage-head div>span{display:block;margin-top:5px;color:var(--c-text-3);font-size:var(--fs-12)}.plan-stage-actions{display:flex;align-items:center;gap:14px}.plan-stage-actions>:deep(.detail-trigger){display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 14px;border:1px solid var(--c-primary);border-radius:var(--r-sm);color:var(--c-primary);font-size:var(--fs-12)}.plan-stage-menu{position:relative}.plan-stage-menu>summary{display:inline-flex;align-items:center;min-height:40px;cursor:pointer;color:var(--c-text-2);font-size:var(--fs-12);list-style:none}.plan-stage-menu>summary::-webkit-details-marker{display:none}.plan-stage-menu>summary::after{content:"⌄";margin-left:6px;color:var(--c-text-3)}.plan-stage-menu[open]>summary{color:var(--c-primary)}.plan-stage-menu-panel{position:absolute;top:44px;right:0;z-index:12;display:grid;min-width:176px;padding:7px;border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-surface);box-shadow:var(--e-2)}.plan-stage-menu-panel>a,.plan-stage-menu-panel :deep(.ws-text-button),.plan-stage-menu-panel :deep(.detail-trigger){display:flex;align-items:center;justify-content:flex-start;width:100%;min-height:40px;padding:0 10px;border:0;border-radius:4px;background:transparent;color:var(--c-text-2);font-size:var(--fs-12);text-align:left}.plan-stage-menu-panel>a:hover,.plan-stage-menu-panel :deep(.ws-text-button:hover),.plan-stage-menu-panel :deep(.detail-trigger:hover){background:var(--c-primary-weak);color:var(--c-primary)}
.plan-context{border-bottom:1px solid var(--c-border)}.plan-context>summary{display:flex;align-items:center;min-height:44px;cursor:pointer;color:var(--c-text-3);font-size:var(--fs-12);list-style:none}.plan-context>summary::-webkit-details-marker{display:none}.plan-context>summary::after{content:"＋";margin-left:8px;color:var(--c-primary)}.plan-context[open]>summary::after{content:"－"}.plan-context-body{display:flex;flex-wrap:wrap;gap:16px 24px;padding:0 0 16px}.plan-context-body>section{min-width:180px;max-width:300px}.plan-context h3{margin:0 0 4px;font-size:var(--fs-12)}.plan-context .is-attention h3{color:var(--c-attention)}.plan-context p,.plan-context ul{margin:0;color:var(--c-text-2);font-size:var(--fs-12);line-height:1.65}.plan-context ul{padding-left:17px}
.plan-task-tools{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:12px 0 4px}.plan-task-tools .information-search{flex:1;min-width:190px;margin:0}.plan-task-tools input{border-color:transparent;background:var(--c-bg)}.plan-task-tools input:focus{border-color:var(--c-primary);background:var(--c-surface)}.plan-filters{display:inline-flex;flex-wrap:wrap}.plan-filters button{position:relative;min-height:38px;padding:0 9px;border:0;background:transparent;color:var(--c-text-3);font-size:var(--fs-12)}.plan-filters button::after{content:"";position:absolute;right:9px;bottom:1px;left:9px;height:2px;background:transparent}.plan-filters button[aria-pressed=true]{color:var(--c-primary);font-weight:var(--fw-medium)}.plan-filters button[aria-pressed=true]::after{background:var(--c-primary)}.plan-task-list{border-top:1px solid var(--c-border)}
@media(max-width:700px){.plan-state{align-items:flex-start;flex-direction:column;padding:22px 0}.plan-overview{margin-top:0}.plan-goal{align-items:flex-start;flex-direction:column;gap:14px}.plan-goal h2{font-size:22px}.plan-progress{width:100%;flex-basis:auto}.plan-goal-actions{gap:12px}.plan-focus{grid-template-columns:minmax(0,1fr) auto;gap:8px 14px;padding:15px}.plan-focus-label{grid-column:1}.plan-focus>strong{grid-column:1/-1;grid-row:2}.plan-focus>a{grid-column:2;grid-row:1;min-height:44px}.plan-route>header{align-items:center}.plan-route-actions{gap:10px}.plan-route-actions>button,.plan-route-actions :deep(.ws-text-button){min-height:44px}.plan-route nav{overflow-x:auto;margin-right:-16px;scrollbar-width:thin}.plan-route ol{display:flex;width:max-content}.plan-route li{flex:0 0 158px}.plan-route li>button{padding-right:12px}.plan-stage-head{align-items:flex-start;flex-direction:column;gap:12px}.plan-stage-actions{width:100%;justify-content:space-between}.plan-stage-actions>:deep(.detail-trigger),.plan-stage-menu>summary{min-height:44px}.plan-stage-menu-panel{top:48px;right:0;min-width:184px}.plan-stage-menu-panel>a,.plan-stage-menu-panel :deep(.ws-text-button),.plan-stage-menu-panel :deep(.detail-trigger){min-height:44px}.plan-context>summary{min-height:48px}.plan-context-body{display:block}.plan-context-body>section{max-width:none;margin-bottom:12px}.plan-task-tools{align-items:stretch;padding-top:10px}.plan-task-tools .information-search{flex-basis:100%}.plan-filters{display:grid;grid-template-columns:repeat(5,auto);width:100%;overflow-x:auto}.plan-filters button{min-height:44px;padding:0 8px;white-space:nowrap}.plan-filters button::after{right:8px;left:8px}}
@media(max-width:700px){.plan-empty-path>header{align-items:flex-start;flex-direction:column}.plan-empty-path>header h2{font-size:22px}.plan-empty-path ol{grid-template-columns:1fr}.plan-empty-path li,.plan-empty-path li+li{padding:14px 0;border-left:0;border-bottom:1px solid var(--c-border)}}
@media print{.plan-task-tools,.restored-plan button,.plan-toast{display:none}.plan-overview{border-top-color:var(--c-border)}.plan-route nav{overflow:visible}}
</style>
