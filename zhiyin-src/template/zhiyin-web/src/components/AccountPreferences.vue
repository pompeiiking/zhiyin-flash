<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {studentApi} from '../api/student-capabilities'
import FormConflict from './FormConflict.vue'
import {rebaseForm,conflictRows} from '../lib/form-conflict'
import type {Preferences} from '../api/backend-types'
const loading=ref(false)
const original=ref<Preferences|null>(null),latest=ref<Preferences|null>(null)
const rows=computed(()=>values.value&&original.value&&latest.value?conflictRows(values.value,original.value,latest.value,{proactive_reminders:'主动提醒',quiet_start:'安静时间开始',quiet_end:'安静时间结束',timezone:'时区',academic_analysis:'学校资料参与分析',material_analysis:'上传材料参与分析'}):[])
async function confirmConflict(){if(!values.value||!original.value||!latest.value)return;values.value=rebaseForm(values.value,original.value,latest.value);original.value=latest.value;latest.value=null;await save()}
const values=ref<Preferences|null>(null),busy=ref(false),error=ref(''),status=ref('')
async function load(){if(loading.value)return;loading.value=true;error.value='';try{values.value=await studentApi.preferences();original.value={...values.value}}catch(e){error.value=(e as Error).message}finally{loading.value=false}}
async function save(){if(!values.value||!original.value||busy.value)return;busy.value=true;error.value='';status.value='';try{values.value=await studentApi.savePreferences({...values.value,expected:original.value,quiet_start:values.value.quiet_start||null,quiet_end:values.value.quiet_end||null});original.value={...values.value};latest.value=null;status.value='偏好已保存，后续提醒与分析请求将按此设置执行。'}catch(e){error.value=(e as Error).message;if((e as {code?:number}).code===1003){try{latest.value=await studentApi.preferences()}catch{error.value+=' 最新记录暂未取得，请稍后重试。'}}}finally{busy.value=false}}
onMounted(load)
</script>
<template><section class="ws-paper"><h2>提醒与资料偏好</h2><p v-if="loading" class="ws-muted" role="status">正在读取已保存的偏好…</p><form v-if="values" class="account-preferences" @submit.prevent="save"><fieldset :disabled="busy"><label><input v-model="values.proactive_reminders" type="checkbox"/>主动提醒</label><label class="ws-field">安静时间开始<input v-model="values.quiet_start" type="time"/></label><label class="ws-field">安静时间结束<input v-model="values.quiet_end" type="time"/></label><p class="ws-muted">按 {{values.timezone}} 执行。清空两个时间可取消安静时段；可跨午夜。</p><label><input v-model="values.academic_analysis" type="checkbox"/>学校资料参与分析</label><label><input v-model="values.material_analysis" type="checkbox"/>上传材料参与分析</label><p class="ws-muted">关闭某一来源后，AI 继续使用本轮对话、本人填写内容和允许的资料；无法确认来源的旧摘要与推导结果不参与本次分析。已保存资料仍可查看、编辑和导出。上传材料关闭时，请移除附件后发送。</p><button class="btn btn--primary" :disabled="busy||latest!==null">{{busy?'正在保存…':'保存偏好'}}</button></fieldset></form><FormConflict v-if="latest" :rows="rows" :busy="busy" @confirm="confirmConflict"/><p v-if="error" role="alert">{{error}}</p><button v-if="!values&&error" class="btn" :disabled="loading" @click="load">重新读取</button><p v-if="status" role="status">{{status}}</p></section></template>
<style scoped>.account-preferences fieldset{display:grid;gap:15px;border:0;padding:0;margin:0;min-width:0}.account-preferences .ws-field{margin-top:0;align-items:stretch}.account-preferences input[type=checkbox]{accent-color:var(--c-primary)}.account-preferences{display:grid;gap:15px;margin-top:16px}.account-preferences label{display:flex;gap:10px;align-items:center}</style>
