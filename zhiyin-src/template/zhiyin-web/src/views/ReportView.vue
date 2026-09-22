<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  exportAsset,
  getReportFullText,
  listAssetVersions,
  track,
  type AssetVersion,
} from '@/api/client'
import AiFrame from '@/components/ai/AiFrame.vue'
import { reportTask, type ReportSummary } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'
import { failureText } from '@/lib/failure'

/**
 * 报告页 —— 正文全部来自后端资产（`GET /app/report/full-text`）。
 *
 * 页面上有三块，来源各不相同，但**没有一块是前端编的**：
 *
 *   1. **结论段**：`POST /app/report/summary`（点开页面时生成，带依据与 rationale）
 *   2. **15 维正文**：报告资产的 `sections` —— 每维带标签、结论、证据引用
 *   3. **判定 / SWOT / 方法 / 来源**：同一份资产的其余字段
 *
 * 没有报告资产时（`sections` 为空、version=0）如实说"还没生成"，
 * 并给一条出路（回今天 / 去看结论段）—— 而不是渲染一份看起来像报告的空壳。
 *
 * 每一句都能点开溯源：维度点证据、结论段点 AI 标记，走的都是同一个抽屉。
 */
const router = useRouter()
const session = useSessionStore()

const report = computed(() => session.report)
const sections = computed(() => report.value?.sections ?? [])
const hasReport = computed(() => sections.value.length > 0)
const dimCount = computed(() => sections.value.reduce((n, s) => n + (s.items?.length ?? 0), 0))

/*
 * 版本历史：报告是**版本化资产**（改一次画像，受影响的资产版本 +1）。
 * 这里读 `/app/assets/report/versions`，让人能看见"这一版是第几版、v1→v2 差在哪"。
 * 正文依旧由 `/app/report/full-text?version=N` 取 —— 版本行只描述，不承载正文。
 */
const versions = ref<AssetVersion[]>([])
const versionError = ref('')

onMounted(async () => {
  try {
    versions.value = await listAssetVersions('report')
  } catch {
    /* 版本历史读不到不影响正文：正文自己那份已经渲染出来了 */
  }
})

/** 导出：目前没有服务端导出，这里如实把这句话说出来 */
async function exportReport() {
  versionError.value = ''
  try {
    const result = await exportAsset('report', 'pdf')
    session.openDrawer('导出报告', result.message || '现在可以用「打印 / 存成 PDF」把这一版存下来。', [
      {
        source: '导出结果',
        detail: result.available
          ? '这一版已经生成，可以从服务端取走。'
          : '服务端导出还没开通：请用页面上的「打印 / 存成 PDF」把这一版存下来。',
        confidence: 1,
        at: '刚刚',
      },
    ])
  } catch (cause) {
    versionError.value = failureText(cause)
  }
}

const verdict = computed(() => (report.value?.verdict ?? {}) as { title?: string; summary?: string })
const swot = computed(() => (report.value?.swot ?? {}) as Record<string, string[]>)
const SWOT_LABELS: { key: string; label: string }[] = [
  { key: 'strength', label: '优势' },
  { key: 'weakness', label: '短板' },
  { key: 'opportunity', label: '机会' },
  { key: 'risk', label: '风险' },
]

function showEvidence(name: string, evidence: string) {
  session.openDrawer(`${name} · 这条结论的证据`, '报告里的原样引用', [
    { source: '证据引用', detail: evidence, confidence: 0.9, at: '报告版本' },
  ])
}

function printReport() {
  window.print()
}

/**
 * 切到某个历史版本。
 *
 * 走的是"重新读那一版正文"（`?version=N`），不是在前端缓存里翻 ——
 * 正文只有后端那一份，前端自己留一份就会在下次生成后对不上。
 */
async function onPickVersion(event: Event) {
  const version = Number((event.target as HTMLSelectElement).value)
  if (!version) return
  try {
    session.report = await getReportFullText(version)
  } catch (cause) {
    versionError.value = failureText(cause)
  }
}

