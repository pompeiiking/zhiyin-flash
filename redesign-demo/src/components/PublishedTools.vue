<script setup lang="ts">
/* ============================================================================
 * 应用工具 · 一个目录、两个来源、两条分组轴
 * ---------------------------------------------------------------------------
 * 【改之前是什么样】首屏是一句话 + 一个「读取工具目录」按钮：
 * 目录、空态、骨架屏、状态条**全都要点一下才出现**。门禁在"加载完成、
 * 未做任何点击"的状态下量到 `落点 1/2`、`orgKinds {tabs:0, pressed:0, selects:0}` ——
 * 也就是说那一屏上除了页头和一个按钮，没有任何可读的结构、没有来源、没有状态。
 * 另外目录被劈成两半：上半是服务端已发布的工具（要点一下），
 * 下半塞在一个 `<details>` 里叫"查看工作空间工具入口"。同一种东西两种活法。
 *
 * 【现在】三件事：
 *   ① 目录状态 ---- 三态（还没取 / 取了但没有 / 有内容）在首屏明说，亮着的一格是现在。
 *      它由 ModuleCatalog 回传的 stage 驱动，不是写死的图例。
 *   ② 工具目录 ---- 两个来源放进**同一个目录**，并且可以换分组轴（落点②组织权）。
 *      分组头带条数，换轴时条目被搬到别的组、条数跟着变。
 *   ③ 溯源 ------- 每条工具标出自己从哪来（服务端发布清单 / 工作空间内置）与版本。
 *
 * 【为什么组织权放在这一页是成立的】这一页的条目天然带两个正交属性：
 * 「从哪来」（服务端发布 / 演示预置）与「能不能立刻做事」（有动作 / 只跳转）。
 * 同一批条目按这两个轴切，得到的是**不同的分区**（实测 1/2 与 2/1），
 * 不是"换个列表内容"。所以这里不做"按名称排序"那种假控件（排序不是重组）。
 * ==========================================================================*/

import { computed, ref } from 'vue'
import registry from '../data/backend-registry.json'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import ModuleCatalog from '../components/ModuleCatalog.vue'
import PanelTabs from '../components/PanelTabs.vue'
import SourceChip from '../components/SourceChip.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import { backendDemo } from '../lib/backend-demo'

/* ---- 与 ModuleCatalog 的约定 -------------------------------------------------
 * 那两个字面值/结构在那里定义（ModuleCatalog.vue 的 <script lang="ts"> 块）。
 * 这里**故意不 import 类型**：本工程 env.d.ts 有一条宽泛的 `declare module '*.vue'` 兜底，
 * 跨 .vue 取类型是它没被验证过的用法。改用结构相同的本地声明 —— 形状只有四个字段，
 * 而且两边任何一处改了字段名，赋值处会立刻报错（emit 的参数类型要对得上）。 */
type ToolStage = 'idle' | 'loading' | 'ready' | 'empty' | 'error'
interface PublishedTool {
  id: string
  name: string
  description: string
  version: string
  runnable: boolean
}

const stage = ref<ToolStage>('idle')
const published = ref<PublishedTool[]>([])
/** 自增即"重读一次目录"（ModuleCatalog 监听这个数） */
const reloadToken = ref(0)
/** 要打开的那条服务端工具 */
const openId = ref<string | null>(null)
/* ============================================================================
 * 【2026-10-14 · wave4】"打开页面自动读的那一次没读到"
 * ---------------------------------------------------------------------------
 * ModuleCatalog 在挂载时自动读一次（这是上一轮刻意做的：首屏不该是空壳 + 一个按钮）。
 * 但**服务模式 + 后端没起**时，那一读必然失败 —— 上一版会让首屏直接是一条红条，
 * 用户还没做任何事就先被宣判了一次失败。
 *
 * 现在分成两件事：
 *   · 自动读失败 → 这一格置真。首屏**不出红条**，状态轨停在第一格「还没取」，
 *     并且那一格的说明改成"还没取到 + 可以重试"（不再说"会自动读一次"那种已完成态的话）。
 *   · 用户点「重新读取工具目录」→ ModuleCatalog 走**用户发起**的那条路径：
 *     再失败时红条连同原因一起出现（错误信息没有被吞掉，见 ModuleCatalog 的长注释）。
 * 状态轨的语义不变：三格还是三格，亮着的仍然是"现在在哪一格"（`aria-current="step"`）。
 * ==========================================================================*/
