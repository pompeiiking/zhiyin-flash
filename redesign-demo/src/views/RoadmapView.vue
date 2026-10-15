<script setup lang="ts">
import OverviewMetric from '../components/OverviewMetric.vue'
import { computed, ref } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'

import LiveActionPlan from '../components/LiveActionPlan.vue'
import AssetNotice from '../components/AssetNotice.vue'
import TaskList from '../components/TaskList.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import UiIcon from '../components/UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
import { taskOriginLabel } from '../lib/presentation'
import { DEMO_PHASE_TASK_IDS } from '../data/phase-tasks'
import SegMeter from '../components/SegMeter.vue'
import MeterRow, { formatScore01 } from '../components/charts/MeterRow.vue'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import SourceChip from '../components/SourceChip.vue'
import { PROFILE_FIELDS, REPORT_SECTIONS, THRESHOLD_COMPARE } from '../data/student'
import type { FieldSource } from '../data/types'
import type { ProfileSource } from '../api/backend-types'
const scenario = computed(() => demo.use.scenario.value)
const books = computed(() => ['计划拆下来的', '建议的', '自己写的', '关键节点'].map(label => ({ label, tasks: demo.state.tasks.filter(t => t.origin === label) })))
const pending = computed(() => [...demo.use.now.value, ...demo.use.waiting.value])
const stages = computed(() => scenario.value.milestones.map(m => ({ ...m, tasks: demo.state.tasks.filter(t => DEMO_PHASE_TASK_IDS[m.id]?.includes(t.id)) })))
const ungrouped = computed(() => pending.value.filter(t => !stages.value.some(s => s.tasks.some(item => item.id === t.id))))
/* 进度读数（MIGRATION §3.3 T1/T2）：分母取自同一批任务，进度条由 StatTile 自己长出来 */
const doneCount = computed(() => demo.use.done.value.length)
const totalCount = computed(() => pending.value.length + doneCount.value)
const stageDone = (tasks: { bucket: string }[]) => tasks.filter(t => t.bucket === 'done').length
/* 「按任务来源查看」原来是一行里套两层的 <details>（外层 .ws-context + 内层 v-for .ws-fold），
   是全站最该拆的一行（MIGRATION §1.3 A7/D6、审计"嵌套 3 层"的元凶）。
   这里按审计给的第二条路收成**一条筛选**：筛选行本身不是折叠层，选中哪一类就重组出哪一类任务。 */
const origin = ref<string | null>(null)
const originGroups = computed(() => books.value.filter(b => b.tasks.length))
const activeOrigin = computed(() => origin.value ?? originGroups.value[0]?.label ?? null)
const shownBook = computed(() => originGroups.value.find(b => b.label === activeOrigin.value) ?? null)
/* LiveActionPlan 正在读计划时，本页不先说"阶段计划还没有形成"（MIGRATION §4.1 K5：假空态） */
const planBusy = ref(false)

/* =============================================================================
 * G-02 右栏的数字来源 —— 全部是派生，没有一个是写死的。
 *
 * 靶子右栏（`.pg-doc__side` 实测 312×1204、23 条叶子文本）里那些数字是样张的演示数据；
 * 真实页按同一把尺子量真实状态，所以每一个量都指得出字段：
 *   · stagedTotal / stagedDone —— 三段按 `DEMO_PHASE_TASK_IDS` 挂上的**真实件数**与其中做完的件数。
 *     段数就是件数：`SegMeter` 的一根条 = 这一段上的一件任务，勾掉一件亮一段
 *     （靶子那三个 4 段 `.meter` 共 12 段是写死的装饰刻度，与本页这段的区别正在这里）。
 *   · unattachedDone —— 已完成、但不挂任何里程碑的件数（与主列「其他待推进任务」同一口径）。
 *   · waitingCount / remainingMinutes —— `bucket === 'waiting'` 的件**不进入**"还要动手"的分钟合计，
 *     与 TodayView 的剩余时间口径逐字一致（那边注释：等结果的条目不计入分钟数）。
 *   · untouchedStages —— 挂了任务、但一件都还没做完的段数。
 * 每一个都能回到 `src/data/scenarios.ts` / `src/data/student.ts` 的具体行，
 * 没有一个是"为了让右栏好看"凑出来的。
 * ========================================================================== */
