<script setup lang="ts">
/**
 * 可视件的**前端分发点**：拿到一块 `Renderable`，按 `kind` 选组件画。
 *
 * 为什么要有这一层（而不是在对话气泡里直接画一张图）：
 * 产品会不断做出新的"功能模块" —— 后端一段取数逻辑 + 前端一整套渲染效果。
 * 分发写在这里，新模块就只做一件事：加一个 `kind` 分支（服务端那边注册同名的
 * 校验函数、把工具挂给该挂的角色），**契约不用动**。
 *
 * 两条纪律：
 *   · 数值一律只读 `payload`，不在前端算、更不猜 —— 点位是服务端从库里读的；
 *   · 认不出的 `kind` **什么都不画**（只留一行控制台日志）。
 *     摆一块空白比不摆更坏：用户会以为"这里本来就该有东西，只是没加载出来"。
 */
import { computed, ref, watch } from 'vue'
import { profileLabel } from '../lib/server-copy'
import ModuleRenderable from '../modules/ModuleRenderable.vue'
import ProfileEvidenceChart from './charts/ProfileEvidenceChart.vue'
import type { EvidenceAssessment } from '../api/backend-types'
import type { RenderableView } from '../api/backend-types'

const props = defineProps<{ item: RenderableView }>()
const expanded = ref(false)
const label = (key: string) => profileLabel(key, ({ courses:'课程表', scores:'成绩单' } as Record<string,string>)[key] || key)
const evidencePoints = computed(() => ((props.item.payload?.points ?? []) as Array<{key?:string;label?:string;assessment?:EvidenceAssessment}>)
  .filter((point): point is {key:string;label:string;assessment?:EvidenceAssessment} =>
    !!point && typeof point.key === 'string' && point.key.trim().length > 0
    && typeof point.label === 'string' && point.label.trim().length > 0)
  .map(point => ({ key: point.key, label: point.label, assessment: point.assessment })))
const legacyBars = computed(() => props.item.kind === 'bars_chart' && !props.item.payload?.metric)

interface BarsPoint {
  label: string
  value: number
}

/**
 * 柱状图的点位：**契约**是 0–1 的比值（`renderers._validate_bars` 会拦），
 * 但上游的分值量纲实测有漂（match_score / 诊断 score 有 0–1、0–100、0–10000 三种），
 * 而这里原先一律 `value * 100` —— 于是用户读到"740000 分"，三根柱子还全长一样
 * （issue 证据截图 3/4/6）。所以这一层不再假设量纲：
 *   · 条宽按**本组最大值**成比例（谁最长谁满格，其余按比例）；
 *   · 数值怎么写看本组的量级：整组 ≤1 才当比值写成百分数，否则原样写（不乘 100）。
 */
const bars = computed<{ title: string; unit: string; points: BarsPoint[]; max: number; ratio: boolean } | null>(() => {
  if (props.item.kind !== 'bars_chart') return null
  const payload = (props.item.payload ?? {}) as { unit?: unknown; points?: unknown }
  const raw = Array.isArray(payload.points) ? payload.points : []
  const points = raw
    .map((point) => {
      const row = point as { label?: unknown; value?: unknown }
      const label = String(row.label ?? '').trim()
      const value = Number(row.value)
      return { label, value: Number.isFinite(value) ? value : NaN }
    })
    .filter((point) => point.label && Number.isFinite(point.value))
  if (points.length < 2) return null
  const max = Math.max(...points.map((point) => point.value), 0)
  return {
    title: props.item.title || '这一轮的分布',
    unit: String(payload.unit ?? ''),
    points,
    max,
    ratio: max <= 1,
  }
})

/** 条宽：按本组最大值成比例；最小留 2% 让"很小"也看得见 */
const width = (value: number, max: number) =>
  `${Math.max(2, Math.min(100, (value / Math.max(max, Number.EPSILON)) * 100))}%`

/*
 * 契约破了要**说出来**，不能静默画歪。
 *
 * 点位契约是 0–1 的比值（服务端 `renderers._validate_bars` 也会拦），
 * 而这里一旦收到 >1 的分值（实测出现过 match_score 7400 那种），
 * 只能按本组最大值成比例画 —— 图还能比，但它已经不是"比值图"了。
 * 这一条 console 警告让"谁送来的量纲不对"在开发时立刻可见，
 * 而不是等用户在截图里读到 740000 分。
 */