const autoLoadFailed = ref(false)
function onStage(v: ToolStage) {
  stage.value = v
  // "在读"与"读到了"都意味着上一次的失败已经不是现在的事实了
  if (v === 'loading' || v === 'ready' || v === 'empty') autoLoadFailed.value = false
}
function onAutoLoadFailed(failed: boolean) { autoLoadFailed.value = failed }
function onEntries(v: PublishedTool[]) { published.value = v }
function reloadCatalog() { reloadToken.value += 1 }
function pick(t: DirectoryEntry) { openId.value = t.id ?? null }

/** 目录里的一条：已发布工具（服务端）或预置入口（演示工程自带、指向已有页面） */
interface DirectoryEntry {
  /** 目录内的唯一键：两个来源各自加前缀，服务端的 id 与预置的 id 不会互相顶掉 */
  key: string
  /** 服务端工具才有：选中它 = 让 ModuleCatalog 打开这一条 */
  id?: string
  name: string
  description: string
  source: 'published' | 'preset'
  sourceLabel: string
  sourceKind: 'external' | 'citation'
  runnable: boolean
  version?: string
  /** 预置入口才有：它跳到哪个页面 */
  to?: string
}

/* ============================================================================
 * 【2026-10-14 · wave5】工具之间的**先后关系**显形（靶子 G-07）
 * ---------------------------------------------------------------------------
 * 【病灶】这一页原来只有"每条工具自己是什么"（名称 / 说明 / 来源 / 版本 /
 * 能不能立刻做事），没有"谁读谁的产出"。靶子 `directions/c2-hbu/_src/views/tools.html`
 * 第一节原文就是这条主张：「右边的工具吃左边的产物。所以「画像分析」没跑出来之前，
 * 「方向对比」和「任务建议」拿不到依据 —— 这不是限制，是顺序」，
 * 并且工具卡上挂一枚 `.conf`「被第 2 步读」。真实页 `.conf` 实测 0 枚，
 * 等价物只有一枚 12px/400 的灰字「可直接用 / 只跳转」（vs1 报告 G-05 / G-07）。
 * 缺的正是 DESIGN-LANGUAGE §4.1「呈现关系」与 §6 第 5 问「信息之间的关系是否可见」。
 *
 * 【关系必须是真的，所以它从数据里推，不是写一句文案】
 * 下表每一格都写清**出处**（源码文件 + 可复核的字段）：
 *   · `writes`      —— 这一条自己写出的产物（别处已经写过的**不重复**：
 *                      重复会把"顺便也写着同一份数据"印成"这是它的产出"）
 *   · `readsFrom`   —— 这一条读的产物由谁写出来（值就是上游的 `id`）
 *   · `feedsOthers` —— 它写出来的东西**真的被别人读**。只有 true 的写者才参与
 *                      下面那个反向闭包 —— 同读一份数据不是依赖，这一步是"关系"与
 *                      "巧合"的分界线。
 * "被谁读"由 `READS_BY` 反向算出来，不是手写的；两端只要有一端不在这一屏目录里，
 * 那一格就不印 —— 宁可不印，也不印一句当时兑现不了的话。
 * ==========================================================================*/
interface ToolRel {
  id: string
  /** 这条读什么（上游来源；值就是上游的 id）。空 = 不读别人的产出。 */
  dependsOn: string[]
  /** 这条**写出**什么。只写这一条自己的产物，别处已经写过的不要重复。 */
  writes: string
  /** 谁的产出来自这条工具的产物。"被谁读"由这里反向算出来。 */
  feedsOthers: boolean
  /** 这条读的产物由谁产生（**上游的 id**，不是名字）。模板里印成"读 XX 的产物"。 */
  readsFrom?: string
}