const waitingCount = computed(() => demo.use.waiting.value.length)
const remainingMinutes = computed(() => demo.use.now.value.reduce((sum, t) => sum + t.minutes, 0))
const stagedTotal = computed(() => stages.value.reduce((sum, m) => sum + m.tasks.length, 0))
const stagedDone = computed(() => stages.value.reduce((sum, m) => sum + stageDone(m.tasks), 0))
const untouchedStages = computed(
  () => stages.value.filter((m) => m.tasks.length > 0 && stageDone(m.tasks) === 0).length,
)
const unattachedDone = computed(
  () => demo.use.done.value.filter((t) => !stages.value.some((m) => m.tasks.some((x) => x.id === t.id))).length,
)

/**
 * 画像里那两条与"时间"有关的处境（每周上限 / 课表空档）。
 * 口径与 `/home` 完全一致：**优先读本次服务回包，没有回包时退回演示画像池** ——
 * 两条路径说的是同一件事；把握度与来源一起带过来，交给 ConfidenceBadge / SourceChip
 * （§4.4：状态与不确定性显形，不把品质信息印成 12px 灰字）。
 */
const FIELD_SOURCE: Record<FieldSource, ProfileSource> = {
  学信网: 'record', 教务系统: 'record', 行为记录: 'record', 学校: 'record',
  对话: 'conversation', 本人填写: 'user_edit', 简历材料: 'resume',
  导师记录: 'mentor', 综合分析: 'assessment',
}
interface ProfileFact { label: string; value: string; source: ProfileSource; confidence: number | null; at: string | null }
function profileFact(key: string): ProfileFact | null {
  const live = backendDemo.state.liveWorkspace?.profile_panel?.fields?.find((f) => f.key === key)
  if (live) {
    return {
      label: live.label || key,
      value: typeof live.value === 'string' ? live.value : String(live.value ?? ''),
      source: live.source,
      confidence: typeof live.confidence === 'number' ? live.confidence : null,
      at: live.updated_at || null,
    }
  }
  const local = PROFILE_FIELDS.find((f) => f.key === key)
  if (!local) return null
  return {
    label: local.label,
    value: local.value,
    source: FIELD_SOURCE[local.source],
    confidence: local.confidence.bars / 3,
    at: local.noted,
  }
}
const timeFact = computed(() => profileFact('time'))
const scheduleFact = computed(() => profileFact('schedule'))
/** 报告里「时间取舍」那一条的第一句依据（data/student.ts:283）—— 口径句照抄原文，不另写文案 */
const timeEvidence = computed(
  () => REPORT_SECTIONS.find((s) => s.key === 'tradeoff')?.dimensions.find((d) => d.key === 'time')?.evidence[0] ?? null,
)
const currentStage = computed(() => {const index=stages.value.findIndex(s=>s.tasks.length ? stageDone(s.tasks)<s.tasks.length : s.progress<1);return index<0?stages.value.length:index+1})
const pipelineText=computed(()=>profileFact('pipeline')?.value??'')
const applications=computed(()=>pipelineText.value.match(/投(?:了)?\s*(\d+)/)?.[1]??'—')
const interviews=computed(()=>pipelineText.value.match(/(\d+)\s*(?:个|次)?\s*(?:回音|面试)/)?.[1]??'—')
const planToday = new Date('2026-10-14T00:00:00') // The labelled demo snapshot, not a live clock.
function deadlineLabel(stage:typeof stages.value[number]){if(!stage.dueAt)return '截止日期未提供';if(stage.progress>=1)return '已完成';const date=new Date(stage.dueAt+'T00:00:00');const days=Math.ceil((date.getTime()-planToday.getTime())/86400000);return days<0?'逾期 '+Math.abs(days)+' 天':days===0?'今天截止':'还剩 '+days+' 天'}
function blockedBy(stage:typeof stages.value[number]){return (stage.dependsOn??[]).map(id=>stages.value.find(s=>s.id===id)).filter(s=>s&&s.progress<1).map(s=>s!.title)}
</script>
<template>
<div class="ws-page plan-page journey-page"><PageHeading title="阶段计划" :description="scenario.grade + ' · ' + scenario.focus"><template #meta><p v-if="!backendDemo.state.liveAction" class="c2-page-meta"><span>计划基准日：2026-10-14；倒计时按此日计算</span></p></template><RouterLink class="btn btn--primary" to="/home">查看当前任务<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading><AssetNotice/><LiveActionPlan v-if="backendDemo.state.dataMode === 'service' || backendDemo.state.liveAction" @busy="planBusy = $event"/><template v-if="!backendDemo.state.liveAction">
<!-- 空态：`.ws-empty` → EmptyState（MIGRATION §4.2 E4）。整块正文被顶掉，所以显式 heading-level="2"（H5）。 -->
<section v-if="!backendDemo.state.planAvailable" class="plan-empty" :aria-busy="planBusy"><SkeletonBlock v-if="planBusy" variant="list" :lines="3"/><EmptyState v-else kind="report" :heading-level="2" :next="false" title="阶段计划还没有形成" description="在咨询中明确方向后，再安排阶段目标和任务。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><button class="ws-text-button" type="button" @click="backendDemo.loadPlanSample()">查看阶段计划示例</button></EmptyState></section>
<!-- G-02：主列 + 右栏。两列与粘性**不在这里重写**：根上的 `journey-page` 让本页加入
     journey.css 里那套形状（`.journey-page .journey-action-grid` 是 `minmax(0,1fr) 312px`，
     `.journey-page .journey-action-aside` 是 `position:sticky`），与 /home 逐值同构 ——
     这正是"同一套做法复制到 /plan"的意思；页面各自不同的只有下面 aside 里的内容。 -->
