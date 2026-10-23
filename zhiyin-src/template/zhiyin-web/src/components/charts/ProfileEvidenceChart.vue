<script setup lang="ts">
import type { EvidenceAssessment } from '../../api/backend-types'
import { assessmentLabel, assessmentPercent } from '../../lib/evidence-assessment'
import { profileLabel } from '../../lib/server-copy'
import EvidenceAssessmentDetails from '../EvidenceAssessmentDetails.vue'
defineProps<{ title: string; points: Array<{ key: string; label: string; assessment?: EvidenceAssessment }>; snapshot?: boolean }>()
</script>
<template>
  <figure class="profile-evidence-chart">
    <figcaption>{{ title || '这几项你现在各有多少把握' }}</figcaption>
    <div class="scale" aria-hidden="true"><span>0%</span><span>100%</span></div>
    <ul v-if="points.length">
      <li v-for="point in points" :key="point.key">
        <strong>{{ profileLabel(point.key, point.label) }}</strong>
        <template v-if="assessmentPercent(point.assessment) !== null">
          <meter min="0" max="1" :value="point.assessment?.score ?? 0" :aria-label="profileLabel(point.key, point.label) + '把握度'">{{ assessmentPercent(point.assessment) }}</meter>
          <span class="numeric">{{ assessmentPercent(point.assessment) }}</span>
        </template>
        <span v-else class="state">{{ assessmentLabel(point.assessment) }}</span>
        <EvidenceAssessmentDetails :assessment="point.assessment ?? null" :snapshot="snapshot" compact />
      </li>
    </ul>
    <p v-else class="empty">还没有可以展示的资料。</p>
  </figure>
</template>
<style scoped>
.profile-evidence-chart { margin: 12px 0; padding: 16px; border: 1px solid var(--c-border); border-radius: 12px; }
figcaption { font-weight: 600; }
.scale { color: var(--c-text-3); font-size: 12px; margin: 8px 0; }
.scale { display: flex; justify-content: space-between; }
ul { list-style: none; padding: 0; margin: 0; }
li { display: grid; grid-template-columns: minmax(100px, 1fr) minmax(100px, 3fr) auto; gap: 8px 14px; padding: 12px 0; border-top: 1px solid var(--c-border); }
li strong { font-size: 14px; overflow-wrap: anywhere; }
meter { width: 100%; height: 16px; accent-color: var(--c-primary); }
.numeric { font-variant-numeric: tabular-nums; }
.state { grid-column: 2 / -1; color: var(--c-text-3); }
.empty { color: var(--c-text-3); }
li :deep(.evidence-assessment) { grid-column: 1 / -1; }
@media (max-width: 480px) { li { grid-template-columns: minmax(0, 1fr) auto; } li strong { grid-column: 1 / -1; } .state { grid-column: 1 / -1; } }
</style>
