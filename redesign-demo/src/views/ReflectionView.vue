<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { demo } from '../store'
import { INTERVENTION, REVIEW_ITEMS } from '../data/student'
import type { ReviewItem } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
import { useRoute } from 'vue-router'
import { attributionLabel } from '../lib/presentation'
import { consultantLabel } from '../lib/consultant'
import PanelTabs from '../components/PanelTabs.vue'
import Foldable from '../components/Foldable.vue'
import EmptyState from '../components/EmptyState.vue'
import StatTile from '../components/StatTile.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { growthRecords } from '../lib/growth-records'
const route = useRoute()
const achievementView = computed(() => route.query.view === 'achievements')
const items = computed<ReviewItem[]>(() => [
  ...demo.use.done.value.filter((t) => t.doneAt === '刚刚').map((t) => ({ id: 'done-' + t.id, when: '刚刚', what: t.title, result: 'done' as const })),
  ...(demo.state.account === 'fresh' ? [] : REVIEW_ITEMS),
])
const completed = computed(() => items.value.filter((r) => r.result === 'done'))
const weekDetail = ref('summary')
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
const REVIEW_VIEWS = [
  { key: 'source', label: '按来源' },
  { key: 'time', label: '按时间看' },
  { key: 'topic', label: '按主题' },
  { key: 'weight', label: '按对结论的贡献' },
  { key: 'result', label: '按结果看' },
  { key: 'reason', label: '按原因看' },
]
/* 与 AssessmentView 同理：PanelTabs 的 v-model 走 string，不写联合类型 */
const reviewView = ref('source')

/* ============================================================================
 * 打印必须按【默认轴】= 按时间看 —— 与 /report 同一条口径、同一套实现
 * ---------------------------------------------------------------------------
 * 【病灶】实测（`emulateMedia({media:'print'})`）：屏幕上切到「按原因看」再打印，
 * 打印稿的分组头是「任务负担过高 / 执行方法需调整 / 还没选原因」。
 * 打印稿的读者看不到 tab 条（`@media print` 里 `.exp-tabs__scroll { display:none }`，
 * experience.css:161），他读到的分组却取决于打印的人当时点了哪个视角 ——
 * 同一页记录，两个人印出来不一样，而纸上没有任何说明。
 *
 * 【口径】打印稿 = 这页默认长什么样：/review 默认「按时间看」，
 * 也就是一条从近到远的完整时间线（加看角之前的那一版）。
 *
 * 【实现】`matchMedia('print')` 为主（真实打印、刷新后接着打印、
 * `emulateMedia({media:'print'})` 三条路径都会翻），beforeprint/afterprint 为真机保险。
 * 实测坑：Playwright 的 emulateMedia **不派发** beforeprint/afterprint，
 * 只监听那一对事件的实现在这条尺子下会静默失效。
 * `reviewView`（用户的屏幕选择）一个字节都不动 —— 打印不许打乱屏幕状态。
 * ==========================================================================*/
const printMedia = ref(false)
let printQuery: MediaQueryList | null = null
function onPrintMediaChange(event: MediaQueryListEvent) { printMedia.value = event.matches }
function onBeforePrintMedia() { printMedia.value = true }
function onAfterPrintMedia() { printMedia.value = false }
onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  printQuery = window.matchMedia('print')
  printMedia.value = printQuery.matches
  printQuery.addEventListener('change', onPrintMediaChange)
  window.addEventListener('beforeprint', onBeforePrintMedia)
  window.addEventListener('afterprint', onAfterPrintMedia)
})
onBeforeUnmount(() => {
  printQuery?.removeEventListener('change', onPrintMediaChange)
  window.removeEventListener('beforeprint', onBeforePrintMedia)
  window.removeEventListener('afterprint', onAfterPrintMedia)
  printQuery = null
})
/** 这一页的默认轴：打印与"还没选过"都按它 */
const DEFAULT_REVIEW_VIEW = 'source'
/** 实际用于**渲染**的轴：打印时是默认轴，屏幕上是用户点的那个 */
const printAxis = computed(() => (printMedia.value ? DEFAULT_REVIEW_VIEW : reviewView.value))

/** 每条记录**当下**的归因：页面上改过的（reviewAttributions）优先于预置值 */
function reasonOf(id: string): string {
  return demo.state.reviewAttributions[id] ?? items.value.find((r) => r.id === id)?.attribution ?? ''
}

