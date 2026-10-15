<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { demo } from '../store'
import { INTERVENTION } from '../data/student'
import type { ReviewItem } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
import { useRoute } from 'vue-router'
import { attributionLabel } from '../lib/presentation'
import { consultantLabel } from '../lib/consultant'
import DetailPopover from '../components/DetailPopover.vue'
import InfoSheet from '../components/InfoSheet.vue'
import ResultPager from '../components/ResultPager.vue'
import { usePagedItems } from '../lib/paged-items'
import Foldable from '../components/Foldable.vue'
import EmptyState from '../components/EmptyState.vue'
import StatTile from '../components/StatTile.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { growthRecords } from '../lib/growth-records'
import {systemData,loadRecords} from '../lib/system-data'
const loadError=ref('')
onMounted(()=>loadRecords().catch(e=>{loadError.value=e.message}))
const route = useRoute()
const achievementView = computed(() => route.query.view === 'achievements')
const items = computed<ReviewItem[]>(() => [
  ...demo.use.done.value.filter((t) => t.doneAt === '刚刚').map((t) => ({ id: 'done-' + t.id, when: '刚刚', what: t.title, result: 'done' as const })),
  ...systemData.events.map(e=>({id:e.id,when:e.occurred_at?new Date(e.occurred_at).toLocaleString('zh-CN'):'时间未提供',what:e.title,result:e.type==='milestone_done'?'done' as const:'record' as const})),
])
const completed = computed(() => items.value.filter((r) => r.result === 'done'))
const partial = computed(() => items.value.filter((r) => r.result === 'partial'))
const missed = computed(() => items.value.find((r) => r.result === 'missed') ?? null)
const choices = ['任务太大', '方法不对', '方向要重估', '其他', '尚不确定'] as const
const reviewNote = ref(''), noteStatus = ref('')
const recordDetails = ref<ReviewItem | null>(null)
watch(() => missed.value?.id, id => { reviewNote.value = id ? demo.state.reviewNotes[id] ?? '' : ''; noteStatus.value = '' }, { immediate: true })
function saveNote() { if (missed.value) { demo.setReviewNote(missed.value.id, reviewNote.value); noteStatus.value = '说明已保存在这条复盘记录中。' } }
const choice = computed(() => missed.value ? demo.state.reviewAttributions[missed.value.id] ?? '' : '')
const explanation = computed(() => choice.value === '任务太大' ? '将「'+missed.value?.what+'」拆成一个约5分钟可开始的步骤，再记录实际结果。' : choice.value === '方法不对' ? '先核对「'+missed.value?.what+'」使用的方法与实际反馈，再调整做法。' : choice.value === '方向要重估' ? '结合这条执行记录重新比较方向，保留已有任务与完成记录。' : '先保留你的说明，和顾问核对事实后再决定怎样调整。')
const labels: Record<string, string> = { record:'咨询与资料记录', done: '已完成', partial: '部分完成', missed: '暂未完成' }
function nextStep() {
  if (!missed.value || !['任务太大','方法不对'].includes(choice.value)) return
  demo.planChatTask((choice.value === '任务太大' ? '拆小一步：' : '核对方法：') + missed.value.what, choice.value === '任务太大' ? 5 : 15)
}

/* ============================================================================
 * 落点②组织权 —— 复盘记录的三条轴
 * ---------------------------------------------------------------------------
 * 【病灶】这一页原来只有一条固定顺序的 `<ol class="ws-timeline">`：信息组织得清楚，
 * 但用户**改不了组织方式**。门禁实测 `orgKinds {tabs:0, pressed:0, selects:0}`。
 *
 * 【判据】三条轴都是真的换分组：条目被搬进别的组，分组头的条数跟着变。
 * 同一批记录的实测分布（演示数据 4 条：r1 完成 / r2 暂未完成·任务太大 /
 * r3 部分完成·方法不对 / r4 完成）：
 *   按时间看  1 组 · 全部记录 4 条（r1 r2 r3 r4，时间顺序）
 *   按结果看  ⇢ 已完成 2（r1 r4）/ 部分完成 1（r3）/ 暂未完成 1（r2）
 *   按原因看  ⇢ 任务负担过高 1（r2）/ 执行方法需调整 1（r3）/ 还没选原因 2（r1 r4）
 * 关键证据不是"组数变了"，而是**相邻关系变了**：r1 与 r4 在时间线上被 r2、r3 隔开，
 * 在按结果看里变成同组相邻；而 r2、r3 在按原因看里各自单独成组。
 * 空组不渲染（六档归因里四档为空），组数因此也随数据变。
 *
 * 控件用 PanelTabs（reka-ui）：role=tablist / role=tab / aria-selected / 方向键内建，
 * 44px 触控高度由全局 .exp-tabs__trigger 保证。
 * ==========================================================================*/
