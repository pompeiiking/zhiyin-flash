<script setup lang="ts">
/* ============================================================================
 * 应用工具 · 一个目录、两个来源、两条分组轴
 * ---------------------------------------------------------------------------
 * 【改之前是什么样】首屏是一句话 + 一个「读取工具目录」按钮：
 * 目录、空态、骨架屏、状态条**全都要点一下才出现**。门禁在"加载完成、
 * 未做任何点击"的状态下量到 `落点 1/2`、`orgKinds {tabs:0, pressed:0, selects:0}` ——
 * 也就是说那一屏上除了页头和一个按钮，没有任何可读的结构、没有来源、没有状态。
 * 另外目录被劈成两半：上半是服务端已发布的工具（要点一下），
 * 下半塞在一个 `<details>` 里叫"查看演示工具入口"。同一种东西两种活法。
 *
 * 【现在】三件事：
 *   ① 目录状态 ---- 三态（还没取 / 取了但没有 / 有内容）在首屏明说，亮着的一格是现在。
 *      它由 ModuleCatalog 回传的 stage 驱动，不是写死的图例。
 *   ② 工具目录 ---- 两个来源放进**同一个目录**，并且可以换分组轴（落点②组织权）。
 *      分组头带条数，换轴时条目被搬到别的组、条数跟着变。
 *   ③ 溯源 ------- 每条工具标出自己从哪来（服务端发布清单 / 本演示预置）与版本。
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

function onStage(v: ToolStage) { stage.value = v }
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

/** 预置入口：演示工程自带。`actions` 非空才算"打开就能做事"，与已发布工具同一把尺。 */
const preset = registry.modules.map<DirectoryEntry>((m) => ({
  key: 'r:' + m.id,
  name: m.name,
  description: m.description,
  source: 'preset',
  sourceLabel: '本演示预置',
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
    { key: 'preset', title: '本演示预置的入口', note: '演示工程自带的条目，指向已经做好的页面。', items: all.filter((t) => t.source === 'preset') },
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
  if (stage.value === 'error') return '这次没有读到发布清单；页头的「重新读取工具目录」可以重试。'
  if (stage.value === 'loading') return '正在读取发布清单…'
  return '还没有读取发布清单。'
}

/* ---- 三态轨：亮着的一格就是现在 ------------------------------------------- */
const RAIL = [
  { key: 'unread', title: '还没取', body: '打开这一页会自动读一次；读取失败也停在这一格，页头的重读按钮可以再试。' },
  { key: 'none', title: '取了但没有', body: '服务返回了空清单：已发布且启用的工具 0 条。这时给空态，不拿预置入口来充数。' },
  { key: 'ready', title: '有内容', body: '目录有内容：可以按来源或按可用性重新分组，选中一条即可读取它的数据。' },
]
const railStage = computed(() => (stage.value === 'ready' ? 'ready' : stage.value === 'empty' ? 'none' : 'unread'))

/* ---- 溯源：目录本身从哪来 -------------------------------------------------- */
const sourceLabel = computed(() => (backendDemo.state.dataMode === 'demo' ? '本地演示数据' : '服务端发布清单'))
const sourceDetail = computed(() =>
  backendDemo.state.dataMode === 'demo'
    ? '本地演示服务（演示模式，不伪装成线上数据）'
    : '服务端 /api/v1/modules，只返回已发布且启用的工具',
)
</script>

<template>
  <div class="ws-page">
    <PageHeading
      title="应用工具"
      description="服务端已发布的工具和本演示预置的入口放在同一个目录里：换一种分法，看的是同一批条目。"
    >
      <button class="btn" :disabled="stage==='loading'" @click="reloadCatalog">
        {{ stage==='loading' ? '正在读取…' : '重新读取工具目录' }}
      </button>
    </PageHeading>

    <!-- ① 三态在首屏：不是图例，是"现在在哪一格" -->
    <section class="tools-state-rail" aria-labelledby="tools-state-title">
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
          <span class="tools-state__body">{{ s.body }}</span>
        </li>
      </ol>
      <p class="tools-source">
        <SourceChip :label="sourceLabel" kind="external" />
        <span>目录逐条来自<strong>{{ sourceDetail }}</strong>；每条工具下面标着它自己的来源与版本。</span>
      </p>
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
                <span class="tools-entry__meta"><SourceChip :label="t.sourceLabel" :kind="t.sourceKind" /><span class="tools-entry__tag">{{ t.runnable ? '可直接用' : '只跳转' }}</span></span>
                <UiIcon class="tools-entry__go" name="arrow" :size="16" />
              </RouterLink>
              <button v-else class="tools-entry" type="button" :aria-pressed="openId === t.id" @click="pick(t)">
                <strong class="tools-entry__name">{{ t.name }}</strong>
                <span class="tools-entry__desc">{{ t.description }}</span>
                <span class="tools-entry__meta"><SourceChip :label="t.sourceLabel" :kind="t.sourceKind" /><span v-if="t.version" class="tools-entry__ver t-num">v{{ t.version }}</span><span class="tools-entry__tag">{{ t.runnable ? '可直接用' : '只跳转' }}</span></span>
                <UiIcon class="tools-entry__go" name="arrow" :size="16" />
              </button>
            </li>
          </ul>
        </section>
      </PanelTabs>
    </section>

    <!-- 运行区：目录在上面选，工具在这里跑。给它一个 h2，工具名才有一级可依
         （否则工具名会去和整页标题抢层级，见 ModuleCatalog 的 .module-catalog__title） -->
    <section class="tools-runner" aria-labelledby="tools-runner-title">
      <div class="ws-section-head">
        <div>
          <h2 id="tools-runner-title">运行区</h2>
          <p>选中的工具在这里读取数据、执行动作；没选中时这里会说明该点什么。</p>
        </div>
      </div>
      <ModuleCatalog :open-id="openId" :reload-token="reloadToken" @update:stage="onStage" @update:entries="onEntries" />
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
.tools-entry__tag { color: var(--c-text-2); }

.tools-entry__go {
  grid-column: 2;
  grid-row: 1 / 4;
  align-self: center;
  color: var(--c-text-3);
}

/* 运行区：与目录之间留一段，让"上面选、下面跑"分成两屏内容而不是一坨 */
.tools-runner { margin-top: var(--sp-7); }

/* 窄屏：三态轨与目录都落成单列；箭头那一列收掉，让说明占满整行 */
@media (max-width: 760px) {
  .tools-state-list { grid-template-columns: minmax(0, 1fr); }
  .tools-entry { grid-template-columns: minmax(0, 1fr); }
  .tools-entry__go { display: none; }
}
</style>
