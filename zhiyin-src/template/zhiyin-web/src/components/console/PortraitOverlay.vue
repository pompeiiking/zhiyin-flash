<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import { track } from '@/api/client'
import { dimensionTask } from '@/ai/registry'
import { useEscLayerManual } from '@/composables/useEscLayer'
import { useSessionStore } from '@/stores/session'
import { splitProfile } from '@/lib/profile'
import PortraitSummary from '@/components/portrait/PortraitSummary.vue'
import PortraitFieldList from '@/components/portrait/PortraitFieldList.vue'
import PortraitDetail from '@/components/portrait/PortraitDetail.vue'
import PortraitEmpty from '@/components/portrait/PortraitEmpty.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { portraitTask, type PortraitAnalysis } from '@/ai/registry'

/**
 * 画像 —— 一块**往里走**的面板。
 *
 * 【先说这一版改了什么，为什么】
 *
 * 上一版把四件事平铺在一屏：抬头统计、雷达 + 整份判断、字段清单、单条明细。
 * 平铺的问题不在间距，在于**它没有层次**：所有内容都同样大声，就等于没有重点。
 * 用户的原话是"整体排版很丑"，同一句里还夹着更要命的一条：
 * **"画像怎么可能把这些基本信息当作核心依据，直接出分析图"** ——
 * 那张雷达图的顶点是学校 / 层次 / 学制 / 预计毕业，全部来自学信网，
 * 把握度恒等于 1.00。图上一圈顶满，什么都没说。那不是画像，是学籍表的截图。
 *
 * 所以这一版做两件事：
 *
 *   ① **把事实和判断分开**（口径在 `lib/profile.ts`，按来源分，不按我们怎么想）：
 *      档案（学校/专业/学籍/学制/入学/预计毕业）只回答"你在哪儿"，
 *      判断（价值取向/兴趣/经历/能力自评/目标方向/约束/卡点）才回答"你是谁"。
 *      分析图**只画判断**；一条判断都还没有时，那里不画图，而是把"为什么没图、
 *      要补哪几条"说清楚 —— 画一张假图比空着更坏。
 *
 *   ② **分成三层**，每层只回答一个问题：
 *      ① 概览：现在是什么样（覆盖、把握、来源）+ 中间那张分析图 + 一张能点的目录
 *      ② 清单：判断 / 档案 / 还差什么 / 整份判断 —— 只负责"找到那一条"
 *      ③ 明细：这一条记了什么、凭什么、意味着什么
 *
 * 层级靠字号与留白立起来（21 / 19 / 15 / 13.5 / 12），主色只落在该点的那一行上。
 * 返回与面包屑只在二层、三层出现 —— 一层没有"上一级"。
 *
 * 【密度开关去掉了】
 * 原来顶部有"舒适 / 紧凑"（还写进 localStorage）。它和清单里的筛选片长得一样，
 * 却答的是另一个问题（一个改排版、一个改数据），点错一次就说不清哪个是哪个。
 * 现在密度由层级决定：目录行该松，清单行该紧。
 *
 * 【中间那张图是第三方组件】
 * Apache ECharts（MIT）+ vue-echarts（MIT），按需引入雷达 / 条形 / 提示框。
 * 用 `defineAsyncComponent` 懒加载：不打开这一页就不会下载它。
 * 外观全部换回外壳的纸与墨，色值从 CSS 变量读 —— 见 PortraitChart.vue 的说明。
 */
const session = useSessionStore()

const PortraitChart = defineAsyncComponent(() => import('@/components/portrait/PortraitChart.vue'))

const profile = computed(() => session.profile)
const fields = computed(() => profile.value?.fields ?? [])
const gaps = computed(() => profile.value?.gaps ?? [])

/* ── 三级导航 ─────────────────────────────────────────────────────
 *
 * 用一条 trail（走过的路）而不是一个 level 字段：
 * 同一条明细可能是从"分析图上的一个点"点进来的，也可能是从"清单里的一行"点进来的 ——
 * 返回要回到**它来的那一层**。单值 level 做不到这件事，只能猜。
 */
type Level = 'overview' | 'dims' | 'records' | 'gaps' | 'analysis' | 'field'

