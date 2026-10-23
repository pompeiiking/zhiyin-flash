<script setup lang="ts">
import { computed } from 'vue'
import type { EvidenceAssessment } from '../api/backend-types'
import { assessmentPercent, assessmentStatus } from '../lib/evidence-assessment'
import { formatDateTime } from '../lib/format'
const props = defineProps<{ assessment?: EvidenceAssessment | null; historical?: boolean }>()
const percent = computed(() => props.historical ? null : assessmentPercent(props.assessment))
</script>
<template>
  <div class="evidence-assessment">
    <p><span>把握度：</span><strong>{{ historical ? '当时未评估' : percent ?? assessmentStatus[assessment?.status ?? 'pending'] }}</strong></p>
    <details v-if="!historical && assessment && (assessment.reasons?.length || assessment.assessed_at)">
      <summary>查看依据</summary>
      <p>这是模型对现有证据支持程度的评估，不表示客观准确率或能力水平。</p>
      <p v-if="assessment.assessed_at">评估于 {{ formatDateTime(assessment.assessed_at) }}</p>
      <ul><li v-for="reason in assessment.reasons" :key="reason">{{ reason }}</li></ul>
      <template v-if="assessment.missing_evidence?.length"><strong>仍缺少的依据</strong><ul><li v-for="item in assessment.missing_evidence" :key="item">{{ item }}</li></ul></template>
      <template v-if="assessment.contradictions?.length"><strong>需要核对的矛盾</strong><ul><li v-for="item in assessment.contradictions" :key="item">{{ item }}</li></ul></template>
      <p v-if="assessment.source_refs?.length">引用资料：{{ assessment.source_refs.map(id => assessment?.sources?.[id] || id).join('、') }}</p>
    </details>
  </div>
</template>
<style scoped>
.evidence-assessment { font-size: 13px; color: var(--c-text-2); }
.evidence-assessment p { margin: 6px 0; overflow-wrap: anywhere; }
.evidence-assessment summary { cursor: pointer; min-height: 32px; display: list-item; padding: 6px 0; color: var(--c-primary); }
.evidence-assessment ul { padding-left: 20px; margin: 6px 0; }
</style>
