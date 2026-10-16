<script setup lang="ts">
import type { ReportFullTextView } from '../api/backend-types'
import { computed, ref, type DeepReadonly } from 'vue'
import MeasurementPanel from './MeasurementPanel.vue'
import InfoSheet from './InfoSheet.vue'
import DetailPopover from './DetailPopover.vue'
import {usePagedItems} from '../lib/paged-items'
import ResultPager from './ResultPager.vue'
const props = defineProps<{ report: DeepReadonly<ReportFullTextView> }>()
const chapter=ref<string|null>(null), appendix=ref(false),query=ref(''),grouping=ref('section'),tag=ref('')
const all=computed(()=>props.report.sections?.flatMap(section=>(section.items??[]).map(item=>({...item,sectionId:section.id,sectionTitle:section.title})))??[])
const tags=computed(()=>[...new Set(all.value.map(i=>i.tag).filter(Boolean))])
const filtered=computed(()=>all.value.filter(i=>(!chapter.value||i.sectionId===chapter.value)&&(!tag.value||i.tag===tag.value)&&[i.name,i.conclusion,i.evidence].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,6)
const groups=computed(()=>[...new Set(paged.value.map(i=>grouping.value==='tag'?i.tag||'未分类':i.sectionTitle))].map(title=>({title,items:paged.value.filter(i=>(grouping.value==='tag'?i.tag||'未分类':i.sectionTitle)===title)})))

const labels: Record<string,string> = { strengths:'优势', weaknesses:'短板', opportunities:'机会', threats:'风险', strength:'优势', weakness:'短板', opportunity:'机会', threat:'风险' }
function content(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(content).filter(Boolean).join('；')
  if (typeof value === 'object') return Object.values(value).map(content).filter(Boolean).join('；')
  return String(value)
}
</script>
<template>
<article class="full-report reading-prose">
 <p class="ws-muted">第{{ report.version }}版 · {{ new Date(report.generated_at).toLocaleString('zh-CN') }}</p>
 <section v-if="report.verdict && content(report.verdict)" class="report-key-evidence"><h2>总体结论</h2><p>{{ content(report.verdict) }}</p></section>
 <section class="report-reading-index"><div class="ws-section-head"><h2>判断与依据</h2><span class="ws-muted">{{all.length}} 项分析</span></div><div class="restored-report-chapters"><button class="btn" :aria-pressed="chapter===null" @click="chapter=null">全部章节</button><button v-for="section in report.sections" :key="section.id" class="btn" :aria-pressed="chapter===section.id" @click="chapter=section.id">{{section.title}} · {{section.items?.length??0}}</button></div><div class="restored-report-tools"><label class="information-search">查找判断或依据<input v-model="query" type="search" placeholder="能力、经历或资料关键词"/></label><label class="ws-field">组织方式<select v-model="grouping"><option value="section">按章节</option><option value="tag">按分析标签</option></select></label><label class="ws-field">分析标签<select v-model="tag"><option value="">全部标签</option><option v-for="t in tags" :key="t">{{t}}</option></select></label></div>
 <section v-for="group in groups" :key="group.title" class="restored-report-group"><h3>{{group.title}}</h3><article v-for="item in group.items" :key="item.sectionId+'-'+item.index" class="report-dimension"><DetailPopover class="judgment-trigger" :title="item.name+' · 支持依据'" :label="'核对'+item.name+'的依据'" side="right"><template #trigger><span class="judgment-copy"><strong>{{item.name}} <small>{{item.tag}}</small></strong><span>{{item.conclusion}}</span><em>核对依据 →</em></span></template><p>{{item.evidence||'这项判断暂未提供依据。'}}</p><p class="ws-muted">来自「{{item.sectionTitle}}」· 第 {{report.version}} 版</p><RouterLink class="ws-text-link" :to="'/chat?question='+encodeURIComponent('我想核对第'+report.version+'版报告中的「'+item.name+'」：'+item.conclusion+'；依据：'+item.evidence)">带着这项判断咨询</RouterLink></DetailPopover></article></section><p v-if="!filtered.length" class="ws-empty">没有符合当前条件的分析。</p><ResultPager v-model:page="page" :total="filtered.length" :size="6" label="报告分析"/></section>
 <div class="restored-report-chapters"><MeasurementPanel asset-type="report" :version="report.version" :subject-id="report.report_id" :dimensions="all.map(i=>({key:String(i.index),label:i.name}))"/><button v-if="report.swot || report.methodologies?.length || report.sources?.length" class="btn" @click="appendix=true">分析方法与资料来源</button></div>
 <InfoSheet :open="appendix" shape="panel" title="分析方法与资料来源" @close="appendix=false"><section v-if="report.swot && Object.keys(report.swot).length"><h2>优势、短板与外部条件</h2><section v-for="(value,key) in report.swot" :key="key" class="ws-section"><h3>{{ labels[key] ?? '补充分析' }}</h3><p>{{ content(value) || '暂未提供' }}</p></section></section><section v-if="report.methodologies?.length" class="ws-section"><h2>方法依据</h2><ul class="ws-mini-list"><li v-for="method in report.methodologies" :key="method">{{ method }}</li></ul></section><section v-if="report.sources?.length" class="ws-section"><h2>资料来源</h2><ul class="ws-mini-list"><li v-for="source in report.sources" :key="source"><a v-if="/^https?:\/\//.test(source)" class="ws-text-link" :href="source" target="_blank" rel="noopener noreferrer">{{ source }}</a><span v-else>{{ source }}</span></li></ul></section></InfoSheet>
 <div class="information-print-only"><section v-for="section in report.sections" :key="section.id" class="report-chapter"><h2>{{ section.title }}</h2><p v-if="section.method">分析方法：{{ section.method }}</p><article v-for="item in section.items" :key="item.index+'-'+item.name"><h3>{{ item.name }} · {{ item.tag }}</h3><p>{{ item.conclusion }}</p><p>{{ item.evidence }}</p></article></section><section v-for="(value,key) in report.swot" :key="key"><h2>{{ labels[key] ?? '补充分析' }}</h2><p>{{ content(value) }}</p></section><h2 v-if="report.methodologies?.length">方法依据</h2><p v-for="method in report.methodologies" :key="method">{{ method }}</p><h2 v-if="report.sources?.length">资料来源</h2><p v-for="source in report.sources" :key="source">{{ source }}</p></div>
</article>
</template>

<style scoped>.report-reading-index{display:block!important;}.restored-report-chapters{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}.restored-report-chapters [aria-pressed=true]{background:var(--c-primary-weak);color:var(--c-primary);border-color:var(--c-primary)}.restored-report-tools{display:flex;flex-wrap:wrap;align-items:end;gap:14px;padding:12px 0 22px}.restored-report-tools .information-search{flex:1;min-width:200px}.restored-report-group>h3{font-size:var(--fs-16);color:var(--c-primary);margin:20px 0 8px}.restored-report-group .report-dimension{padding:16px 0;border-bottom:1px solid var(--c-border)}.judgment-trigger{display:block;width:100%;text-align:left;white-space:normal}.judgment-copy{display:grid;gap:8px;color:var(--c-text)}.judgment-copy strong{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:var(--fs-14)}.judgment-copy small{color:var(--c-text-3);font-weight:400;font-size:var(--fs-12)}.judgment-copy>span{line-height:1.8;font-size:var(--fs-14);font-weight:400}.judgment-copy em{font-size:var(--fs-12);font-style:normal;color:var(--c-primary)}.restored-report-group .report-dimension p{margin:10px 0;line-height:1.8}@media print{.report-reading-index,.restored-report-chapters{display:none}}</style>