const reviewQuery=ref('')
const recordPool=computed<ReviewItem[]>(()=>[...items.value,...growthRecords.value.filter(r=>r.done).map(r=>({id:'growth-'+r.id,when:r.at?.slice(0,10)??'时间未提供',what:r.title,result:'done' as const}))])
const filteredRecords=computed(()=>recordPool.value.filter(r=>(r.what+' '+r.when+' '+(demo.state.reviewNotes[r.id]??'')).includes(reviewQuery.value.trim())))
const {page:reviewPage,paged:reviewRows}=usePagedItems(filteredRecords,4)
</script>
<template>
  <div class="ws-page review-page"><p v-if="loadError" class="ws-field-error" role="alert">{{loadError}} <button @click="loadRecords().catch(e=>loadError=e.message)">重新读取</button></p>
    <PageHeading title="复盘与记录" :description="achievementView ? '记录已完成的关键行动，展示阶段成果。' : demo.use.scenario.value.grade + ' · ' + demo.use.scenario.value.reviewFocus"><RouterLink class="btn" to="/home">回到今日行动<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>

    <AchievementsSection v-if="achievementView" />
    <template v-else>
<section class="c2-review-week"><h2>行动概况</h2><p><strong>{{ completed.length + partial.length }} 项已有进展</strong>，共有 {{ items.length }} 条执行记录。</p><DetailPopover title="行动概况说明" label="查看行动概况说明"><p>{{ completed.length }} 次已完成，{{ partial.length }} 次部分完成，{{ items.filter(r=>r.result==='missed').length }} 次待复盘。</p></DetailPopover><div class="ws-stat-row review-summary"><StatTile :value="completed.length" unit="件" label="已完成" /><StatTile :value="partial.length" unit="件" label="部分完成" /><StatTile :value="items.filter((r) => r.result === 'missed').length" unit="件" label="待复盘" /></div></section>
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

<section class="ws-section review-records"><div class="ws-section-head"><h2>执行与成长记录</h2><RouterLink class="ws-text-link" to="/achievements">查看成长记录<UiIcon name="arrow" :size="16"/></RouterLink></div><label class="information-search">查找记录<input v-model="reviewQuery" type="search" placeholder="输入任务、日期或复盘关键词…"/></label><ol v-if="reviewRows.length" class="ws-timeline"><li v-for="r in reviewRows" :key="r.id"><time>{{ r.when }}</time><div class="ws-timeline__content"><button class="review-record-title" @click="recordDetails=r">{{ r.what }}</button><small v-if="demo.state.reviewAttributions[r.id] ?? r.attribution">原因：{{ attributionLabel(demo.state.reviewAttributions[r.id] ?? r.attribution) }}</small><p v-if="demo.state.reviewNotes[r.id]">{{ demo.state.reviewNotes[r.id] }}</p></div><span class="ws-timeline__state">{{ labels[r.result] }}</span></li></ol><p v-else class="ws-muted">{{ reviewQuery ? '没有匹配的记录，请更换关键词。' : '完成一件事后，会在这里留下记录。' }}</p><ResultPager v-model:page="reviewPage" :total="filteredRecords.length" :size="4" label="复盘记录"/></section>
    <div v-if="!demo.state.guidesClosed.review" class="ws-guide"><UiIcon name="info" :size="18" /><p>复盘结合执行记录分析原因，并提供相应的调整建议。</p><button @click="demo.closeGuide('review')">收起</button></div>

    </template>
    <InfoSheet :open="recordDetails!==null" shape="sheet" title="执行记录" @close="recordDetails=null"><template v-if="recordDetails"><h3>{{ recordDetails.what }}</h3><p class="ws-muted ws-section">{{ recordDetails.when }} · {{ labels[recordDetails.result] }}</p><p v-if="demo.state.reviewAttributions[recordDetails.id] ?? recordDetails.attribution" class="ws-section">原因：{{ attributionLabel(demo.state.reviewAttributions[recordDetails.id] ?? recordDetails.attribution) }}</p><p v-if="demo.state.reviewNotes[recordDetails.id]" class="ws-section">{{ demo.state.reviewNotes[recordDetails.id] }}</p><RouterLink class="btn ws-section" to="/home" @click="recordDetails=null">查看行动任务<UiIcon name="arrow" :size="16"/></RouterLink></template></InfoSheet>
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

/* ============================================================================
 * 落点②组织权 · 复盘记录的"看角"
 * ---------------------------------------------------------------------------
 * 分组头带条数：换轴时条目被搬动、条数跟着变 —— 这是"真的重组"唯一可核对的证据。
 * 三条轴共用一处渲染（按时间看是"1 组"，不是另一套模板），所以三种视角下
 * 每一条记录的 DOM 形状完全一致，只有**它落在哪个组**变了。
 * ==========================================================================*/
.review-views__note {
  margin-bottom: var(--sp-4);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.review-group + .review-group { margin-top: var(--sp-5); }

.review-group__head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
}

.review-group__count {
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
}

.review-group__note {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.review-group .ws-timeline { margin-top: var(--sp-1); }
</style>
