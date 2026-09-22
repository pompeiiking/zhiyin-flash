<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import { track } from '@/api/client'
import { dimensionTask } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'
import PortraitSummary from '@/components/portrait/PortraitSummary.vue'
import PortraitFieldList from '@/components/portrait/PortraitFieldList.vue'
import PortraitDetail from '@/components/portrait/PortraitDetail.vue'
import PortraitEmpty from '@/components/portrait/PortraitEmpty.vue'
import PortraitRadar from '@/components/portrait/PortraitRadar.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { portraitTask, type PortraitAnalysis } from '@/ai/registry'
import { PORTRAIT } from '@/data/content'

/**
 * 画像 —— 先说"你现在是个什么处境"，再往下才是字段清单。
 *
 * **全部内容都归后端**：
 *   · 字段、把握度、来源、更新时间、证据：`GET /app/workspace` 的 profile_panel；
 *   · 还缺哪几条、建议怎么补：同一个回包的 gaps；
 *   · 整份画像的判断：`POST /app/portrait/analysis`（打开就算，整份画像一份）；
 *   · "这一条是什么意思"那段解读：`POST /app/dimensions/{字段 key}`（点开才算）。
 *
 * 为什么那一段要按字段 key 去生成，而不是拿展示名：后端按 key 取该字段的全部依据，
 * 名字是给人看的，取数得用 key。所以这里传 `field.key`。
 *
 * 【风格】这一页**自带一套材质**（下面 `.pt` 里那组 `--pt-*`），不跟着外壳的
 * "纸与墨"走：外壳是暖纸，这一页是一块冷白的玻璃。两者靠遮罩分开，
 * 读起来是"桌面上摊着一页纸，纸上压着一块玻璃板"。换皮肤只改那一组变量。
 */
const session = useSessionStore()

/**
 * 显示密度 —— 风格定制的一部分。
 *
 * 同一个人在不同场景下要的东西不一样：**看细节时**要宽松（在画像页逐条读），
 * **扫一眼时**要紧凑（把它当侧栏用）。所以密度是个开关，而不是一个写死的数。
 * 状态记在本地：用户调过一次，下次进来还是那样。
 */
const DENSITY_KEY = 'zhiyin_portrait_density'
const density = ref<'cozy' | 'compact'>(localStorage.getItem(DENSITY_KEY) === 'compact' ? 'compact' : 'cozy')
function setDensity(next: 'cozy' | 'compact') {
  density.value = next
  localStorage.setItem(DENSITY_KEY, next)
}

const profile = computed(() => session.profile)
const fields = computed(() => profile.value?.fields ?? [])
const gaps = computed(() => profile.value?.gaps ?? [])

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

/*
 * 左侧选中的是哪一项：`analysis`（整体判断）/ `gaps`（缺口清单）/ 某个字段的 key。
 * 它取代了原来那个 showGaps 布尔 —— 三种视图挤在一个布尔里，
 * 迟早会出现"既不是字段也不是缺口"的空档，而且默认值只能是三者之一。
 */
const view = ref<string>(session.portraitFocus === 'gaps' ? 'gaps' : 'analysis')
const showGaps = computed({
  get: () => view.value === 'gaps',
  set: (on: boolean) => {
    if (on) view.value = 'gaps'
    else if (view.value === 'gaps') view.value = 'analysis'
  },
})

/**
 * 缺口清单被展示出来（注册表里的 collect_gap_show）。
 *
 * 传"还剩几条"而不是布尔：这条埋点要回答的是"缺口还剩几条时他才会来看"，
 * 布尔答不了这个问题。
 */
