<script setup lang="ts">
import { ref } from 'vue'
import { backendClient } from '../api/backend-client'
import type { AssetVersionView, ReportFullTextView } from '../api/backend-types'
defineEmits<{ open: [report: ReportFullTextView, metadata: AssetVersionView | null] }>()
const versions = ref<AssetVersionView[] | null>(null), busy = ref(false), error = ref(''), reading = ref<number | null>(null)
async function load() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { const data = await backendClient.versions('report'); if (!Array.isArray(data)) throw new Error('Incomplete versions'); versions.value = data.slice().sort((a,b)=>b.version-a.version) }
  catch { error.value = '暂时没有取得版本记录，已有内容仍保留。请重试。' }
  finally { busy.value = false }
}
async function read(version: number, emit: (event: 'open', report: ReportFullTextView, metadata: AssetVersionView | null) => void) {
  if (reading.value !== null) return
  reading.value = version; error.value = ''
  try { const data = await backendClient.report(version); if (data.version !== version) throw new Error('Wrong version'); emit('open', data, versions.value?.find(v=>v.version===version) ?? null) }
  catch { error.value = '这版完整正文暂时没有取得，请重试。当前报告没有被替换。' }
  finally { reading.value = null }
}
</script>
<template><section class="report-history-live"><div class="ws-section-head"><h2>完整版本与更新状态</h2><button class="btn" :disabled="busy||reading!==null" @click="load">{{ busy?'正在读取…':'读取版本记录' }}</button></div><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><template v-if="versions"><article v-for="v in versions" :key="v.asset_id+'-'+v.version" class="history-entry"><div class="ws-section-head"><h3>第{{ v.version }}版</h3><span class="ws-attention" v-if="v.needs_recompute">待更新</span><span class="ws-muted" v-else>当前记录无需重算</span></div><time>{{ new Date(v.created_at).toLocaleString('zh-CN') }}</time><p class="ws-section">{{ v.diff_from_previous || '本版没有提供差异摘要。' }}</p><p v-if="v.depends_on_profile_keys?.length" class="ws-muted">依赖的个人信息：{{ v.depends_on_profile_keys.join('、') }}</p><p v-if="v.needs_recompute" class="ws-attention">依据已有变化，阅读这版时请同时核对最新个人信息。</p><button class="btn ws-section" :disabled="reading!==null" @click="read(v.version,$emit)">{{ reading===v.version?'正在读取…':'阅读第'+v.version+'版完整正文' }}</button></article><p v-if="!versions.length" class="ws-empty">尚无已保存的报告版本。</p></template><p v-else class="ws-muted ws-section">按所选数据来源读取完整正文、生成时间、依赖信息和待更新标记。演示模式提供三版虚构报告。</p></section></template>