const trail = ref<Level[]>([session.portraitFocus === 'gaps' ? 'gaps' : 'overview'])
const level = computed<Level>(() => trail.value[trail.value.length - 1])
const atRoot = computed(() => trail.value.length === 1)

function go(next: Level) {
  if (level.value === next) return
  trail.value = [...trail.value, next]
}
function back() {
  if (trail.value.length > 1) trail.value = trail.value.slice(0, -1)
}

/**
 * Esc 的归属。
 *
 * 浮层自己注册的那一层 Esc 是"关掉整个面板"。这里在二层、三层**压在它上面**：
 * Esc 归栈顶，于是它先退一层，退到一层之后再按才关面板 ——
 * 这是"往里走了两步，一次 Esc 把面板整个关掉"那个别扭感的解法。
 */
const escBack = useEscLayerManual(() => back())
watch(
  () => trail.value.length,
  (n) => (n > 1 ? escBack.activate() : escBack.deactivate()),
  { immediate: true },
)

const selectedKey = ref<string | null>(null)

/**
 * 第三层要的那一条。
 *
 * 形状在这里**归一**（而不是让子组件去猜后端字段名）：`updated_at` → `updatedAt`、
 * 缺省值补上。归一放在这一处，子模块就只认一种形状。
 */
const selected = computed(() => {
  const field = fields.value.find((f) => f.key === selectedKey.value) ?? fields.value[0]
  if (!field) return null
  return {
    key: field.key,
    label: nameOf(field),
    confidence: field.confidence ?? 0,
    source: field.source,
    updatedAt: String(field.updated_at ?? ''),
    value: field.value,
    evidence: field.evidence ?? [],
  }
})

/**
 * 来源枚举 → 用户读得懂的说法。
 *
 * 六个取值由内核契约 `ProfileSource` 定死（不是自由字符串）：学信网与教务系统
 * 这类权威记录统一走 `record`，所以这里没有、也不需要有它们各自的名字。
 * 认不出来的取值不给用户看原始码，退回一句中性说法。
 */
const SOURCE_LABEL: Record<string, string> = {
  resume: '简历',
  conversation: '对话',
  assessment: '测评',
  behavior_inference: '行为推断',
  mentor: '导师',
  record: '权威记录',
}

const sourceLabel = (source: string) => SOURCE_LABEL[source] ?? '记录'

/**
 * 这个字段在界面上叫什么。
 *
 * 三级来源，顺序不能变：字段自带的名字（模型写画像时一起给的）→ 动态资源里的
 * 对照表（老数据没有名字时兜住）→ 字段键。最后一级是兜底不是正常路径：
 * 画面上出现 `interest_direction` 这种英文，说明前两级都没拿到。
 */
const nameOf = (field: { key: string; label?: string }) =>
  field.label || session.copyBundle[`profile.field.${field.key}`] || field.key

/** 时间戳只留到分钟：秒与毫秒是给日志看的，不是给人看的 */
const stamp = (value: string | null | undefined) =>
  value ? value.slice(0, 16).replace('T', ' ') : '尚未记录'

/**
 * 一条记录的取值怎么读给人看。
 *
 * 取值形状由后端给（可能是字符串，也可能是若干项）。此前这里对非字符串直接
 * `JSON.stringify` —— 画像里存了一条多值的记录，界面上就会冒出
 * `["产品","数据分析"]` 这样一串带引号带括号的东西：用户看不出这是什么，
 * 也不该看到数据在库里长什么样。
 */
function readValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  const items = Array.isArray(value) ? value : Object.values(value as Record<string, unknown>)
  const parts = items.map(readValue).filter((part) => part && part !== '—')
  return parts.length ? parts.join('、') : '—'
}

/** 证据是后端给的字符串引用；点开看它原样是什么 */
function showEvidence(label: string, evidence: string[]) {
  session.openDrawer(
    `「${label}」的全部依据`,
    `${evidence.length} 条 · 每条都是记录的原样`,
    evidence.map((e) => ({ source: '记录', detail: e, confidence: 0.8, at: '导入时' })),
  )
}

function showGap(gap: { id: string; name: string; question: string; suggested: string }) {
  session.openDrawer(`缺的这一条：${gap.name || gap.id}`, gap.question, [
    { source: '为什么算缺', detail: gap.question, confidence: 1, at: '采集策略' },
    { source: '建议怎么补', detail: gap.suggested, confidence: 1, at: '采集策略' },
  ])
}