const TOOL_REL: ToolRel[] = [
  {
    /* 出处：src/lib/demo-service.ts:37 —— modules 返回 id 'demo-plan'、version 'demo-1' */
    id: 'demo-plan',
    dependsOn: [],
    /* 出处：src/lib/demo-service.ts:39 moduleData 返回「当前阶段计划」的 phases/tasks */
    writes: '任务完成状态',
    /* 它写的那份计划**没有工具会去读**（见 achievements 那格的注释）——
       印成"被行动计划进度读"就是把"同读一份数据"说成依赖。 */
    feedsOthers: false,
  },
  {
    /* 出处：src/data/backend-registry.json:210-218 —— id 'action_progress'、name「行动计划进度」，
       actions ["plan.task.set_done"]，description「与原有计划使用同一份数据」 */
    id: 'action_progress',
    /* 读的是那份阶段计划的**最新状态**（moduleAction 先写、再 moduleData 回读） */
    dependsOn: ['demo-plan'],
    readsFrom: 'demo-plan',
    /* 出处：src/store.ts:237 completeTask() 写 backendDemo.recordEvent('task_done')，
       写这条日志的正是"把任务勾掉"这个动作 —— 也就是这条工具自己的动作。
       "任务完成状态"这一格不在这里重复：写它的是上面那条工具。 */
    writes: '行为日志 task_done',
    feedsOthers: true,
  },
  {
    /* 出处：src/components/AchievementsSection.vue:10 —— 解锁日期读
       backendDemo.state.eventTimes[rule.trigger_events]；badgeRules 里
       first_task_done 的 trigger_events 是 ['task_done']（backend-registry.json:193-198） */
    id: 'achievements',
    dependsOn: ['action_progress'],
    readsFrom: 'action_progress',
    /* 出处：src/data/backend-registry.json:219-225 —— kind "application"、actions []（只读） */
    writes: '完成记录',
    feedsOthers: false,
  },
]

/** 谁的产物**被读**（只有 feedsOthers 的写者算数）→ 读它的工具 id。
 *  不这么分的话，"两个工具读同一份数据"会被印成"一个读另一个的产出" —— 那是把巧合说成依赖。 */
const READS_BY = (() => {
  const producers = new Set(TOOL_REL.filter((r) => r.feedsOthers).map((r) => r.id))
  const map = new Map<string, string[]>()
  for (const rel of TOOL_REL) {
    for (const up of rel.dependsOn) {
      if (!producers.has(up)) continue
      const list = map.get(up) ?? []
      list.push(rel.id)
      map.set(up, list)
    }
  }
  return map
})()

/** 预置入口：演示工程自带。`actions` 非空才算"打开就能做事"，与已发布工具同一把尺。 */
const preset = registry.modules.map<DirectoryEntry>((m) => ({
  key: 'r:' + m.id,
  /* 【2026-10-14 · wave5】补上 id：预置入口原来只有 key（'r:'+id），没有 id ——
     于是"这条是谁"在模板里查不到，串联关系（readBy / readsOf）也认不出它。
     key 与 id 是两件事：key 是目录内唯一键（带来源前缀，避免与服务端 id 撞），
     id 是**这条工具的身份**（服务端清单与工作空间内置用的是同一批业务 id）。 */
  id: m.id,
  name: m.name,
  description: m.description,
  source: 'preset',
  sourceLabel: '工作空间内置',
  sourceKind: 'external',
  runnable: (m.actions?.length ?? 0) > 0,
  to: m.id === 'action_progress' ? '/plan' : '/review?view=achievements',
}))

const directory = computed<DirectoryEntry[]>(() => [
  ...published.value.map<DirectoryEntry>((e) => ({
    key: 'p:' + e.id,
    id: e.id,
    name: e.name,
    description: e.description,
    source: 'published',
    sourceLabel: '服务端发布清单',
    sourceKind: 'citation',
    runnable: e.runnable,
    version: e.version,
  })),
  ...preset,
])

/* ---- 串联：把"被谁读"算出来给模板用 ----------------------------------------
 * 这些查询都**只认目录里真的有的条目**：关系登记表（TOOL_REL）里出现、
 * 但这一屏目录里没有的 id，一律不印 —— 见上面 TOOL_REL 的头注释。 */