<template v-else>
<div class="journey-action-grid">
<div class="journey-action-main">
<section class="c2-profile-stats" aria-label="阶段计划概览"><OverviewMetric label="当前阶段"><template #value><strong>{{ currentStage }}</strong><small>/ {{ stages.length }} 步</small></template><p>从当前目标开始，再接上下一阶段</p></OverviewMetric><OverviewMetric label="任务已完成"><template #value><strong>{{ doneCount }}</strong><small>/ {{ totalCount }} 条</small></template><p>{{ pending.length }} 件仍在推进，完成记录独立保留</p></OverviewMetric><OverviewMetric label="岗位申请"><template #value><strong>{{ applications }}</strong><small>家</small></template><p>{{ pipelineText || '还没有可核对的投递记录' }}</p></OverviewMetric><OverviewMetric label="面试 / 回应"><template #value><strong>{{ interviews }}</strong><small>次</small></template><p>取自投递记录，没有提供时保留为空</p></OverviewMetric></section>
<!-- 阶段：当前阶段（i===0）static＝永远可见（审计"当前阶段默认收起＝用户看不到自己该做什么"）；
     其余阶段保留可折叠、但默认展开（审计"第二三阶段默认一屏看不到"）。两者同一形状，
     LiveActionPlan 的阶段头用同一套规则，/plan 与 /home 不再漂移。 -->
<section class="plan-stages c2-plan-surface"><h2>{{ stages.length }} 步怎么接力</h2><Foldable v-for="(m,i) in stages" :key="m.id" variant="group" :static="i === 0" :default-open="i > 0" :title="m.title"><template #title><span class="plan-stage__title"><span class="plan-stage__mark" aria-hidden="true" /><span class="plan-stage__copy"><strong>{{ m.title }}</strong></span><span class="c2-stage-reading"><b>{{ Math.round(m.progress*100) }}%</b><small>{{ m.window }}</small></span></span></template><p class="c2-stage-window"><time v-if="m.dueAt" :datetime="m.dueAt">{{ m.window }}</time><span v-else>{{ m.window }}</span><strong :class="{'ws-attention':deadlineLabel(m).startsWith('逾期')}">{{ deadlineLabel(m) }}</strong></p><p>{{ m.note }}</p><p class="c2-stage-handoff">{{ m.handoff || '完成这一段后，继续核对下一步的条件。' }}</p><p v-if="blockedBy(m).length" class="c2-proof-note">前一步「{{ blockedBy(m).join('、') }}」还没完成。后一步的期限仍保留，请先核对正在沿用的材料。</p><div class="c2-stage-progress" role="progressbar" :aria-valuenow="Math.round(m.progress*100)" aria-valuemin="0" aria-valuemax="100" :aria-label="m.title"><i :style="{width:m.progress*100+'%'}"/></div><p class="c2-stage-window">挂 {{ m.tasks.length }} 条任务 · 完成 {{ stageDone(m.tasks) }} 条。任务完成情况与阶段目标进度分别保留。</p><Foldable v-if="m.tasks.length" variant="inline" :title="'查看这一步的 ' + m.tasks.length + ' 件任务'"><TaskList :items="m.tasks"/></Foldable><p v-else class="ws-muted">此阶段尚未关联执行任务。</p><RouterLink class="ws-text-link" :to="'/chat?topic=' + encodeURIComponent(m.title)">讨论本阶段的下一步<UiIcon name="arrow" :size="16" /></RouterLink></Foldable></section><section v-if="ungrouped.length" class="ws-section"><h2 class="ws-section-title">其他待推进任务</h2><TaskList :items="ungrouped"/></section>
<section class="plan-sources ws-section"><h2 class="ws-section-title">按任务来源查看</h2><div class="plan-sources__filter" role="group" aria-label="按任务来源筛选"><button v-for="b in originGroups" :key="b.label" type="button" class="plan-sources__chip" :aria-pressed="activeOrigin === b.label" @click="origin = b.label">{{ taskOriginLabel(b.label) }}<b>{{ b.tasks.length }}</b></button></div><TaskList v-if="shownBook?.tasks.length" :items="shownBook.tasks"/><p v-else class="ws-muted ws-section">这一类还没有任务。</p></section>
</div>

