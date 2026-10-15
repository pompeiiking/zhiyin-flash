<script setup lang="ts">
import type { ReportFullTextView } from '../api/backend-types'
import { computed, ref, type DeepReadonly } from 'vue'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
const props = defineProps<{ report: DeepReadonly<ReportFullTextView> }>()
const chapter=ref<string|null>(null), appendix=ref(false)
const selected=computed(()=>props.report.sections?.find(section=>section.id===chapter.value))
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
 <section class="report-reading-index"><h2>报告分析</h2><button v-for="section in report.sections" :key="section.id" class="information-entry" @click="chapter=section.id"><span><strong>{{ section.title }}</strong><small>{{ section.items?.length ?? 0 }} 项分析 · {{ section.items?.[0]?.name || '查看本章内容' }}</small></span><UiIcon name="arrow" :size="18"/></button><p v-if="!report.sections?.length" class="ws-muted">本次报告尚未返回详细分析章节。</p></section>
 <button v-if="report.swot || report.methodologies?.length || report.sources?.length" class="information-entry" @click="appendix=true"><span><strong>分析方法与资料来源</strong><small>核对优势、短板、外部条件和报告使用的资料</small></span><UiIcon name="arrow" :size="18"/></button>
 <InfoSheet :open="chapter!==null" shape="panel" :title="selected?.title ?? '报告分析'" @close="chapter=null"><section v-if="selected" class="reading-prose"><p v-if="selected.method" class="ws-muted">分析方法：{{ selected.method }}</p><article v-for="item in selected.items" :key="item.index+'-'+item.name" class="report-dimension"><div class="ws-section-head"><h3>{{ item.name }}</h3><span class="ws-muted">{{ item.tag }}</span></div><p>{{ item.conclusion }}</p><div v-if="item.evidence" class="report-evidence"><h4>支持依据</h4><p>{{ item.evidence }}</p></div></article></section></InfoSheet>
 <InfoSheet :open="appendix" shape="panel" title="分析方法与资料来源" @close="appendix=false"><section v-if="report.swot && Object.keys(report.swot).length"><h2>优势、短板与外部条件</h2><section v-for="(value,key) in report.swot" :key="key" class="ws-section"><h3>{{ labels[key] ?? '补充分析' }}</h3><p>{{ content(value) || '暂未提供' }}</p></section></section><section v-if="report.methodologies?.length" class="ws-section"><h2>方法依据</h2><ul class="ws-mini-list"><li v-for="method in report.methodologies" :key="method">{{ method }}</li></ul></section><section v-if="report.sources?.length" class="ws-section"><h2>资料来源</h2><ul class="ws-mini-list"><li v-for="source in report.sources" :key="source"><a v-if="/^https?:\/\//.test(source)" class="ws-text-link" :href="source" target="_blank" rel="noopener noreferrer">{{ source }}</a><span v-else>{{ source }}</span></li></ul></section></InfoSheet>
 <div class="information-print-only"><section v-for="section in report.sections" :key="section.id" class="report-chapter"><h2>{{ section.title }}</h2><p v-if="section.method">分析方法：{{ section.method }}</p><article v-for="item in section.items" :key="item.index+'-'+item.name"><h3>{{ item.name }} · {{ item.tag }}</h3><p>{{ item.conclusion }}</p><p>{{ item.evidence }}</p></article></section><section v-for="(value,key) in report.swot" :key="key"><h2>{{ labels[key] ?? '补充分析' }}</h2><p>{{ content(value) }}</p></section><h2 v-if="report.methodologies?.length">方法依据</h2><p v-for="method in report.methodologies" :key="method">{{ method }}</p><h2 v-if="report.sources?.length">资料来源</h2><p v-for="source in report.sources" :key="source">{{ source }}</p></div>
</article>
</template>
