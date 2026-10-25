<script setup lang="ts">
/*
 * ProfileInsights —— 「整体分析」+ 从一行信息钻进去看的详情弹层。
 *
 * 对应 MIGRATION：
 *   · §2.2 第 17 条 / §2.3：详情弹层现在是 `wide`（→ `panel`：桌面居中宽盒、小屏**全屏**），
 *     **语义用错了**。它是"从一行信息就地钻进去看细节"的检查器（与 `ConversationView:830`
 *     同类），内容长、含流式 AI 结果与底部固定跳转按钮 → `shape="sheet"`（桌面右侧抽屉、
 *     小屏底部面板）。`wide` 会把小屏变成全屏，丢掉"从哪来的"空间关系。
 *     注意 `InfoSheet.vue:54-58` 的 `resolvedShape` 里 `wide` 优先于 `shape`，
 *     所以这里**必须同时去掉 `wide`**，否则 `shape` 会被静默覆盖。
 *   · §4.3 B13 / §3.4 G4e：`<p v-if="stale" class="asset-notice">` 只是"说了一句"，
 *     没有任何动作位 → `StatusBanner tone="warning"` + `actionLabel="更新分析"` + `@action="analyze"`。
 *     `warning` 只能手动关（StatusBanner 的口径），因为"这份分析要重新核对"是一个**状态**，
 *     不该 4 秒后自己溜走。
 *   · §4.1 K10：`<p v-else-if="!analysis.busy.value" class="ws-muted ws-section">` 是
 *     "静态说明句当首屏正文" → `EmptyState`（说明 + 一个真的能按的动作）。
 *   · §3.2 S10：`<AiResultMeta>` 在弹层里 —— 弹层本身已经是一层，所以内部的
 *     `Foldable` 用 `inline`（`AiResultMeta` 自己就是这么写的），不叠加第二层。
 */
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { useAiTask } from '../lib/use-ai-task'
import type { PortraitAnalysis, DimensionReading, GapClarify } from '../api/ai-types'
import ReadableText from './ReadableText.vue'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import EmptyState from './EmptyState.vue'
import InfoSheet from './InfoSheet.vue'
import StatusBanner from './StatusBanner.vue'
import { studentVoice } from '../lib/student-voice'
import { studentizeRefs, visibleEvidence } from '../lib/format'
import { translateFieldKeys } from '../lib/server-copy'
const analysis = useAiTask<PortraitAnalysis>(), dimension = useAiTask<DimensionReading>(), gap = useAiTask<GapClarify>()
const analysisSerial=ref(-1)
const stale=computed(()=>!!analysis.result.value&&analysisSerial.value!==backendDemo.state.profileEditSerial)
async function analyze(){const revision=backendDemo.state.profileEditSerial;const result=await analysis.run('portraitAnalysis');if(result)analysisSerial.value=revision}
type Detail = {
  key: string
  label: string
  gap: boolean
  /** report/gapLocal 直接展示已有事实，不再去请求只接受画像字段/真实缺口的接口。 */
  mode?: 'report' | 'gapLocal'
  full?: string
  evidence?: string[]
  why?: string
  next?: string
  ask?: string
}
const detail = ref<Detail | null>(null)
function inspect(key: string, label: string, missing = false) {
  dimension.cancel(); gap.cancel(); dimension.result.value = null; gap.result.value = null
  detail.value = { key, label, gap: missing }; void readDetail()
}
/** 报告维度不是画像字段：用它自己已有的结论和依据展开，避免发给 /app/dimensions 造成 404。 */
function inspectReport(full: string, label: string, evidence: string[] = []) {
  dimension.cancel(); gap.cancel(); dimension.result.value = null; gap.result.value = null
  detail.value = { key: '', label, gap: false, mode: 'report', full, evidence }
}
/** 采集清单里的缺口不一定在 profile.gaps 中；直接展示策略层已经给出的解释。 */
function inspectGap(key: string, label: string, note: { why?: string; next?: string; ask?: string }) {
  dimension.cancel(); gap.cancel(); dimension.result.value = null; gap.result.value = null
  detail.value = { key, label, gap: true, mode: 'gapLocal', ...note }
}
function readDetail() {
  if (!detail.value || detail.value.mode) return
  return detail.value.gap
    ? gap.run('gap', { params: { gap_key: detail.value.key } })
    : dimension.run('dimension', { params: { dimension_id: detail.value.key } })
}
function close() { dimension.cancel(); gap.cancel(); detail.value = null }
defineExpose({ inspect, inspectReport, inspectGap })
</script>
<template>
<section class="profile-insights"><div class="ws-section-head"><h2>整体分析</h2><button v-if="analysis.result.value" class="btn" :disabled="analysis.busy.value" @click="analyze">重新分析</button></div>
<AiStatus :busy="analysis.busy.value" :error="analysis.error.value" :progress="analysis.progress.value" @cancel="analysis.cancel" @retry="analyze"/>
<StatusBanner v-if="stale && analysis.result.value" class="ws-section" tone="warning" message="个人信息已更正，这份分析需要重新核对。可重新分析，原结果仍保留。" action-label="重新分析" @action="analyze"/><template v-if="analysis.result.value"><h3 class="ws-section">{{ studentVoice(analysis.result.value.data.headline) }}</h3><ReadableText :text="studentVoice(analysis.result.value.data.reading)"/><div class="analysis-columns"><section v-for="group in [{title:'已有优势',items:analysis.result.value.data.strengths},{title:'需要留意',items:analysis.result.value.data.watchouts},{title:'优先行动',items:analysis.result.value.data.next}]" :key="group.title"><h4>{{ group.title }}</h4><ul class="ws-mini-list"><li v-for="p in group.items" :key="p.label"><strong>{{ studentVoice(p.label) }}</strong><p>{{ studentVoice(p.why) }}</p></li></ul></section></div><AiResultMeta :result="analysis.result.value"/></template>
<EmptyState v-else-if="!analysis.busy.value" kind="profile" size="sm" title="还没有整体分析" description="把已有信息放在一起看，核对优势、限制和下一步；资料不足时保留待确认项。" :next="false"><button class="btn btn--primary" @click="analyze">分析已有信息</button></EmptyState></section>
<!-- Details can open while the overview dialog is closed. Keep them outside that hidden ancestor. -->
<Teleport to="body"><InfoSheet :open="detail!==null" shape="sheet" :title="detail ? (detail.gap?'补充':'深入了解')+detail.label : '画像详情'" @close="close">
<template v-if="detail?.gap">
  <template v-if="detail.mode === 'gapLocal'">
    <h3>{{ detail.label }}</h3>
    <p v-if="detail.why" class="ws-section">{{ detail.why }}</p>
    <p v-if="detail.next" class="ws-section">下一步：{{ detail.next }}</p>
    <p v-if="detail.ask" class="ws-section">可以直接回答：{{ detail.ask }}</p>
    <RouterLink class="btn btn--primary ws-section" :to="'/chat?gap='+encodeURIComponent(detail.key)+'&label='+encodeURIComponent(detail.label)" @click="close">在咨询中补充这项信息</RouterLink>
  </template>
  <template v-else>
    <AiStatus :busy="gap.busy.value" :error="gap.error.value" :progress="gap.progress.value" @cancel="gap.cancel" @retry="readDetail"/><template v-if="gap.result.value"><h3>{{ studentVoice(gap.result.value.data.question) }}</h3><p class="ws-section">{{ studentVoice(gap.result.value.data.whyNow) }}</p><ul class="ws-mini-list"><li v-for="p in gap.result.value.data.options" :key="p.label"><strong>{{ studentVoice(p.label) }}</strong><p>{{ studentVoice(p.why) }}</p></li></ul><AiResultMeta :result="gap.result.value"/></template><RouterLink class="btn btn--primary ws-section" :to="'/chat?gap='+encodeURIComponent(detail.key)+'&label='+encodeURIComponent(detail.label)" @click="close">在咨询中补充这项信息</RouterLink>
  </template>
