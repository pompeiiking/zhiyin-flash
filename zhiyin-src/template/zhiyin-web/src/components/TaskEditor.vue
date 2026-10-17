<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {localDateTime} from '../lib/form-values.mjs'
import {studentApi} from '../api/student-capabilities'
import type {ActionTaskView,PhaseEdit,TaskEdit,TaskValues} from '../api/backend-types'
import {backendDemo} from '../lib/backend-demo'
import DetailPopover from './DetailPopover.vue'
const props=defineProps<{task?:ActionTaskView;split?:boolean;triggerText?:string;phaseId?:string}>()
const savedId=ref('')
const requestId=ref(''), expectedTask=ref<TaskValues|null>(null)
function snapshot(t:ActionTaskView, phaseId:string):TaskValues { return {text:t.text,phase_id:phaseId,status:t.done?'completed':t.status??'pending',progress:t.done?100:t.progress??0,waiting_reason:t.waiting_reason??'',due_date:t.due_date??null,scheduled_at:t.scheduled_at??null,estimated_minutes:t.estimated_minutes??null,parent_task_id:t.parent_task_id??null} }
const open=ref(false),busy=ref(false),error=ref(''),status=ref('')
const phases=computed(()=>backendDemo.state.liveAction?.phases??[])
const localTime=localDateTime
const text=ref(''),phase=ref(''),state=ref<TaskEdit['status']>('pending'),progress=ref(0),reason=ref(''),due=ref(''),schedule=ref(''),minutes=ref<number|undefined>()
// 没有阶段计划时，"安排新任务"不能是死胡同：在表单里直接建第一个阶段。
const newPhaseName=ref(''),creatingPhase=ref(false)
watch(open,v=>{if(!v)return;savedId.value='';requestId.value=crypto.randomUUID();const t=props.task;text.value=props.split?'':t?.text??'';phase.value=phases.value.find(p=>(p.tasks??[]).some(row=>row.task_id===t?.task_id))?.id??phases.value.find(p=>p.id===props.phaseId)?.id??phases.value[0]?.id??'';state.value=props.split?'pending':t?.done?'completed':t?.status??'pending';progress.value=props.split?0:t?.progress??0;reason.value=props.split?'':t?.waiting_reason??'';due.value=localTime(t?.due_date);schedule.value=props.split?'':localTime(t?.scheduled_at);minutes.value=props.split?undefined:t?.estimated_minutes??undefined;expectedTask.value=t&&!props.split?snapshot(t,phase.value):null;error.value='';status.value='';newPhaseName.value='';creatingPhase.value=false})
watch(state,(value,previous)=>{if(value!=='completed'&&previous==='completed')progress.value=0})
// 新阶段创建成功后，下拉从 0 项变成 1 项：自动选中它，用户不用再点一次。
watch(phases,list=>{if(!phase.value&&list.length)phase.value=list[list.length-1]?.id??''})
async function createPhase(){
  const name=newPhaseName.value.trim()
  if(creatingPhase.value||!name)return
  creatingPhase.value=true;error.value='';status.value=''
  try{
    const payload:PhaseEdit={client_request_id:crypto.randomUUID(),expected_phase:null,name,depends_on:[],starts_at:null,ends_at:null,blocking_conditions:[],handoff_requirements:[]}
    const plan=await studentApi.savePhase(payload)
    backendDemo.setAction(plan)
    const created=(plan.phases??[]).find(p=>p.name===name)
    phase.value=created?.id??(plan.phases??[]).at(-1)?.id??''
    newPhaseName.value=''
    status.value='阶段已创建，可以继续安排任务。'
  }catch(e){error.value=(e as Error).message}
  finally{creatingPhase.value=false}
}
async function save(){if(busy.value)return;busy.value=true;error.value='';status.value='';try{const oldIds=new Set(phases.value.flatMap(p=>(p.tasks??[]).map(t=>t.task_id)));const plan=await studentApi.saveTask({client_request_id:requestId.value,expected_task:expectedTask.value,text:text.value.trim(),phase_id:phase.value,status:state.value,progress:state.value==='completed'?100:progress.value,waiting_reason:reason.value,due_date:due.value?new Date(due.value).toISOString():null,scheduled_at:schedule.value?new Date(schedule.value).toISOString():null,estimated_minutes:minutes.value||null,parent_task_id:props.split?props.task?.task_id:props.task?.parent_task_id},savedId.value||(props.split?undefined:props.task?.task_id));const added=(plan.phases??[]).flatMap(p=>p.tasks??[]).filter(t=>!oldIds.has(t.task_id));savedId.value=savedId.value||(props.split?undefined:props.task?.task_id)||(added.length===1?added[0]?.task_id:'')||'';const currentPhase=(plan.phases??[]).find(p=>(p.tasks??[]).some(t=>t.task_id===savedId.value));const currentTask=currentPhase?.tasks?.find(t=>t.task_id===savedId.value);if(currentTask&&currentPhase)expectedTask.value=snapshot(currentTask,currentPhase.id || phase.value);backendDemo.setAction(plan);status.value='已保存到阶段计划。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template>
  <DetailPopover v-model="open" :label="split?'拆分任务：'+task?.text:task?'编辑与排期：'+task.text:'安排新任务'" :title="split?'拆分任务':task?'编辑任务':'安排新任务'" side="right">
    <template #trigger>{{triggerText || (split?'拆分':task?'编辑与排期':'安排新任务')}}</template>
    <form class="task-editor" @submit.prevent="save">
      <fieldset :disabled="busy">
        <label class="ws-field">任务内容<input v-model="text" required maxlength="500"/></label>
        <div v-if="!phases.length" class="task-editor-phase-empty">
          <p>还没有阶段：先在这里建第一个阶段，任务就能挂到它下面。</p>
          <div class="task-editor-phase-create">
            <label class="ws-field">新阶段名称<input v-model="newPhaseName" maxlength="100" placeholder="例如：完成第一个可演示作品"/></label>
            <button type="button" class="btn" :disabled="creatingPhase||!newPhaseName.trim()" @click="createPhase">{{creatingPhase?'正在创建…':'新建阶段'}}</button>
          </div>
          <p class="task-editor-phase-alt">也可以到 <RouterLink to="/plan">阶段计划</RouterLink> 里创建并安排完整阶段。</p>
        </div>
        <div class="task-editor-pair">
          <label v-if="phases.length" class="ws-field">所属阶段<select v-model="phase" required><option v-for="p in phases" :key="p.id" :value="p.id">{{p.name}}</option></select></label>
          <label class="ws-field">状态<select v-model="state"><option value="pending">待执行</option><option value="in_progress">进行中</option><option value="waiting">等待中</option><option value="completed">已完成</option></select></label>
        </div>
        <label v-if="state==='in_progress'" class="ws-field">进度（%）<input v-model.number="progress" type="number" min="0" max="99"/></label>
        <label v-if="state==='waiting'" class="ws-field">等待原因<input v-model="reason" required maxlength="500"/></label>
        <label class="ws-field">截止时间<input v-model="due" type="datetime-local"/></label>
        <details class="task-editor-schedule" :open="!!task?.scheduled_at||!!task?.estimated_minutes"><summary>开始时间与预计用时{{schedule||minutes?' · 已填写':' · 选填'}}</summary><label class="ws-field">安排开始时间<input v-model="schedule" type="datetime-local"/></label><label class="ws-field">预计用时（分钟）<input v-model.number="minutes" type="number" min="1" max="1440"/></label></details>
        <p v-if="split" class="ws-muted">新任务将保留与原任务的拆分关系，原任务不会自动完成。</p>
        <p v-if="error" role="alert" class="ws-field-error">{{error}}</p>
        <p v-if="status" role="status">{{status}}</p>
        <button class="btn btn--primary" :disabled="busy||!phase">{{busy?'正在保存…':'保存安排'}}</button>
      </fieldset>
    </form>
  </DetailPopover>
</template>
<style scoped>
.task-editor-pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
.task-editor-phase-empty{display:grid;gap:10px;padding:12px;border:1px dashed var(--c-primary-border);border-radius:var(--r-sm);background:var(--c-primary-weak)}
.task-editor-phase-empty p{margin:0;color:var(--c-text-2);font-size:var(--fs-14);line-height:1.6}
.task-editor-phase-create{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:end}
.task-editor-phase-create .btn{min-height:44px;white-space:nowrap}
.task-editor-phase-alt{color:var(--c-text-3)!important;font-size:var(--fs-12)!important}
.task-editor-schedule{border-top:1px solid var(--c-border);padding-top:4px}
.task-editor-schedule summary{cursor:pointer;min-height:44px;display:list-item;align-content:center;color:var(--c-primary)}
.task-editor-schedule .ws-field{margin-bottom:12px}
.task-editor button[type=submit]{width:100%}
.task-editor fieldset{display:grid;gap:12px;border:0;padding:0;margin:0;min-width:0}
.task-editor{display:grid;gap:12px;min-width:230px}
.task-editor input,.task-editor select{max-width:100%}
@media(max-width:600px){.task-editor-pair{grid-template-columns:minmax(0,1fr)}.task-editor-phase-create{grid-template-columns:minmax(0,1fr)}.task-editor{min-width:0}}
</style>
