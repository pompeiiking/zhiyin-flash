<script setup lang="ts">
/*
 * MIGRATION §1.3 A12 / §1.5：本页只保留层折叠 —— 所以这里**不再折**。
 *   ① 生成按钮搬出折叠头：旧写法把按钮放在 `<details>` 体内，用户要先点开折叠才能生成
 *      （Foldable.vue:37-39：动作折叠起来＝用户找不到动作）；
 *   ② 结果也不再折第二次：它是这个动作**刚刚产出**的东西，
 *      折上等于"点了生成还要再点一次才看得到"（DESIGN-LANGUAGE §4.4 完成时没有落点）；
 *   ③ 口径说明（K12：曾经**永远显示**）只在"还没有结果"时出现，有结果后让位给结果；
 *   ④ 进行中给骨架屏（SkeletonBlock inline），不再只把加载态写进按钮文案（P2）。
 */
import { useAiTask } from '../lib/use-ai-task'
import type { TimetablePlan } from '../api/ai-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import SkeletonBlock from './SkeletonBlock.vue'
const task=useAiTask<TimetablePlan>()
</script>
<template><section class="ws-section"><div class="timetable-advice__head"><h2 class="ws-section-title">结合课表安排可投入时间</h2><button class="btn" :disabled="task.busy.value" @click="task.run('timetable')"><SkeletonBlock v-if="task.busy.value" inline variant="text" :lines="1" /><span v-else>{{ task.result.value?'更新时间建议':'生成时间建议' }}</span></button></div><p v-if="!task.result.value" class="ws-muted timetable-advice__hint">空课格不直接代表空闲。结合课程、限制与行为记录核对时间安排。</p><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('timetable')"/><template v-if="task.result.value"><h3 class="ws-section">{{ task.result.value.data.headline }}</h3><ul class="ws-mini-list"><li v-for="p in task.result.value.data.windows" :key="p.day+p.slot"><strong>{{ p.day }} · {{ p.slot }}</strong><p>{{ p.why }}</p></li></ul><ol class="ws-mini-list"><li v-for="p in task.result.value.data.moves" :key="p.at+p.what">{{ p.at }} · {{ p.what }}<p>{{ p.why }}</p></li></ol><p v-if="!task.result.value.data.windows?.length" class="ws-muted">本次没有足够依据给出可投入时间段。</p><AiResultMeta :result="task.result.value"/></template></section></template>

<style scoped>
/* 动作按钮与标题同排：折叠头之外的"明路"，用户不必先展开任何东西才能生成 */
.timetable-advice__head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-4); flex-wrap: wrap; }
.timetable-advice__hint { margin-top: var(--sp-3); }
</style>