/* ── 事实与判断 ──────────────────────────────────────────────────
 *
 * 切一刀的地方只有一处（lib/profile.ts），这里只负责把两堆分别摆到该摆的地方：
 * 判断 → 分析图 + 判断清单；档案 → 档案清单。混在一起是上一版最大的误区。
 */
const split = computed(() => splitProfile(fields.value))
const pendingKeys = computed(() => new Set(gaps.value.map((g) => g.id)))

const toItem = (field: { key: string; label?: string; confidence?: number; source: string; updated_at?: string | null; evidence?: string[]; value?: unknown }) => ({
  key: field.key,
  label: nameOf(field),
  confidence: field.confidence ?? 0,
  source: field.source,
  updatedAt: String(field.updated_at ?? ''),
  evidenceCount: (field.evidence ?? []).length,
  pending: pendingKeys.value.has(field.key),
})

const dimItems = computed(() => split.value.judgments.map(toItem))
const factItems = computed(() =>
  split.value.facts.map((f) => ({
    ...toItem(f),
    value: readValue(f.value),
    sourceLabel: sourceLabel(f.source),
  })),
)

/** 分析图的点：只有判断维度，且要带证据条数（工具提示里要给） */
const chartDims = computed(() =>
  split.value.judgments.map((f) => ({
    key: f.key,
    name: nameOf(f),
    value: f.confidence ?? 0,
    evidence: (f.evidence ?? []).length,
  })),
)

/** 抬头统计要的是**全部**字段（覆盖度是后端按全部算的），但要单独告诉它有几条判断 */
const allItems = computed(() => fields.value.map(toItem))

/** 整体解读的三栏（AnalysisPoint[]：label + why） */
const PA_COLS = [
  { key: 'strengths', label: '亮点' },
  { key: 'watchouts', label: '要小心' },
  { key: 'next', label: '下一步' },
] as const

const analysisTask = () => portraitTask() as never

/** 点图上的一个点 / 点清单的一行：都是"看这一条" */
function openField(key: string) {
  selectedKey.value = key
  go('field')
}

/** 点趋势上的某个拐点：那一次发生了什么 */
function onTrend(index: number) {
  const field = selected.value
  if (!field) return
  session.openDrawer(
    `${nameOf(field)} · 这一点为什么动`,
    '每次变动都有触发它的事',
    [{ source: '第 ' + (index + 1) + ' 个点', detail: '点开看当时发生了什么', confidence: 1, at: '趋势' }],
  )
}

/*
 * 缺口清单被展示出来（注册表里的 collect_gap_show）。
 *
 * 传"还剩几条"而不是布尔：这条埋点要回答的是"缺口还剩几条时他才会来看"，
 * 布尔答不了这个问题。
 */
watch(level, (now) => {
  if (now === 'gaps') track('collect_gap_show', { missing: gaps.value.length })
})

const CRUMB: Record<Level, string> = {
  overview: '概览',
  dims: '判断维度',
  records: '档案信息',
  gaps: '还差什么',
  analysis: '整份画像的判断',
  field: '这一条',
}

const levelTitle = computed(() => (level.value === 'field' ? selected.value?.label ?? '这一条' : CRUMB[level.value]))

const levelMeta = computed(() => {
  switch (level.value) {
    case 'dims':
      return `${dimItems.value.length} 条`
    case 'records':
      return `${factItems.value.length} 条`
    case 'gaps':
      return gaps.value.length ? `${gaps.value.length} 条` : '齐了'
    case 'analysis':
      return 'AI'
    case 'field':
      return selected.value ? `把握 ${selected.value.confidence.toFixed(2)}` : ''
    default:
      return ''
  }
})

/** 从哪一层点进来的 —— 决定返回键上写什么 */
const backTo = computed(() => {
  if (level.value !== 'field' || trail.value.length <= 2) return '概览'
  const parent = trail.value[trail.value.length - 2]
  return CRUMB[parent] ?? '概览'
})