onMounted(() => {
  // 打开完整报告页 —— 注册表里 diagnosis_view 是 frontend 通道的事件
  track('diagnosis_view', { version: report.value?.version ?? 0, dims: dimCount.value })
})
</script>

<template>
  <div class="report">
    <header class="top">
      <div class="top__l">
        <button class="back label" type="button" @click="router.push('/')">← 回到今天</button>
        <span class="mono top__sep">/</span>
        <span class="label top__crumb">完整报告</span>
      </div>
      <div class="top__r">
        <span class="label top__meta">
          <template v-if="hasReport">
            第 {{ report?.version }} 版 · {{ sections.length }} 组 · {{ dimCount }} 条维度 ·
            {{ report?.generated_at?.slice(0, 10) }}
          </template>
          <template v-else>还没有报告</template>
        </span>
        <!--
          版本历史：改一次画像，报告就多一版。
          这里把"第 1 版 → 这一版"的差异摆出来 —— 版本号不是一个装饰。
        -->
        <select
          v-if="versions.length > 1"
          class="top__versions"
          :value="report?.version ?? 0"
          aria-label="报告版本"
          @change="onPickVersion"
        >
          <option v-for="v in versions" :key="v.version" :value="v.version">
            第 {{ v.version }} 版 · {{ v.created_at?.slice(0, 10) }}{{ v.diff_from_previous ? ` · ${v.diff_from_previous}` : '' }}
          </option>
        </select>
        <button class="btn ghost" type="button" @click="printReport">打印 / 存成 PDF</button>
        <button class="btn ghost" type="button" @click="exportReport">导出</button>
      </div>
    </header>

    <main class="doc">
      <!-- 一、结论段（生成） -->
      <section class="lead">
        <p class="label lead__kicker">这一版报告的结论</p>
        <AiFrame :task="() => reportTask() as never" :label="'正在总结'">
          <template #default="{ data }">
            <div v-if="data" class="lead__body">
              <h1 class="lead__head editorial">{{ (data as ReportSummary).headline }}</h1>
              <div class="lead__cols">
                <p v-for="(p, i) in (data as ReportSummary).paragraphs ?? []" :key="i">{{ p }}</p>
              </div>
              <ol v-if="(data as ReportSummary).moves?.length" class="moves">
                <li v-for="(m, i) in (data as ReportSummary).moves" :key="i">
                  <span class="moves__n mono">{{ String(i + 1).padStart(2, '0') }}</span>
                  <span class="moves__label">{{ m.label }}</span>
                  <span class="moves__why">{{ m.why }}</span>
                </li>
              </ol>
            </div>
          </template>
        </AiFrame>
      </section>

      <!-- 二、判定：报告资产自带的一句话结论 -->
      <section v-if="verdict.title" class="verdict sheet">
        <h2 class="verdict__head">{{ verdict.title }}</h2>
        <p v-if="verdict.summary" class="verdict__sub">{{ verdict.summary }}</p>
      </section>

      <!-- 三、15 维正文：后端写成什么样，这里就长什么样 -->
      <template v-if="hasReport">
        <section v-for="section in sections" :id="section.id" :key="section.id" class="sec">
          <header class="sec__head">
            <h2 class="editorial">{{ section.title }}</h2>
            <span v-if="section.method" class="label sec__method">{{ section.method }}</span>
          </header>

          <ul class="dims">
            <li v-for="item in section.items ?? []" :key="item.index" class="dim">
              <div class="dim__row">
                <span class="mono dim__index">{{ String(item.index).padStart(2, '0') }}</span>
                <span class="dim__name">{{ item.name }}</span>
                <span class="dim__tag" :data-tag="item.tag">{{ item.tag }}</span>
              </div>
              <p class="dim__conclusion">{{ item.conclusion }}</p>
              <button class="dim__ev" type="button" @click="showEvidence(item.name, item.evidence)">
                <span class="label">证据</span>
                <span class="dim__ev-text">{{ item.evidence }}</span>
              </button>
            </li>
          </ul>
        </section>

        <!-- 四、SWOT -->
        <section v-if="Object.keys(swot).length" class="swot">
          <h2 class="editorial">四象限</h2>
          <div class="swot__grid">
            <article v-for="q in SWOT_LABELS" :key="q.key" class="quad">
              <h3 class="label">{{ q.label }}</h3>
              <ul>
                <li v-for="(line, i) in swot[q.key] ?? []" :key="i">{{ line }}</li>
              </ul>
            </article>
          </div>
        </section>

        <!-- 五、方法与来源 -->
        <section v-if="(report?.methodologies ?? []).length || (report?.sources ?? []).length" class="basis">
          <div v-if="(report?.methodologies ?? []).length" class="basis__col">
            <span class="label">这一版用了哪些方法</span>
            <div class="chips">
              <span v-for="m in report?.methodologies ?? []" :key="m" class="chip">{{ m }}</span>
            </div>
          </div>
          <div v-if="(report?.sources ?? []).length" class="basis__col">
            <span class="label">事实来源</span>
            <ul class="src">
              <li v-for="s in report?.sources ?? []" :key="s">{{ s }}</li>
            </ul>
          </div>
        </section>
      </template>

      <!-- 还没有报告资产：说清楚，并给一条出路 -->
      <section v-else class="empty sheet">
        <h2 class="empty__head">报告还没生成。</h2>
        <p class="empty__body">
          报告来自<b>诊断</b>这一步：画像补到能定方向之后，主理会生成它，
          之后每次打开读的都是那一版（不会重新算）。
        </p>
        <div class="empty__acts">
          <button class="btn" type="button" @click="router.push('/')">回到今天，继续补画像</button>
        </div>
      </section>

      <p v-if="versionError" class="label version-error" role="alert">{{ versionError }}</p>
    </main>
  </div>