</template>
<template v-else>
  <template v-if="detail?.mode === 'report'">
    <ReadableText v-if="detail.full" :text="studentVoice(detail.full)"/>
    <p v-if="visibleEvidence(detail.evidence).length" class="ws-section"><strong>这条判断引用的原材料</strong></p>
    <ul v-if="visibleEvidence(detail.evidence).length" class="ws-mini-list"><li v-for="line in visibleEvidence(detail.evidence)" :key="line">{{ translateFieldKeys(studentizeRefs(line)) }}</li></ul>
    <p v-else class="ws-muted">这条判断目前没有附原材料，可回到画像或对话继续核对。</p>
  </template>
  <template v-else>
    <AiStatus :busy="dimension.busy.value" :error="dimension.error.value" :progress="dimension.progress.value" @cancel="dimension.cancel" @retry="readDetail"/><template v-if="dimension.result.value"><h3>{{ studentVoice(dimension.result.value.data.conclusion) }}</h3><ReadableText :text="studentVoice(dimension.result.value.data.reading)"/><dl v-if="Number.isFinite(dimension.result.value.data.score)" class="analysis-measures"><div><dt>本次评分</dt><dd>{{ dimension.result.value.data.score }}</dd></div><div v-if="dimension.result.value.data.bench"><dt>方向基准</dt><dd>{{ dimension.result.value.data.bench }}</dd></div></dl><ol v-if="dimension.result.value.data.trend?.length" class="ws-mini-list"><li v-for="p in dimension.result.value.data.trend" :key="p.at">{{ p.at }} · {{ p.v }}<p>{{ studentVoice(p.why) }}</p></li></ol><p class="ws-section">下一步：{{ studentVoice(dimension.result.value.data.next) }}</p><AiResultMeta :result="dimension.result.value"/></template>
  </template>
  <RouterLink v-if="detail && detail.mode !== 'report'" class="ws-text-link ws-section" :to="'/chat?gap='+encodeURIComponent(detail.key)+'&label='+encodeURIComponent(detail.label)" @click="close">补充这项信息的依据</RouterLink>
</template>
</InfoSheet></Teleport>
</template>
