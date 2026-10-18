<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { studentApi, type Comparison } from '../api/student-capabilities'
import type { DirectionWeights } from '../api/backend-types'
import DetailPopover from './DetailPopover.vue'
import MeasurementPanel from './MeasurementPanel.vue'
import FormConflict from './FormConflict.vue'
import { conflictRows, rebaseForm } from '../lib/form-conflict'

const data = ref<Comparison | null>(null)
const error = ref('')
const loading = ref(false)
const busy = ref(false)
const status = ref('')
const expanded = ref('')
const defaults = () => ({ major: 1, jobs: 1, salary: 1, stability: 1, location: 1 })
const draft = ref<DirectionWeights>(defaults())
const original = ref<DirectionWeights | null>(null)
const latest = ref<DirectionWeights | null>(null)
const id = useId()
const dimensions = [{ key: 'major', label: '专业对口' }, { key: 'jobs', label: '岗位数量' }, { key: 'salary', label: '起薪水平' }, { key: 'stability', label: '稳定性' }, { key: 'location', label: '通勤与地点' }] as const
const allDimensions = [...dimensions, { key: 'opportunity', label: '机会坐标' }, { key: 'feasibility', label: '可达性坐标' }]
const points = computed(() => data.value?.plans.filter(plan => plan.opportunity != null && plan.feasibility != null) ?? [])
const hasScores = computed(() => data.value?.plans.some(plan => plan.score != null) ?? false)
const conflictDetails = computed(() => original.value && latest.value ? conflictRows(
  draft.value,
  original.value,
  latest.value,
  Object.fromEntries(dimensions.map(item => [item.key, item.label])),
) : [])