</template>

<style scoped>
.report { min-height: 100dvh; display: flex; flex-direction: column; padding-bottom: 96px; }

.top {
  position: sticky; top: 0; z-index: var(--z-shell);
  display: flex; align-items: center; justify-content: space-between; gap: var(--s5);
  padding: var(--s3) var(--s6);
  background: var(--glass-2);
  backdrop-filter: blur(var(--glass-blur));
  border-bottom: var(--bw) solid var(--line-2);
}
.top__l { display: flex; align-items: center; gap: var(--s3); }
.back { color: var(--ink-2); transition: color var(--mo-fast) var(--mo-out); }
.back:hover { color: var(--accent); }
.top__sep, .top__crumb { color: var(--ink-3); }
.top__r { display: flex; align-items: center; gap: var(--s4); }
.top__meta { color: var(--ink-3); }
.top__versions {
  max-width: 260px; height: 28px; padding: 0 var(--s2);
  border: 1px solid var(--line-2); border-radius: var(--r-pill);
  background: var(--n-1); color: var(--ink-2);
  font-size: var(--fs-small);
}
.version-error { color: var(--warn); }

.doc {
  width: min(1080px, 100%); margin: 0 auto;
  padding: var(--s7) var(--s6) var(--s9);
  display: flex; flex-direction: column; gap: var(--s7);
}

/* ── 结论段 ─────────────────────────────────────────────────────── */
.lead { display: flex; flex-direction: column; gap: var(--s4); }
.lead__kicker { color: var(--mk-green); }
.lead__body { display: flex; flex-direction: column; gap: var(--s5); }
.lead__head { font-size: clamp(26px, 3vw, 40px); line-height: 1.22; max-width: 26ch; }
.lead__cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--s5); }
.lead__cols p { font-size: var(--fs-body); line-height: 1.8; color: var(--ink-2); }