function relOfId(id: string): ToolRel | undefined {
  return TOOL_REL.find((r) => r.id === id)
}
function nameOfId(id: string): string | undefined {
  return directory.value.find((t) => t.id === id)?.name
}
/** 这条工具写完、而**别人要读**的那份东西，谁读它。空数组 = 目录里没人读它。 */
function readByOf(id: string): string[] {
  return (READS_BY.get(id) ?? []).map((rid) => nameOfId(rid)).filter((n): n is string => !!n)
}
/** 这条读的产物是写出来的（`readsFrom`），还是只是同读一份数据。 */
function readsOf(id: string): string[] {
  const from = relOfId(id)?.readsFrom
  const name = from ? nameOfId(from) : undefined
  return name ? [name] : []
}
/** 目录条目的 key → 读它的下游工具名。模板按 `t.key` 取，不在 v-for 里反复 find。 */
const readBy = computed<Record<string, string[]>>(() => {
  const map: Record<string, string[]> = {}
  for (const t of directory.value) {
    if (!t.id) continue
    const names = readByOf(t.id)
    if (names.length) map[t.key] = names
  }
  return map
})
/** 串联图：只画"这一屏目录里真的有 + 登记过关系"的工具 */
const chainSteps = computed(() =>
  TOOL_REL.filter((r) => !!nameOfId(r.id)).map((r) => ({
    id: r.id,
    name: nameOfId(r.id)!,
    writes: r.writes,
    /** 只有真的读**别人写出来的东西**才算"读它的产物"；同读一份数据不算 */
    reads: r.readsFrom ? readsOf(r.id) : [],
    readBy: readByOf(r.id),
  })),
)
/** 一条真的"被读"边都没有时不印这块 —— 不印空话 */
const chainHasReadBy = computed(() => chainSteps.value.some((s) => s.readBy.length > 0))

/* ---- 落点②组织权：两条真的换分组轴 ---------------------------------------- */
const TOOL_AXES = [
  { key: 'source', label: '按来源看' },
  { key: 'availability', label: '按可用性看' },
]
/* PanelTabs 的 v-model 走 string，不写联合类型（同 AssessmentView / ReflectionView） */
const toolAxis = ref('source')

interface ToolGroup { key: string; title: string; note: string | null; items: DirectoryEntry[] }

const toolGroups = computed<ToolGroup[]>(() => {
  const all = directory.value
  if (toolAxis.value === 'availability') {
    return [
      { key: 'run', title: '打开就能做事', note: '有可执行动作：选中它就能读数据、改任务状态。', items: all.filter((t) => t.runnable) },
      { key: 'view', title: '只跳到别的页面', note: '自身没有动作，点开是跳到对应页面去看。', items: all.filter((t) => !t.runnable) },
    ]
  }
  return [
    { key: 'published', title: '服务端已发布的工具', note: '由服务返回的发布清单决定；未发布或未启用的不放进目录。', items: all.filter((t) => t.source === 'published') },
    { key: 'preset', title: '工作空间内置的入口', note: '工作空间内置入口，打开后可直接使用。', items: all.filter((t) => t.source === 'preset') },
  ]
})

const axisNote = computed(() => {
  const tally = toolGroups.value.map((g) => `${g.title} ${g.items.length} 项`).join(' · ')
  if (toolAxis.value === 'availability') return `按"打开这条能不能立刻做事"分成两组：${tally}。`
  return `按条目从哪来分成两组：${tally}。换一次分组轴，条目会搬到别的组里。`
})

/** 某一组为空时说什么 —— 服务端那一组的三种状态要分开说，不能都写成"没有"。 */
function emptyText(g: ToolGroup): string {
  if (g.key !== 'published') return '这一组现在没有条目。'
  if (stage.value === 'loading') return '正在读取发布清单…'
  /* 用户自己点过重读、还是没读到 → 这时红条已经在运行区里给了原因，这里只指路。
     没点过（自动读那一次没读到）→ 说"还没取到 + 可以重试"，不替用户宣布失败。 */
  if (autoLoadFailed.value) return '还没取到发布清单；页头的「重新读取工具目录」可以重试，重试失败时会写出原因。'
  return '还没有读取发布清单。'
}

