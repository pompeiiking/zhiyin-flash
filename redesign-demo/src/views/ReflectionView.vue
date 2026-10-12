<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import { INTERVENTION, REVIEW_ITEMS } from '../data/student'
import type { ReviewItem } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
import { useRoute } from 'vue-router'
import { attributionLabel } from '../lib/presentation'
import { consultantLabel } from '../lib/consultant'
const route = useRoute()
const achievementView = computed(() => route.query.view === 'achievements')
const items = computed<ReviewItem[]>(() => [
  ...demo.use.done.value.filter((t) => t.doneAt === '刚刚').map((t) => ({ id: 'done-' + t.id, when: '刚刚', what: t.title, result: 'done' as const })),
  ...(demo.state.account === 'fresh' ? [] : REVIEW_ITEMS),
])
const completed = computed(() => items.value.filter((r) => r.result === 'done'))
const partial = computed(() => items.value.filter((r) => r.result === 'partial'))
const missed = computed(() => items.value.find((r) => r.result === 'missed') ?? null)
const choices = ['任务太大', '方法不对', '方向要重估'] as const
const choice = computed(() => missed.value ? demo.state.reviewAttributions[missed.value.id] ?? missed.value.attribution ?? '任务太大' : '任务太大')
const explanation = computed(() => choice.value === '任务太大' ? '建议将 3 个岗位的申请任务拆分为单个岗位申请，先执行约 5 分钟的准备步骤。' : choice.value === '方法不对' ? '建议修订简历中的项目经历，明确职责、行动与成果，并根据投递反馈评估效果。' : '建议重新比较各方向的匹配依据与主要风险，调整方向时保留已有执行记录。')
const labels: Record<string, string> = { done: '已完成', partial: '部分完成', missed: '暂未完成' }
function nextStep() {
  if (choice.value === '任务太大') demo.planChatTask('先投 1 家半导体方向的工艺岗', 5)
  else demo.planChatTask('把简历第一页的一段经历写具体', 15)
}
</script>
<template>
  <div class="ws-page">
    <PageHeading title="复盘与记录" :description="achievementView ? '记录已完成的关键行动，展示阶段成果。' : demo.use.scenario.value.grade + ' · ' + demo.use.scenario.value.reviewFocus"><RouterLink class="btn" to="/home">回到今日行动<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="desk-section-nav" aria-label="复盘视图"><RouterLink to="/review" :aria-current="!achievementView ? 'page' : undefined">推进与复盘</RouterLink><RouterLink to="/review?view=achievements" :aria-current="achievementView ? 'page' : undefined">完成记录</RouterLink></nav>
    <AchievementsSection v-if="achievementView" />
    <template v-else>
    <div class="ws-review-summary"><span><strong>{{ completed.length }}</strong>件已完成</span><span><strong>{{ partial.length }}</strong>件部分完成</span><span><strong>{{ items.filter((r) => r.result === 'missed').length }}</strong>件待复盘</span></div>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <template v-if="missed"><h2 class="ws-section-title">未完成任务分析</h2><p style="margin-top: var(--sp-4)">待复盘任务：「{{ missed.what }}」。</p><p class="ws-muted" style="margin-top: var(--sp-2)">请选择影响执行的主要原因，查看调整建议。</p><div class="ws-attributions" aria-label="复盘归因"><button v-for="a in choices" :key="a" :aria-pressed="choice === a" @click="demo.setReviewAttribution(missed.id, a)">{{ attributionLabel(a) }}</button></div><div class="ws-review-result" aria-live="polite"><p>{{ explanation }}</p><div class="ws-inline-actions"><RouterLink v-if="choice === '方向要重估'" class="btn btn--primary" to="/directions">重新比较方向<UiIcon name="arrow" :size="16" /></RouterLink><button v-else class="btn btn--primary" @click="nextStep">添加调整任务<UiIcon name="arrow" :size="16" /></button><RouterLink class="ws-text-link" to="/chat">咨询调整方案</RouterLink></div></div></template>
        <div v-else class="ws-empty"><h2 class="ws-section-title">{{ completed.length ? '当前没有待复盘任务' : '暂无执行记录' }}</h2><p>完成行动任务后，可在此查看执行记录与复盘建议。</p><RouterLink class="btn btn--primary" to="/home">查看当前任务</RouterLink></div>
      </section>
      <aside class="ws-aside"><section><h2>近期完成任务</h2><ul v-if="completed.length" class="ws-mini-list"><li v-for="r in completed.slice(0, 4)" :key="r.id">{{ r.what }}<p class="ws-muted">{{ r.when }}</p></li></ul><p v-else>完成第一件事后，会在这里看到它。</p></section><section><h2>执行支持</h2><p>可通过拆分任务、调整方法或重新评估方向处理执行障碍。</p><button class="ws-text-button" @click="demo.openIntervention()">查看提醒示例<UiIcon name="arrow" :size="16" /></button><details class="ws-fold"><summary>主动提醒规则<UiIcon name="chevron" :size="16" /></summary><ul class="ws-mini-list"><li v-for="r in INTERVENTION.rules" :key="r">{{ r }}</li></ul><p class="ws-muted">主动提醒由{{ consultantLabel(INTERVENTION.host) }}提供。</p></details></section></aside>
    </div>
    <section class="ws-paper ws-section"><div class="ws-section-head"><div><h2>执行时间线</h2><p>只记录事实与时间，完成状态可以在今日任务里恢复。</p></div></div><ol v-if="items.length" class="ws-timeline"><li v-for="r in items" :key="r.id"><time>{{ r.when }}</time><div class="ws-timeline__content">{{ r.what }}<small v-if="demo.state.reviewAttributions[r.id] ?? r.attribution">原因：{{ attributionLabel(demo.state.reviewAttributions[r.id] ?? r.attribution) }}</small></div><span class="ws-timeline__state">{{ labels[r.result] }}</span></li></ol><p v-else class="ws-muted">完成一件事，就会留下第一条记录。</p></section>
    <div v-if="!demo.state.guidesClosed.review" class="ws-guide"><UiIcon name="info" :size="18" /><p>复盘结合执行记录分析原因，并提供相应的调整建议。</p><button @click="demo.closeGuide('review')">收起</button></div>
    <p class="ws-demo-note">历史复盘为预置示例；当前演示里刚完成的任务会加入记录。</p>
    </template>
  </div>
</template>
