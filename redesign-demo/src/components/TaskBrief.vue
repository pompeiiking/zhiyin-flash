<script setup lang="ts">
import { useAiTask } from '../lib/use-ai-task'
import type { BriefToday } from '../api/ai-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
const task=useAiTask<BriefToday>()
</script>
<template><details class="ws-context"><summary>今天先做什么，为什么</summary><button class="btn ws-section" :disabled="task.busy.value" @click="task.run('brief')">{{ task.result.value?'更新今日简报':'生成今日简报' }}</button><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('brief')"/><template v-if="task.result.value"><h3 class="ws-section">{{ task.result.value.data.headline }}</h3><ul class="ws-mini-list"><li v-for="p in task.result.value.data.because" :key="p.text">{{ p.text }}<small>依据：{{ p.from }}</small></li></ul><p v-if="task.result.value.data.ifYouSkip" class="ws-section">{{ task.result.value.data.ifYouSkip }}</p><ul class="ws-mini-list"><li v-for="p in task.result.value.data.next" :key="p.id"><RouterLink class="ws-text-link" :to="'/chat?gap='+encodeURIComponent(p.id)">{{ p.label }}</RouterLink><p>{{ p.why }}</p></li></ul><ul class="ws-mini-list"><li v-for="p in task.result.value.data.changed" :key="p.text">{{ p.text }} · {{ p.at }}</li></ul><AiResultMeta :result="task.result.value"/></template><p v-else class="ws-muted ws-section">根据已有任务、事实和时间安排生成；缺资料时先说明缺口。</p></details></template>
