<script setup lang="ts">
import { computed, ref, watch, type DeepReadonly } from 'vue'
import DirectionScoring from './DirectionScoring.vue'
import InfoSheet from './InfoSheet.vue'
import {directionRanking} from '../lib/action-insights.mjs'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const comparisonOpen=ref(false),order=ref('original')
import type { DirectionPlanListView, DirectionPlanView } from '../api/backend-types'
const props = defineProps<{ plans: DeepReadonly<DirectionPlanListView>; saving: boolean; error: string }>()
defineEmits<{ select: [id: string] }>()
const ranked=computed(()=>directionRanking(props.plans.plans??[],order.value))
const validScore=(score:unknown):score is number=>typeof score==='number'&&Number.isFinite(score)&&score>=0&&score<=1
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
<template><section class="direction-details"><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="direction-toolbar"><p class="direction-current">{{ selected ? '当前方向：'+selectedName : '尚未确认方向。先逐项比较，再作选择。' }}</p><DetailPopover v-if="plans.match_score_method" title="匹配判断依据"><template #trigger>匹配分如何计算</template><p>{{ plans.match_score_method }}</p></DetailPopover>
<label v-if="plans.plans?.length" class="ws-field direction-order">排列方式<select v-model="order"><option value="original">方案原顺序</option><option value="score">按匹配分排序</option></select></label></div><p v-if="invalidSelected" class="asset-notice" role="status">此前选择暂未出现在这次方案中。请重新读取，或比较后选择新的方向；原选择记录仍保留。</p><template v-if="plans.plans?.length"><div class="live-direction-list"><article v-for="plan in ranked" :key="plan.id" class="live-direction-row" :class="{'is-selected':selected===plan.id,'is-candidate':candidate===plan.id}"><div class="direction-identity"><span class="ws-muted">{{ roles[plan.role] }}{{ selected===plan.id ? ' · 当前方向' : '' }}</span><h2>{{ plan.name }}</h2><div class="restored-score"><template v-if="validScore(plan.match_score)"><strong>{{Math.round(plan.match_score*100)}}<small> / 100 匹配分</small></strong><meter min="0" max="1" :value="plan.match_score" :aria-label="plan.name+'匹配分'"/></template><span v-else class="ws-muted">匹配分未提供</span></div></div><dl class="direction-essentials"><div><dt>目标</dt><dd>{{ preview(plan.target_desc || '尚未提供目标说明') }}</dd></div><div><dt>主要风险</dt><dd class="ws-attention">{{ preview(plan.main_risk || '具体风险有待核对') }}</dd></div></dl><div class="direction-choice"><DetailPopover :title="plan.name+' · 匹配依据'" :label="'查看'+plan.name+'匹配依据'"><template #trigger>匹配依据<UiIcon name="info" :size="16"/></template><p>{{ plan.fit_reason || '尚未提供匹配依据' }}</p></DetailPopover><label class="direction-radio"><input v-model="candidate" type="radio" name="direction-candidate" :value="plan.id" :disabled="saving"/>{{ selected===plan.id?'当前方向':'作为候选' }}</label></div></article></div><button class="btn" @click="comparisonOpen=true">逐项核对目标、差距与建议<UiIcon name="arrow" :size="16"/></button><InfoSheet :open="comparisonOpen" shape="panel" title="方向目标、差距与建议" @close="comparisonOpen=false"><div class="compare-desktop local-table-scroll"><table class="fact-table"><caption class="sr-only">最新方向的目标、要求、现状、建议与风险</caption><thead><tr><th scope="col">比较项目</th><th v-for="p in plans.plans" :key="p.id" scope="col"><small>{{ roles[p.role] }}</small>{{ p.name }}</th></tr></thead><tbody><tr v-for="criterion in criteria" :key="criterion"><th scope="row">{{ criterion }}</th><td v-for="p in plans.plans" :key="p.id"><ol :class="{'ws-attention':criterion==='主要风险'}"><li v-for="(v,i) in values(p,criterion)" :key="i">{{ v }}</li></ol></td></tr><tr><th scope="row">候选方向</th><td v-for="p in plans.plans" :key="p.id"><label class="direction-radio"><input v-model="candidate" name="live-direction-desktop" type="radio" :value="p.id" :disabled="saving"/>{{ selected===p.id?'当前方向':'作为候选' }}</label></td></tr></tbody></table></div>
<div class="compare-mobile"><section v-for="criterion in criteria" :key="criterion" class="compare-criterion"><h3>{{ criterion }}</h3><article v-for="p in plans.plans" :key="p.id"><strong>{{ roles[p.role] }} · {{ p.name }}</strong><ol :class="{'ws-attention':criterion==='主要风险'}"><li v-for="(v,i) in values(p,criterion)" :key="i">{{ v }}</li></ol></article></section><fieldset class="ws-field"><legend>候选方向</legend><label v-for="p in plans.plans" :key="p.id" class="direction-radio"><input v-model="candidate" name="live-direction-mobile" type="radio" :value="p.id" :disabled="saving"/>{{ p.name }}{{ selected===p.id?' · 当前方向':'' }}</label></fieldset></div>
</InfoSheet><section class="direction-confirm"><div><h2>{{ pending?.name || '比较后再确认' }}</h2><p>{{ candidate===selected&&selected?'当前选择已确认，仍可调整。':'确认会保存你的方向选择，已有执行记录保留。' }}</p></div><button class="btn btn--primary" :disabled="saving||!pending||candidate===selected" @click="$emit('select',candidate)">{{ saving?'正在保存…':'确认方向' }}</button></section><p v-if="selected" class="desk-status" role="status">已确认「{{ selectedName }}」。报告和计划的更新状态请分别核对。</p><DirectionScoring/><nav class="ws-related"><RouterLink to="/report?focus=versions">核对报告更新状态</RouterLink><RouterLink to="/plan">查看阶段计划</RouterLink></nav></template><p v-else class="ws-empty">当前尚未取得方向方案。可在咨询中补充必要信息。</p><div class="information-print-only"><h2>方向比较明细</h2><section v-for="p in plans.plans" :key="p.id"><h3>{{p.name}} · {{roles[p.role]}}</h3><section v-for="criterion in criteria" :key="criterion"><h4>{{criterion}}</h4><ul><li v-for="(v,i) in values(p,criterion)" :key="i">{{v}}</li></ul></section></section></div></section></template>
<style scoped>
.direction-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 20px;padding-bottom:16px;border-bottom:1px solid var(--c-border)}
.direction-toolbar .direction-current{flex:1;margin:0;padding:0;border:0;min-width:200px}
.direction-order{display:flex;flex-direction:row;align-items:center;gap:10px;margin:0;font-size:14px}.direction-order select{width:auto}
.direction-details .live-direction-row{display:grid;grid-template-columns:minmax(150px,.8fr) minmax(0,2fr) auto;gap:20px;align-items:center;padding:20px 0}
.direction-details .live-direction-row.is-candidate{padding-left:16px}
.direction-identity h2{margin:4px 0;font-size:20px}.direction-essentials{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:0}
.direction-essentials dt{font-size:13px;color:var(--c-text-3);margin-bottom:6px}.direction-essentials dd{margin:0;line-height:1.7;overflow-wrap:anywhere;font-size:14px}
.direction-choice{display:flex;flex-direction:column;align-items:flex-start;gap:8px}.direction-details .restored-score{margin:8px 0 0;flex-wrap:wrap;gap:6px}
@media(max-width:900px){.direction-details .live-direction-row{grid-template-columns:minmax(0,1fr) auto;gap:12px}.direction-identity{grid-column:1}.direction-essentials{grid-column:1/-1;grid-row:2}.direction-choice{grid-column:2;grid-row:1}.direction-identity h2{font-size:18px}}
@media(max-width:480px){.direction-essentials{grid-template-columns:1fr;gap:12px}.direction-order{width:100%;justify-content:space-between}}
.live-direction-row.is-candidate{border-left:3px solid var(--c-primary);padding-left:16px;background:linear-gradient(90deg,var(--c-primary-weak),transparent 80%)}.live-direction-row h2,.live-direction-row p{overflow-wrap:anywhere}.direction-radio{min-height:44px;cursor:pointer}.restored-direction-tools{gap:16px;align-items:center;margin:20px 0}.restored-score{display:flex;gap:16px;align-items:center;margin:12px 0}.restored-score strong{font-size:24px;color:var(--c-primary)}.restored-score small{font-size:12px;color:var(--c-text-3);font-weight:400}.restored-score meter{width:100px;height:8px;accent-color:var(--c-primary)}.restored-preference{display:flex;flex-wrap:wrap;gap:12px;padding:16px 0;border:0;border-bottom:1px solid var(--c-border)}.restored-preference legend{padding-top:14px;font-weight:600}.restored-preference label{display:flex;align-items:center;gap:6px;min-height:40px}</style>
