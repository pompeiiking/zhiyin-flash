<script setup lang="ts">
import {studentApi} from '../api/student-capabilities'
import DetailPopover from './DetailPopover.vue'
import { studentVersionDiff } from '../lib/student-voice'
import { computed, onMounted } from 'vue'
import { ref } from 'vue'
import { backendClient } from '../api/backend-client'
import type { AssetVersionView, ReportFullTextView } from '../api/backend-types'
import SkeletonBlock from './SkeletonBlock.vue'
import EmptyState from './EmptyState.vue'
import StatTile from './StatTile.vue'
import { formatDateTime } from '../lib/format'
const props = withDefaults(defineProps<{assetType?: 'report'|'direction_plan'|'action_plan'}>(),{assetType:'report'})
defineEmits<{ open: [report: ReportFullTextView, metadata: AssetVersionView | null] }>()
const heading=computed(()=>props.assetType==='direction_plan'?'方案版本与更新状态':props.assetType==='action_plan'?'计划版本与更新状态':'完整版本与更新状态')
const historical=ref<{version:number;content:any}|null>(null)
async function readSnapshot(version:number){error.value='';try{historical.value=await studentApi.snapshot(props.assetType,version)}catch(e){error.value=(e as Error).message}}
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
const formatDate=(value:string)=>formatDateTime(value)||'未记录时间'
onMounted(()=>{ void load() })
</script>
<template><section class="report-history-live">
  <div class="ws-section-head"><h2>{{heading}}</h2><button class="btn" :disabled="busy||reading!==null" @click="load">{{ busy?'正在读取…':'读取版本记录' }}</button></div>
  <p v-if="error" class="ws-field-error" role="alert">{{ error }}</p>
  <SkeletonBlock v-if="busy&&!versions" variant="list" :lines="3" />
  <template v-if="versions">
    <div v-if="assetType==='report'" class="report-version-list">
      <article v-for="(v,index) in versions" :key="v.asset_id+'-'+v.version" class="report-version-row" :class="{'report-version-row--attention':v.needs_recompute}">
        <div class="report-version-row__identity"><strong>第 {{v.version}} 版</strong><span>{{v.needs_recompute?'待重新核对':index===0?'当前版本':'已保存'}}</span></div>
        <div class="report-version-row__content"><p>{{studentVersionDiff(v.diff_from_previous)||'本版没有提供差异摘要。'}}</p><div class="report-version-row__meta"><time :datetime="v.created_at">{{formatDate(v.created_at)}}</time><DetailPopover v-if="v.depends_on_profile_keys?.length" :title="'第 '+v.version+' 版参考的个人信息'" :label="'查看第'+v.version+'版参考的个人信息'"><template #trigger>参考了 {{v.depends_on_profile_keys.length}} 项个人信息</template><p>{{v.depends_on_profile_keys.join('、')}}</p></DetailPopover><span v-else>未记录依赖信息</span></div></div>
        <button class="btn" :disabled="reading!==null" @click="read(v.version,$emit)">{{reading===v.version?'正在读取…':'阅读本版'}}</button>
      </article>
    </div>
    <template v-else>
    <article v-for="v in versions" :key="v.asset_id+'-'+v.version" class="history-entry">
      <!-- 读数与来源分开：版本号是读数（StatTile），"这版读数还算不算数"是同一个瓦片上的状态；
           依赖的个人信息与生成时间是来源，走下面两行、**不**塞进 trend 字段
           （trend 的语义是"趋势方向"，不是时间戳 —— 塞进去会长期误导下一个读它的人） -->
      <StatTile
        :label="'第' + v.version + '版读数'"
        :value="v.version"
        :state="v.needs_recompute ? 'recompute' : 'done'"
      />
      <p class="ws-muted ws-section">生成于 {{ formatDate(v.created_at) }}</p>
      <p class="ws-section">{{ studentVersionDiff(v.diff_from_previous) || '本版没有提供差异摘要。' }}</p>
      <p v-if="v.depends_on_profile_keys?.length" class="ws-muted">参考的个人信息：{{ v.depends_on_profile_keys.join('、') }}</p>
      <DetailPopover :title="'第 '+v.version+' 版正文'" side="right" @update:model-value="open=>open&&readSnapshot(v.version)"><template #trigger>阅读历史正文</template><template v-if="historical?.version===v.version"><template v-if="assetType==='action_plan'"><section v-for="p in historical.content.phases" :key="p.id||p.name"><h3>{{p.name}}</h3><p v-for="t in p.tasks" :key="t.id">{{t.done?'✓':'○'}} {{t.text}}</p></section></template><template v-else><section v-for="p in historical.content" :key="p.id" class="history-direction"><h3>{{p.name}}</h3><dl><div><dt>方向目标</dt><dd>{{p.target_desc||'本版未提供'}}</dd></div><div><dt>匹配依据</dt><dd>{{p.fit_reason||'本版未提供'}}</dd></div><div><dt>主要风险</dt><dd>{{p.main_risk||'本版未提供'}}</dd></div></dl><section v-if="p.gaps?.length"><h4>差距与补齐建议</h4><article v-for="(gap,index) in p.gaps" :key="gap.id||index"><strong>{{gap.requirement||'未命名要求'}}</strong><p>当前情况：{{gap.current_state||'本版未提供'}}</p><p>补齐建议：{{gap.suggestion||'本版未提供'}}</p></article></section></section></template></template><p v-else>正在读取历史正文；缺少快照时会在版本列表显示原因。</p></DetailPopover>
    </article>
    </template>
    <EmptyState v-if="!versions.length" kind="report" size="sm" title="尚无已保存的资产版本" description="生成第一版后，这里会按版本列出生成时间、依赖信息与更新状态。" />
  </template>
  <p v-else-if="!busy" class="ws-muted ws-section">按所选数据来源读取完整正文、生成时间、依赖信息和待更新标记。</p>
