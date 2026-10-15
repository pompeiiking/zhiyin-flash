<script setup lang="ts">
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
import { computed, ref } from 'vue'
import InfoSheet from './InfoSheet.vue'
const compareOpen=ref(false), prioritiesOpen=ref(false)
import type { DirectionPlan } from '../data/types'
import { directionCriteria as criteria, directionPriorities as weights } from '../lib/direction-comparison'
const props = defineProps<{ items: readonly DirectionPlan[]; selectedId?: string }>()
defineEmits<{ pick: [id: string] }>()
const roleIndex = (item:DirectionPlan) => item.role==='主攻'?0:item.role==='平行'?1:2
const ranking = computed(()=>{
 const total=criteria.reduce((n,c)=>n+weights[c.key]!,0)
 return props.items.map(item=>({item,score:Math.round(criteria.reduce((n,c)=>n+c.scores[roleIndex(item)]!*weights[c.key]!,0)/total)})).sort((a,b)=>b.score-a.score)
})
const rankText = computed(()=>ranking.value.map(e=>`${e.item.title} ${e.score}`).join(' > '))
const strongest = computed(()=>criteria.filter(c=>weights[c.key]===Math.max(...Object.values(weights))).map(c=>c.label).join('、'))
const importanceOptions = [{value:1,label:'低'},{value:2,label:'较低'},{value:3,label:'适中'},{value:4,label:'较高'},{value:5,label:'高'}]
function reset(){criteria.forEach(c=>{weights[c.key]=3})}
</script>
<template>
 <div class="c2-compare">
<div class="direction-reading-actions"><button class="btn" @click="compareOpen=true">逐项比较方向<UiIcon name="directions" :size="16"/></button><button class="btn" @click="prioritiesOpen=true">调整选择偏好<UiIcon name="settings" :size="16"/></button><DetailPopover title="当前选择偏好" label="查看当前选择偏好"><p>优先考虑：{{ strongest }}</p><p>比较分用于同一批方向之间的排序，不代表就业概率。</p></DetailPopover></div>
<div class="c2-ranked-directions direction-choice-list"><article v-for="entry in ranking" :key="entry.item.id" class="c2-ranked-direction direction-option" :class="{'c2-ranked-direction--picked':selectedId===entry.item.id}">
 <header class="direction-option__head"><span class="direction-option__symbol"><UiIcon :name="entry.item.role==='主攻'?'cpu':entry.item.role==='平行'?'battery':'flask'" :size="25"/></span><div><span class="direction-option__role">{{ entry.item.role }}</span><h2>{{ entry.item.title }}</h2></div><div class="direction-option__score"><strong>{{ entry.score }}</strong><small>比较分</small></div></header>
 <div class="direction-signals" aria-label="主要比较项"><div v-for="criterion in criteria.filter(c=>['major','pay','stable'].includes(c.key))" :key="criterion.key"><span>{{ criterion.label }}<b>{{ criterion.scores[roleIndex(entry.item)] }}</b></span><span class="direction-signal-track"><i :style="{width:criterion.scores[roleIndex(entry.item)]+'%'}"/></span></div></div>
 <p class="direction-option__risk"><UiIcon name="info" :size="15"/><span>{{ entry.item.risk }}</span></p>
 <div class="direction-option__actions"><button class="btn" :class="{'btn--primary':selectedId===entry.item.id}" :aria-pressed="selectedId===entry.item.id" @click="$emit('pick',entry.item.id)">{{ selectedId===entry.item.id?'当前候选':'选择这个方向' }}<UiIcon v-if="selectedId===entry.item.id" name="check" :size="16"/></button><DetailPopover :title="entry.item.title + ' · 支持依据'" :label="'查看' + entry.item.title + '支持依据'"><template #trigger>支持依据<UiIcon name="info" :size="16"/></template><ul><li v-for="e in entry.item.evidence" :key="e">{{ e }}</li></ul></DetailPopover></div>