/**
 * 一层里该先点哪一个。
 *
 * 顺序按"现在卡在哪儿"排：有缺口先补缺口（它挡着后面每一件事）；
 * 有判断维度就逐条核对；两样都没有（画像里全是档案）时**不给任何一行加主色** ——
 * 那时候该做的是去说话，不是点目录，把绿色压在一个空清单上等于指错了路。
 */
const leadEntry = computed<'dims' | 'gaps' | null>(() => {
  if (gaps.value.length) return 'gaps'
  if (dimItems.value.length) return 'dims'
  return null
})
</script>

<template>
  <Overlay
    title="你的画像"
    subtitle="全部来自你自己的记录 · 每一条都能追回去"
    :size="allItems.length ? 'tall' : 'mid'"
    from="portrait"
    @close="session.closeOverlay()"
  >
    <!-- 整页的材质走这一组变量（见下面 .pt），子组件只认变量不认色值 -->
    <div class="pt" :class="{ 'pt--blank': !allItems.length }">
      <!-- 一条记录都没有：整页只留"为什么空着 + 现在点哪里" -->
      <PortraitEmpty v-if="!allItems.length" />

      <template v-else>
        <!--
          二层、三层的抬头：返回键 + 面包屑 + 这一段叫什么 + 一行数字。
          一层没有这一条 —— 一层没有"上一级"，摆一个返回键只会让人怀疑自己走错了。
        -->
        <header v-if="!atRoot" class="bar">
          <button class="back" type="button" @click="back">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <path d="M7.6 2.4 4 6l3.6 3.6" fill="none" stroke="currentColor" stroke-width="1.6"
                    stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            返回 {{ backTo }}
          </button>
          <div class="bar__t">
            <span class="label bar__crumb">你的画像</span>
            <h3 class="bar__title">{{ levelTitle }}</h3>
          </div>
          <span v-if="levelMeta" class="bar__meta">{{ levelMeta }}</span>
        </header>

        <!-- ── 第一层：概览 ────────────────────────────────────────────
             抬头统计 → 中间那张分析图 → 一张能点的目录。
             这一层只回答"现在是什么样"，不展开任何一条明细。
        -->
        <template v-if="level === 'overview'">
          <PortraitSummary
            :overall="profile?.overall ?? 0"
            :coverage="profile?.coverage ?? 0"
            :fields="allItems"
            :judgment-count="dimItems.length"
            :gap-count="gaps.length"
            :updated-at="profile?.updatedAt ?? null"
          />

          <div class="ov">
            <div class="ov__fig">
              <!--
                有判断维度才画图。一条都没有时这里**不画** ——
                拿档案事实画出来的图是假的，而假图比空白更坏：
                它看起来像"系统已经分析过你了"。
              -->
              <PortraitChart
                v-if="chartDims.length"
                :dims="chartDims"
                :selected="selectedKey"
                @select="openField"
              />

              <section v-else class="nofig">
                <span class="label nofig__k">这张图暂时画不出来</span>
                <h4 class="nofig__t">现在记下的，全是档案</h4>
                <p class="nofig__d">
                  学校、专业、学籍、学制这些是从学信网抄下来的<b>事实</b>，
                  把握度都一样，画成图只会得到一圈顶满的线 —— 它说明不了你是谁。
                </p>
                <p class="nofig__d">
                  图上要有东西，得先有这几条：兴趣、价值取向、经历、能力自评。
                  它们只能你亲口说，别人替不了。
                </p>
                <div class="nofig__acts">
                  <button class="primary" type="button" @click="session.openOverlay('talk')">去聊两句</button>
                  <button class="ghost" type="button" @click="go('gaps')">看还差哪几条</button>
                </div>
              </section>
            </div>

            <nav class="menu" aria-label="画像里能去哪">
              <span class="label menu__k">往下看</span>
              <ul>
                <li>
                  <button
                    class="mrow" :class="{ 'mrow--lead': leadEntry === 'dims' }"
                    type="button" @click="go('dims')"
                  >
                    <span class="mrow__badge">{{ dimItems.length || '—' }}</span>
                    <span class="mrow__body">
                      <span class="mrow__t">判断维度</span>
                      <span class="mrow__d">
                        {{ dimItems.length
                          ? '兴趣、价值取向、经历……会变的那几条'
                          : '还没有 —— 说几句就有了' }}
                      </span>
                    </span>
                    <span class="mrow__go" aria-hidden="true">→</span>
                  </button>
                </li>
                <li>
                  <button class="mrow" type="button" @click="go('records')">
                    <span class="mrow__badge">{{ factItems.length }}</span>
                    <span class="mrow__body">
                      <span class="mrow__t">档案信息</span>
                      <span class="mrow__d">学校、专业、学籍：从权威记录抄下来的事实</span>
                    </span>
                    <span class="mrow__go" aria-hidden="true">→</span>
                  </button>
                </li>
                <li>
                  <button
                    class="mrow" :class="{ 'mrow--lead': leadEntry === 'gaps' }"
                    type="button" @click="go('gaps')"
                  >
                    <span class="mrow__badge">{{ gaps.length || '✓' }}</span>
                    <span class="mrow__body">
                      <span class="mrow__t">还差什么</span>
                      <span class="mrow__d">
                        {{ gaps.length ? '补上它，后面的判断才稳' : '关键字段都拿到了，没有缺口' }}
                      </span>
                    </span>
                    <span class="mrow__go" aria-hidden="true">→</span>
                  </button>
                </li>
                <li>
                  <button class="mrow" type="button" @click="go('analysis')">
                    <span class="mrow__badge mrow__badge--ai">AI</span>
                    <span class="mrow__body">
                      <span class="mrow__t">整份画像的判断</span>
                      <span class="mrow__d">把这一份合起来读一遍：亮点、要小心、下一步</span>
                    </span>
                    <span class="mrow__go" aria-hidden="true">→</span>
                  </button>
                </li>
              </ul>
            </nav>
          </div>
        </template>

        <!-- ── 第二层：判断维度 ───────────────────────────────────── -->
        <PortraitFieldList
          v-else-if="level === 'dims'"
          kind="judgment"
          :items="dimItems"
          :selected-key="selectedKey"
          :gap-count="gaps.length"
          @select="openField"
        />

        <!-- ── 第二层：档案信息 ───────────────────────────────────── -->
        <div v-else-if="level === 'records'" class="records">
          <p class="records__lead">
            这些是从权威记录直接抄下来的事实，不是你自述的 —— 所以它们没有"把握度"，
            也不需要你去核对。它们只说明"你在哪儿"，不说明你是谁。
          </p>
          <PortraitFieldList
            kind="record"
            :items="factItems"
            :selected-key="selectedKey"
            :gap-count="0"
            @select="openField"
          />
        </div>

        <!-- ── 第二层：还差什么 ───────────────────────────────────── -->
        <div v-else-if="level === 'gaps'" class="gaps-view">
          <p class="gaps-view__lead">
            {{ gaps.length
              ? '这些还没定下来 —— 补上它，后面的判断才稳。'
              : '当前没有缺口：关键字段都拿到了。' }}
          </p>
          <ul v-if="gaps.length" class="gaps">
            <li v-for="gap in gaps" :key="gap.id">
              <button class="gap" type="button" @click="showGap(gap)">
                <span class="gap__t">{{ gap.name || gap.id }}</span>
                <span class="gap__go" aria-hidden="true">看怎么补 →</span>
                <span class="gap__why">{{ gap.question }}</span>
                <span class="gap__next">{{ gap.suggested }}</span>
              </button>
            </li>
          </ul>
          <div v-else class="done">
            <span class="done__mark" aria-hidden="true">✓</span>
            <p class="done__t">画像里该有的都在了。</p>
            <button class="link" type="button" @click="go('analysis')">看整份判断 →</button>
          </div>
        </div>

        <!-- ── 第二层：整份画像的判断 ─────────────────────────────── -->
        <section v-else-if="level === 'analysis'" class="pa">
          <AiFrame :task="analysisTask">
            <template #default="{ data }">
              <div v-if="data" class="pa__body">
                <h4 class="pa__headline">{{ (data as PortraitAnalysis).headline }}</h4>
                <p class="pa__reading">{{ (data as PortraitAnalysis).reading }}</p>
                <div class="pa__cols">
                  <section v-for="col in PA_COLS" :key="col.key" class="pa__col">
                    <h5 class="label pa__col-k">{{ col.label }}</h5>
                    <ul>
                      <li v-for="pt in (data as PortraitAnalysis)[col.key]" :key="pt.label">
                        <span class="pa__lab">{{ pt.label }}</span>
                        <span class="pa__why">{{ pt.why }}</span>
                      </li>
                    </ul>
                  </section>
                </div>
                <p class="pa__foot">
                  这一段读的是整份画像。想核对某一条，回上一层逐条看 —— 每条都写着它从哪来。
                </p>
              </div>
            </template>
          </AiFrame>
        </section>

        <!-- ── 第三层：这一条 ────────────────────────────────────── -->
        <PortraitDetail
          v-else-if="selected"
          :field="selected"
          :source-label="sourceLabel(selected.source)"
          :read-value="readValue"
          :stamp="stamp"
          :task="() => dimensionTask(selected!.key) as never"
          @evidence="showEvidence(selected.label, selected.evidence)"
          @pick-trend="onTrend"
        />
      </template>
    </div>
  </Overlay>
