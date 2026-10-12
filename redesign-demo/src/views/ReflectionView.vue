<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import { INTERVENTION, REVIEW_ITEMS } from '../data/student'
import type { ReviewItem } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
import { useRoute } from 'vue-router'
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
const explanation = computed(() => choice.value === '任务太大' ? '把「投 3 家」改成「先投 1 家」。只做 5 分钟，先有一个可以完成的开头。' : choice.value === '方法不对' ? '先换一种做法。把简历第一页的一段经历改成具体的行动与结果，再看有没有帮助。' : '重新看看三条路各自的依据与代价。方向可以改，已经做过的事会保留。')
const labels: Record<string, string> = { done: '已完成', partial: '推进了一半', missed: '暂未完成' }
function nextStep() {
  if (choice.value === '任务太大') demo.planChatTask('先投 1 家半导体方向的工艺岗', 5)
  else demo.planChatTask('把简历第一页的一段经历写具体', 15)
}
</script>
<template>
  <div class="ws-page">
    <PageHeading title="复盘与记录" :description="achievementView ? '只记录做过的事，不把停顿归到人身上。' : demo.use.scenario.value.grade + ' · ' + demo.use.scenario.value.reviewFocus"><RouterLink class="btn" to="/home">回到今日行动<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="desk-section-nav" aria-label="复盘视图"><RouterLink to="/review" :aria-current="!achievementView ? 'page' : undefined">推进与复盘</RouterLink><RouterLink to="/review?view=achievements" :aria-current="achievementView ? 'page' : undefined">完成记录</RouterLink></nav>
    <AchievementsSection v-if="achievementView" />
    <template v-else>
    <div class="ws-review-summary"><span><strong>{{ completed.length }}</strong>件已完成</span><span><strong>{{ partial.length }}</strong>件推进了一半</span><span><strong>{{ items.filter((r) => r.result === 'missed').length }}</strong>件需要一起想想</span></div>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <template v-if="missed"><h2 class="ws-section-title">下一次，怎样让这件事更好做？</h2><p style="margin-top: var(--sp-4)">上次没做成的，是「{{ missed.what }}」。</p><p class="ws-muted" style="margin-top: var(--sp-2)">归因归到任务、方法或方向，不归到人。</p><div class="ws-attributions" aria-label="复盘归因"><button v-for="a in choices" :key="a" :aria-pressed="choice === a" @click="demo.setReviewAttribution(missed.id, a)">{{ a }}</button></div><div class="ws-review-result" aria-live="polite"><p>{{ explanation }}</p><div class="ws-inline-actions"><RouterLink v-if="choice === '方向要重估'" class="btn btn--primary" to="/report?focus=choose">重新比较方向<UiIcon name="arrow" :size="16" /></RouterLink><button v-else class="btn btn--primary" @click="nextStep">把这一小步排进今天<UiIcon name="arrow" :size="16" /></button><RouterLink class="ws-text-link" to="/chat">也可以聊聊</RouterLink></div></div></template>
        <div v-else class="ws-empty"><h2 class="ws-section-title">{{ completed.length ? '已经做过的事，值得留一份记录' : '先做一小步，再回来看看' }}</h2><p>复盘从真实行动开始。没发生的事，不需要提前给自己评价。</p><RouterLink class="btn btn--primary" to="/home">看看今天这一件</RouterLink></div>
      </section>
      <aside class="ws-aside"><section><h2>你已经推进的事</h2><ul v-if="completed.length" class="ws-mini-list"><li v-for="r in completed.slice(0, 4)" :key="r.id">{{ r.what }}<p class="ws-muted">{{ r.when }}</p></li></ul><p v-else>完成第一件事后，会在这里看到它。</p></section><section><h2>卡住时，也有人接着你</h2><p>做不动可以拆小、换方法或改方向。不是每一次停顿，都要靠更用力来解决。</p><button class="ws-text-button" @click="demo.openIntervention()">看看一次陪伴提醒<UiIcon name="arrow" :size="16" /></button><details class="ws-fold"><summary>什么时候会主动提醒<UiIcon name="chevron" :size="16" /></summary><ul class="ws-mini-list"><li v-for="r in INTERVENTION.rules" :key="r">{{ r }}</li></ul><p class="ws-muted">能主动开口的，只有{{ INTERVENTION.host }}。</p></details></section></aside>
    </div>
    <section class="ws-paper ws-section"><div class="ws-section-head"><div><h2>这一轮发生了什么</h2><p>只记录事实与时间，完成状态可以在今日任务里恢复。</p></div></div><ol v-if="items.length" class="ws-timeline"><li v-for="r in items" :key="r.id"><time>{{ r.when }}</time><div class="ws-timeline__content">{{ r.what }}<small v-if="demo.state.reviewAttributions[r.id] ?? r.attribution">归到：{{ demo.state.reviewAttributions[r.id] ?? r.attribution }}</small></div><span class="ws-timeline__state">{{ labels[r.result] }}</span></li></ol><p v-else class="ws-muted">完成一件事，就会留下第一条记录。</p></section>
    <div v-if="!demo.state.guidesClosed.review" class="ws-guide"><UiIcon name="info" :size="18" /><p>先看你推进了什么，再决定下一步怎样更好做。选择一个原因，会得到对应的行动建议。</p><button @click="demo.closeGuide('review')">收起</button></div>
    <p class="ws-demo-note">历史复盘为预置示例；当前演示里刚完成的任务会加入记录。</p>
    </template>
  </div>
</template>