</article></div>
  <InfoSheet :open="compareOpen" shape="panel" title="逐项比较方向" @close="compareOpen=false">  <section class="c2-compare-section" aria-labelledby="c2-comparison-title">
   <header class="c2-compare-head"><h2 id="c2-comparison-title">方向对比</h2><span>5 项</span></header>
   <DetailPopover title="比较与排序说明" label="查看比较与排序说明"><template #trigger>评分与排序说明<UiIcon name="info" :size="16"/></template><p>各项采用 0–100 的比较刻度。排序分为各项评分按考虑程度加权的平均值，用于辅助比较，确认方向仍由你决定。</p></DetailPopover>
   <div class="c2-rank-reading" role="status" aria-live="polite"><strong>当前排序：{{ rankText }}</strong><p>当前优先考虑：{{ strongest }}</p></div>
   <div class="c2-score-scroll" tabindex="0" aria-label="三个方向的同刻度比较，窄屏可横向滚动">
    <table class="c2-score-table"><caption>三个方向 × 五个比较项 · 同一刻度 0–100 · 每行标出最高和最低</caption>
     <thead><tr><th scope="col">比较项</th><th v-for="item in items" :key="item.id" scope="col">{{ item.title }} <small>{{ item.role }}</small></th></tr></thead>
     <tbody><tr v-for="criterion in criteria" :key="criterion.key"><th scope="row">{{ criterion.label }}</th><td v-for="item in items" :key="item.id"><strong>{{ criterion.scores[roleIndex(item)] }}</strong><div class="c2-score-track"><i :style="{width:criterion.scores[roleIndex(item)]+'%'}" :class="{'c2-score-high':criterion.scores[roleIndex(item)]===Math.max(...criterion.scores),'c2-score-low':criterion.scores[roleIndex(item)]===Math.min(...criterion.scores)}" /></div><small>{{ criterion.scores[roleIndex(item)]===Math.max(...criterion.scores)?'最高':criterion.scores[roleIndex(item)]===Math.min(...criterion.scores)?'最低':'—' }}</small></td></tr></tbody>
    </table>
   </div><div class="direction-mobile-comparison"><section v-for="criterion in criteria" :key="criterion.key"><h3>{{ criterion.label }}</h3><div v-for="item in items" :key="item.id"><span>{{ item.title }}</span><strong>{{ criterion.scores[roleIndex(item)] }}</strong></div></section></div>
  </section>
</InfoSheet>
  <InfoSheet :open="prioritiesOpen" shape="panel" title="调整选择偏好" @close="prioritiesOpen=false">  <section class="c2-compare-section" aria-labelledby="c2-weights-title"><header class="c2-compare-head"><h2 id="c2-weights-title">调整考虑因素</h2><button class="btn btn--sm" @click="reset">恢复同等权重</button></header>
   <div class="c2-weight-list importance-choices"><fieldset v-for="criterion in criteria" :key="criterion.key"><legend>{{ criterion.label }}的重要程度</legend><div class="importance-options"><label v-for="option in importanceOptions" :key="option.value"><input v-model.number="weights[criterion.key]" type="radio" :name="'importance-' + criterion.key" :value="option.value"/><span>{{ option.label }}</span></label></div></fieldset></div><p class="c2-compare-note">选择每项因素的重要程度。调整只影响比较排序，不会替你确认方向。</p>
  </section>
</InfoSheet>
  <div class="information-print-only">  <section class="c2-compare-section" aria-labelledby="print-comparison-title">
   <header class="c2-compare-head"><h2 id="print-comparison-title">方向对比</h2><span>5 项</span></header>
   <DetailPopover title="比较与排序说明" label="查看比较与排序说明"><template #trigger>评分与排序说明<UiIcon name="info" :size="16"/></template><p>各项采用 0–100 的比较刻度。排序分为各项评分按考虑程度加权的平均值，用于辅助比较，确认方向仍由你决定。</p></DetailPopover>
   <div class="c2-rank-reading" role="status" aria-live="polite"><strong>当前排序：{{ rankText }}</strong><p>当前优先考虑：{{ strongest }}</p></div>
   <div class="c2-score-scroll" tabindex="0" aria-label="三个方向的同刻度比较，窄屏可横向滚动">
    <table class="c2-score-table"><caption>三个方向 × 五个比较项 · 同一刻度 0–100 · 每行标出最高和最低</caption>
     <thead><tr><th scope="col">比较项</th><th v-for="item in items" :key="item.id" scope="col">{{ item.title }} <small>{{ item.role }}</small></th></tr></thead>
     <tbody><tr v-for="criterion in criteria" :key="criterion.key"><th scope="row">{{ criterion.label }}</th><td v-for="item in items" :key="item.id"><strong>{{ criterion.scores[roleIndex(item)] }}</strong><div class="c2-score-track"><i :style="{width:criterion.scores[roleIndex(item)]+'%'}" :class="{'c2-score-high':criterion.scores[roleIndex(item)]===Math.max(...criterion.scores),'c2-score-low':criterion.scores[roleIndex(item)]===Math.min(...criterion.scores)}" /></div><small>{{ criterion.scores[roleIndex(item)]===Math.max(...criterion.scores)?'最高':criterion.scores[roleIndex(item)]===Math.min(...criterion.scores)?'最低':'—' }}</small></td></tr></tbody>
    </table>
   </div><div class="direction-mobile-comparison"><section v-for="criterion in criteria" :key="criterion.key"><h3>{{ criterion.label }}</h3><div v-for="item in items" :key="item.id"><span>{{ item.title }}</span><strong>{{ criterion.scores[roleIndex(item)] }}</strong></div></section></div>
  </section>
  <section class="c2-compare-section" aria-labelledby="print-weights-title"><header class="c2-compare-head"><h2 id="print-weights-title">调整考虑因素</h2><button class="btn btn--sm" @click="reset">恢复同等权重</button></header>
   <div class="c2-weight-list importance-choices"><fieldset v-for="criterion in criteria" :key="criterion.key"><legend>{{ criterion.label }}的重要程度</legend><div class="importance-options"><label v-for="option in importanceOptions" :key="option.value"><input v-model.number="weights[criterion.key]" type="radio" :name="'print-importance-' + criterion.key" :value="option.value"/><span>{{ option.label }}</span></label></div></fieldset></div><p class="c2-compare-note">选择每项因素的重要程度。调整只影响比较排序，不会替你确认方向。</p>
  </section>
