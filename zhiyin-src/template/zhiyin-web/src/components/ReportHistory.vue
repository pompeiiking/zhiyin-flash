<script setup lang="ts">
import { onMounted } from 'vue'
import { ref } from 'vue'
import { backendClient } from '../api/backend-client'
import type { AssetVersionView, ReportFullTextView } from '../api/backend-types'
import SkeletonBlock from './SkeletonBlock.vue'
import EmptyState from './EmptyState.vue'
import StatTile from './StatTile.vue'
const props = withDefaults(defineProps<{assetType?: 'report'|'direction_plan'|'action_plan'}>(),{assetType:'report'})
defineEmits<{ open: [report: ReportFullTextView, metadata: AssetVersionView | null] }>()
const versions = ref<AssetVersionView[] | null>(null), busy = ref(false), error = ref(''), reading = ref<number | null>(null)
async function load() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { const data = await backendClient.versions(props.assetType); if (!Array.isArray(data)) throw new Error('Incomplete versions'); versions.value = data.slice().sort((a,b)=>b.version-a.version) }
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
onMounted(()=>{ void load() })
</script>
<template><section class="report-history-live">
  <div class="ws-section-head"><h2>完整版本与更新状态</h2><button class="btn" :disabled="busy||reading!==null" @click="load">{{ busy?'正在读取…':'读取版本记录' }}</button></div>
  <p v-if="error" class="ws-field-error" role="alert">{{ error }}</p>
  <SkeletonBlock v-if="busy&&!versions" variant="list" :lines="3" />
  <template v-if="versions">
    <article v-for="v in versions" :key="v.asset_id+'-'+v.version" class="history-entry">
      <!-- 读数与来源分开：版本号是读数（StatTile），"这版读数还算不算数"是同一个瓦片上的状态；
           依赖的个人信息与生成时间是来源，走下面两行、**不**塞进 trend 字段
           （trend 的语义是"趋势方向"，不是时间戳 —— 塞进去会长期误导下一个读它的人） -->
      <StatTile
        :label="'第' + v.version + '版读数'"
        :value="v.version"
        :state="v.needs_recompute ? 'recompute' : 'done'"
      />
      <p class="ws-muted ws-section">生成于 {{ new Date(v.created_at).toLocaleString('zh-CN') }}</p>
      <p class="ws-section">{{ v.diff_from_previous || '本版没有提供差异摘要。' }}</p>
      <p v-if="v.depends_on_profile_keys?.length" class="ws-muted">依赖的个人信息：{{ v.depends_on_profile_keys.join('、') }}</p>
      <button v-if="assetType==='report'" class="btn ws-section" :disabled="reading!==null" @click="read(v.version,$emit)">{{ reading===v.version?'正在读取…':'阅读第'+v.version+'版完整正文' }}</button>
    </article>
    <EmptyState v-if="!versions.length" kind="report" size="sm" title="尚无已保存的资产版本" description="生成第一版后，这里会按版本列出生成时间、依赖信息与更新状态。" />
  </template>
  <p v-else-if="!busy" class="ws-muted ws-section">按所选数据来源读取完整正文、生成时间、依赖信息和待更新标记。</p>
</section></template>
