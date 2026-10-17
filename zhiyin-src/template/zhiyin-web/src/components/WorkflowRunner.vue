<script setup lang="ts">
import {computed,ref} from 'vue'
import {backendRequest} from '../api/backend-client'
import {auth} from '../lib/auth'
import StructuredFacts from './StructuredFacts.vue'
/**
 * 运行已发布流程是**管理操作**（流程编号要管理员给，还有"允许写入"开关）。
 * 学生拿不到流程编号，看到表单只会困惑、甚至以为能自行提权（深度测试 D2）。
 * 所以只有开发者/管理员角色才渲染；学生端整块不出现。
 */
const isDeveloper=computed(()=>['admin','developer'].includes(auth.state.bootstrap?.identity?.role??''))
const id=ref(''),input=ref('{}'),confirm=ref(false),busy=ref(false),error=ref(''),result=ref<Record<string,unknown>|null>(null)
let requestId=''
async function run(){
 if(busy.value)return
 error.value=''
 try{
  if(!id.value.trim())throw new Error('请填写管理员提供的已发布流程编号。')
  let data:unknown
  try{data=JSON.parse(input.value)}catch{throw new Error('流程参数不是合法的 JSON，请检查括号、引号和逗号是否成对后重试。')}
  if(!data||Array.isArray(data)||typeof data!=='object')throw new Error('流程参数须为 JSON 对象，例如 {"keyword":"示例"}。')
  busy.value=true;requestId ||= crypto.randomUUID()
  result.value=await backendRequest<Record<string,unknown>>('workflowRun',{params:{workflow_id:id.value.trim()},body:{request_id:requestId,input:data,mode:'live',confirm_actions:confirm.value},timeout:180000})
  requestId=''
 }catch(e){
  const message=(e as Error).message||''
  // 兜底：服务端若仍返回英文解析异常，也不要原样丢给学生。
  error.value=/JSON|Unexpected|position \d+|SyntaxError/i.test(message)&&/Expected|Unexpected|token/i.test(message)
    ? '流程参数不是合法的 JSON，请检查括号、引号和逗号是否成对后重试。'
    : message
 }finally{busy.value=false}
}
function changed(){requestId='';result.value=null}
</script>
<template><details v-if="isDeveloper" class="ws-context"><summary>运行已发布流程（管理员）</summary><p class="ws-muted">填写管理员提供的流程编号与参数。流程权限仍由系统检查。</p><form @submit.prevent="run"><label class="ws-field">流程编号<input v-model="id" :disabled="busy" @input="changed"/></label><label class="ws-field">流程参数<textarea v-model="input" :disabled="busy" rows="4" @input="changed"/></label><label><input v-model="confirm" type="checkbox" :disabled="busy" @change="changed"/>允许此流程执行写入操作</label><p v-if="error" role="alert" class="ws-field-error">{{error}}</p><button class="btn" :disabled="busy">{{busy?'执行中…':'运行流程'}}</button></form><StructuredFacts v-if="result" :value="result"/></details></template>