</div>
 </div>
</template>
<style scoped>
.c2-compare { display:grid; gap:20px; }
.c2-compare-section,.c2-ranked-direction { padding:20px; border:1px solid var(--c-border); border-radius:16px; background:var(--c-surface); box-shadow:var(--e-2); min-width:0; }
.c2-compare-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.c2-compare-head h2 { font-size:var(--fs-16); font-weight:700; }
.c2-compare-head > span,.c2-compare-head small { font-size:var(--fs-12); color:var(--c-text-3); }
.c2-compare-note { font-size:var(--fs-12); color:var(--c-text-3); line-height:1.8; margin-top:6px; }
.c2-rank-reading { padding:14px 16px; border:1px solid var(--c-border); border-radius:12px; background:var(--c-surface-2); font-size:var(--fs-14); margin-top:16px; }
.c2-rank-reading p { font-size:var(--fs-12); line-height:1.8; color:var(--c-text-3); margin-top:4px; }
.c2-score-scroll { overflow-x:auto; border:1px solid var(--c-border); border-radius:12px; }
.c2-score-table { border-collapse:collapse; width:100%; min-width:700px; font-size:var(--fs-12); }
.c2-score-table caption { text-align:left; padding:12px 16px; background:var(--c-surface-2); color:var(--c-text-3); }
.c2-score-table th,.c2-score-table td { border-top:1px solid var(--c-border); padding:12px 16px; }
.c2-score-table th { text-align:left; color:var(--c-text-3); background:var(--c-surface-2); }
.c2-score-table thead small { font-weight:400; }
.c2-score-table tbody th { width:112px; }
.c2-score-table td { text-align:right; width:28%; }
.c2-score-table td strong { font-size:var(--fs-20); line-height:1.45; font-weight:700; font-variant-numeric:tabular-nums; }
.c2-score-track { height:5px; margin:4px 0; }
.c2-score-track i { display:block; height:5px; border-radius:3px; background:var(--c-text-3); opacity:.6; }
.c2-score-track .c2-score-high { opacity:1; background:var(--c-text-2); }
.c2-score-track .c2-score-low { background:repeating-linear-gradient(90deg,var(--c-border-strong) 0 2px,transparent 2px 4px); opacity:1; }
.c2-score-table td small { font-size:var(--fs-12); color:var(--c-text-3); }
.c2-weight-list { display:grid; grid-template-columns:1fr 1fr; gap:16px 24px; margin-top:20px; }
.c2-weight-list label { display:grid; grid-template-columns:84px minmax(0,1fr) 36px; gap:12px; align-items:center; font-size:var(--fs-14); }
.c2-weight-list input { width:100%; min-height:44px; accent-color:var(--c-primary); }
.c2-weight-list output { font-size:var(--fs-12); font-variant-numeric:tabular-nums; }
.c2-ranked-directions { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.c2-ranked-direction h2 { font-size:var(--fs-20); margin:16px 0; }
.c2-ranked-direction ul { list-style:disc; padding-left:18px; font-size:var(--fs-14); line-height:1.8; }
.c2-ranked-direction p { font-size:var(--fs-14); line-height:1.8; margin:16px 0; }
.c2-ranked-direction--picked { border-color:var(--c-primary); background:var(--c-primary-weak); }
.c2-ranked-direction .btn { width:100%; }
@media(max-width:767px) { .c2-weight-list,.c2-ranked-directions { grid-template-columns:1fr; } .c2-compare-section { padding:16px; } .c2-compare-head { flex-wrap:wrap; } }
@media print { .c2-weight-list { display:none; } .c2-score-scroll { overflow:visible; } .c2-score-table { min-width:0; } .c2-ranked-directions { display:block; } }
</style>