</section></template>

<style scoped>
.report-version-list{margin-top:20px;border-top:1px solid var(--c-border)}.report-version-row{display:grid;grid-template-columns:130px minmax(0,1fr) auto;gap:20px;align-items:center;padding:20px 4px;border-bottom:1px solid var(--c-border)}.report-version-row--attention{border-left:3px solid var(--c-attention);padding-left:14px}.report-version-row__identity{display:grid;gap:6px}.report-version-row__identity strong{font-size:var(--fs-16)}.report-version-row__identity span{width:max-content;padding:3px 7px;border-radius:999px;background:var(--c-surface-3);color:var(--c-text-2);font-size:var(--fs-12)}.report-version-row--attention .report-version-row__identity span{background:var(--c-attention-weak);color:var(--c-attention-strong)}.report-version-row__content{min-width:0}.report-version-row__content>p{line-height:1.65}.report-version-row__meta{display:flex;flex-wrap:wrap;align-items:center;gap:2px 16px;margin-top:8px;color:var(--c-text-3);font-size:var(--fs-12);font-variant-numeric:tabular-nums}.report-version-row__meta :deep(.detail-trigger){min-height:32px;padding:0;color:var(--c-primary);font-size:var(--fs-12)}@media(max-width:767px){.report-version-row{grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:18px 0}.report-version-row__content{grid-column:1 / -1;grid-row:2}.report-version-row>.btn{grid-column:2;grid-row:1}.report-version-row--attention{padding-left:12px}}
.history-direction+ .history-direction{margin-top:20px;padding-top:20px;border-top:1px solid var(--c-border)}.history-direction dl{display:grid;gap:12px;margin:12px 0}.history-direction dt{color:var(--c-text-3);font-size:var(--fs-12)}.history-direction dd{margin:3px 0 0;line-height:1.6}.history-direction h4{margin:16px 0 8px}.history-direction article{padding:10px 0;border-top:1px solid var(--c-border)}.history-direction article p{margin-top:5px;color:var(--c-text-2)}
</style>
