<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { demo } from '../store'
import { INTERVENTION, REVIEW_ITEMS } from '../data/student'
import type { ReviewItem } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
import { useRoute } from 'vue-router'
import { attributionLabel } from '../lib/presentation'
import { consultantLabel } from '../lib/consultant'
import Foldable from '../components/Foldable.vue'
import EmptyState from '../components/EmptyState.vue'
import StatTile from '../components/StatTile.vue'
import StatusBanner from '../components/StatusBanner.vue'
const route = useRoute()
const achievementView = computed(() => route.query.view === 'achievements')
const items = computed<ReviewItem[]>(() => [
  ...demo.use.done.value.filter((t) => t.doneAt === '刚刚').map((t) => ({ id: 'done-' + t.id, when: '刚刚', what: t.title, result: 'done' as const })),
  ...(demo.state.account === 'fresh' ? [] : REVIEW_ITEMS),
])
const completed = computed(() => items.value.filter((r) => r.result === 'done'))
const partial = computed(() => items.value.filter((r) => r.result === 'partial'))
const missed = computed(() => items.value.find((r) => r.result === 'missed') ?? null)
const choices = ['任务太大', '方法不对', '方向要重估', '其他', '尚不确定'] as const
const reviewNote = ref(''), noteStatus = ref('')
watch(() => missed.value?.id, id => { reviewNote.value = id ? demo.state.reviewNotes[id] ?? '' : ''; noteStatus.value = '' }, { immediate: true })
function saveNote() { if (missed.value) { demo.setReviewNote(missed.value.id, reviewNote.value); noteStatus.value = '说明已保存在这条复盘记录中。' } }
const choice = computed(() => missed.value ? demo.state.reviewAttributions[missed.value.id] ?? '' : '')
const explanation = computed(() => choice.value === '任务太大' ? '将「'+missed.value?.what+'」拆成一个约5分钟可开始的步骤，再记录实际结果。' : choice.value === '方法不对' ? '先核对「'+missed.value?.what+'」使用的方法与实际反馈，再调整做法。' : choice.value === '方向要重估' ? '结合这条执行记录重新比较方向，保留已有任务与完成记录。' : '先保留你的说明，和顾问核对事实后再决定怎样调整。')
const labels: Record<string, string> = { done: '已完成', partial: '部分完成', missed: '暂未完成' }
function nextStep() {
  if (!missed.value || !['任务太大','方法不对'].includes(choice.value)) return
  demo.planChatTask((choice.value === '任务太大' ? '拆小一步：' : '核对方法：') + missed.value.what, choice.value === '任务太大' ? 5 : 15)
}
</script>
<template>
  <div class="ws-page">
    <PageHeading title="复盘与记录" :description="achievementView ? '记录已完成的关键行动，展示阶段成果。' : demo.use.scenario.value.grade + ' · ' + demo.use.scenario.value.reviewFocus"><RouterLink class="btn" to="/home">回到今日行动<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="desk-section-nav" aria-label="复盘视图"><RouterLink to="/review" :aria-current="!achievementView ? 'page' : undefined">推进与复盘</RouterLink><RouterLink to="/review?view=achievements" :aria-current="achievementView ? 'page' : undefined">完成记录</RouterLink></nav>
    <AchievementsSection v-if="achievementView" />
    <template v-else>
    <div class="ws-stat-row review-summary"><StatTile :value="completed.length" unit="件" label="已完成" /><StatTile :value="partial.length" unit="件" label="部分完成" /><StatTile :value="items.filter((r) => r.result === 'missed').length" unit="件" label="待复盘" /></div>
    <section class="ws-paper ws-section"><div class="ws-section-head"><div><h2>执行时间线</h2><p>只记录事实与时间，完成状态可以在今日任务里恢复。</p></div></div><ol v-if="items.length" class="ws-timeline"><li v-for="r in items" :key="r.id"><time>{{ r.when }}</time><div class="ws-timeline__content">{{ r.what }}<small v-if="demo.state.reviewAttributions[r.id] ?? r.attribution">原因：{{ attributionLabel(demo.state.reviewAttributions[r.id] ?? r.attribution) }}</small><p v-if="demo.state.reviewNotes[r.id]" class="review-note">{{ demo.state.reviewNotes[r.id] }}</p></div><span class="ws-timeline__state">{{ labels[r.result] }}</span></li></ol><p v-else class="ws-muted">完成一件事，就会留下第一条记录。</p></section>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <template v-if="missed"><h2 class="ws-section-title">未完成任务分析</h2><p style="margin-top: var(--sp-4)">待复盘任务：「{{ missed.what }}」。</p><p class="ws-muted" style="margin-top: var(--sp-2)">请选择影响执行的主要原因，查看调整建议。</p><fieldset class="ws-attributions review-choices"><legend class="sr-only">复盘归因</legend><label v-for="a in choices" :key="a" :class="{'review-choice--on': choice === a}"><input type="radio" name="review-reason" :checked="choice === a" @change="demo.setReviewAttribution(missed.id, a)" />{{ attributionLabel(a) }}</label></fieldset><form class="ws-section" @submit.prevent="saveNote"><label class="ws-field">补充实际情况<textarea v-model="reviewNote" maxlength="500" rows="3" placeholder="发生了什么、试过什么，或者还不确定的原因…"/></label><button class="btn" type="submit">保存复盘说明</button></form><StatusBanner v-if="noteStatus" tone="success" class="ws-section" :message="noteStatus" @dismiss="noteStatus = ''" /><p v-if="!choice" class="ws-muted ws-section">还没有确认原因。也可以先和顾问讨论，再决定怎样调整。</p><div v-if="choice" class="ws-review-result" aria-live="polite"><p>{{ explanation }}</p><div class="ws-inline-actions"><RouterLink v-if="choice === '方向要重估'" class="btn btn--primary" to="/directions">重新比较方向<UiIcon name="arrow" :size="16" /></RouterLink><button v-else-if="choice==='任务太大'||choice==='方法不对'" class="btn btn--primary" @click="nextStep">添加调整任务<UiIcon name="arrow" :size="16" /></button><RouterLink class="ws-text-link" :to="'/chat?question='+encodeURIComponent('我想复盘：'+missed.what+'。'+reviewNote)">咨询调整方案</RouterLink></div></div></template>
        <EmptyState v-else class="ws-section" kind="review" :heading-level="2" :title="completed.length ? '当前没有待复盘任务' : '暂无执行记录'" description="完成行动任务后，可在此查看执行记录与复盘建议。" action-to="/home" action-label="查看当前任务" />
      </section>
      <div class="review-side">
        <section class="review-side__recent"><h2>近期完成任务</h2><ul v-if="completed.length" class="ws-mini-list"><li v-for="r in completed.slice(0, 4)" :key="r.id">{{ r.what }}<p class="ws-muted">{{ r.when }}</p></li></ul><p v-else>完成第一件事后，会在这里看到它。</p></section>
        <section class="review-side__support"><h2>执行支持</h2><p>可通过拆分任务、调整方法或重新评估方向处理执行障碍。</p><button class="ws-text-button" @click="demo.openIntervention()">查看提醒示例<UiIcon name="arrow" :size="16" /></button></section>
        <Foldable title="主动提醒规则" variant="inline"><ul class="ws-mini-list"><li v-for="r in INTERVENTION.rules" :key="r">{{ r }}</li></ul><p class="ws-muted">主动提醒由{{ consultantLabel(INTERVENTION.host) }}提供。</p></Foldable>
      </div>
    </div>

    <div v-if="!demo.state.guidesClosed.review" class="ws-guide"><UiIcon name="info" :size="18" /><p>复盘结合执行记录分析原因，并提供相应的调整建议。</p><button @click="demo.closeGuide('review')">收起</button></div>
    <p class="ws-demo-note">历史复盘为预置示例；当前演示里刚完成的任务会加入记录。</p>
    </template>
  </div>
</template>

<style scoped>
/* 三个读数是同一把尺（StatTile）：等宽分栏、窄屏落成单列 */
.review-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--sp-5); margin-bottom: var(--sp-3); }
@media (max-width: 760px) { .review-summary { grid-template-columns: minmax(0, 1fr); gap: var(--sp-4); } }
/* 右栏：近期完成 + 执行支持是主信息（static），只有"主动提醒规则"折一层 */
.review-side { display: grid; gap: var(--sp-6); align-content: start; min-width: 0; }
.review-side__recent h2, .review-side__support h2 { font-size: var(--fs-16); font-weight: var(--fw-semibold); }
.review-side__recent .ws-mini-list, .review-side__support p { margin-top: var(--sp-3); }
.review-side__support p { color: var(--c-text-2); font-size: var(--fs-14); line-height: 1.8; }
.review-side__support .ws-text-button { margin-top: var(--sp-3); }
</style>