const RESULT_BUCKETS = [
  { key: 'done', title: '已完成', note: '这些已经发生，可以作为下一次的参照。' },
  { key: 'partial', title: '部分完成', note: '做了一部分 —— 记录里写着卡在哪一步。' },
  { key: 'missed', title: '暂未完成', note: '没做完的记录。原因可以在左栏选定。' },
]

/** 原因轴：前五档与左栏归因选项逐字同序，最后是"还没选原因"。 */
const REASON_BUCKETS = [
  { key: '任务太大', title: '任务负担过高', note: null },
  { key: '方法不对', title: '执行方法需调整', note: null },
  { key: '方向要重估', title: '方向需重新评估', note: null },
  { key: '其他', title: '其他原因', note: null },
  { key: '尚不确定', title: '还没弄清楚', note: null },
  { key: '', title: '还没选原因', note: '这些记录还没有归因；选定原因之后，它会移到对应的组里。' },
]

interface ReviewGroup { key: string; title: string; note: string | null; items: ReviewItem[] }
const recordPool = computed<ReviewItem[]>(() => [...items.value,...growthRecords.value.filter(r=>r.done).map(r=>({id:'growth-'+r.id,when:r.at?.slice(0,10)??'时间未提供',what:r.title,result:'done' as const}))])

const reviewGroups = computed<ReviewGroup[]>(() => {
  const all = recordPool.value
  if (printAxis.value === 'source') return [
    {key:'live',title:'本次执行留下的记录',note:'本次完成的任务。',items:all.filter(r=>r.id.startsWith('done-'))},
    {key:'sample',title:'预置复盘记录',note:'这份演示样张的原始复盘。',items:all.filter(r=>!r.id.startsWith('done-')&&!r.id.startsWith('growth-'))},
    {key:'growth',title:'成长与核验记录',note:'与周活动读数分别保留，避免重复计数。',items:all.filter(r=>r.id.startsWith('growth-'))},
  ].filter(group=>group.items.length)
  if (printAxis.value === 'time') return [...new Set(all.map(r=>r.when))].map(when=>({key:when,title:when,note:null,items:all.filter(r=>r.when===when)}))
  if (printAxis.value === 'topic') {
    const topicOf=(r:ReviewItem)=>r.id.startsWith('growth-')?growthRecords.value.find(g=>'growth-'+g.id===r.id)?.topic??'回头看':/简历|项目|材料/.test(r.what)?'材料与经历':/投|岗位|面试/.test(r.what)?'岗位与申请':'安排与探索'
    return [...new Set(all.map(topicOf))].map(title=>({key:title,title,note:null,items:all.filter(r=>topicOf(r)===title)}))
  }
  if (printAxis.value === 'weight') return [
    {key:'activity',title:'支撑这一周动手的判断',note:'摘要只计算执行记录，成长依据另列。',items:all.filter(r=>!r.id.startsWith('growth-')&&r.result!=='missed')},
    {key:'obstacle',title:'解释没有完成的那一次',note:'归因仍在具体任务上，不归到人。',items:all.filter(r=>r.result==='missed')},
    {key:'growth',title:'确认已经发生过的成长',note:'这些确认记录不重复计入本周动手次数。',items:all.filter(r=>r.id.startsWith('growth-'))},
  ].filter(group=>group.items.length)
  if (printAxis.value === 'result') {
    return RESULT_BUCKETS
      .map((b) => ({ key: b.key, title: b.title, note: b.note, items: all.filter((r) => r.result === b.key) }))
      .filter((g) => g.items.length > 0)
  }
  if (printAxis.value === 'reason') {
    return REASON_BUCKETS
      .map((b) => ({ key: b.key || 'none', title: b.title, note: b.note, items: all.filter((r) => reasonOf(r.id) === b.key) }))
      .filter((g) => g.items.length > 0)
  }
  return [{ key: 'all', title: '全部记录', note: null, items: all }]
})

/* 说明句跟着**渲染出来的那条轴**：打印时屏幕上那句话也换成默认轴的说法，
   否则"按原因看"的说明会留在纸上，与下面的分组自相矛盾。 */