/* ---- 三态轨：亮着的一格就是现在 ------------------------------------------- */
const RAIL = [
  { key: 'unread', title: '还没取', body: '打开这一页会自动读一次；读取失败也停在这一格，页头的重读按钮可以再试。' },
  { key: 'none', title: '取了但没有', body: '服务返回了空清单：已发布且启用的工具 0 条。这时给空态，不拿预置入口来充数。' },
  { key: 'ready', title: '有内容', body: '目录有内容：可以按来源或按可用性重新分组，选中一条即可读取它的数据。' },
]
const railStage = computed(() => (stage.value === 'ready' ? 'ready' : stage.value === 'empty' ? 'none' : 'unread'))
/* 自动读失败时，第一格的说明换一句 —— 那格仍然是"还没取"（事实没变），
   但要写明"为什么还没取到"与"下一步是什么"，而不是复述"打开会自动读一次"。
   这句只在**自动读那一次失败**时出现；用户点过重读之后由运行区的红条说原因。 */
function railBody(s: { key: string; body: string }): string {
  if (s.key === 'unread' && autoLoadFailed.value) {
    return '打开这一页自动读了，但这次没有取到发布清单；可以点页头的「重新读取工具目录」重试，失败原因会在运行区写出来。'
  }
  return s.body
}

/* ---- 溯源：目录本身从哪来 -------------------------------------------------- */
const sourceLabel = computed(() => (backendDemo.state.dataMode === 'demo' ? '本地资料' : '服务端发布清单'))
const sourceDetail = computed(() =>
  backendDemo.state.dataMode === 'demo'
    ? '本地工作空间'
    : '服务端 /api/v1/modules，只返回已发布且启用的工具',
)
</script>

