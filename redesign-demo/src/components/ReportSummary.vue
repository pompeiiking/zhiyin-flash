<script setup lang="ts">
import { useAiTask } from '../lib/use-ai-task'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
const task=useAiTask<{headline:string;paragraphs:string[];moves:{label:string;why:string}[]}>()
</script>
<template><section><h2>报告要点</h2><button class="btn" :disabled="task.busy.value" @click="task.run('reportSummary')">{{task.result.value?'重新解读':'解读本份报告'}}</button><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('reportSummary')"/><template v-if="task.result.value"><h3>{{task.result.value.data.headline}}</h3><p v-for="p in task.result.value.data.paragraphs" :key="p">{{p}}</p><ul><li v-for="m in task.result.value.data.moves" :key="m.label"><strong>{{m.label}}</strong><p>{{m.why}}</p></li></ul><AiResultMeta :result="task.result.value"/></template></section></template>
