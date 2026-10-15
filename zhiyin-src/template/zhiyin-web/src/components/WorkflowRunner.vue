<script setup lang="ts">
import {ref} from 'vue'
import {backendRequest} from '../api/backend-client'
import StructuredFacts from './StructuredFacts.vue'
const id=ref(''),input=ref('{}'),confirm=ref(false),busy=ref(false),error=ref(''),result=ref<Record<string,unknown>|null>(null)
let requestId=''
async function run(){
 if(busy.value)return
 error.value=''
 try{
  if(!id.value.trim())throw new Error('请填写管理员提供的已发布流程编号。')
  const data=JSON.parse(input.value)
  if(!data||Array.isArray(data)||typeof data!=='object')throw new Error('流程参数须为 JSON 对象。')
  busy.value=true;requestId ||= crypto.randomUUID()
  result.value=await backendRequest<Record<string,unknown>>('workflowRun',{params:{workflow_id:id.value.trim()},body:{request_id:requestId,input:data,mode:'live',confirm_actions:confirm.value},timeout:180000})
  requestId=''
 }catch(e){error.value=(e as Error).message}finally{busy.value=false}
}
function changed(){requestId='';result.value=null}
</script>
<template><details class="ws-context"><summary>运行已发布流程</summary><p class="ws-muted">填写管理员提供的流程编号与参数。流程权限仍由系统检查。</p><form @submit.prevent="run"><label class="ws-field">流程编号<input v-model="id" :disabled="busy" @input="changed"/></label><label class="ws-field">流程参数<textarea v-model="input" :disabled="busy" rows="4" @input="changed"/></label><label><input v-model="confirm" type="checkbox" :disabled="busy" @change="changed"/>允许此流程执行写入操作</label><p v-if="error" role="alert" class="ws-field-error">{{error}}</p><button class="btn" :disabled="busy">{{busy?'执行中…':'运行流程'}}</button></form><StructuredFacts v-if="result" :value="result"/></details></template>
