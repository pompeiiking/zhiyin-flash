<script setup lang="ts">
import { useAiTask } from '../lib/use-ai-task'
import type { TimetablePlan } from '../api/ai-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
const task=useAiTask<TimetablePlan>()
</script>
<template><details class="ws-context"><summary>结合课表安排可投入时间</summary><p class="ws-muted ws-section">空课格不直接代表空闲。结合课程、限制与行为记录核对时间安排。</p><button class="btn" :disabled="task.busy.value" @click="task.run('timetable')">{{ task.result.value?'更新时间建议':'生成时间建议' }}</button><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('timetable')"/><template v-if="task.result.value"><h3 class="ws-section">{{ task.result.value.data.headline }}</h3><ul class="ws-mini-list"><li v-for="p in task.result.value.data.windows" :key="p.day+p.slot"><strong>{{ p.day }} · {{ p.slot }}</strong><p>{{ p.why }}</p></li></ul><ol class="ws-mini-list"><li v-for="p in task.result.value.data.moves" :key="p.at+p.what">{{ p.at }} · {{ p.what }}<p>{{ p.why }}</p></li></ol><p v-if="!task.result.value.data.windows?.length" class="ws-muted">本次没有足够依据给出可投入时间段。</p><AiResultMeta :result="task.result.value"/></template></details></template>
