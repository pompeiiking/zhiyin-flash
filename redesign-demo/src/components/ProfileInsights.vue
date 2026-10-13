<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { useAiTask } from '../lib/use-ai-task'
import type { PortraitAnalysis, DimensionReading, GapClarify } from '../api/ai-types'
import ReadableText from './ReadableText.vue'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import InfoSheet from './InfoSheet.vue'
const analysis = useAiTask<PortraitAnalysis>(), dimension = useAiTask<DimensionReading>(), gap = useAiTask<GapClarify>()
const analysisSerial=ref(-1)
const stale=computed(()=>!!analysis.result.value&&analysisSerial.value!==backendDemo.state.profileEditSerial)
async function analyze(){const revision=backendDemo.state.profileEditSerial;const result=await analysis.run('portraitAnalysis');if(result)analysisSerial.value=revision}
const detail = ref<{ key: string; label: string; gap: boolean } | null>(null)
function inspect(key: string, label: string, missing = false) {
  dimension.cancel(); gap.cancel(); dimension.result.value = null; gap.result.value = null
  detail.value = { key, label, gap: missing }; void readDetail()
}
function readDetail() { if (detail.value) return detail.value.gap ? gap.run('gap', { params: { gap_key: detail.value.key } }) : dimension.run('dimension', { params: { dimension_id: detail.value.key } }) }
function close() { dimension.cancel(); gap.cancel(); detail.value = null }
defineExpose({ inspect })
</script>
<template>
<section class="profile-insights"><div class="ws-section-head"><h2>整体分析</h2><button class="btn" :disabled="analysis.busy.value" @click="analyze">{{ analysis.result.value ? '更新整体分析' : '分析已有信息' }}</button></div>
<AiStatus :busy="analysis.busy.value" :error="analysis.error.value" :progress="analysis.progress.value" @cancel="analysis.cancel" @retry="analyze"/>
<p v-if="stale" class="asset-notice" role="status">个人信息已更正，这份分析需要重新核对。可更新分析，原结果仍保留。</p><template v-if="analysis.result.value"><h3 class="ws-section">{{ analysis.result.value.data.headline }}</h3><ReadableText :text="analysis.result.value.data.reading"/><div class="analysis-columns"><section v-for="group in [{title:'已有优势',items:analysis.result.value.data.strengths},{title:'需要留意',items:analysis.result.value.data.watchouts},{title:'优先行动',items:analysis.result.value.data.next}]" :key="group.title"><h4>{{ group.title }}</h4><ul class="ws-mini-list"><li v-for="p in group.items" :key="p.label"><strong>{{ p.label }}</strong><p>{{ p.why }}</p></li></ul></section></div><AiResultMeta :result="analysis.result.value"/></template>
<p v-else-if="!analysis.busy.value" class="ws-muted ws-section">把已有信息放在一起看，核对优势、限制和下一步。资料不足时保留待确认项。</p></section>
<InfoSheet :open="detail!==null" :title="detail ? (detail.gap?'补充':'深入了解')+detail.label : '画像详情'" wide @close="close">
<template v-if="detail?.gap"><AiStatus :busy="gap.busy.value" :error="gap.error.value" :progress="gap.progress.value" @cancel="gap.cancel" @retry="readDetail"/><template v-if="gap.result.value"><h3>{{ gap.result.value.data.question }}</h3><p class="ws-section">{{ gap.result.value.data.whyNow }}</p><ul class="ws-mini-list"><li v-for="p in gap.result.value.data.options" :key="p.label"><strong>{{ p.label }}</strong><p>{{ p.why }}</p></li></ul><AiResultMeta :result="gap.result.value"/></template><RouterLink class="btn btn--primary ws-section" :to="'/chat?gap='+encodeURIComponent(detail.key)+'&label='+encodeURIComponent(detail.label)" @click="close">在咨询中补充这项信息</RouterLink></template>
<template v-else><AiStatus :busy="dimension.busy.value" :error="dimension.error.value" :progress="dimension.progress.value" @cancel="dimension.cancel" @retry="readDetail"/><template v-if="dimension.result.value"><h3>{{ dimension.result.value.data.conclusion }}</h3><ReadableText :text="dimension.result.value.data.reading"/><dl v-if="Number.isFinite(dimension.result.value.data.score)" class="analysis-measures"><div><dt>本次评分</dt><dd>{{ dimension.result.value.data.score }}</dd></div><div v-if="dimension.result.value.data.bench"><dt>方向基准</dt><dd>{{ dimension.result.value.data.bench }}</dd></div></dl><ol v-if="dimension.result.value.data.trend?.length" class="ws-mini-list"><li v-for="p in dimension.result.value.data.trend" :key="p.at">{{ p.at }} · {{ p.v }}<p>{{ p.why }}</p></li></ol><p class="ws-section">下一步：{{ dimension.result.value.data.next }}</p><AiResultMeta :result="dimension.result.value"/></template><RouterLink v-if="detail" class="ws-text-link ws-section" :to="'/chat?gap='+encodeURIComponent(detail.key)" @click="close">补充这项信息的依据</RouterLink></template>
</InfoSheet>
</template>