<!-- ============================ 右栏（G-02） ============================
     靶子这一页的 `.pg-doc__side` 实测 312×1204、23 条叶子文本；真实页原来是 0 条 ——
     整块不存在，所以 /plan 读起来只剩一个阶段列表（报告 G-02）。
     下面四段覆盖靶子那三块（处境 / 缺口与刻度 / 代价）；靶子中间那一块在真实数据里
     是两件事（三段各挂了几件 · 三条刻度对照），所以拆成两段写，不硬塞成一块。 -->
<aside class="journey-action-aside">

  <!-- ① 处境：靶子那 5 行 `.kv`。真实数据里站得住的是这 5 行，每行指得出字段：
       data/scenarios.ts:98（现在这一步）/ :99（报告重点）/ :123（复盘关注），
       data/student.ts:79-85（每周上限）、:134-141（课表空档）。 -->
  <section aria-labelledby="planCtxT">
    <h2 id="planCtxT">{{ scenario.grade }}这一段的处境</h2>
    <div class="hm-kv">
      <div class="hm-kv__r"><span class="hm-kv__k">现在这一步</span><span class="hm-kv__v">{{ scenario.nextStep }}</span></div>
      <div class="hm-kv__r"><span class="hm-kv__k">报告重点</span><span class="hm-kv__v">{{ scenario.reportFocus }}</span></div>
      <div class="hm-kv__r"><span class="hm-kv__k">复盘关注</span><span class="hm-kv__v">{{ scenario.reviewFocus }}</span></div>
      <div v-if="timeFact" class="hm-kv__r">
        <span class="hm-kv__k">{{ timeFact.label }}</span>
        <span class="hm-kv__v">{{ timeFact.value }}<span class="plan-side__facts"><ConfidenceBadge :confidence="timeFact.confidence" /><SourceChip :source="timeFact.source" :at="timeFact.at" /></span></span>
      </div>
      <div v-if="scheduleFact" class="hm-kv__r">
        <span class="hm-kv__k">{{ scheduleFact.label }}</span>
        <span class="hm-kv__v">{{ scheduleFact.value }}<span class="plan-side__facts"><ConfidenceBadge :confidence="scheduleFact.confidence" /><SourceChip :source="scheduleFact.source" :at="scheduleFact.at" /></span></span>
      </div>
    </div>
    <!-- 口径句：出处是报告里「时间取舍」那一条的依据原文（data/student.ts:283） -->
    <p v-if="timeEvidence" class="hm-side__warn">{{ timeEvidence }}</p>
  </section>

  <!-- ② 段数 = 件数：靶子在这一页画了 3 个 4 段的 `.meter`（共 12 段，段数是写死的装饰刻度）。
       这里每一段的段数就是 `DEMO_PHASE_TASK_IDS` 挂上去的真实件数，亮段数就是其中做完的件数 ——
       也正是 SegMeter 头部注释写明的那条纪律（"/plan 每段 = 这一段挂的任务数"）。 -->
  <section aria-labelledby="planStagesT">
    <h2 id="planStagesT">这三步各挂了几件</h2>
    <p class="hm-side__n"><b>{{ stagedTotal }}</b> 条挂在这三段上</p>
    <p class="hm-side__d">{{ stages.length }} 段一共挂了 {{ stagedTotal }} 条任务，做完 {{ stagedDone }} 条；另有 {{ unattachedDone }} 条已完成的任务不挂任何里程碑。一根条 = 这一段上的一件任务，勾掉一件亮一段。</p>
    <div v-for="(m, i) in stages" :key="m.id" class="plan-side__stage">
      <div class="plan-side__stage-head"><span>{{ i + 1 }}. {{ m.title }}</span><span>{{ stageDone(m.tasks) }} / {{ m.tasks.length }}</span></div>
      <SegMeter v-if="m.tasks.length" :total="m.tasks.length" :lit="stageDone(m.tasks)" :label="`第 ${i + 1} 段挂着 ${m.tasks.length} 件任务，已完成 ${stageDone(m.tasks)} 件`" />
      <p v-else class="plan-side__empty">这一段还没有关联执行任务，所以它没有条可画（不画空轨道）。</p>
      <p class="plan-side__when">{{ m.window }}</p>
    </div>
  </section>

  <!-- ③ 缺口与刻度：靶子这块是 `.cmp` 三行（呈现能力 46 / 50、项目经历 20 / 60、专业对口 88 / 70）。
       真实数据里这三行就是 `THRESHOLD_COMPARE`（data/student.ts:306-310），画法直接复用报告页的
       MeterRow（`.mtr`："一把尺子上并排表达自身值 / 要求值 / 差距"）—— 同一条信息在两页同一把尺，
       不另造一个条（那正是"同一条规范散在多处"的开头）。 -->
  <section aria-labelledby="planGapT">
    <h2 id="planGapT">这三步都压在同一个缺口上</h2>
    <div class="plan-side__cmp">
      <MeterRow v-for="d in THRESHOLD_COMPARE" :key="d.label" :label="d.label" :value="d.mine / 100" :requirement="d.requirement / 100" :format="formatScore01" />
    </div>
    <ul class="plan-side__notes">
      <li v-for="d in THRESHOLD_COMPARE" :key="d.label"><b>{{ d.label }}</b>：{{ d.note }}</li>
    </ul>
    <RouterLink class="ws-text-link" to="/report">看报告里的这条对照<UiIcon name="arrow" :size="16" /></RouterLink>
  </section>

  <!-- ④ 代价可见：靶子那两段是写给"第一段的时间窗已经过了"的。真实页**不解析**时间窗字符串
       （`9 月 20 日前`这种话推出来的"逾期 N 天"没有任何字段支撑，那就是编数字），
       改成三个算得出来的事实：等待中的件数、还要动手的分钟、有几段一件都没做完。 -->
  <section aria-labelledby="planRiskT">
    <h2 id="planRiskT">现在最容易拖没的两件事</h2>
    <p><b>{{ waitingCount }} 件在「等待中」</b>：它们不计入"还要动手"的分钟数（与今日行动同一口径），所以清单上看不出它们和今天要做的事有什么区别。</p>
    <p>还要动手的是 <b>{{ remainingMinutes }} 分钟</b>；这三段里现在有 <b>{{ untouchedStages }} 段</b>一件都还没做完。计划不会自己顺延 —— 这一段不动，下一步的时间窗照走。</p>
    <RouterLink class="ws-text-link" to="/review">看执行记录里卡在哪一步<UiIcon name="arrow" :size="16" /></RouterLink>
  </section>
