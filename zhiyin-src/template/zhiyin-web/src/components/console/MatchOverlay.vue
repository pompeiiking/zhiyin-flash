<script setup lang="ts">
import { computed } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import MatchMatrix from '@/components/charts/MatchMatrix.vue'
import { matchTask, type MatchResult } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'

/**
 * 学职网匹配与整体推荐。
 *
 * 这一页回答的是"我该往哪走"，而且必须比用户自己想的更具体：
 *   1. **对照基准是外面的** —— 学职网的职业条目，不是我们编的标准
 *   2. **矩阵让你看见缺口在哪一格** —— 差的不是"你不行"，是某一行某一列
 *   3. **推荐要能被否决** —— 采纳/否决本身就是信息，会回流进画像
 *
 * 没有"综合来看建议你考虑……"这种话：每一句判断都由矩阵里的某几格撑起来。
 */
const session = useSessionStore()

const decided = computed(() => ({
  accepted: session.acceptedSuggestions.includes('match-main'),
  dismissed: session.dismissedSuggestions.includes('match-main'),
}))

/**
 * 点开一格：这一格的**两边**分别从哪来 —— 要求和现状都从这次生成的 result 里取。
 * 不再去本地那张职业表里查：那会让"图上画的"和"点开说的"变成两份数据。
 */
function pickCell(track: string, skill: string, result: MatchResult, citations: { source: string; detail: string; confidence?: number; at?: string; origin?: string }[]) {
  const cell = result.cells.find((c) => c.track === track && c.skill === skill)
  const basis = citations.filter((c) => c.detail.includes(track) || c.detail.includes(skill))
  session.openDrawer(`${track} · ${skill}`, '这一格的两边分别从哪来', [
    { source: '外面的要求', detail: `职业库里，${track} 对「${skill}」要求 ${cell?.need ?? '—'}。`, confidence: 0.88, at: '' },
    { source: '你的现状', detail: `从你的课程与成绩折算出来是 ${cell?.have ?? '—'}。`, confidence: 0.9, at: '' },
    ...basis.map((c) => ({ source: c.source, detail: c.detail, confidence: c.confidence, at: c.at, origin: c.origin })),
    { source: '差在哪', detail: `差 ${Math.max(0, (cell?.need ?? 0) - (cell?.have ?? 0)).toFixed(2)} —— 差的不是"你不行"，是这一格还缺证据或还缺训练。`, confidence: 0.86, at: '这条判断' },
  ])
}

function decide(kind: 'accept' | 'dismiss') {
  if (kind === 'accept') {
    session.acceptSuggestion('match-main')
    session.openDrawer('已采纳这条推荐', '它会变成你今天的一件事', [
      { source: '动作', detail: '「补呈现能力」已排进下周四的空档，和课表对齐。', confidence: 1, at: '刚刚' },
      { source: '回流', detail: '你的采纳与完成情况会写回画像，下次推荐会更准。', confidence: 0.9, at: '规则' },
    ])
  } else {
    session.dismissSuggestion('match-main')
    session.openDrawer('已记下你的否决', '否决也是一条信息', [
      { source: '动作', detail: '这条推荐暂时收起，但我会记住你否掉了它。', confidence: 1, at: '刚刚' },
      { source: '为什么要记', detail: '如果你连续否掉同类推荐，说明我的判断模型偏了 —— 那要改的是我，不是你。', confidence: 0.86, at: '规则' },
    ])
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
      <template #default="{ data, citations }">
        <div v-if="data" class="match">
          <div class="match__left sheet">
            <MatchMatrix
              :cells="(data as MatchResult).cells"
              :tracks="[...new Set((data as MatchResult).cells.map((c) => c.track))]"
              @pick="(track, skill) => pickCell(track, skill, data as MatchResult, citations)"
            />
          </div>

          <aside class="match__right sheet">
            <div class="res">
              <h3 class="res__head editorial">{{ (data as MatchResult).recommend.title }}</h3>
              <p class="res__body">{{ (data as MatchResult).recommend.body }}</p>

              <span class="label">四条方向的匹配度</span>
              <ul class="rank">
                <li v-for="(r, i) in (data as MatchResult).ranking" :key="r.track">
                  <span class="rank__n mono">{{ i + 1 }}</span>
                  <span class="rank__name">{{ r.track }}</span>
                  <span class="rank__bar"><i :style="{ width: `${Math.round(r.fit * 100)}%` }" /></span>
                  <span class="rank__fit mono">{{ r.fit.toFixed(2) }}</span>
                  <span class="rank__gap">{{ r.gap }}</span>
                </li>
              </ul>

              <span class="label">这三句撑起了上面的判断</span>
              <ul class="because">
                <li v-for="(b, i) in (data as MatchResult).recommend.because" :key="i">{{ b }}</li>
              </ul>

              <div class="act">
                <button class="btn primary" type="button" :aria-pressed="decided.accepted" @click="decide('accept')">
                  {{ decided.accepted ? '已采纳 ✓' : '采纳这条推荐' }}
                </button>
                <button class="btn ghost" type="button" :aria-pressed="decided.dismissed" @click="decide('dismiss')">
                  {{ decided.dismissed ? '已否决' : '不适合我' }}
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
.rank li { display: grid; grid-template-columns: 18px 76px 1fr 40px auto; align-items: center; gap: var(--s2); padding: 7px var(--s2); border-radius: var(--r-sm); }
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