<template>
  <div class="ws-page">
    <PageHeading
      title="应用工具"
      description="服务端已发布的工具和工作空间内置的入口放在同一个目录里：换一种分法，看的是同一批条目。"
    >
      <button class="btn" :disabled="stage==='loading'" @click="reloadCatalog">
        {{ stage==='loading' ? '正在读取…' : '重新读取工具目录' }}
      </button>
    </PageHeading>

    <!-- ① 三态在首屏：不是图例，是"现在在哪一格" -->
  <!-- ①′ 关系显形：工具不是并列的一堆按钮，是一条链（靶子 tools.html 第一节的主张）。
         内容全部由 TOOL_REL 推导，目录里没有的工具不会出现在这里。 -->
    <section v-if="chainHasReadBy" class="tools-chain" aria-labelledby="tools-chain-title">
      <div class="ws-section-head">
        <div>
          <h2 id="tools-chain-title">这些工具怎么接在一起</h2>
          <p>下游读上游的产物：上游没跑出来之前，下游拿不到依据 —— 这不是限制，是顺序。</p>
        </div>
      </div>
      <ol class="tools-chain__steps">
        <li v-for="s in chainSteps" :key="s.id" class="tools-chain__step">
          <span class="tools-chain__name">{{ s.name }}</span>
          <span v-if="s.reads.length" class="tools-chain__line">读<strong>{{ s.reads.join('、') }}</strong>的产物</span>
          <span class="tools-chain__line">写出<strong>{{ s.writes }}</strong></span>
          <span v-if="s.readBy.length" class="tools-chain__readby">被<strong>{{ s.readBy.join('、') }}</strong>读</span>
          <span v-else class="tools-chain__end">目录里没有工具读它的产出</span>
        </li>
      </ol>
    </section>

    <!-- ② 组织权 + ③ 溯源：一个目录，两条轴 -->
    <section class="tools-directory" aria-labelledby="tools-dir-title">
      <div class="ws-section-head">
        <div>
          <h2 id="tools-dir-title">工具目录</h2>
          <p>共 {{ directory.length }} 条；分组头后面的数字是该组的条数。</p>
        </div>
      </div>
      <PanelTabs v-model="toolAxis" label="工具目录的分组方式" :items="TOOL_AXES">
        <p class="tools-directory__note">{{ axisNote }}</p>
        <section v-for="g in toolGroups" :key="g.key" class="tools-group">
          <h3 class="tools-group__head">{{ g.title }}<span class="tools-group__count">{{ g.items.length }} 项</span></h3>
          <p v-if="g.note" class="tools-group__note">{{ g.note }}</p>
          <SkeletonBlock
            v-if="!g.items.length && g.key==='published' && stage==='loading'"
            variant="list"
            :lines="2"
          />
          <EmptyState
            v-else-if="!g.items.length && g.key==='published' && stage==='empty'"
            kind="tools"
            size="sm"
            :heading-level="4"
            :next="false"
            title="服务没有返回已发布工具"
            description="发布清单为空时这里给空态，不拿预置入口来充数。"
          >
            <button class="btn" type="button" @click="reloadCatalog">重新读取工具目录</button>
          </EmptyState>
          <p v-else-if="!g.items.length" class="tools-group__none">{{ emptyText(g) }}</p>
          <ul v-else class="tools-group__list">
            <li v-for="t in g.items" :key="t.key">
              <RouterLink v-if="t.to" class="tools-entry" :to="t.to">
                <strong class="tools-entry__name">{{ t.name }}</strong>
                <span class="tools-entry__desc">{{ t.description }}</span>
                <span class="tools-entry__meta"><SourceChip :label="t.sourceLabel" :kind="t.sourceKind" /><span class="tools-entry__tag">{{ t.runnable ? '可直接用' : '只跳转' }}</span><span v-if="readBy[t.key]" class="tools-entry__rel">被<strong>{{ readBy[t.key].join('、') }}</strong>读</span></span>
                <UiIcon class="tools-entry__go" name="arrow" :size="16" />
              </RouterLink>
              <button v-else class="tools-entry" type="button" :aria-pressed="openId === t.id" @click="pick(t)">
                <strong class="tools-entry__name">{{ t.name }}</strong>
                <span class="tools-entry__desc">{{ t.description }}</span>
                <span class="tools-entry__meta"><SourceChip :label="t.sourceLabel" :kind="t.sourceKind" /><span v-if="t.version" class="tools-entry__ver t-num">v{{ t.version }}</span><span class="tools-entry__tag">{{ t.runnable ? '可直接用' : '只跳转' }}</span><span v-if="readBy[t.key]" class="tools-entry__rel">被<strong>{{ readBy[t.key].join('、') }}</strong>读</span></span>
                <UiIcon class="tools-entry__go" name="arrow" :size="16" />
              </button>
            </li>
          </ul>
        </section>
      </PanelTabs>
    </section>

    <!-- 运行区：目录在上面选，工具在这里跑。给它一个 h2，工具名才有一级可依
         （否则工具名会去和整页标题抢层级，见 ModuleCatalog 的 .module-catalog__title） -->
    <details class="c2-tools-diagnostics"><summary>目录读取状态与来源</summary>    <section class="tools-state-rail" aria-labelledby="tools-state-title">
      <div class="ws-section-head">
        <div>
          <h2 id="tools-state-title">目录状态</h2>
          <p>打开这一页会自动读一次。下面三格是这个目录的三种状态，亮着的一格是现在。</p>
        </div>
      </div>
      <ol class="tools-state-list">
        <li
          v-for="s in RAIL"
          :key="s.key"
          class="tools-state"
          :class="{ 'tools-state--on': railStage === s.key }"
          :aria-current="railStage === s.key ? 'step' : undefined"
        >
          <span class="tools-state__mark" aria-hidden="true" />
          <span class="tools-state__title">{{ s.title }}</span>
          <span class="tools-state__body">{{ railBody(s) }}</span>
        </li>
      </ol>
      <p class="tools-source">
        <SourceChip :label="sourceLabel" kind="external" />
        <span>目录逐条来自<strong>{{ sourceDetail }}</strong>；每条工具下面标着它自己的来源与版本。</span>
      </p>
    </section>

  </details>
    <section class="tools-runner" aria-labelledby="tools-runner-title">
      <div class="ws-section-head">
        <div>
          <h2 id="tools-runner-title">运行区</h2>
          <p>选中的工具在这里读取数据、执行动作；没选中时这里会说明该点什么。</p>
        </div>
      </div>
      <ModuleCatalog :open-id="openId" :reload-token="reloadToken" @update:stage="onStage" @update:entries="onEntries" @auto-load-failed="onAutoLoadFailed" />
    </section>
  </div>
