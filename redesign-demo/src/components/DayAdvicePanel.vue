<script setup lang="ts">
import { watch } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import type { DayAdvice } from '../api/ai-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import ReadableText from './ReadableText.vue'
const props=defineProps<{ date: string }>(),task=useAiTask<DayAdvice>()
function load(){return task.run('dayAdvice',{params:{day:props.date},arg:-new Date().getTimezoneOffset()})}
watch(()=>props.date,()=>{task.cancel();task.result.value=null;void load()},{immediate:true})
</script>
<template><section class="ws-section"><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="load"/><template v-if="task.result.value"><h4>{{ task.result.value.data.headline }}</h4><p class="ws-muted">{{ task.result.value.data.date }}</p><ReadableText :text="task.result.value.data.reading"/><ul class="ws-mini-list"><li v-for="p in task.result.value.data.plan" :key="p.label"><strong>{{ p.label }}</strong><p>{{ p.why }}</p></li></ul><p class="ws-attention">{{ task.result.value.data.watch }}</p><AiResultMeta :result="task.result.value"/></template></section></template>
