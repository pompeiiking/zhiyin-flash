<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {dateKey} from '../lib/action-insights.mjs'
import {studentApi} from '../api/student-capabilities'
import {backendDemo} from '../lib/backend-demo'
import InfoSheet from './InfoSheet.vue'
const props=defineProps<{phaseId?:string}>()
const savedId=ref('')
const open=ref(false),name=ref(''),dependencies=ref<string[]>([]),start=ref(''),end=ref(''),blocks=ref(''),handoff=ref(''),busy=ref(false),error=ref(''),status=ref('')
const phases=computed(()=>backendDemo.state.liveAction?.phases??[])
watch(open,v=>{if(!v)return;savedId.value='';const p=phases.value.find(p=>p.id===props.phaseId);name.value=p?.name??'';dependencies.value=[...(p?.depends_on??[])];start.value=dateKey(p?.starts_at);end.value=dateKey(p?.ends_at);blocks.value=p?.blocking_conditions?.join('\n')??'';handoff.value=p?.handoff_requirements?.join('\n')??'';status.value='';error.value=''})
async function save(){if(busy.value)return;error.value='';status.value='';if(start.value&&end.value&&end.value<start.value){error.value='结束日期不能早于开始日期。';return}busy.value=true;try{const oldIds=new Set(phases.value.map(p=>p.id));const plan=await studentApi.savePhase({name:name.value,depends_on:dependencies.value,starts_at:start.value?new Date(start.value+'T00:00').toISOString():null,ends_at:end.value?new Date(end.value+'T23:59').toISOString():null,blocking_conditions:blocks.value.split('\n').filter(Boolean),handoff_requirements:handoff.value.split('\n').filter(Boolean)},savedId.value||props.phaseId);savedId.value=savedId.value||props.phaseId||(plan.phases??[]).find(p=>!oldIds.has(p.id))?.id||'';backendDemo.setAction(plan);status.value='阶段安排已保存。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template>
  <button class="ws-text-button" type="button" @click="open=true">{{phaseId?'编辑阶段与交接':'新增阶段'}}</button>
  <InfoSheet :open="open" shape="panel" :title="phaseId?'编辑阶段与交接':'新增阶段'" @close="open=false">
    <form class="phase-editor" @submit.prevent="save">
      <fieldset :disabled="busy">
        <label class="ws-field">阶段名称<input v-model="name" required maxlength="100"/></label>
        <div class="phase-editor__dates">
          <label class="ws-field">开始日期<input v-model="start" type="date"/></label>
          <label class="ws-field">结束日期<input v-model="end" type="date" :min="start||undefined"/></label>
        </div>
        <fieldset class="phase-editor__dependencies"><legend>需要先完成的阶段</legend>
          <label v-for="p in phases.filter(p=>p.id!==(savedId||phaseId))" :key="p.id"><input v-model="dependencies" type="checkbox" :value="p.id"/>{{p.name}}</label>
          <p v-if="!phases.some(p=>p.id!==(savedId||phaseId))" class="ws-muted">暂无其他阶段，可以独立开始。</p>
        </fieldset>
        <div class="phase-editor__dates">
          <label class="ws-field">阻塞条件<textarea v-model="blocks" rows="3" placeholder="每行一项，没有可留空"/></label>
          <label class="ws-field">交接要求<textarea v-model="handoff" rows="3" placeholder="完成本阶段后需要交付什么，每行一项"/></label>
        </div>
      </fieldset>
      <footer class="phase-editor__footer">
        <p v-if="error" role="alert">{{error}}</p><p v-if="status" role="status">{{status}}</p>
        <div><button type="button" class="btn" @click="open=false">{{status?'完成':'取消'}}</button><button class="btn btn--primary" :disabled="busy">{{busy?'正在保存…':'保存阶段'}}</button></div>
      </footer>
    </form>
  </InfoSheet>
</template>
<style scoped>
.phase-editor{display:grid;gap:20px}.phase-editor fieldset{display:grid;gap:18px;border:0;padding:0;min-width:0}.phase-editor .ws-field{margin:0}.phase-editor__dates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.phase-editor .phase-editor__dependencies{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:16px;background:var(--c-bg);border-radius:var(--r-sm)}.phase-editor__dependencies p{grid-column:1/-1}.phase-editor__dependencies legend{padding:0 0 8px;font-weight:500}.phase-editor__dependencies label{display:flex;align-items:center;gap:8px;min-height:32px}.phase-editor__footer{position:sticky;bottom:-32px;background:var(--c-surface);padding:16px 0;border-top:1px solid var(--c-border);z-index:1}.phase-editor__footer>div{display:flex;justify-content:flex-end;gap:12px}.phase-editor__footer p{margin-bottom:12px}.phase-editor textarea{resize:vertical}@media(max-width:600px){.phase-editor .phase-editor__dependencies{grid-template-columns:1fr}.phase-editor__dates{grid-template-columns:1fr;gap:14px}.phase-editor__footer{bottom:-24px}}
</style>