</template>

<style scoped>
/*
 * 这一页自带的材质 —— 「案头卷宗」。
 *
 * 曾经这一页是一块冷白的玻璃板（石板墨文字 + Tailwind 默认蓝紫青），和外壳的
 * 暖纸完全割裂，用户判它"非常丑"。现在整组令牌全部回到外壳的"纸与墨"：
 * 纸面、墨字、石膏凹槽、马克笔分类色。子模块里没有一条写死的色值，
 * 换皮肤仍然只改这一组变量。
 */
.pt {
  --pt-ink: var(--ink-1);
  --pt-muted: var(--ink-2);
  /*
   * 说明文字的最小对比度：对纸白 5.2:1。再浅一档就只在 3 字头，
   * 说明文字会先于标题失去可读性。
   */
  --pt-faint: var(--ink-3);

  --pt-surface: var(--c-paper);
  --pt-well: var(--c-sand-1);

  --pt-line: var(--line-2);
  --pt-line-strong: var(--line-3);
  --pt-track: var(--c-sand-1);

  /*
   * 强调色就是外壳那一支绿。`--pt-accent` 承载文字与深底（对纸白 8.4:1），
   * `--pt-accent-2` 只做图形标记。
   */
  --pt-accent: var(--accent);
  --pt-accent-2: var(--accent-bright);
  --pt-accent-deep: var(--accent-deep);
  --pt-soft: var(--accent-soft);
  /* 风险用外壳的陶橙，不再另起一支琥珀 */
  --pt-warn: var(--warn);

  /* 纸比玻璃方：圆角整体收一档，纸的"边"才立得住 */
  --pt-r-sm: 8px;
  --pt-r-md: 12px;
  --pt-r-lg: 16px;

  /* 来源分类色：直接用外壳的马克笔（顺序对齐 PortraitSummary 的图例分配） */
  --pt-src-1: var(--mk-blue);
  --pt-src-2: var(--mk-purple);
  --pt-src-3: var(--mk-teal);
  --pt-src-4: var(--mk-orange);
  --pt-src-5: var(--mk-green);

  position: relative;
  display: grid; gap: var(--s4);
  align-content: start;
  min-height: 0;
  padding: var(--s5);
  background: var(--paper-lit);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-lg);
  /* 纸的厚度：外壳同一套三层投影 + 顶部高光，不再自备冷灰大模糊 */
  box-shadow: var(--e-4), var(--inner-hi);
}
/* 面上的光：从上面打下来（与 .sheet 同一手法），不再有冷绿的径向光晕 */
.pt::before {
  content: "";
  position: absolute; inset: 0 0 auto 0; height: 42%;
  border-radius: inherit;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72), transparent);
}
.pt > * { position: relative; }

