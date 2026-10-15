<script setup lang="ts">
import DetailPopover from '../components/DetailPopover.vue'
import { computed, ref } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'

import LiveActionPlan from '../components/LiveActionPlan.vue'
import TaskBrief from '../components/TaskBrief.vue'
import { backendDemo } from '../lib/backend-demo'
import AssetNotice from '../components/AssetNotice.vue'
import TaskList from '../components/TaskList.vue'
import EmptyState from '../components/EmptyState.vue'
import StatTile from '../components/StatTile.vue'
import SegMeter from '../components/SegMeter.vue'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import SourceChip from '../components/SourceChip.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import { taskOriginLabel } from '../lib/presentation'
import PanelTabs from '../components/PanelTabs.vue'
import { DEMO_PHASE_TASK_IDS } from '../data/phase-tasks'
import { PROFILE_FIELDS, REPORT_SECTIONS } from '../data/student'
import type { ProfileSource } from '../api/backend-types'

const smallest = computed(() => demo.use.smallestNow.value)
const group = ref('now')
const groups = computed(() => [
  { key: 'now', label: '其他待执行', items: demo.use.now.value.filter(t => t.id !== smallest.value?.id) },
  { key: 'waiting', label: '等待中', items: demo.use.waiting.value },
  { key: 'done', label: '已完成', items: demo.use.done.value },
])
const active = computed(() => groups.value.find((g) => g.key === group.value)!)
const lastDone = computed(() => demo.use.done.value.find((t) => t.id === demo.state.lastDoneId))
/* 执行记录那一段原本只有一句分母文案（"已完成 N 件任务…"）—— 换成 StatTile，
   读数和进度条一起长出来（MIGRATION §3.3 T8）。与 /plan 的"当前安排"是同一形状。 */
const doneCount = computed(() => demo.use.done.value.length)
const totalCount = computed(() => demo.use.done.value.length + demo.use.now.value.length + demo.use.waiting.value.length)
const addOpen = ref(false)
const title = ref('')
const minutes = ref(5)
const error = ref('')
function add() {
  if (!title.value.trim()) { error.value = '先写下你准备做什么。'; return }
  demo.planChatTask(title.value.trim(), minutes.value)
  title.value = ''; error.value = ''; addOpen.value = false; group.value = 'now'
}

/* =============================================================================
 * G-01 / G-08 的**数字来源** —— 全部是派生，没有一个是写死的。
 * 靶子那一栏写着"65 分钟 / 5 件里 1 件做完"（c2-hbu/_src/views/home.html:315），
 * 那是样张演示数据；真实页要按同一把尺子量真实状态，所以三个量都从 store 派生：
 *   · remainingMinutes = `bucket === 'now'` 的任务分钟合计
 *     （等结果那两条 `bucket === 'waiting'` 的分钟**不计入** —— 这正是靶子
 *      `.hm-side__d` 那句"等结果的那两条不进去"的口径，也和不做就能自圆其说的
 *      "剩余时间"区别开：它是"还要动手多久"，不是"清单还有多少条"）
 *   · lineTotal  = 这一批任务的总件数（`state.tasks.length`）
 *   · lineDone   = 其中 `bucket === 'done'` 的件数
 * 段数就是件数：勾掉一件 → lineDone +1 → 条亮一段、分钟数重算。没有任何一段是装饰刻度。
 * ========================================================================== */