</aside>
</div>
<nav class="ws-related" aria-label="计划相关操作"><RouterLink to="/schedule">查看日历与课表<UiIcon name="calendar" :size="16" /></RouterLink><RouterLink to="/directions">调整方向<UiIcon name="directions" :size="16" /></RouterLink><RouterLink to="/review">复盘并调整任务<UiIcon name="review" :size="16" /></RouterLink></nav></template></template><p v-if="!backendDemo.state.liveAction" class="ws-demo-note">阶段目标关联具体任务；任务计数随完成与恢复更新。没有关联任务的阶段不显示推测进度。</p></div>
</template>
<style scoped>
/* ---- 读数：StatTile 是单列右对齐的，必须给一个**确定宽度**，进度条才不是"和文字一样宽" ----
   `flex: 1 1 auto` 是 2026-10-14 补的：主列收进 `.journey-action-grid` 之后，
   `.plan-current` 里的这一块原来是 shrink-to-fit，StatTile 的进度条实测只有 80×6
   （报告 G-02 记的就是这个"尺度过小"）。撑满之后由 `.plan-current__tile` 的
   max-width:320px 收口 —— 条宽从 80 回到 300 上下，读数才看得见。 */
.plan-current__main { display: flex; flex: 1 1 auto; flex-direction: column; gap: var(--sp-2); min-width: 0; }
.plan-current__tile { max-width: 320px; }
.plan-stage__title { display: flex; align-items: center; gap: var(--sp-4); width: 100%; min-width: 0; }
.plan-stage__mark { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border: 1px solid var(--c-border-strong); border-radius: var(--r-sm); font-size: var(--fs-14); color: var(--c-text-2); }
.plan-stage__copy { flex: 1; min-width: 0; }
.plan-stage__copy strong { display: block; font-size: var(--fs-16); font-weight: var(--fw-medium); line-height: 1.7; }
.plan-stage__tile { flex: none; width: min(220px, 46%); }

