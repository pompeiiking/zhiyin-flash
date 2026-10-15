<script setup lang="ts">
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
import { computed } from 'vue'
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
function reset(){criteria.forEach(c=>{weights[c.key]=3})}
</script>
<template>
 <div class="c2-compare">
  <section class="c2-compare-section" aria-labelledby="c2-comparison-title">
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
  <section class="c2-compare-section" aria-labelledby="c2-weights-title"><header class="c2-compare-head"><h2 id="c2-weights-title">调整考虑因素</h2><button class="btn btn--sm" @click="reset">恢复同等权重</button></header>
   <div class="c2-weight-list"><label v-for="criterion in criteria" :key="criterion.key"><span>{{ criterion.label }}</span><input v-model.number="weights[criterion.key]" type="range" min="1" max="5" step="1" :aria-label="criterion.label+'看重程度'" /><output>{{ weights[criterion.key] }} / 5</output></label></div><p class="c2-compare-note">1 档最轻，5 档最重。只改变比较排序；原始评分与已确认的方向独立保留。</p>
  </section>
  <div class="c2-ranked-directions"><article v-for="entry in ranking" :key="entry.item.id" class="c2-ranked-direction" :class="{'c2-ranked-direction--picked':selectedId===entry.item.id}"><div class="c2-compare-head"><span>{{ entry.item.role }}</span><strong>{{ entry.score }}<small> 排序分</small></strong></div><h2>{{ entry.item.title }}</h2><DetailPopover :title="entry.item.title + ' · 支持依据'" :label="'查看' + entry.item.title + '支持依据'"><template #trigger>支持依据<UiIcon name="info" :size="16"/></template><ul><li v-for="e in entry.item.evidence" :key="e">{{ e }}</li></ul></DetailPopover><p class="ws-attention">{{ entry.item.risk }}</p><button class="btn" :aria-pressed="selectedId===entry.item.id" @click="$emit('pick',entry.item.id)">{{ selectedId===entry.item.id?'当前候选':'选择这个方向' }}</button></article></div>
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