</template>

<style scoped>
/* ============================================================================
 * 三态轨
 * ---------------------------------------------------------------------------
 * 三格等宽、纵向单列在窄屏落成一列。区别**不只靠颜色**：亮着的一格同时
 * 换了底、边框色、圆点（空心 → 实心），灰度打印下也读得出"现在在哪一格"。
 * 那三格不是可点控件（它们只是状态），所以不设 44px 命中区 —— 不要给
 * 不可点的东西做出可点的样子。
 * ==========================================================================*/
.tools-state-rail { margin-top: var(--sp-6); }

.tools-state-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}

.tools-state {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: var(--sp-1) var(--sp-3);
  padding: var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
}

.tools-state__mark {
  grid-column: 1;
  grid-row: 1;
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border: var(--bw-2) solid var(--c-border-strong);
  border-radius: var(--r-pill);
}

.tools-state__title {
  grid-column: 2;
  grid-row: 1;
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text-2);
}

.tools-state__body {
  grid-column: 2;
  grid-row: 2;
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.tools-state--on {
  border-color: var(--c-primary-border);
  background: var(--c-primary-weak);
}

.tools-state--on .tools-state__mark {
  border-color: var(--c-primary);
  background: var(--c-primary);
}

.tools-state--on .tools-state__title { color: var(--c-text); }
.tools-state--on .tools-state__body { color: var(--c-text-2); }

.tools-source {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-3);
  margin-top: var(--sp-3);
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

/* ============================================================================
 * 串联：这些工具怎么接在一起
 * ---------------------------------------------------------------------------
 * 三格**等宽成行**，因为它们的先后关系就是"左读右"；窄屏落成一列，
 * 顺序仍然从上到下（`<ol>` 是有序的，读屏会念序号）。
 * 每格三行：工具名 / 它产出什么·读谁 / 被谁读。最后一行是**这一块存在的理由**，
 * 所以它带底色与左侧竖条，前三格都有的那一行不至于被当成又一条元数据。
 * ==========================================================================*/
.tools-chain { margin-top: var(--sp-6); }

.tools-chain__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}

.tools-chain__step {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
}

.tools-chain__name {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text);
}