watch(showGaps, (on) => {
  if (on) track('collect_gap_show', { missing: gaps.value.length })
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

/**
 * 第二层要的那份清单。
 *
 * 把"字段"与"缺口"按 key 对齐：某一条既在画像里、又出现在待补里，
 * 说明它还**没定下来**（把握低），列表上要能一眼看出来。
 */
const items = computed(() => {
  const pendingKeys = new Set(gaps.value.map((g) => g.id))
  return fields.value.map((field) => ({
    key: field.key,
    label: nameOf(field),
    confidence: field.confidence ?? 0,
    source: field.source,
    updatedAt: String(field.updated_at ?? ''),
    evidenceCount: (field.evidence ?? []).length,
    pending: pendingKeys.has(field.key),
  }))
})

/** 整体解读的三栏（AnalysisPoint[]：label + why） */
const PA_COLS = [
  { key: 'strengths', label: '亮点' },
  { key: 'watchouts', label: '要小心' },
  { key: 'next', label: '下一步' },
] as const

/** 雷达图的维度：后端没给（演示态）就退回示例画像的维度 */
const radarDims = computed(() => {
  const dims = (session.profile?.dimensions?.length ? session.profile.dimensions : PORTRAIT.dimensions) as { id: string; name: string; value: number }[]
  return dims.map((d) => ({ id: d.id, name: d.name, value: d.value }))
})
const analysisTask = () => portraitTask() as never

function select(key: string) {
  selectedKey.value = key
  view.value = 'analysis'
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
</script>

<template>
  <Overlay
    title="你的画像"
    subtitle="全部来自你自己的记录 · 每一条都能追回去"
    :size="items.length ? 'tall' : 'mid'"
    from="portrait"
    @close="session.closeOverlay()"
  >
    <!-- 风格定制：整屏的材质都走这一组变量，换一组就换一种皮肤 -->
    <div class="pt" :class="[`pt--${density}`, { 'pt--blank': !items.length }]">
      <!-- 一条记录都没有：整页只留"为什么空着 + 现在点哪里" -->
      <PortraitEmpty v-if="!items.length" />

      <template v-else>
        <div class="pt__tools">
          <div class="seg" role="group" aria-label="显示密度">
            <button
              type="button" class="seg__b" :class="{ 'seg__b--on': density === 'cozy' }"
              :aria-pressed="density === 'cozy'" @click="setDensity('cozy')"
            >舒适</button>
            <button
              type="button" class="seg__b" :class="{ 'seg__b--on': density === 'compact' }"
              :aria-pressed="density === 'compact'" @click="setDensity('compact')"
            >紧凑</button>
          </div>

          <button
            class="gaps-btn" :class="{ 'gaps-btn--on': view === 'gaps' }"
            type="button" :aria-pressed="view === 'gaps'"
            @click="view = view === 'gaps' ? 'analysis' : 'gaps'"
          >
            还差什么
            <b>{{ gaps.length }}</b>
          </button>
        </div>

        <!-- 抬头：覆盖 / 格子 / 来源 -->
        <PortraitSummary
          :overall="profile?.overall ?? 0"
          :coverage="profile?.coverage ?? 0"
          :fields="items"
          :gap-count="gaps.length"
          :updated-at="profile?.updatedAt ?? null"
        />

        <!--
          图表汇总：左 = 手绘蛛网雷达（rough.js 直绘，点维度切明细），
          右 = 模型对**整份画像**的判断（点开才算，缓存按整份画像存）。
          这一回答的是"合起来看你是个什么人"，下面的清单回答"每一条是什么"。
        -->
        <div v-if="view === 'analysis'" class="pt__overview">
          <PortraitRadar :dims="radarDims" :selected="selectedKey" @select="select" />

          <section class="pa">
            <h3 class="pa__t">整份画像的判断</h3>
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
                </div>
              </template>
            </AiFrame>
          </section>
        </div>

        <!-- 左：清单。右：详情 -->
        <div class="pt__body">
          <aside class="pt__side">
            <PortraitFieldList
              :items="items"
              :selected-key="selectedKey"
              :gap-count="gaps.length"
              @select="select"
            />
          </aside>

          <section class="pt__main">
            <!-- 缺口清单：每条都写清"为什么缺 + 建议怎么补" -->
            <div v-if="view === 'gaps'" class="gaps-view">
              <h3 class="gaps-view__t">还差这些 —— 补上它，后面的判断才稳。</h3>
              <p v-if="!gaps.length" class="muted">当前没有缺口：关键字段都拿到了。</p>
              <ul v-else class="gaps">
                <li v-for="gap in gaps" :key="gap.id">
                  <button class="gap" type="button" @click="showGap(gap)">
                    <span class="gap__t">{{ gap.name || gap.id }}</span>
                    <span class="gap__why">{{ gap.question }}</span>
                    <span class="gap__next">{{ gap.suggested }}</span>
                  </button>
                </li>
              </ul>
            </div>

            <!--
              单条字段：三段式（内容 → 依据 → 解读）。

              这里没有 v-else 兜底：进到这一支说明 `items` 非空，而 `selected` 取的是
              "选中的那条，取不到就取第一条" —— 有清单就一定有内容可显示。
              空画像已经在上面整页接管了，不存在第三种状态。
            -->
            <PortraitDetail
              v-else
              :field="selected!"
              :source-label="sourceLabel(selected!.source)"
              :read-value="readValue"
              :stamp="stamp"
              :task="() => dimensionTask(selected!.key) as never"
              @evidence="showEvidence(selected!.label || selected!.key, selected!.evidence ?? [])"
              @pick-trend="onTrend"
            />
          </section>
        </div>
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
   * `--pt-accent-2` 只做渐变与图形标记。
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

  /*
   * 来源分类色：直接用外壳的马克笔（矿物色相，深支对纸白 ≥4.5:1）。
   * 顺序对齐 PortraitSummary 的图例分配：群青 / 梅 / 青灰 / 赭石 / 苔。
   */
  --pt-src-1: var(--mk-blue);
  --pt-src-2: var(--mk-purple);
  --pt-src-3: var(--mk-teal);
  --pt-src-4: var(--mk-orange);
  --pt-src-5: var(--mk-green);

  --pt-gap: var(--s4);

  position: relative;
  display: grid; gap: var(--s3);
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

.pt--compact { --pt-gap: var(--s3); }
/*
 * 空画像：**内容决定高度**。
 *
 * 上一版这里是 `align-content: center; justify-items: center` —— 把一小块
 * 虚线框摆进一张铺满 800px 的纸中央，上下各留两百多像素白。
 * 打开就是"一大片空白中间钉着一张小纸"。现在纸自己收缩到内容，
 * 空状态由 PortraitEmpty 当成一张海报来排（左色块 + 右三步）。
 */
.pt--blank { padding: var(--s5); align-content: start; justify-items: stretch; }

.pt__tools { display: flex; align-items: center; gap: var(--s2); }

/* 分段控件：凹槽 + 浮起的选中块。全页只有这一套控件语法 */
.seg {
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
  gap: 2px; padding: 3px;
  border-radius: var(--pt-r-sm);
  background: var(--pt-well);
}
.seg__b {
  height: 24px; padding: 0 11px; border-radius: 6px;
  font-size: var(--t-xs); font-weight: 500; color: var(--pt-muted);
  transition: background 160ms var(--ease-out), color 160ms var(--ease-out), box-shadow 160ms var(--ease-out);
}
.seg__b:hover { color: var(--pt-ink); }
.seg__b--on { background: var(--pt-surface); color: var(--pt-ink); box-shadow: var(--e-1), var(--inner-hi); }

.gaps-btn {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 6px;
  height: 30px; padding: 0 12px;
  border: 1px solid var(--pt-line); border-radius: var(--r-pill);
  background: var(--pt-surface); color: var(--pt-muted);
  font-size: var(--t-xs); font-weight: 500;
  box-shadow: var(--e-1), var(--inner-hi);
  transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out), background 160ms var(--ease-out);
}
.gaps-btn:hover { border-color: var(--pt-line-strong); color: var(--pt-ink); }
.gaps-btn b { color: var(--pt-faint); font-weight: 600; font-variant-numeric: tabular-nums; }
.gaps-btn--on { border-color: var(--pt-accent); color: var(--pt-accent); background: var(--pt-soft); }
.gaps-btn--on b { color: var(--pt-accent); }

.pt__body {
  display: grid; grid-template-columns: 288px minmax(0, 1fr);
  gap: var(--pt-gap);
  align-items: start;
  min-height: 0;
}
.pt__side { position: sticky; top: 0; min-width: 0; }
.pt__main { min-width: 0; }
.pt--compact .pt__body { grid-template-columns: 240px minmax(0, 1fr); }

/* 缺口清单 */
.gaps-view { display: grid; gap: var(--s3); }
.gaps-view__t {
  font-family: var(--font-editorial);
  font-size: 19px; font-weight: 600; letter-spacing: -0.01em; color: var(--pt-ink);
}
.gaps-view .muted { font-size: var(--t-sm); color: var(--pt-muted); }
.gaps { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.gap {
  display: grid; gap: 5px; width: 100%; text-align: left;
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
.gap__t { font-size: var(--t-sm); font-weight: 600; color: var(--pt-ink); }
.gap__why { font-size: var(--t-sm); color: var(--pt-muted); line-height: 1.7; }
.gap__next { font-size: var(--t-xs); color: var(--pt-accent); }

/*
 * 图表汇总区：左雷达右判断，之间一条发丝线分 —— 不套卡片。
 * "合起来看"的这一层和"逐条看"的那一层之间，用留白与一条线分节。
 */
.pt__overview {
  display: grid; grid-template-columns: minmax(280px, 400px) minmax(0, 1fr);
  gap: var(--s5); align-items: start;
  padding: var(--s4) 0 var(--s2);
  border-bottom: 1px solid var(--line-1);
}

.pa { display: grid; gap: var(--s3); min-width: 0; }
.pa__t {
  font-size: var(--t-xs); font-weight: 600; color: var(--pt-muted);
  letter-spacing: 0;
}
.pa__headline {
  font-family: var(--font-editorial);
  font-size: 19px; font-weight: 600; line-height: 1.5; color: var(--pt-ink);
}
.pa__reading { font-size: var(--t-sm); color: var(--pt-muted); line-height: 1.8; max-width: 68ch; }
.pa__cols { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s4); }
.pa__col { display: grid; gap: 6px; align-content: start; }
.pa__col-k { color: var(--ink-4); }
.pa__col ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.pa__col li { display: grid; gap: 2px; }
.pa__lab { font-size: var(--t-xs); font-weight: 600; color: var(--pt-ink); line-height: 1.5; }
.pa__why { font-size: var(--t-xs); color: var(--pt-faint); line-height: 1.65; }

@media (max-width: 1080px) {
  .pt__body { grid-template-columns: minmax(0, 1fr); }
  .pt__side { position: static; }
  .pt__overview { grid-template-columns: minmax(0, 1fr); }
  .pa__cols { grid-template-columns: minmax(0, 1fr); }
}
</style>