.moves { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.moves li {
  display: grid; grid-template-columns: 34px 220px minmax(0, 1fr);
  align-items: baseline; gap: var(--s3);
  padding: var(--s3) var(--s4);
  border-left: 3px solid var(--mk-green);
  background: var(--accent-soft);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}
.moves__n { color: var(--mk-green); }
.moves__label { font-size: var(--fs-body); color: var(--ink-1); }
.moves__why { font-size: var(--fs-small); color: var(--ink-2); }

/* ── 判定 ───────────────────────────────────────────────────────── */
.verdict { padding: var(--s5); display: flex; flex-direction: column; gap: var(--s2); }
.verdict__head { font-size: var(--fs-lg); color: var(--ink-1); }
.verdict__sub { font-size: var(--fs-body); color: var(--ink-2); line-height: 1.8; }

/* ── 15 维正文 ──────────────────────────────────────────────────── */
.sec { display: flex; flex-direction: column; gap: var(--s4); scroll-margin-top: 88px; }
.sec__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s4); border-bottom: var(--bw) solid var(--line-2); padding-bottom: var(--s2); }
.sec__method { color: var(--ink-3); }

.dims { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s3); }
.dim { padding: var(--s4) var(--s5); border: var(--bw) solid var(--line-2); border-radius: var(--r-md); background: var(--n-1); }
.dim__row { display: flex; align-items: baseline; gap: var(--s3); }
.dim__index { color: var(--ink-3); }
.dim__name { font-size: var(--fs-body); color: var(--ink-1); }
.dim__tag {
  margin-left: auto; padding: 1px var(--s3); border-radius: var(--r-pill);
  background: var(--fill-hover); color: var(--ink-2);
  font-size: var(--fs-small);
}
.dim__tag[data-tag="优势"] { background: var(--accent-soft); color: var(--mk-green); }
.dim__tag[data-tag="短板"] { background: rgba(194, 90, 18, 0.12); color: var(--warn); }
.dim__conclusion { margin-top: var(--s3); font-size: var(--fs-body); color: var(--ink-1); line-height: 1.8; }
.dim__ev {
  margin-top: var(--s3); width: 100%;
  display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: var(--s3);
  padding: var(--s3) 0 0; border-top: 1px dashed var(--line-2);
  text-align: left;
}
.dim__ev .label { color: var(--mk-green); }
.dim__ev-text { font-size: var(--fs-small); color: var(--ink-2); }
.dim__ev:hover .dim__ev-text { color: var(--ink-1); }

/* ── SWOT / 方法来源 ────────────────────────────────────────────── */
.swot { display: flex; flex-direction: column; gap: var(--s4); }
.swot__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--s3); }
.quad { padding: var(--s4); border: var(--bw) solid var(--line-2); border-radius: var(--r-md); background: var(--n-1); }
.quad .label { color: var(--ink-3); }
.quad ul { margin: var(--s3) 0 0; padding-left: var(--s4); display: grid; gap: var(--s2); }
.quad li { font-size: var(--fs-small); color: var(--ink-1); line-height: 1.7; }

.basis { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--s5); }
.basis__col { display: flex; flex-direction: column; gap: var(--s2); }
.basis__col .label { color: var(--ink-3); }
.chips { display: flex; flex-wrap: wrap; gap: var(--s2); }
.chip {
  padding: 2px var(--s3); border-radius: var(--r-pill);
  border: 1px solid var(--line-2); color: var(--ink-2); font-size: var(--fs-small);
}
.src { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.src li { font-size: var(--fs-small); color: var(--ink-2); }

/* ── 空态 ───────────────────────────────────────────────────────── */
.empty { padding: var(--s7); display: flex; flex-direction: column; gap: var(--s3); align-items: flex-start; }
.empty__head { font-size: var(--fs-lg); color: var(--ink-1); }
.empty__body { font-size: var(--fs-body); color: var(--ink-2); line-height: 1.8; max-width: 60ch; }
.empty__acts { margin-top: var(--s2); }

@media (max-width: 1000px) {
  .doc { padding: var(--s5) var(--s4) var(--s8); }
  .moves li { grid-template-columns: 28px minmax(0, 1fr); }
}
</style>