const reviewAxisNote = computed(() => {
  if (printAxis.value === 'source') return `按来源重新分组：${recordPool.value.length} 条执行与成长记录；周活动只计算执行事实。`
  if (printAxis.value === 'topic') return `按正在说明的事情重新分组：同一批 ${recordPool.value.length} 条记录，内容没有更换。`
  if (printAxis.value === 'weight') return '把支撑动手、解释阻碍和确认成长的依据分别组织，避免重复计数。'
  const n = items.value.length
  const groups = reviewGroups.value.length
  if (printAxis.value === 'result') return `按完成结果重新分组：${groups} 组 · 共 ${n} 条；条目从时间线上搬进对应的组。`
  if (printAxis.value === 'reason') return `按你选的原因重新分组：${groups} 组 · 共 ${n} 条；还没归因的单独成组。`
  return `按发生时间从近到远排：共 ${n} 条。切换到「按结果看」或「按原因看」，同一批记录会被重新分组。`
})
</script>
<template>
  <div class="ws-page review-page">
    <PageHeading title="复盘与记录" :description="achievementView ? '记录已完成的关键行动，展示阶段成果。' : demo.use.scenario.value.grade + ' · ' + demo.use.scenario.value.reviewFocus"><RouterLink class="btn" to="/home">回到今日行动<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="desk-section-nav" aria-label="复盘视图"><RouterLink to="/review" :aria-current="!achievementView ? 'page' : undefined">推进与复盘</RouterLink><RouterLink to="/review?view=achievements" :aria-current="achievementView ? 'page' : undefined">完成记录</RouterLink></nav>
    <AchievementsSection v-if="achievementView" />
    <template v-else>
<section class="c2-review-week"><h2>这一周到底动了几次</h2><p>按下面这批记录计算：完成与部分完成都算动了手，未完成的保留当时的原因。</p><div class="c2-review-zoom" role="group" aria-label="本周复盘的阅读粒度"><button v-for="entry in [{key:'summary',label:'摘要'},{key:'detail',label:'细节'},{key:'raw',label:'原始记录'}]" :key="entry.key" :aria-pressed="weekDetail === entry.key" @click="weekDetail = entry.key">{{ entry.label }}</button></div><p v-if="weekDetail === 'summary'"><strong>{{ completed.length + partial.length }} 次动了手</strong>，这批共有 {{ items.length }} 条记录。没做完的那一件，从任务、方法或方向上核对原因。</p><p v-else-if="weekDetail === 'detail'">{{ completed.length }} 次已经完成，{{ partial.length }} 次做了一部分，{{ items.filter(r=>r.result==='missed').length }} 次还没有完成。<template v-if="missed">最近一次没有做完的是「{{ missed.what }}」，记录的原因是 {{ attributionLabel(demo.state.reviewAttributions[missed.id] ?? missed.attribution ?? '尚不确定') }}。</template></p><ul v-else><li v-for="item in items" :key="item.id"><time>{{ item.when }}</time> · {{ item.what }} · {{ labels[item.result] }}</li></ul>    <div class="ws-stat-row review-summary"><StatTile :value="completed.length" unit="件" label="已完成" /><StatTile :value="partial.length" unit="件" label="部分完成" /><StatTile :value="items.filter((r) => r.result === 'missed').length" unit="件" label="待复盘" /></div></section>
    <section class="ws-paper ws-section"><div class="ws-section-head"><div><h2>这 {{ recordPool.length }} 条记录，按什么看</h2><p>只记录事实与时间；同一批记录可以按时间、结果或原因重新分组。完成状态可以在今日任务里恢复。</p></div></div><PanelTabs v-model="reviewView" label="执行记录的视角" :items="REVIEW_VIEWS"><p class="review-views__note">{{ reviewAxisNote }}</p><template v-if="items.length"><section v-for="g in reviewGroups" :key="g.key" class="review-group"><h3 class="review-group__head">{{ g.title }}<span class="review-group__count">{{ g.items.length }} 条</span></h3><p v-if="g.note" class="review-group__note">{{ g.note }}</p><ol class="ws-timeline"><li v-for="r in g.items" :key="r.id"><time>{{ r.when }}</time><div class="ws-timeline__content">{{ r.what }}<small v-if="demo.state.reviewAttributions[r.id] ?? r.attribution">原因：{{ attributionLabel(demo.state.reviewAttributions[r.id] ?? r.attribution) }}</small><p v-if="demo.state.reviewNotes[r.id]" class="review-note">{{ demo.state.reviewNotes[r.id] }}</p></div><span class="ws-timeline__state">{{ labels[r.result] }}</span></li></ol></section></template><p v-else class="ws-muted">完成一件事，就会留下第一条记录。</p></PanelTabs></section>
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