async function confirmConflict() {
  if (!original.value || !latest.value) return
  draft.value = rebaseForm(draft.value, original.value, latest.value)
  original.value = { ...latest.value }
  latest.value = null
  await save()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await studentApi.compare()
    draft.value = { ...defaults(), ...data.value.weights }
    original.value = { ...data.value.weights }
    latest.value = null
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function save() {
  if (busy.value || loading.value || !data.value) return
  status.value = ''
  error.value = ''
  if (!dimensions.some(dimension => (draft.value[dimension.key] ?? 0) > 0)) {
    error.value = '请至少保留一项大于 0 的权重。'
    return
  }
  busy.value = true
  try {
    const saved = await studentApi.saveWeights({ ...draft.value, expected: { ...(original.value ?? data.value!.weights) } })
    data.value!.weights = saved
    draft.value = { ...saved }
    original.value = { ...saved }
    latest.value = null
    await load()
    status.value = error.value ? '偏好已保存，比较结果暂未更新，请重新读取。' : '偏好已保存，比较结果已更新。'
  } catch (e) {
    error.value = (e as Error).message
    if ((e as { code?: number }).code === 1003) {
      try { latest.value = await studentApi.weights() }
      catch { error.value += ' 最新记录暂未取得，请稍后重试。' }
    }
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="direction-scoring" :aria-busy="loading || busy">
    <header class="scoring-head">
      <div><span class="scoring-eyebrow">辅助决策</span><h2>用你的取舍复核一次</h2><p>只在路线本身仍然难分高下时使用。量化结果帮助发现差异，不替代真实体验。</p></div>
      <div class="scoring-head__actions">
        <DetailPopover v-if="data?.method" title="偏好比较如何计算" label="了解偏好比较方法"><template #trigger>计算说明</template><p>{{ data.method }}</p></DetailPopover>
        <DetailPopover title="调整比较权重" label="调整偏好比较权重">
          <template #trigger>调整权重</template>
          <form class="weight-form" @submit.prevent="save">
            <fieldset :disabled="busy || loading || !data">
              <label v-for="dimension in dimensions" :key="dimension.key" class="ws-field">{{ dimension.label }}<span class="weight-control"><input v-model.number="draft[dimension.key]" type="range" min="0" max="5" step="1" /><output>{{ draft[dimension.key] }}</output></span></label>
            </fieldset>
            <p class="ws-muted">0 表示不计入，至少保留一项；缺少依据的维度不会自动补分。</p>
            <FormConflict v-if="latest" :rows="conflictDetails" :busy="busy" @confirm="confirmConflict" />
            <div class="ws-inline-actions"><button type="button" class="btn" :disabled="busy || loading || !data" @click="draft = defaults(); status = ''">同等权重</button><button class="btn btn--primary" :disabled="busy || loading || !data || latest !== null">{{ busy ? '正在保存…' : '保存并重算' }}</button></div>
          </form>
        </DetailPopover>
      </div>
    </header>

    <p v-if="loading" class="ws-muted" role="status">正在读取偏好与量化依据…</p>
    <p v-if="error" class="ws-field-error" role="alert">{{ error }} <button class="ws-text-button" :disabled="loading || busy" @click="load">重试</button></p>
    <p v-if="status" role="status">{{ status }}</p>

    <template v-if="data">
      <div v-if="data.plans.length && hasScores" class="preference-results" aria-label="个人偏好比较结果">
        <article v-for="plan in data.plans" :key="plan.id"><h3>{{ plan.name }}</h3><strong>{{ plan.score == null ? '—' : Math.round(plan.score * 100) }}</strong><span>{{ plan.score == null ? '偏好依据待补充' : '偏好比较 / 100' }}</span><p v-if="plan.missing.length">缺少 {{ plan.missing.length }} 项依据</p></article>
      </div>
      <div v-else-if="data.plans.length" class="preference-empty" role="status"><span>还不能按偏好排序</span><strong>先补一条最想核对的路线</strong><p>目前缺少专业、岗位、起薪、稳定性或地点依据。无需一次补完，先从最影响你决定的一项开始。</p></div>
      <p v-else class="ws-muted">当前尚无可比较的方向方案。</p>

      <details v-if="data.plans.length" class="scoring-details">
        <summary>补充比较依据</summary>
        <div class="scoring-details__body">
          <div v-if="points.length" class="direction-quadrant" aria-label="方向机会与可达性">
            <span class="quadrant-y">机会 ↑</span><span class="quadrant-x">可达性 →</span>
            <button v-for="point in points" :key="point.id" type="button" class="quadrant-point" :style="{ left: (10 + point.feasibility! * 75) + '%', bottom: (10 + point.opportunity! * 75) + '%' }" :aria-label="point.name+'：查看量化依据'" :aria-expanded="expanded === point.id" :aria-controls="expanded === point.id ? id + point.id : undefined" @click="expanded = expanded === point.id ? '' : point.id">{{ point.name }}</button>
          </div>
          <p v-else class="ws-muted scoring-hint">补齐机会与可达性后，这里会出现象限；现有缺项仍可在下方补充。</p>
          <article v-for="plan in data.plans" :key="plan.id" class="scoring-row">
            <div class="scoring-row__summary"><div><h3>{{ plan.name }}</h3><p v-if="plan.missing.length" class="ws-muted">缺少：{{ plan.missing.map(key => dimensions.find(dimension => dimension.key === key)?.label ?? key).join('、') }}</p></div><button type="button" class="ws-text-button" :aria-expanded="expanded === plan.id" :aria-controls="expanded === plan.id ? id + plan.id : undefined" @click="expanded = expanded === plan.id ? '' : plan.id">{{ expanded === plan.id ? '收起记录' : '核对并补充' }}</button></div>
            <div v-if="expanded === plan.id" :id="id + plan.id" class="scoring-evidence"><MeasurementPanel v-if="data.version != null" asset-type="direction_plan" :version="data.version" :subject-id="plan.id" :dimensions="allDimensions" @saved="load" /><p v-else class="ws-muted">当前方案尚无可记录量表的版本。</p></div>
          </article>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.direction-scoring{min-width:0}.scoring-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:3px 2px 19px;border-bottom:1px solid var(--c-border)}.scoring-eyebrow{display:block;margin-bottom:5px;color:var(--c-primary);font-size:var(--fs-12);font-weight:var(--fw-semibold)}.scoring-head h2{margin:0 0 5px;font-size:var(--fs-20)}.scoring-head p{max-width:620px;color:var(--c-text-2);font-size:var(--fs-14);line-height:1.65}.scoring-head__actions{display:flex;align-items:center;gap:14px;flex:none}.preference-results{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-bottom:1px solid var(--c-border)}.preference-results article{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:baseline;gap:4px 10px;padding:17px 14px;border-right:1px solid var(--c-border)}.preference-results article:first-child{padding-left:0}.preference-results article:last-child{padding-right:0;border-right:0}.preference-results h3{min-width:0;font-size:var(--fs-14);overflow-wrap:anywhere}.preference-results strong{color:var(--c-primary);font-size:var(--fs-20);font-variant-numeric:tabular-nums}.preference-results span{grid-column:1/-1;color:var(--c-text-3);font-size:var(--fs-12)}.preference-results p{grid-column:1/-1;color:var(--c-text-2);font-size:var(--fs-12)}.preference-empty{display:grid;gap:5px;margin:18px 0 2px;padding:20px 22px;border-left:3px solid var(--c-primary);border-radius:0 10px 10px 0;background:var(--c-primary-weak)}.preference-empty>span{color:var(--c-primary);font-size:var(--fs-12);font-weight:var(--fw-semibold)}.preference-empty>strong{font-size:var(--fs-16)}.preference-empty>p{max-width:680px;color:var(--c-text-2);font-size:var(--fs-13);line-height:1.65}.scoring-details{margin-top:6px;border-bottom:1px solid var(--c-border)}.scoring-details>summary{min-height:48px;padding:14px 0;color:var(--c-text-2);font-weight:var(--fw-semibold);cursor:pointer}.scoring-details__body{padding-top:4px}.scoring-row{padding:14px 0;border-bottom:1px solid var(--c-border)}.scoring-row__summary{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.scoring-row h3{font-size:var(--fs-14);overflow-wrap:anywhere}.scoring-row p{margin-top:4px;font-size:var(--fs-12)}.scoring-evidence{margin-top:12px;padding-left:16px;border-left:2px solid var(--c-border)}.weight-form,.weight-form fieldset{display:grid;gap:14px}.weight-form fieldset{min-width:0;margin:0;padding:0;border:0}.weight-control{display:flex;align-items:center;gap:16px}.weight-control output{min-width:2ch;color:var(--c-primary);font-variant-numeric:tabular-nums}.direction-quadrant{position:relative;height:220px;margin:12px 0 18px;border-left:1px solid var(--c-border);border-bottom:1px solid var(--c-border);background:linear-gradient(90deg,transparent 49.8%,var(--c-border) 50%,transparent 50.2%),linear-gradient(transparent 49.8%,var(--c-border) 50%,transparent 50.2%)}.quadrant-point{position:absolute;max-width:38%;padding:8px 10px;transform:translateX(-50%);border:1px solid var(--c-border);border-radius:8px;background:var(--c-primary-weak);color:var(--c-primary);font-size:var(--fs-12);overflow-wrap:anywhere;cursor:pointer}.quadrant-point:hover,.quadrant-point[aria-expanded=true]{border-color:var(--c-primary)}.quadrant-y{position:absolute;top:0;left:4px}.quadrant-x{position:absolute;right:0;bottom:0}.scoring-hint{margin:8px 0 12px}
@media(max-width:700px){.scoring-head{display:grid}.scoring-head__actions{justify-content:flex-start}.preference-results{grid-template-columns:1fr}.preference-results article{padding:12px 0;border-right:0;border-bottom:1px solid var(--c-border)}.preference-results article:last-child{border-bottom:0}.preference-empty{padding:17px 18px}.scoring-evidence{padding-left:10px}}
</style>