/*
 * 空画像：**内容决定高度**。纸自己收缩到内容，空状态由 PortraitEmpty
 * 当成一张海报来排（左色块 + 右三步）。
 */
.pt--blank { padding: var(--s5); align-content: start; justify-items: stretch; }

/* ── 二层 / 三层的抬头 ───────────────────────────────────────────── */
.bar {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center; gap: var(--s4);
  padding-bottom: var(--s3);
  border-bottom: 1px solid var(--line-1);
}
.back {
  display: inline-flex; align-items: center; gap: 5px;
  height: 30px; padding: 0 12px 0 9px;
  border: 1px solid var(--pt-line); border-radius: var(--r-pill);
  background: var(--pt-surface); color: var(--pt-muted);
  font-size: var(--t-xs); font-weight: 500;
  box-shadow: var(--e-1), var(--inner-hi);
  transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out);
}
.back:hover { border-color: var(--pt-line-strong); color: var(--pt-ink); }
.back svg { transition: transform 160ms var(--ease-out); }
.back:hover svg { transform: translateX(-2px); }

.bar__t { display: grid; gap: 1px; min-width: 0; }
.bar__crumb { color: var(--ink-4); }
.bar__title {
  font-family: var(--font-editorial);
  font-size: 21px; font-weight: 600; letter-spacing: -0.01em; color: var(--pt-ink);
}
/* 长度兜底：字段名可能很长（"简历与作品材料"），不能把抬头撑破 */
.bar__title, .bar__meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar__meta { font-size: var(--t-xs); color: var(--pt-faint); font-variant-numeric: tabular-nums; }

