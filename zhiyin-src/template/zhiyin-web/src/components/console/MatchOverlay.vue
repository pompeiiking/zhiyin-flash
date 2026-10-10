<script setup lang="ts">
import { ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import GlyphIcon from '@/components/ui/GlyphIcon.vue'
import MatchMatrix from '@/components/charts/MatchMatrix.vue'
import { matchTask, type MatchResult } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'
import { acceptCareerMatch } from '@/api/client'
import { isMatchAccepted, saveMatchAcceptance } from '@/lib/careerMatch'

const session = useSessionStore()
const saving = ref(false)
const error = ref('')
const statusLabel = { reported: '有自述或经历，待核验', studied: '只有课程线索', unknown: '尚缺相关材料' }
function pickCell(track: string, skill: string, result: MatchResult) {
  const cell = result.cells.find((c) => c.track === track && c.skill === skill)
  if (!cell) return
  session.openDrawer(`${track} · ${skill}`, result.method, [
    { source: '职业要求原文', detail: cell.requirement, at: cell.fetched_at },
    { source: '来源链接', detail: cell.source_url, at: cell.fetched_at },
    ...cell.student_evidence.map((detail) => ({ source: '你的材料', detail })),
    { source: '证据状态', detail: statusLabel[cell.status] },
  ])
}
async function decide(kind: 'accept' | 'dismiss', result: MatchResult) {
  if (saving.value) return
  error.value = ''
  if (kind === 'dismiss') {
    session.dismissSuggestion(result.recommendation_id)
    return
  }
  saving.value = true
  try {
    await saveMatchAcceptance(result, acceptCareerMatch, (plan) => session.applyActionPlan(plan))
    session.acceptSuggestion(result.recommendation_id)
    session.openDrawer('推荐任务已保存', '可以到行动计划查看并安排时间',
      result.actions.map((text) => ({ source: '已保存的任务', detail: text })))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '这次任务没有保存成功，请稍后重新采纳。'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Overlay
    title="匹配与推荐"
    subtitle="对照职业库里的职业条目 · 每格都能点开看依据"
    from="match"
    @close="session.closeOverlay()"
  >
    <!--
      矩阵和推荐必须在同一个 AiFrame 里：矩阵的每一格都来自这次生成的 cells，
      分开写就会出现"图是空的、右边有结论"这种对不上的情况。
    -->
    <AiFrame :task="() => matchTask() as never" class="match__frame">
      <template #default="{ data }">
        <div v-if="data" class="match">
          <div class="match__left sheet">
            <MatchMatrix
              :cells="(data as MatchResult).cells"
              :tracks="[...new Set((data as MatchResult).cells.map((c) => c.track))]"
              @pick="(track, skill) => pickCell(track, skill, data as MatchResult)"
            />
          </div>

          <aside class="match__right sheet">
            <div class="res">
              <h3 class="res__head editorial">{{ (data as MatchResult).recommend.title }}</h3>
              <p class="res__body">{{ (data as MatchResult).recommend.body }}</p>

              <p class="res__body">{{ (data as MatchResult).method }}</p>
               <span class="label">方向与证据对照</span>
              <ul class="rank">
                <li v-for="(r, i) in (data as MatchResult).ranking" :key="r.track">
                  <span class="rank__n mono">{{ i + 1 }}</span>
                  <span class="rank__name">{{ r.track }}</span>
                   <span class="rank__why">{{ r.why }}</span>
                  <span class="rank__gap">{{ r.gap }}</span>
                </li>
              </ul>

              <span class="label">职业要求原文</span>
              <ul class="because">
                <li v-for="(b, i) in (data as MatchResult).recommend.because" :key="i">{{ b }}</li>
              </ul>

              <ul class="because">
                 <li v-for="cell in (data as MatchResult).cells" :key="cell.track + cell.skill">
                   <a :href="cell.source_url" target="_blank" rel="noopener noreferrer">{{ cell.track }} · {{ cell.skill }} · 查看来源</a>
                   <span>（抓取：{{ cell.fetched_at }}）</span>
                 </li>
               </ul>
               <span class="label">采纳后加入行动计划的任务（时间待安排）</span>
               <ul class="because"><li v-for="action in (data as MatchResult).actions" :key="action">{{ action }}</li></ul>
               <p v-if="error" role="alert">{{ error }}</p>
               <div class="act">
                <button class="btn primary" type="button" :disabled="saving || isMatchAccepted(data as MatchResult, session.actionPlan)" :aria-pressed="isMatchAccepted(data as MatchResult, session.actionPlan)" @click="decide('accept', data as MatchResult)">
                  <template v-if="isMatchAccepted(data as MatchResult, session.actionPlan)">已采纳 <GlyphIcon name="check" :size="13" /></template>
                  <template v-else>{{ saving ? '正在保存任务' : '采纳这条推荐' }}</template>
                </button>
                <button class="btn ghost" type="button" :disabled="saving || isMatchAccepted(data as MatchResult, session.actionPlan)" :aria-pressed="session.dismissedSuggestions.includes((data as MatchResult).recommendation_id)" @click="decide('dismiss', data as MatchResult)">
                  {{ session.dismissedSuggestions.includes((data as MatchResult).recommendation_id) ? '已否决' : '不适合我' }}
                </button>
              </div>
            </div>
          </aside>
        </div>
      </template>
    </AiFrame>
  </Overlay>
</template>

<style scoped>
/*
 * 两块薄片并排浮着（底板已经拿掉）：左边矩阵、右边结论。
 * 各自出纸、各自滚动 —— 原来它们只是铺在同一块大板上的两栏。
 */
.match__frame { flex: 1; min-height: 0; }
.match { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); gap: var(--s4); }
.match__left { overflow: auto; padding: var(--s4) var(--s5); }
.match__right { overflow: auto; padding: var(--s5); }

.res { display: flex; flex-direction: column; gap: var(--s3); }
.res__head { font-size: var(--t-h3); line-height: 1.45; }
.res__body { font-size: var(--fs-small); line-height: 1.8; color: var(--ink-2); }

.rank { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.rank li { display: grid; grid-template-columns: 18px 100px 1fr; align-items: center; gap: var(--s2); padding: 7px var(--s2); border-radius: var(--r-sm); }
.rank li:nth-child(odd) { background: var(--fill-subtle); }
.rank__n { color: var(--ink-3); }
.rank__name { font-size: var(--fs-small); color: var(--ink-1); }
.rank__bar { height: 6px; border-radius: 3px; background: var(--fill-hover); overflow: hidden; }
.rank__bar i { display: block; height: 100%; background: var(--mk-green); border-radius: 3px; }
.rank__fit { color: var(--ink-2); text-align: right; }
.rank__gap { font-size: var(--t-xs); color: var(--warn); }

.because { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.because li { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7; padding-left: var(--s4); position: relative; }
.because li::before { content: "—"; position: absolute; left: 0; color: var(--mk-green); }

.act { display: flex; gap: var(--s2); padding-top: var(--s3); }

@media (max-width: 980px) {
  .match { grid-template-columns: minmax(0, 1fr); }
}
</style>