watch(bars, (chart) => {
  if (chart && !chart.ratio) {
    console.warn(
      '[chart] 柱状图的点超出了 0–1 的契约，已按本组最大值成比例显示：',
      chart.points.map((point) => `${point.label}=${point.value}`).join(' / '),
    )
  }
})

/**
 * 数值怎么写给人看。
 *
 * 整组都是 0–1 的比值时，写成百分数（后面跟上这一件自己的单位 `%` / `分`）——
 * 用户不用自己换算。整组超过 1 时说明上游就是按"分"给的：**原样写**，
 * 再乘一次 100 会得到 740000 那种数字（issue 截图）。
 */
const numberText = (value: number, unit: string, ratio: boolean) =>
  ratio
    ? `${Math.round(Math.min(100, Math.max(0, value * 100)))}${unit || '%'}`
    : `${Math.round(value)}${unit}`
</script>

<template>
  <ProfileEvidenceChart v-if="item.kind === 'profile_evidence_chart'" :title="item.title || '把握度'" :points="evidencePoints" />
  <aside v-if="legacyBars" class="rb rb--notice" role="note"><strong>旧版图表记录</strong><p>这张图保留当时的原始数值，指标口径未标识，不代表新版把握度评估。</p></aside>
  <ModuleRenderable v-if="item.kind.startsWith('module.')" :kind="item.kind" :payload="item.payload || {}" />
  <figure v-if="bars" class="rb">
    <figcaption class="label rb__k">{{ bars.title }}</figcaption>
    <ul class="rb__rows">
      <li v-for="point in (expanded ? bars.points : bars.points.slice(0, 6))" :key="point.label">
        <span class="rb__label">{{ label(point.label) }}</span>
        <span class="rb__bar"><i :style="{ width: width(point.value, bars.max) }" /></span>
        <span class="mono rb__num">{{ numberText(point.value, bars.unit, bars.ratio) }}</span>
      </li>
    </ul>
    <table class="sr-only print-table">
      <caption>{{ bars.title }}（数据表）</caption>
      <thead><tr><th scope="col">项目</th><th scope="col">数值</th></tr></thead>
      <tbody><tr v-for="point in bars.points" :key="point.label"><td>{{ label(point.label) }}</td><td>{{ numberText(point.value, bars.unit, bars.ratio) }}</td></tr></tbody>
    </table>
    <button v-if="bars.points.length > 6" class="rb__expand" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起部分条目' : `展开其余 ${bars.points.length - 6} 项` }}</button>
  </figure>
</template>

<style scoped>
/* 横条 + 数值：窄也放得下，因为它本来就是"比较"用的 */
.rb { margin: 12px 0; padding:16px; display: grid; gap: 14px; border:1px solid var(--c-border);border-radius:14px;background:var(--c-surface); }
.rb--notice { gap:6px; background:var(--c-surface-2); color:var(--c-text-2); font-size:13px; line-height:1.7; }
.rb--notice strong { color:var(--c-text); font-weight:600; }
.rb--notice p { margin:0; }
.rb__k { color: var(--c-text-2);font-size:13px;line-height:1.65; }
.rb__rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
/*
 * 三列：名字 / 条 / 数值。
 * 名字那列原来上限 6em，"FDE · 在客…" 这种带半个说明的词被截成看不懂的样子
 * （issue 证据截图 4），所以放宽到 10em；数值那列原来 3.4em 装不下"7400 分"，
 * 于是单位被折到第二行（截图 3），改成按内容给宽并禁止折行。
 */
.rb__rows li { display: grid; grid-template-columns: minmax(4em, 7em) minmax(20px,1fr) auto; gap: 10px; align-items: center; }
/*
 * 标签允许**两行**：长类目名（"FDE 主攻 · 在客户现场"）截成 "FDE · 在客…" 之后
 * 用户读不出它指的是哪条路（issue #18）。两行够装下常见的方案名，
 * 再长的仍然省略 —— 行高不能因为一个名字而把整张图撑开。
 */
.rb__label {
  font-size: 12px; color: var(--c-text-2);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; overflow-wrap: anywhere;
}
.rb__bar { height: 6px; border-radius: 999px; background: var(--c-primary-weak); overflow: hidden; }
.rb__bar i { display: block; height: 100%; border-radius: inherit; background: var(--c-primary); }
.rb__num { font-size: 12px; color: var(--c-text-3); text-align: right; white-space: nowrap; }
.rb__expand {background:none;border:0;color:var(--c-primary);font-size:12px;min-height:36px;text-align:left;cursor:pointer;}
</style>
