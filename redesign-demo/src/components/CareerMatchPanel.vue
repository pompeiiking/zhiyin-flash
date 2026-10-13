<script setup lang="ts">
import { computed } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import type { MatchResult } from '../api/ai-types'
import type { IntelItemView } from '../api/backend-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
const props = defineProps<{ facts: readonly IntelItemView[] }>()
defineEmits<{ read: [id: string]; facts: [query: string] }>()
const task = useAiTask<MatchResult>()
const tracks = computed(() => [...new Set(task.result.value?.data.cells?.map(c => c.track) ?? [])])
const skills = computed(() => [...new Set(task.result.value?.data.cells?.map(c => c.skill) ?? [])])
function cell(track: string, skill: string) { return task.result.value?.data.cells?.find(c => c.track === track && c.skill === skill) }
function numeric(value: unknown) { return typeof value === 'number' && Number.isFinite(value) }
</script>
<template><section class="career-match"><div class="ws-section-head"><h2>职业匹配</h2><button class="btn btn--primary" :disabled="task.busy.value" @click="task.run('careerMatch')">{{ task.result.value ? '更新匹配结果' : '比较画像与岗位要求' }}</button></div><p class="ws-muted ws-section">比较要求与已有事实。缺少要求或个人依据时，不给出推测评分。</p><AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('careerMatch')"/>
<template v-if="task.result.value"><section class="report-lead"><h3>{{ task.result.value.data.recommend?.title || '暂无推荐结论' }}</h3><p>{{ task.result.value.data.recommend?.body }}</p><ul class="ws-mini-list"><li v-for="e in task.result.value.data.recommend?.because" :key="e">{{ e }}</li></ul></section>
<section v-if="task.result.value.data.ranking?.length" class="ws-section"><h3>方向排序与取舍</h3><ol class="match-ranking"><li v-for="r in task.result.value.data.ranking" :key="r.track"><div class="ws-section-head"><h4>{{ r.track }}</h4><span v-if="numeric(r.fit)" class="ws-muted">契合度 {{ r.fit }}</span></div><p>{{ r.why }}</p><p class="ws-attention">差距与风险：{{ r.gap || '本次没有提供具体差距' }}</p><button class="ws-text-button" @click="$emit('facts',r.track)">查看对应资讯事实</button></li></ol></section>
<section v-if="tracks.length" class="ws-section"><h3>要求与现状逐项对照</h3><div class="compare-desktop local-table-scroll"><table class="fact-table"><caption class="sr-only">各方向的能力要求与当前情况</caption><thead><tr><th scope="col">能力</th><th v-for="t in tracks" :key="t" scope="col">{{ t }}</th></tr></thead><tbody><tr v-for="s in skills" :key="s"><th scope="row">{{ s }}</th><td v-for="t in tracks" :key="t"><template v-if="cell(t,s)">要求 {{ cell(t,s)?.need }} · 现状 {{ cell(t,s)?.have }}</template><span v-else>未提供数据</span></td></tr></tbody></table></div><div class="compare-mobile"><section v-for="s in skills" :key="s" class="compare-criterion"><h4>{{ s }}</h4><article v-for="t in tracks" :key="t"><strong>{{ t }}</strong><p v-if="cell(t,s)">要求 {{ cell(t,s)?.need }} · 现状 {{ cell(t,s)?.have }}</p><p v-else>未提供数据</p></article></section></div></section>
<p v-else class="ws-muted ws-section">本次没有可比较的完整数值。请依据上方说明补充资料。</p><AiResultMeta :result="task.result.value"/>
<details v-if="props.facts.length" class="ws-context"><summary>已读取的资讯事实</summary><ul class="ws-mini-list"><li v-for="f in props.facts" :key="f.id"><button class="ws-text-button" @click="$emit('read',f.id)">{{ f.title }}</button><small>{{ f.source_name }}</small></li></ul></details></template>
<p v-else-if="!task.busy.value" class="ws-empty">取得匹配结果后，在这里查看结论、依据、差距和原始资讯。</p></section></template>
