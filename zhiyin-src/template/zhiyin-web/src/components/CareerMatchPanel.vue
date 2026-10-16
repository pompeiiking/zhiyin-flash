<script setup lang="ts">
import { computed } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import { formatScore01 } from './charts/MeterRow.vue'
import type { MatchResult } from '../api/ai-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import EmptyState from './EmptyState.vue'
import Foldable from './Foldable.vue'
import StatTile from './StatTile.vue'

const task = useAiTask<MatchResult>()
const tracks = computed(() => [...new Set(task.result.value?.data.cells?.map((item) => item.track) ?? [])])
const skills = computed(() => [...new Set(task.result.value?.data.cells?.map((item) => item.skill) ?? [])])
const comparisonCount = computed(() => tracks.value.length * skills.value.length)

function cell(track: string, skill: string) {
  return task.result.value?.data.cells?.find((item) => item.track === track && item.skill === skill)
}

function numeric(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value)
}

function run() {
  if (!task.busy.value) void task.run('careerMatch')
}

defineExpose({ run })
</script>

<template>
  <section class="career-match">
    <AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="run" />

    <template v-if="task.result.value">
      <div class="career-match__again">
        <p>结果基于当前画像和本次读取到的岗位要求。</p>
        <button class="btn" type="button" :disabled="task.busy.value" @click="run">重新匹配</button>
      </div>

      <section class="report-lead career-match__lead">
        <h3>{{ task.result.value.data.recommend?.title || '暂无推荐结论' }}</h3>
        <p v-if="!task.result.value.data.ranking?.length">本次证据不足以形成可靠排序时，不展示推测分数。</p>
      </section>

      <section v-if="task.result.value.data.ranking?.length" class="career-match__ranking">
        <h3>方向排序与取舍</h3>
        <ol>
          <li v-for="result in task.result.value.data.ranking" :key="result.track">
            <div class="career-match__rank-head">
              <h4>{{ result.track }}</h4>
              <StatTile v-if="numeric(result.fit)" class="match-fit" :score="result.fit / 100" :format="formatScore01" unit="分" label="契合度" />
            </div>
            <p>{{ result.why }}</p>
            <p class="ws-attention">需要补足：{{ result.gap || '本次没有提供具体差距' }}</p>
          </li>
        </ol>
      </section>

      <Foldable
        v-if="task.result.value.data.recommend?.body || task.result.value.data.recommend?.because?.length"
        class="career-match__details"
        variant="section"
        title="查看分析说明与依据"
        :count="task.result.value.data.recommend?.because?.length || null"
      >
        <p class="career-match__analysis">{{ task.result.value.data.recommend?.body }}</p>
        <ul v-if="task.result.value.data.recommend?.because?.length" class="ws-mini-list">
          <li v-for="evidence in task.result.value.data.recommend?.because" :key="evidence">{{ evidence }}</li>
        </ul>
        <AiResultMeta :result="task.result.value" />
      </Foldable>

      <Foldable v-if="tracks.length" class="career-match__details" variant="section" title="查看逐项能力对照" :count="comparisonCount">
        <div class="compare-desktop local-table-scroll">
          <table class="fact-table">
            <caption class="sr-only">各方向的能力要求与当前情况</caption>
            <thead><tr><th scope="col">能力</th><th v-for="track in tracks" :key="track" scope="col">{{ track }}</th></tr></thead>
            <tbody>
              <tr v-for="skill in skills" :key="skill">
                <th scope="row">{{ skill }}</th>
                <td v-for="track in tracks" :key="track">
                  <template v-if="cell(track, skill)">要求 {{ cell(track, skill)?.need }} · 现状 {{ cell(track, skill)?.have }}</template>
                  <span v-else>未提供数据</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="compare-mobile">
          <section v-for="skill in skills" :key="skill" class="compare-criterion">
            <h4>{{ skill }}</h4>
            <article v-for="track in tracks" :key="track">
              <strong>{{ track }}</strong>
              <p v-if="cell(track, skill)">要求 {{ cell(track, skill)?.need }} · 现状 {{ cell(track, skill)?.have }}</p>
              <p v-else>未提供数据</p>
            </article>
          </section>
        </div>
      </Foldable>
    </template>

    <EmptyState
      v-else-if="!task.busy.value"
      kind="search-empty"
      size="sm"
      title="还没有匹配结果"
      description="点击后才会比较当前画像和岗位要求，不会自动运行。"
      :next="false"
    >
      <button class="btn btn--primary" type="button" @click="run">开始岗位匹配</button>
    </EmptyState>
  </section>
</template>

<style scoped>
.career-match__again { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 20px; color: var(--c-text-3); font-size: 12px; }
.career-match__lead { margin-bottom: 28px; }
.career-match__lead > p { margin-top: 10px; color: var(--c-text-2); font-size: 13px; line-height: 1.75; }
.career-match__ranking > h3 { margin-bottom: 8px; font-size: 16px; font-weight: 650; }
.career-match__ranking ol { display: grid; }
.career-match__ranking li { padding: 18px 0; border-bottom: 1px solid var(--c-border); }
.career-match__rank-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.career-match__rank-head h4 { font-size: 15px; font-weight: 650; }
.career-match__ranking li > p { max-width: 54em; margin-top: 8px; font-size: 13px; line-height: 1.75; }
.match-fit { flex: none; min-width: 132px; }
.career-match__details { margin-top: 8px; }
.career-match__analysis { max-width: 58em; white-space: pre-line; }

@media (max-width: 640px) {
  .career-match__again, .career-match__rank-head { align-items: stretch; }
  .career-match__again { display: grid; }
  .career-match__again .btn { justify-self: start; min-height: 44px; }
  .career-match__rank-head { display: grid; }
  .match-fit { width: 100%; }
}
</style>
