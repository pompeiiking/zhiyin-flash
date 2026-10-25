<script setup lang="ts">
import { computed } from 'vue'
import type { EvidenceAssessment } from '../api/backend-types'
import { assessmentLabel } from '../lib/evidence-assessment'
import { formatDateTime, studentizeRefs } from '../lib/format'
import { translateFieldKeys } from '../lib/server-copy'
const props = defineProps<{ assessment?: EvidenceAssessment | null; historical?: boolean; snapshot?: boolean; compact?: boolean }>()
const label = computed(() => props.historical ? '报告保存时未评估' : assessmentLabel(props.assessment))
const stale = computed(() => props.assessment?.status === 'stale')
const hasDetails = computed(() => !!props.assessment && (!!props.assessment.reasons?.length || !!props.assessment.assessed_at))
// reasons 等是模型写的说明：新产出口径已要求学生语言，这里兜住存量文本里的
// 内部编号（field:/evidence:/chsi-pdf:// 等）。
const studentText = (value: string) => translateFieldKeys(studentizeRefs(value))
const citedSources = computed(() => (props.assessment?.source_refs ?? [])
  .map(id => props.assessment?.sources?.[id] || id)
  .map(studentText))
</script>
<template>
  <div class="evidence-assessment">
    <p v-if="!compact"><span>把握度：</span><strong>{{ label }}</strong><span v-if="snapshot && !historical" class="snapshot-note">（报告保存时的评估）</span></p>
    <details v-if="hasDetails">
      <summary>查看依据</summary>
      <p v-if="snapshot" class="snapshot-note">这是报告保存时的评估，不是你现在的资料状态。</p>
      <p v-if="stale" class="snapshot-note">以下依据来自资料变化前，结论需要重新评估后才能当作当前判断。</p>
      <p>这是模型对现有证据支持程度的评估，不表示客观准确率或能力水平。</p>
      <p v-if="assessment?.assessed_at">评估于 {{ formatDateTime(assessment.assessed_at) }}</p>
      <ul><li v-for="reason in assessment?.reasons" :key="reason">{{ studentText(reason) }}</li></ul>
      <template v-if="assessment?.missing_evidence?.length"><strong>仍缺少的依据</strong><ul><li v-for="item in assessment.missing_evidence" :key="item">{{ studentText(item) }}</li></ul></template>
      <template v-if="assessment?.contradictions?.length"><strong>需要核对的矛盾</strong><ul><li v-for="item in assessment.contradictions" :key="item">{{ studentText(item) }}</li></ul></template>
      <p v-if="citedSources.length">引用资料：{{ citedSources.join('、') }}</p>
    </details>
  </div>
</template>
<style scoped>
.evidence-assessment { font-size: 13px; color: var(--c-text-2); }
.evidence-assessment p { margin: 6px 0; overflow-wrap: anywhere; }
.evidence-assessment summary { cursor: pointer; min-height: 44px; display: list-item; padding: 11px 0; color: var(--c-primary); }
.evidence-assessment ul { padding-left: 20px; margin: 6px 0; }
.snapshot-note { color: var(--c-text-3); font-size: 12px; }
</style>
