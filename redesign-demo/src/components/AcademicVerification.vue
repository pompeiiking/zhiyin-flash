<script setup lang="ts">
import { ref } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import type { BindResult } from '../api/ai-types'
import { backendClient } from '../api/backend-client'
import { backendDemo } from '../lib/backend-demo'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import StatusBanner from './StatusBanner.vue'
const code=ref(''),validation=ref(''),status=ref(''),task=useAiTask<BindResult>(),reading=ref(false)
const serviceVerified=ref(false)
defineEmits<{ sample: [] }>()
async function loadWorkspace(){if(reading.value)return;reading.value=true;status.value='';const verified=serviceVerified.value&&backendDemo.state.dataMode==='service';try{const result=await backendClient.workspace();backendDemo.setWorkspace(result);status.value=verified?'已读取核验后的个人资料。':'已读取当前学校资料。'}catch{status.value=verified?'核验结果已取得，但最新档案暂时没有读取成功。原内容仍保留，可重试读取。':'当前学校资料没有读取成功。原内容仍保留，可重试读取。'}finally{reading.value=false}}
async function verify(){validation.value='';serviceVerified.value=false;if(!code.value.trim()){validation.value='请填写在线验证码。';return}const result=await task.run('chsi',{arg:code.value.trim()});if(result){serviceVerified.value=true;result.data.lifted.forEach(p=>backendDemo.markProfileChange(p.dim));code.value='';await loadWorkspace()}}
</script>
<template><div><p class="ws-muted">仅需学信网在线验证码，无需账号密码。仅在你点击核验后提交验证码。</p><form @submit.prevent="verify"><label class="ws-field">在线验证码<input v-model="code" autocomplete="off" maxlength="80" placeholder="输入本次申请的在线验证码"/></label><p v-if="validation" class="ws-field-error" role="alert">{{ validation }}</p><button class="btn btn--primary" :disabled="task.busy.value||reading" type="submit">{{ task.busy.value?'正在核验…':'核验并更新资料' }}</button><a class="ws-text-link ws-section" href="https://www.chsi.com.cn/" target="_blank" rel="noopener noreferrer">去学信网获取验证码</a></form><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="verify"/><p v-if="task.error.value" class="ws-muted">验证码已失效或过期时，请重新申请；服务不可用时可稍后重试，原资料和输入保留。</p><template v-if="task.result.value"><ol class="ws-mini-list"><li v-for="step in task.result.value.data.steps" :key="step.id"><strong>{{ step.label }}</strong><p>{{ step.detail }}</p><p class="ws-muted">{{ step.source }}<span v-if="step.got"> · {{ step.got }} 条资料</span></p></li></ol><ul class="ws-mini-list"><li v-for="p in task.result.value.data.lifted" :key="p.dim">{{ p.because }}</li></ul><AiResultMeta :result="task.result.value"/><StatusBanner v-if="status" tone="success" size="sm" class="ws-section" :message="status" @dismiss="status = ''" /><button class="btn ws-section" :disabled="reading" @click="loadWorkspace">{{ reading?'正在读取…':serviceVerified?'读取更新后的资料':'读取当前资料' }}</button></template></div></template>