/* ── 第一层：中间那张图 + 右边的目录 ─────────────────────────────── */
.ov {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
  gap: var(--s6);
  align-items: start;
}
.ov__fig { min-width: 0; display: grid; }

/*
 * 画不出图时的那一屏。
 *
 * 它要顶住一个诱惑：拿档案事实凑一张图出来。所以这段文字必须**自己解释清楚**
 * 为什么这里空着 —— 空白会被读成"没做完"，有理由的空白才是设计。
 */
.nofig {
  display: grid; gap: var(--s3); align-content: start;
  padding: var(--s5);
  border: 1px dashed var(--pt-line-strong);
  border-radius: var(--pt-r-md);
  background: var(--fill-subtle);
}
.nofig__k { color: var(--ink-4); }
.nofig__t {
  font-family: var(--font-editorial);
  font-size: 21px; font-weight: 600; letter-spacing: -0.01em; color: var(--pt-ink);
}
.nofig__d { font-size: var(--t-sm); color: var(--pt-muted); line-height: 1.8; max-width: 52ch; }
.nofig__acts { display: flex; gap: var(--s2); padding-top: var(--s1); }
.primary {
  height: 34px; padding: 0 16px; border-radius: var(--r-pill);
  background: var(--pt-accent); color: var(--accent-ink);
  font-size: var(--t-sm); font-weight: 600;
  box-shadow: var(--e-2);
  transition: transform 160ms var(--ease-out), background 160ms var(--ease-out);
}
.primary:hover { background: var(--pt-accent-deep); transform: translateY(-1px); }
.ghost {
  height: 34px; padding: 0 16px; border-radius: var(--r-pill);
  border: 1px solid var(--pt-line); background: var(--pt-surface); color: var(--pt-muted);
  font-size: var(--t-sm); font-weight: 500;
  transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out);
}
.ghost:hover { border-color: var(--pt-line-strong); color: var(--pt-ink); }

.menu { display: grid; gap: var(--s2); align-content: start; }
.menu__k { color: var(--ink-4); }
.menu ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }

/*
 * 目录行。
 *
 * 它是这一层唯一的交互物，所以长得像"一条能按下去的纸"：
 * 左边一枚方章（数字 / ✓ / AI）、中间两行字、右边一个箭头。
 * 该点的那一行换成签名绿 —— 一屏只允许有一个主色块。
 */
.mrow {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center; gap: var(--s3);
  width: 100%; text-align: left;
  padding: 12px 14px;
  border: 1px solid var(--pt-line);
  border-radius: var(--pt-r-md);
  background: var(--pt-surface);
  box-shadow: var(--e-1), var(--inner-hi);
  transition: border-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out),
              transform 160ms var(--ease-out), background 160ms var(--ease-out);
}
.mrow:hover {
  border-color: var(--pt-line-strong);
  box-shadow: var(--e-2), var(--inner-hi);
  transform: translateY(-1px);
}
.mrow--lead { border-color: var(--pt-accent); background: var(--pt-soft); }

