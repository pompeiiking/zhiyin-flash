<script setup lang="ts">
import type { AiResult } from '../api/ai-types'
defineProps<{ result: AiResult<unknown> }>()
function sourceLink(value?: string) { return value && /^https?:\/\//i.test(value) ? value : undefined }
</script>
<template><p v-if="result.meta.by.includes('本地演示')" class="ws-demo-note">演示结果 · 本地预设，未调用模型或核验服务。</p><details class="ws-context ai-sources"><summary>依据与生成说明</summary><p v-if="result.rationale" class="ws-section">{{ result.rationale }}</p><ul class="ws-mini-list"><li v-for="(c,i) in result.citations" :key="i"><strong>{{ c.source }}</strong><p>{{ c.detail }}</p><small v-if="c.at">{{ c.at }}</small><a v-if="sourceLink(c.origin)" class="ws-text-link" :href="sourceLink(c.origin)" target="_blank" rel="noopener noreferrer">核对原始来源</a></li></ul><p v-if="!result.citations.length" class="ws-muted">本次结果没有返回具体来源，请结合已有资料核对。</p><p class="ws-muted ws-section">{{ result.meta.by }} · {{ result.meta.at ? new Date(result.meta.at).toLocaleString('zh-CN') : '时间未提供' }}{{ result.meta.cached ? ' · 已保存的结果' : '' }}</p></details></template>
