<script setup lang="ts">
/*
 * CareerMatchPanel —— 职业匹配面板（`/intel` 的第二个视图）。
 *
 * 本次改动逐条对应 MIGRATION：
 *   · §1.3 A14 / §4.3 B16：`facts` 折叠改 `Foldable variant="inline"`，
 *     `source_name` 灰字改 `SourceChip`（有真实 URL 的事实才配得上"来源"徽标）。
 *   · §3.3 T13：`<span class="ws-muted">契合度 {{ r.fit }}</span>` 这种"读数的灰字化"
 *     换成 `StatTile`（`r.fit` 在 `data/demo-ai.ts:11` 是 `Math.round(p.fitScore*100)`，
 *     即 **0–100 整数** → 用 `formatScore01` 印整分，不显示成 4600%）。
 *   · §4.2 E6 + `PLAN.md:78`：匹配空态原来是**一句 `ws-empty` 灰字、没有任何下一步**。
 *     现在换成 `EmptyState kind="search-empty"` + 三个可执行动作（空态不允许没有出口）。
 */
import { computed } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import { formatScore01 } from './charts/MeterRow.vue'
import type { MatchResult } from '../api/ai-types'
import type { IntelItemView } from '../api/backend-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import EmptyState from './EmptyState.vue'
import Foldable from './Foldable.vue'
import SourceChip from './SourceChip.vue'
import StatTile from './StatTile.vue'
const props = defineProps<{ facts: readonly IntelItemView[] }>()
const emit = defineEmits<{ read: [id: string]; facts: [query: string] }>()
const task = useAiTask<MatchResult>()
const tracks = computed(() => [...new Set(task.result.value?.data.cells?.map(c => c.track) ?? [])])
const skills = computed(() => [...new Set(task.result.value?.data.cells?.map(c => c.skill) ?? [])])
function cell(track: string, skill: string) { return task.result.value?.data.cells?.find(c => c.track === track && c.skill === skill) }
function numeric(value: unknown) { return typeof value === 'number' && Number.isFinite(value) }
/* 只有带真实外链的事实才用 SourceChip（它是"可核对外部记录"的形态）；
   演示条目的 source_name 是自由文本，硬套徽标会假装有出处（MIGRATION U3 的缺口）。 */
function hasLink(url?: string) { return !!url && /^https?:\/\//i.test(url) }
function run() { void task.run('careerMatch') }
</script>
<template><section class="career-match"><div class="ws-section-head"><h2>职业匹配</h2><button class="btn btn--primary" :disabled="task.busy.value" @click="run">{{ task.result.value ? '重新生成匹配结果' : '比较画像与岗位要求' }}</button></div><p class="ws-muted ws-section">比较要求与已有事实。缺少要求或个人依据时，不给出推测评分。</p><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="run"/>
<template v-if="task.result.value"><section class="report-lead"><h3>{{ task.result.value.data.recommend?.title || '暂无推荐结论' }}</h3><p>{{ task.result.value.data.recommend?.body }}</p><ul class="ws-mini-list"><li v-for="e in task.result.value.data.recommend?.because" :key="e">{{ e }}</li></ul></section>
<section v-if="task.result.value.data.ranking?.length" class="ws-section"><h3>方向排序与取舍</h3><ol class="match-ranking"><li v-for="r in task.result.value.data.ranking" :key="r.track"><div class="ws-section-head"><h4>{{ r.track }}</h4><StatTile v-if="numeric(r.fit)" class="match-fit" :score="r.fit/100" :format="formatScore01" unit="分" label="契合度"/></div><p>{{ r.why }}</p><p class="ws-attention">差距与风险：{{ r.gap || '本次没有提供具体差距' }}</p><button class="ws-text-button" @click="emit('facts',r.track)">查看对应资讯事实</button></li></ol></section>
<section v-if="tracks.length" class="ws-section"><h3>要求与现状逐项对照</h3><div class="compare-desktop local-table-scroll"><table class="fact-table"><caption class="sr-only">各方向的能力要求与当前情况</caption><thead><tr><th scope="col">能力</th><th v-for="t in tracks" :key="t" scope="col">{{ t }}</th></tr></thead><tbody><tr v-for="s in skills" :key="s"><th scope="row">{{ s }}</th><td v-for="t in tracks" :key="t"><template v-if="cell(t,s)">要求 {{ cell(t,s)?.need }} · 现状 {{ cell(t,s)?.have }}</template><span v-else>未提供数据</span></td></tr></tbody></table></div><div class="compare-mobile"><section v-for="s in skills" :key="s" class="compare-criterion"><h4>{{ s }}</h4><article v-for="t in tracks" :key="t"><strong>{{ t }}</strong><p v-if="cell(t,s)">要求 {{ cell(t,s)?.need }} · 现状 {{ cell(t,s)?.have }}</p><p v-else>未提供数据</p></article></section></div></section>
<p v-else class="ws-muted ws-section">本次没有可比较的完整数值。请依据上方说明补充资料。</p><AiResultMeta :result="task.result.value"/>
<Foldable v-if="props.facts.length" variant="inline" :title="'已读取的资讯事实'" :count="props.facts.length"><ul class="ws-mini-list"><li v-for="f in props.facts" :key="f.id"><button class="ws-text-button" @click="emit('read',f.id)">{{ f.title }}</button><SourceChip v-if="hasLink(f.source_url)" class="match-src" source="record" :at="f.fetched_at ?? null"/><small v-else class="ws-muted">{{ f.source_name }}</small></li></ul></Foldable></template>
<EmptyState
  v-else-if="!task.busy.value"
  class="match-empty"
  kind="search-empty"
  size="sm"
  title="还没有匹配结果"
  description="补齐画像里的经历与岗位要求后，这里会给出结论、依据和差距。"
  :next="false"
>
  <div class="match-empty__actions">
    <button class="btn btn--primary" @click="run">比较画像与岗位要求</button>
    <button v-if="props.facts.length" class="ws-text-button" @click="emit('read', props.facts[0]!.id)">先核对一条资讯来源</button>
  </div>
</EmptyState></section></template>

<style scoped>
/* 契合度读数：瓦片是右对齐的，在「方向标题 + 读数」这一行里给它一个固定宽度，
   否则两个元素的宽度会随文案长度互相挤（这行本来就是"标题在左、读数在右"）。 */
.match-fit {
  flex: none;
  min-width: 132px;
}
.match-src {
  margin-left: var(--sp-3);
}
/* 空态的动作区：EmptyState 的默认插槽顶掉 kind 预设，
   所以这两个按钮就是这一屏唯一的出口 —— 主按钮必须是"能立刻做的那件事" */
.match-empty__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-5);
}
</style>