.mrow__badge {
  min-width: 38px; height: 38px; padding: 0 8px;
  display: grid; place-items: center;
  border-radius: 10px;
  background: var(--pt-well); color: var(--pt-muted);
  font-family: var(--font-editorial);
  font-size: var(--t-body); font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.mrow--lead .mrow__badge { background: var(--pt-accent); color: var(--accent-ink); }
.mrow__badge--ai { font-size: var(--t-xs); letter-spacing: 0.04em; }

.mrow__body { display: grid; gap: 2px; min-width: 0; }
.mrow__t { font-size: var(--t-body); font-weight: 600; color: var(--pt-ink); }
.mrow__d { font-size: var(--t-xs); color: var(--pt-faint); line-height: 1.6; }
.mrow__go {
  color: var(--ink-4); font-size: var(--t-sm);
  transition: color 160ms var(--ease-out), transform 160ms var(--ease-out);
}
.mrow:hover .mrow__go { color: var(--pt-accent); transform: translateX(2px); }

/* ── 第二层：档案 ────────────────────────────────────────────────── */
.records { display: grid; gap: var(--s3); align-content: start; }
.records__lead { font-size: var(--t-sm); color: var(--pt-muted); line-height: 1.75; max-width: 74ch; }

/* ── 第二层：还差什么 ────────────────────────────────────────────── */
.gaps-view { display: grid; gap: var(--s3); align-content: start; }
.gaps-view__lead { font-size: var(--t-sm); color: var(--pt-muted); line-height: 1.7; }
.gaps { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.gap {
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px var(--s4);
  width: 100%; text-align: left;
  padding: var(--s3) var(--s4);
  border: 1px solid var(--pt-line); border-radius: var(--pt-r-md);
  background: var(--pt-surface);
  box-shadow: var(--e-1), var(--inner-hi);
  transition: border-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out), transform 160ms var(--ease-out);
}
.gap:hover {
  border-color: var(--pt-line-strong); transform: translateY(-1px);
  box-shadow: var(--e-2), var(--inner-hi);
}
.gap__t { font-size: var(--t-body); font-weight: 600; color: var(--pt-ink); }
.gap__go {
  grid-row: 1 / span 3; align-self: center;
  font-size: var(--t-xs); color: var(--pt-accent); white-space: nowrap;
}
.gap__why { grid-column: 1; font-size: var(--t-sm); color: var(--pt-muted); line-height: 1.7; }
.gap__next { grid-column: 1; font-size: var(--t-xs); color: var(--pt-accent); }

.done { display: grid; justify-items: start; gap: var(--s2); padding: var(--s5) 0; }
.done__mark {
  display: grid; place-items: center; width: 34px; height: 34px;
  border-radius: 50%; background: var(--pt-soft); color: var(--pt-accent);
  font-size: 17px;
}
.done__t { font-family: var(--font-editorial); font-size: var(--t-h4); color: var(--pt-ink); }
.link {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--t-sm); font-weight: 500; color: var(--pt-accent);
}
.link:hover { text-decoration: underline; }

/* ── 第二层：整份画像的判断 ──────────────────────────────────────── */
.pa { display: grid; gap: var(--s3); min-width: 0; }
.pa__body { display: grid; gap: var(--s4); }
.pa__headline {
  font-family: var(--font-editorial);
  font-size: 22px; font-weight: 600; line-height: 1.45; color: var(--pt-ink);
  max-width: 46ch;
}
.pa__reading { font-size: var(--t-body); color: var(--pt-muted); line-height: 1.8; max-width: 72ch; }
.pa__cols {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s5);
  padding-top: var(--s3);
  border-top: 1px solid var(--line-1);
}
.pa__col { display: grid; gap: 8px; align-content: start; }
.pa__col-k { color: var(--ink-4); }
.pa__col ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s3); }
.pa__col li { display: grid; gap: 3px; }
.pa__lab { font-size: var(--t-sm); font-weight: 600; color: var(--pt-ink); line-height: 1.5; }
.pa__why { font-size: var(--t-xs); color: var(--pt-faint); line-height: 1.65; }
.pa__foot {
  padding-top: var(--s3);
  border-top: 1px dashed var(--line-2);
  font-size: var(--t-xs); color: var(--pt-faint); line-height: 1.7;
}

@media (max-width: 1080px) {
  .ov { grid-template-columns: minmax(0, 1fr); gap: var(--s5); }
  .pa__cols { grid-template-columns: minmax(0, 1fr); gap: var(--s4); }
}
</style>
