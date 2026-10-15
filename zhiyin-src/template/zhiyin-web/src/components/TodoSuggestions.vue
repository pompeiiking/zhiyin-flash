<script setup lang="ts">
import { ref } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import type { TodoSuggestion } from '../api/ai-types'
import { backendClient } from '../api/backend-client'
import { backendDemo } from '../lib/backend-demo'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
const task=useAiTask<TodoSuggestion[]>(), decisions=ref<Record<string,string>>({}),saving=ref(''),error=ref('')
async function accept(item: TodoSuggestion){if(saving.value)return;saving.value=item.id;error.value='';try{const note=await backendClient.addNote({kind:'todo',text:item.label});backendDemo.upsertNote(note);decisions.value[item.id]='已添加为个人待办'}catch{error.value='这条建议没有保存成功，请重试；原记录仍保留。'}finally{saving.value=''}}
</script>
<template><details class="ws-context"><summary>查看待办建议</summary><button class="btn ws-section" :disabled="task.busy.value||!!saving" @click="task.run('noteSuggestions')">{{ task.result.value?'更新待办建议':'生成待办建议' }}</button><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('noteSuggestions')"/><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><template v-if="task.result.value"><article v-for="item in task.result.value.data" :key="item.id" class="suggestion-row"><h3>{{ item.label }}</h3><p>{{ item.why }}</p><p class="ws-muted">{{ item.from }} · {{ item.when }}</p><p v-if="decisions[item.id]" role="status">{{ decisions[item.id] }}</p><div v-else class="ws-inline-actions"><button class="btn" :disabled="!!saving" @click="accept(item)">{{ saving===item.id?'正在保存…':'采纳为待办' }}</button><button class="ws-text-button" :disabled="!!saving" @click="decisions[item.id]='本次不采用，个人记录没有改变'">暂不采用</button></div></article><p v-if="!task.result.value.data.length" class="ws-empty">当前没有待办建议。</p><AiResultMeta :result="task.result.value"/></template><p v-else class="ws-muted ws-section">建议与自己写下的记录分开，采纳后才加入个人待办。</p></details></template>
