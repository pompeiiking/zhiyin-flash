<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {dateKey} from '../lib/action-insights.mjs'
import {studentApi} from '../api/student-capabilities'
import {backendDemo} from '../lib/backend-demo'
import DetailPopover from './DetailPopover.vue'
const props=defineProps<{phaseId?:string}>()
const savedId=ref('')
const open=ref(false),name=ref(''),dependencies=ref<string[]>([]),start=ref(''),end=ref(''),blocks=ref(''),handoff=ref(''),busy=ref(false),error=ref(''),status=ref('')
const phases=computed(()=>backendDemo.state.liveAction?.phases??[])
watch(open,v=>{if(!v)return;savedId.value='';const p=phases.value.find(p=>p.id===props.phaseId);name.value=p?.name??'';dependencies.value=[...(p?.depends_on??[])];start.value=dateKey(p?.starts_at);end.value=dateKey(p?.ends_at);blocks.value=p?.blocking_conditions?.join('\n')??'';handoff.value=p?.handoff_requirements?.join('\n')??'';status.value='';error.value=''})
async function save(){if(busy.value)return;error.value='';status.value='';if(start.value&&end.value&&end.value<start.value){error.value='结束日期不能早于开始日期。';return}busy.value=true;try{const oldIds=new Set(phases.value.map(p=>p.id));const plan=await studentApi.savePhase({name:name.value,depends_on:dependencies.value,starts_at:start.value?new Date(start.value+'T00:00').toISOString():null,ends_at:end.value?new Date(end.value+'T23:59').toISOString():null,blocking_conditions:blocks.value.split('\n').filter(Boolean),handoff_requirements:handoff.value.split('\n').filter(Boolean)},savedId.value||props.phaseId);savedId.value=savedId.value||props.phaseId||(plan.phases??[]).find(p=>!oldIds.has(p.id))?.id||'';backendDemo.setAction(plan);status.value='阶段安排已保存。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template><DetailPopover v-model="open" :label="phaseId?'编辑阶段与交接':'新增阶段'" :title="phaseId?'编辑阶段':'新增阶段'" side="right"><template #trigger>{{phaseId?'编辑阶段与交接':'新增阶段'}}</template><form class="phase-editor" @submit.prevent="save"><fieldset :disabled="busy"><label class="ws-field">阶段名称<input v-model="name" required maxlength="100"/></label><fieldset><legend>需要先完成的阶段</legend><label v-for="p in phases.filter(p=>p.id!==(savedId||phaseId))" :key="p.id"><input v-model="dependencies" type="checkbox" :value="p.id"/>{{p.name}}</label></fieldset><label class="ws-field">开始日期<input v-model="start" type="date"/></label><label class="ws-field">结束日期<input v-model="end" type="date" :min="start||undefined"/></label><label class="ws-field">阻塞条件（每行一项）<textarea v-model="blocks"/></label><label class="ws-field">交接要求（每行一项）<textarea v-model="handoff"/></label><p v-if="error" role="alert">{{error}}</p><p v-if="status" role="status">{{status}}</p><button class="btn btn--primary" :disabled="busy">{{busy?'正在保存…':'保存阶段'}}</button></fieldset></form></DetailPopover></template>
<style scoped>.phase-editor{display:grid;gap:12px;min-width:230px}.phase-editor fieldset{display:grid;gap:8px;border:0;padding:0}</style>