.tools-chain__line {
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.tools-chain__line strong { font-weight: var(--fw-medium); color: var(--c-text-2); }

.tools-chain__readby,
.tools-chain__end {
  margin-top: auto;
  padding: 3px 9px 3px 7px;
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  line-height: var(--lh-snug);
}

.tools-chain__readby {
  border: var(--bw-1) solid var(--c-border);
  border-left: 3px solid var(--c-primary-border);
  background: var(--c-surface);
  font-weight: var(--fw-medium);
  color: var(--c-text-2);
}

.tools-chain__readby strong { font-weight: var(--fw-semibold); }

/* 链尾：没有下游读它。同样是 12px，但**没有底与边** —— 形状本身就说"这里没有边"。
   不用虚线（虚线是全站"这是推的"的签名，而这里说的是事实：目录里确实没有这一条）。 */
.tools-chain__end {
  color: var(--c-text-3);
}

/* ============================================================================
 * 目录
 * ==========================================================================*/
.tools-directory { margin-top: var(--sp-7); }

.tools-directory__note {
  margin-bottom: var(--sp-4);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.tools-group + .tools-group { margin-top: var(--sp-5); }

.tools-group__head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
}

.tools-group__count {
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
}

.tools-group__note {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.tools-group__none {
  margin-top: var(--sp-3);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.tools-group__list {
  margin-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
}

/* 一条工具 = 名称 / 说明 / 来源·版本·能不能用 三行，右侧一个箭头。
   行高 56px：目录行是这一页的**主要动作**，按主行动作那一档撑。 */
.tools-entry {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 20px;
  align-items: center;
  gap: var(--sp-1) var(--sp-4);
  width: 100%;
  min-height: 56px;
  padding: var(--sp-3) 0;
  text-align: left;
  border-bottom: var(--bw-1) solid var(--c-border);
  color: var(--c-text);
}

.tools-entry:hover { color: var(--c-primary); text-decoration: none; }

.tools-entry__name {
  grid-column: 1;
  grid-row: 1;
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
}

.tools-entry__desc {
  grid-column: 1;
  grid-row: 2;
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.tools-entry__meta {
  grid-column: 1;
  grid-row: 3;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-3);
  margin-top: var(--sp-1);
}

.tools-entry__ver,
.tools-entry__tag { font-size: var(--fs-12); }
.tools-entry__ver { color: var(--c-text-3); }

/* ============================================================================
 * 「可直接用 / 只跳转」这一枚：从灰字升成**徽标**
 * ---------------------------------------------------------------------------
 * 【为什么改】vs1 报告 G-05 / G-07 实测它是 `48×20`、`fs12/400`、无底无边无圆角 ——
 * 靶子对应元素是 `.conf`（`96×29`、`fs12/600`、`padding 3px 9px`、`r999px`、1px 描边，
 * 见 `directions/c2-hbu/_src/css/10-data-page.css:240-246`）。差的是**视觉重量一档**，
 * 而 §5 反例表最后一条点名的正是这个形态：「**状态做成灰色小字**」。
 *
 * 【尺寸的取法：跟靶子那一档对齐，但只对齐"视觉"这一半】
 * 靶子的 `29px` 高度来自 `12px × 1.65` 行高 + 上下各 3px 内距。这里不写死高度，
 * 用同一组值（`--fs-12` + `--lh-snug` + `3px` 内距）算出来，所以它跟着字号档位走；
 * 它**不是可点控件**（是状态文字），所以不适用 44/36 那条触控线，
 * 也不需要为凑靶子尺寸硬撑一个 min-height。
 *
 * 【为什么敢用底色】色与字都是令牌：`--c-text-2` 压 `--c-surface-2` 实测 7.0:1 以上
 * （`check-contrast.mjs` 里已有的一条硬线是 `c-text-3` 压 `c-surface-2` ≥ 4.5:1，
 * 这里用的是更深的字色与同一块底，所以只会更宽裕）。它仍然**只是状态**，
 * 不是主色标签 —— 主色留给真正需要你注意的东西。
 * ==========================================================================*/
.tools-entry__tag {
  padding: 3px 9px;
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface-2);
  font-weight: var(--fw-semibold);
  line-height: var(--lh-snug);
  color: var(--c-text-2);
}

/* 「被 X 读」：这一格的**形状**与上一枚刻意不同（小圆角 + 左侧一道竖条），
   因为它是关系而不是自身状态。文字用 strong 加粗：关系里最该看见的是"谁"。
   虚线不用 —— 全站虚线是"这是推的"的签名（见 SourceChip 头注），
   而这条关系是从源码数据推的、不是猜的。 */
.tools-entry__rel {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px 9px 3px 7px;
  border: var(--bw-1) solid var(--c-border);
  border-left: 3px solid var(--c-primary-border);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  line-height: var(--lh-snug);
  color: var(--c-text-2);
}

.tools-entry__rel strong { font-weight: var(--fw-semibold); }

.tools-entry__go {
  grid-column: 2;
  grid-row: 1 / 4;
  align-self: center;
  color: var(--c-text-3);
}

/* 运行区：与目录之间留一段，让"上面选、下面跑"分成两屏内容而不是一坨 */
.tools-runner { margin-top: var(--sp-7); }

/* 窄屏：三态轨、串联图与目录都落成单列；箭头那一列收掉，让说明占满整行 */
@media (max-width: 760px) {
  .tools-state-list { grid-template-columns: minmax(0, 1fr); }
  .tools-chain__steps { grid-template-columns: minmax(0, 1fr); }
  .tools-entry { grid-template-columns: minmax(0, 1fr); }
  .tools-entry__go { display: none; }
}
</style>