/* ---- 空态块（整块顶掉正文时的上下留白；EmptyState 自己不带外距） ---- */
.plan-empty { padding: var(--sp-6) 0; }

/* ---- 主列进 `.journey-action-grid` 之后，块自身的 margin-top 与列间距会叠起来
   （28 + 40 = 68px），所以把它们归零，只留列间距那一档。选择器带主列前缀 → 只作用于
   本页这一列，不动 redesign.css 里 `.plan-stages` / workspace.css 里 `.ws-section` 的共享规则。 ---- */
.journey-page .journey-action-main .plan-stages,
.journey-page .journey-action-main .ws-section { margin-top: 0; }

/* =============================================================================
 * 右栏（G-02）—— 这里只写 /plan 独有的两块形状。
 * 两列、粘性、段间分隔线、h2 / p / 链接的字号字重**全部**来自 journey.css 的
 * `.journey-page …`（与 /home 同一套），一个值都不在这里重写；否则同一条规范就有了
 * 第二份拷贝（journey.css:24-38 那段注释记的正是这件事）。
 * ========================================================================== */
.plan-side__facts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-1) var(--sp-2); margin-top: var(--sp-1); }
.plan-side__stage { margin-top: var(--sp-4); }
.plan-side__stage-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--sp-3); margin-bottom: var(--sp-2); font-size: var(--fs-14); font-weight: var(--fw-medium); line-height: var(--lh-snug); color: var(--c-text); }
.plan-side__stage-head > span:last-child { flex: none; color: var(--c-text-2); font-variant-numeric: tabular-nums; }
.plan-side__empty, .plan-side__when { font-size: var(--fs-12); }
.plan-side__cmp { display: flex; flex-direction: column; gap: var(--sp-5); margin-top: var(--sp-4); }
.plan-side__notes { display: flex; flex-direction: column; gap: var(--sp-2); margin-top: var(--sp-4); padding-left: 0; list-style: none; font-size: var(--fs-12); line-height: var(--lh-normal); color: var(--c-text-3); }
.plan-side__notes b { font-weight: var(--fw-semibold); color: var(--c-text-2); }

/* ---- 按来源：一条筛选。不做成 PanelTabs：那是页面级视图切换，
        这里是同一批任务的**重组**（DESIGN-LANGUAGE §4.2），而且它必须 ≥44px 触控目标 ---- */
.plan-sources__filter { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-3); }
.plan-sources__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 44px;
  padding: 0 var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: var(--fs-14);
  transition: background-color var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out), color var(--dur-1) var(--ease-out);
}
.plan-sources__chip:hover { border-color: var(--c-border-strong); color: var(--c-text); }
.plan-sources__chip[aria-pressed='true'] { background: var(--c-primary-weak); border-color: var(--c-primary-border); color: var(--c-primary); font-weight: var(--fw-medium); }
.plan-sources__chip b { font-weight: var(--fw-medium); color: var(--c-text-3); font-variant-numeric: tabular-nums; }
.plan-sources__chip[aria-pressed='true'] b { color: inherit; }

@media (prefers-reduced-motion: reduce) {
  .plan-sources__chip { transition: none; }
}
/* 窄屏：阶段头一行放不下"序号 + 标题 + 读数"，挤在一起标题会碎成三行。
   让读数换到自己的整行 —— 顺序不变（先标题后读数），进度条也因此拿满宽度。 */
@media (max-width: 480px) {
  .plan-stage__title { flex-wrap: wrap; row-gap: var(--sp-2); }
  .plan-stage__tile { width: 100%; }
}
</style>
