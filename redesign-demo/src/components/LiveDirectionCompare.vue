<script setup lang="ts">
import { computed, ref, watch, type DeepReadonly } from 'vue'
import InfoSheet from './InfoSheet.vue'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const comparisonOpen=ref(false)
import type { DirectionPlanListView, DirectionPlanView } from '../api/backend-types'
const props = defineProps<{ plans: DeepReadonly<DirectionPlanListView>; saving: boolean; error: string }>()
defineEmits<{ select: [id: string] }>()
const candidate = ref('')
const selected = computed(() => props.plans.selected_id || props.plans.plans?.find(p => p.selected)?.id || '')
watch(selected, id => { candidate.value = id }, { immediate: true })
const invalidSelected = computed(() => !!selected.value&&!props.plans.plans?.some(p=>p.id===selected.value))
const selectedName = computed(() => props.plans.plans?.find(p=>p.id===selected.value)?.name || '此前保存的方向')
const pending = computed(() => props.plans.plans?.find(p => p.id === candidate.value))
const roles = { main: '主攻', parallel: '平行', fallback: '保底' }
const preview=(text:string)=>text.length>110 ? text.slice(0,110)+'…' : text
const criteria = ['方向目标','匹配依据','方向要求','当前情况','补齐建议','主要风险']
function values(plan: DeepReadonly<DirectionPlanView>, criterion: string): readonly string[] {
  if (criterion==='方向目标') return [plan.target_desc || '尚未提供目标说明']
  if (criterion==='匹配依据') return [plan.fit_reason || '尚未提供匹配依据']
  if (criterion==='主要风险') return [plan.main_risk || '尚未提供具体风险，请进一步核对']
  const list = plan.gaps?.map(g => criterion==='方向要求' ? g.requirement : criterion==='当前情况' ? g.current_state || '尚待补充' : g.suggestion || '尚未提供建议') ?? []
  return list.length ? list : ['本次未提供差距明细']
}
</script>
<template><section class="direction-details"><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><p class="direction-current">{{ selected ? '当前方向：'+selectedName : '尚未确认方向。先逐项比较，再作选择。' }}</p><p v-if="invalidSelected" class="asset-notice" role="status">此前选择暂未出现在这次方案中。请重新读取，或比较后选择新的方向；原选择记录仍保留。</p><p v-if="plans.match_score_method" class="ws-muted">匹配判断依据：{{ plans.match_score_method }}</p>
<template v-if="plans.plans?.length"><div class="live-direction-list"><article v-for="plan in plans.plans" :key="plan.id" class="live-direction-row"><div><span class="ws-muted">{{ roles[plan.role] }}{{ selected===plan.id ? ' · 当前方向' : '' }}</span><h2>{{ plan.name }}</h2><p>{{ preview(plan.target_desc || '尚未提供目标说明') }}</p><p class="ws-attention">{{ preview(plan.main_risk || '具体风险有待核对') }}</p><DetailPopover :title="plan.name+' · 匹配依据'" :label="'查看'+plan.name+'匹配依据'"><template #trigger>匹配依据<UiIcon name="info" :size="16"/></template><p>{{ plan.fit_reason || '尚未提供匹配依据' }}</p></DetailPopover></div><label class="direction-radio"><input v-model="candidate" type="radio" name="direction-candidate" :value="plan.id" :disabled="saving"/>{{ selected===plan.id?'当前方向':'作为候选' }}</label></article></div><button class="btn" @click="comparisonOpen=true">逐项核对目标、差距与建议<UiIcon name="arrow" :size="16"/></button><InfoSheet :open="comparisonOpen" shape="panel" title="方向目标、差距与建议" @close="comparisonOpen=false"><div class="compare-desktop local-table-scroll"><table class="fact-table"><caption class="sr-only">最新方向的目标、要求、现状、建议与风险</caption><thead><tr><th scope="col">比较项目</th><th v-for="p in plans.plans" :key="p.id" scope="col"><small>{{ roles[p.role] }}</small>{{ p.name }}</th></tr></thead><tbody><tr v-for="criterion in criteria" :key="criterion"><th scope="row">{{ criterion }}</th><td v-for="p in plans.plans" :key="p.id"><ol :class="{'ws-attention':criterion==='主要风险'}"><li v-for="(v,i) in values(p,criterion)" :key="i">{{ v }}</li></ol></td></tr><tr><th scope="row">候选方向</th><td v-for="p in plans.plans" :key="p.id"><label class="direction-radio"><input v-model="candidate" name="live-direction-desktop" type="radio" :value="p.id" :disabled="saving"/>{{ selected===p.id?'当前方向':'作为候选' }}</label></td></tr></tbody></table></div>
<div class="compare-mobile"><section v-for="criterion in criteria" :key="criterion" class="compare-criterion"><h3>{{ criterion }}</h3><article v-for="p in plans.plans" :key="p.id"><strong>{{ roles[p.role] }} · {{ p.name }}</strong><ol :class="{'ws-attention':criterion==='主要风险'}"><li v-for="(v,i) in values(p,criterion)" :key="i">{{ v }}</li></ol></article></section><fieldset class="ws-field"><legend>候选方向</legend><label v-for="p in plans.plans" :key="p.id" class="direction-radio"><input v-model="candidate" name="live-direction-mobile" type="radio" :value="p.id" :disabled="saving"/>{{ p.name }}{{ selected===p.id?' · 当前方向':'' }}</label></fieldset></div>
</InfoSheet><section class="direction-confirm"><div><h2>{{ pending?.name || '比较后再确认' }}</h2><p>{{ candidate===selected&&selected?'当前选择已确认，仍可调整。':'确认会保存你的方向选择，已有执行记录保留。' }}</p></div><button class="btn btn--primary" :disabled="saving||!candidate||candidate===selected" @click="$emit('select',candidate)">{{ saving?'正在保存…':'确认方向' }}</button></section><p v-if="selected" class="desk-status" role="status">已确认「{{ selectedName }}」。报告和计划的更新状态请分别核对。</p><nav class="ws-related"><RouterLink to="/report?focus=versions">核对报告更新状态</RouterLink><RouterLink to="/plan">查看阶段计划</RouterLink></nav></template><p v-else class="ws-empty">当前尚未取得方向方案。可在咨询中补充必要信息。</p></section></template>