const nowTasks = computed(() => demo.use.now.value)
const lineTotal = computed(() => demo.state.tasks.length)
const lineDone = computed(() => doneCount.value)
const remainingMinutes = computed(() => nowTasks.value.reduce((sum, t) => sum + t.minutes, 0))

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'] as const
/** 页头第一枚 tag 的日期：真的取当天，不写死"10 月 14 日" */
const todayLabel = computed(() => {
  const d = new Date()
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${WEEKDAYS[d.getDay()]}`
})

/**
 * 画像里那条「每周可投入」——**同时**是页头品质标与右栏来源的同一份数据。
 * 优先读本次服务回包（`liveWorkspace.profile_panel`），没有回包时退回演示画像池；
 * 两条路径给同一件事，不各说各话（把握度也一起带过来，供 ConfidenceBadge 用）。
 */
interface TimeFact { label: string; value: string; source: ProfileSource; confidence: number | null; at: string | null }
const timeFact = computed<TimeFact | null>(() => {
  const live = backendDemo.state.liveWorkspace?.profile_panel?.fields?.find((f) => f.key === 'time')
  if (live) {
    return {
      label: live.label || '每周可投入',
      value: typeof live.value === 'string' ? live.value : String(live.value ?? ''),
      source: live.source,
      confidence: typeof live.confidence === 'number' ? live.confidence : null,
      at: live.updated_at || null,
    }
  }
  const local = PROFILE_FIELDS.find((f) => f.key === 'time')
  if (!local) return null
  return { label: local.label, value: local.value, source: 'user_edit', confidence: local.confidence.bars / 3, at: local.noted }
})
/** 只印事实本身（"6 小时"），括号里的"待核对"交给紧挨着的 ConfidenceBadge 承担 */
function shortValue(raw: string): string {
  return raw.split(/[（(]/)[0]?.trim() || raw
}

/** 今天当前这一件挂在阶段计划的哪一段（`data/phase-tasks.ts` 的显式关联，不按标题猜） */
const focusMilestone = computed(() => {
  const id = smallest.value?.id
  if (!id) return null
  const msId = Object.keys(DEMO_PHASE_TASK_IDS).find((k) => DEMO_PHASE_TASK_IDS[k].includes(id))
  if (!msId) return null
  return demo.use.scenario.value.milestones.find((m) => m.id === msId) ?? null
})

/** 报告里「时间取舍」那一条 —— 它是"空课格不代表空闲"这句话的原始出处，不另写文案 */
const timeDimension = computed(() =>
  REPORT_SECTIONS.find((s) => s.key === 'tradeoff')?.dimensions.find((d) => d.key === 'time') ?? null,
)

/* =============================================================================
 * 课表空档：**从教务快照真算**，不是画一句"周三、周五下午各 2 小时"。
 * 口径：下午 = 第 5–8 节；某一天下午没有任何课 = 那半天是空的。
 * 只算周一–周五（周末不参与"今天还剩多少时间"的估算）。
 * 这也是"空课格不代表空闲"这句提醒的落点：数字算得出来，但它只是"没有课"。
 * ========================================================================== */
const AFTERNOON_PERIODS = [5, 6, 7, 8] as const
const freeAfternoons = computed(() => {
  const courses = backendDemo.state.academic?.courses
  if (!courses?.length) return []
  const out: { label: string; hours: number }[] = []
  for (let weekday = 1; weekday <= 5; weekday++) {
    const busy = new Set<number>()
    for (const c of courses) {
      if (c.weekday !== weekday) continue
      const from = c.start_period
      const to = c.end_period
      if (typeof from !== 'number' || typeof to !== 'number') continue
      for (let p = from; p <= to; p++) busy.add(p)
    }
    const freePeriods = AFTERNOON_PERIODS.filter((p) => !busy.has(p)).length
    if (freePeriods) out.push({ label: WEEKDAYS[weekday]!, hours: freePeriods / 2 })
  }
  return out
})
const freeAfternoonText = computed(() =>
  freeAfternoons.value.map((f) => `${f.label}下午 ${f.hours} 小时`).join('、'),
)
const academicAt = computed(() => backendDemo.state.academic?.imported_at ?? null)
</script>
<template>
  <div class="ws-page journey-page">
    <!-- 页头第 3 行（G-05）：靶子 `.pgh__meta` = 3 个事实 tag + 3 个品质标。
         这里给的是**真实字段**：今天的日期、今天可做的件数与分钟合计、这一批的完成数、
         以及画像里"每周可投入"那条（值 + 把握度 + 来源三件一起，缺一件就退回灰字）。 -->
    <PageHeading title="今日行动" description="从一件具体的小事开始，让想好的方向往前走。">
      <template #meta>
        <span class="tag">{{ todayLabel }}</span>
        <span class="tag">今天可做 {{ nowTasks.length }} 件 · 共 {{ remainingMinutes }} 分钟</span>
        <span class="tag">这一批 {{ lineDone }} / {{ lineTotal }} 件已完成</span>
        <span v-if="timeFact" class="tag">{{ timeFact.label }} {{ shortValue(timeFact.value) }}</span>
        <ConfidenceBadge v-if="timeFact" :confidence="timeFact.confidence" />
        <SourceChip v-if="timeFact" :source="timeFact.source" :at="timeFact.at" />
      </template>
      <RouterLink class="btn" to="/plan"><UiIcon name="path" :size="16" />看阶段计划</RouterLink>
    </PageHeading>
    <AssetNotice/><LiveActionPlan v-if="backendDemo.state.dataMode === 'service' || backendDemo.state.liveAction" today/><template v-if="!backendDemo.state.liveAction">
    <section v-if="lastDone" :key="lastDone.id" class="journey-complete" role="status">
      <span class="journey-complete__mark"><UiIcon name="check" :size="24" /></span>
      <div><h2>又完成了一步</h2><p>{{ lastDone.title }}</p></div>
      <button class="ws-text-button" @click="demo.reopenTask(lastDone.id)">恢复任务</button>
    </section>
    <div class="journey-action-grid">
      <div class="journey-action-main">
    <section v-if="smallest" class="c2-today-task"><header class="c2-today-task-head"><h2>当前优先任务</h2><span>今天 1 件</span></header><p class="c2-today-task-note">完成后可继续下一项任务。</p><div class="journey-focus">
      <div class="journey-focus__copy">
        <div class="c2-today-task-sources"><SourceChip :label="taskOriginLabel(smallest.origin)" kind="citation" /><span class="tag">{{ smallest.minutes }} 分钟 · 今天</span></div><h2>{{ smallest.title }}</h2><DetailPopover title="任务依据与关联计划" label="查看任务依据与关联计划"><template #trigger>为什么建议这项任务<UiIcon name="info" :size="16" /></template><div class="c2-today-task-why"><h3>为什么是现在</h3><p>{{ smallest.why }}</p></div><div class="c2-today-task-evidence"><h3>它连着哪条差距</h3><RouterLink to="/report"><strong>呈现能力</strong><span>示例 46 / 要求 50，差 4 分</span><small>看报告里这条 →</small></RouterLink><RouterLink v-if="focusMilestone" to="/plan"><strong>实践证据</strong><span>{{ focusMilestone.title }}</span><small>看它挂在哪个里程碑 →</small></RouterLink></div></DetailPopover>
        <div class="journey-focus__meta"><span><UiIcon name="review" :size="17" />约 {{ smallest.minutes }} 分钟</span><span><UiIcon name="action" :size="17" />{{ taskOriginLabel(smallest.origin) }}</span><span v-if="smallest.due"><UiIcon name="calendar" :size="17" />{{ smallest.due }}</span></div>
        <div class="journey-focus__actions"><RouterLink class="btn" to="/chat">咨询此任务<UiIcon name="chat" :size="16"/></RouterLink><button class="btn" @click="demo.completeTask(smallest.id)">标记完成<UiIcon name="check" :size="18" /></button><button v-if="smallest.minutes > 5" class="ws-text-button" @click="demo.shrinkTask(smallest.id)">先拆成 5 分钟</button><RouterLink v-else class="ws-text-link" to="/chat">需要调整，和顾问聊聊<UiIcon name="arrow" :size="16" /></RouterLink></div>
      </div>
    </div></section>
    <!-- 空态：`.ws-empty` → EmptyState（MIGRATION §4.2 E1，kind=notes）。
         整块正文被空态顶掉，所以显式 heading-level="2"（H5：不显式传会从 h2 掉成 h3）。 -->
    <section v-else class="ws-paper"><EmptyState kind="notes" :heading-level="2" :title="demo.use.done.value.length ? '当前任务已完成' : '暂无行动任务'" description="完成咨询并明确方向后，可生成行动任务。"><RouterLink class="btn btn--primary" to="/chat">开始咨询</RouterLink></EmptyState></section>

        <!-- G-08：进行时读数。靶子 `.hm-live__t`（14px/**600**）+ 紧跟其后的 560×5 分段 meter
             （c2-hbu/_src/views/home.html:123-126）。真实页原来只有 `.journey-focus__meta`
             那句 14px/400 的元数据标签，静图丢掉"走到哪了"。 -->
        <section class="hm-live" aria-labelledby="hmLiveT">
          <div class="hm-live__head"><h2 id="hmLiveT">任务完成情况</h2><span class="hm-live__n">{{ lineDone }} / {{ lineTotal }}</span></div>
          <p class="hm-live__t">已经做完 <b>{{ lineDone }} 件</b>，待执行任务预计 <b>{{ remainingMinutes }} 分钟</b>。<template v-if="smallest">下一件：<b>{{ smallest.title }}</b>。</template><template v-else>今天没有待执行的任务了。</template></p>
          <SegMeter v-if="lineTotal" :total="lineTotal" :lit="lineDone" :label="`这一批 ${lineTotal} 件里已完成 ${lineDone} 件`" />
          <p class="hm-live__note">完成任务后自动更新，等待结果的事项不计入预计用时。</p>
        </section>
        <section class="ws-paper journey-task-list">
          <div class="ws-section-head"><h2>执行队列</h2><span class="ws-muted">按状态查看</span></div>
          <PanelTabs v-model="group" label="任务分组" :items="groups.map(g => ({ key: g.key, label: g.label, count: g.items.length }))"><TaskList :items="active.items.filter(t => group !== 'now' || t.id !== smallest?.id)" :mode="group" /></PanelTabs>
        </section>
      </div>
      <aside class="journey-action-aside ws-related-block">

        <!-- G-01：右栏第一块。靶子 `.hm-side__n b` 实测 36×52、**30px/700**、文本"65"；
             这里印的是 `remainingMinutes`（正在做的任务的分钟合计），它会随勾选重算。 -->
        <section aria-labelledby="hmSideTimeT">
          <h2 id="hmSideTimeT">今天还剩多少时间</h2>
          <p class="hm-side__n"><b>{{ remainingMinutes }}</b> 分钟</p>
          <p class="hm-side__d">{{ lineTotal }} 件里 {{ lineDone }} 件做完。这个数字只算"还要动手"的时间 —— 等结果的条目不计入。</p>
          <SegMeter v-if="lineTotal" :total="lineTotal" :lit="lineDone" :label="`这一批 ${lineTotal} 件里已完成 ${lineDone} 件`" />
          <div class="hm-side__src">
            <SourceChip v-if="academicAt" source="record" :at="academicAt" />
            <SourceChip v-if="timeFact" :source="timeFact.source" :at="timeFact.at" />
          </div>
          <!-- 口径句：它解释"空课格 ≠ 空闲"这个反直觉读数。空档是真从课表算的，
               这句提醒的出处是报告里「时间取舍」那一条的门槛解释，不另写文案。 -->
          <p v-if="freeAfternoonText" class="hm-side__warn">按课表算出来的空档：{{ freeAfternoonText }}。<b>空课格不代表空闲</b>：{{ timeDimension?.threshold }}</p>
          <p v-else class="hm-side__warn"><b>还没有读到课表快照</b>：这一栏只用你自己填的可投入时间估算。</p>
        </section>

        <!-- G-01：右栏第二块。靶子这块是 5 行 `.kv`（排在第一位 / 它补的缺口 / 不做会怎样 /
             做不动的可能 / 谁排的）。真实数据里能站住的只有下面这 5 行 —— 每一行都指得出字段，
             所以没有"做不动的可能"那一行：任务模型里没有那个字段，不为了凑版式编一个。 -->
        <section aria-labelledby="hmSideWhyT">
          <h2 id="hmSideWhyT">为什么今天排的是这一件</h2>
          <div v-if="smallest" class="hm-kv">
            <div class="hm-kv__r"><span class="hm-kv__k">排在第一位</span><span class="hm-kv__v">{{ smallest.title }}</span></div>
            <div class="hm-kv__r"><span class="hm-kv__k">为什么是现在</span><span class="hm-kv__v">{{ smallest.why }}</span></div>
            <div class="hm-kv__r"><span class="hm-kv__k">它补的那一段</span><span class="hm-kv__v">{{ focusMilestone ? focusMilestone.title + '（' + focusMilestone.window + '）' : '还没有挂到任何一个阶段' }}</span></div>
            <div class="hm-kv__r"><span class="hm-kv__k">谁排的</span><span class="hm-kv__v">{{ taskOriginLabel(smallest.origin) }}</span></div>
            <div class="hm-kv__r"><span class="hm-kv__k">今天它占多少</span><span class="hm-kv__v">{{ smallest.minutes }} 分钟（今天还要动 {{ remainingMinutes }} 分钟）</span></div>
          </div>
          <RouterLink class="ws-text-link" to="/plan">这条挂在阶段计划的哪一段<UiIcon name="arrow" :size="16" /></RouterLink>
        </section>

        <section><h2>执行记录</h2><StatTile v-if="lastDone" label="已完成" :value="doneCount" :denominator="totalCount" :trend="{ label: '可在完成记录中查看' }"/><p v-else>完成任务后，将在此显示最近的执行记录。</p><RouterLink class="ws-text-link" to="/review">查看复盘记录<UiIcon name="arrow" :size="16" /></RouterLink></section>
        <section><p>执行遇到困难时，可通过咨询调整任务或方案。</p><RouterLink class="ws-text-link" to="/chat">回到对话<UiIcon name="arrow" :size="16" /></RouterLink></section>
      </aside>
    </div>
    <div v-if="!demo.state.guidesClosed.home" class="ws-guide"><UiIcon name="info" :size="18" /><p>优先完成当前建议任务。其他任务可按状态查看，完成后支持恢复。</p><button @click="demo.closeGuide('home')">收起</button></div>

    </template><section class="c2-plan-tools"><div><button class="btn" @click="addOpen = true"><UiIcon name="plus" :size="16" />添加个人待办</button><TaskBrief/></div><LiveActionPlan v-if="backendDemo.state.dataMode === 'demo' && !backendDemo.state.liveAction" today/></section><InfoSheet :open="addOpen" shape="dialog" title="记一件今天能做的事" @close="addOpen = false"><form @submit.prevent="add"><label class="ws-field">做什么<input v-model="title" maxlength="100" placeholder="例如：给学长发一条消息" /></label><label class="ws-field">大约需要多久<select v-model.number="minutes"><option :value="5">5 分钟</option><option :value="15">15 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">排进今天</button><button class="ws-text-button" type="button" @click="addOpen = false">先不记</button></div></form></InfoSheet>
  </div>
</template>
