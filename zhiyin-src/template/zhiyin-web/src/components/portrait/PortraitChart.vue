<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, RadarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { tierOf } from '@/lib/profile'

/*
 * 按需注册：只装这一页真正用到的那几个模块（雷达 / 条形 / 提示框 / 直角坐标系）。
 * 全量 `import * as echarts from 'echarts'` 会把地图、漏斗、关系图这些
 * 一次全打进包里 —— 这一页一个都不需要。
 */
use([RadarChart, BarChart, TooltipComponent, GridComponent, CanvasRenderer])

/**
 * 画像的**分析图** —— 这一页中间那张。
 *
 * 【它画的是什么，不画什么】
 *
 * 只画**判断维度**：价值取向、兴趣、经历、能力自评、目标方向、现实约束、卡住的地方。
 * 不画学校、层次、学制、预计毕业那一批 —— 那些是从学信网抄下来的**档案事实**，
 * 把握度恒等于 1.00，画进图里每个顶点都顶满，等于什么都没说
 * （判据见 `lib/profile.ts` 的 `isJudgment`）。
 *
 * 所以这张图回答的是"**我现在怎么看自己**"，不是"我的学籍信息填全了没有"。
 * 一个只有档案、还没有判断的画像，这里不画图 —— 画出来的那张图是假的。
 *
 * 【为什么用 ECharts】
 *
 * 手绘那版（rough.js 直绘）是静态的：图形再好看，点不动、悬不住、也不报数。
 * 这一版交给 Apache ECharts（MIT）+ vue-echarts（MIT）：
 *   · 悬停有 tooltip（这条是什么、把握多少、几条依据）；
 *   · 条形图**点一下就进那一条**（雷达上直接点顶点 ECharts 不支持，所以雷达旁边
 *     常驻一排维度片，悬停高亮、点击进入 —— 两个视图都能一路点到明细）；
 *   · 切换视图会重排动画，不是硬切一张图。
 *
 * 【外观为什么不是 ECharts 默认那样】
 *
 * 默认主题是"数据大屏"：深蓝紫、渐变填充、发光。这一版全部换回外壳的纸与墨 ——
 * 轴线走铅笔线（--line-1/2）、顶点走马克笔绿、警告档走陶橙与梅红、
 * 提示框是一张纸片而不是黑气泡。色值**从 CSS 变量读**，不在这个文件里写死，
 * 换皮肤仍然只改 tokens.css 一处。
 */
export interface ChartDim {
  key: string
  name: string
  /** 把握度 0–1 */
  value: number
  /** 有几条依据 —— 工具提示里要给出来，它是"这条稳不稳"的另一半 */
  evidence: number
}

const props = defineProps<{
  dims: ChartDim[]
  selected?: string | null
}>()

const emit = defineEmits<{ (e: 'select', key: string): void }>()

/*
 * 主题取值：一次性从根元素读出来。
 * 读不到就退回 tokens.css 里的同一批值（兜底是给 SSR / 单测用的，不是常态）。
 */
function readTokens() {
  const cs = getComputedStyle(document.documentElement)
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback
  return {
    ink1: v('--ink-1', '#2b2721'),
    ink2: v('--ink-2', '#584f3f'),
    ink3: v('--ink-3', '#6c614c'),
    ink4: v('--ink-4', '#a89c80'),
    line1: v('--line-1', 'rgba(43, 39, 33, 0.10)'),
    line2: v('--line-2', 'rgba(43, 39, 33, 0.18)'),
    paper: v('--c-paper', '#fffdf4'),
    green: v('--mk-green', '#257040'),
    orange: v('--mk-orange', '#bf5518'),
    pink: v('--mk-pink', '#c23a62'),
  }
}

const T = ref(readTokens())
onMounted(() => (T.value = readTokens()))

/** 三档把握对应三支马克笔：稳 = 绿、中 = 陶橙、薄 = 梅红 */
const tierColor = (value: number) =>
  ({ low: T.value.pink, mid: T.value.orange, high: T.value.green })[tierOf(value)]

/**
 * 视图：雷达给形状，条形给排序与逐条点击。
 *
 * 维度少于 3 个时雷达画不出多边形（两条边不成形），自动落到条形 ——
 * 与其画一个退化的三角形，不如给一张能读的表。
 */
const view = ref<'radar' | 'bar'>('radar')
const canRadar = computed(() => props.dims.length >= 3)
watch(canRadar, (ok) => { if (!ok) view.value = 'bar' }, { immediate: true })

/** 条形图按把握度升序排 —— ECharts 的类目轴从下往上画，于是最稳的那条落在最上面 */
const bars = computed(() => {
  const list = [...props.dims].sort((a, b) => a.value - b.value)
  return {
    names: list.map((d) => d.name),
    values: list.map((d) => ({ value: d.value, itemStyle: { color: tierColor(d.value) } })),
    keys: list.map((d) => d.key),
    list,
  }
})

/** 提示框：一张纸片，不是黑气泡。排版与页面里的其它小字一致 */
const tooltipBox = () => ({
  backgroundColor: T.value.paper,
  borderColor: T.value.line2,
  borderWidth: 1,
  padding: [9, 12],
  extraCssText: 'border-radius:10px; box-shadow:0 8px 22px rgba(43,39,33,0.14);',
  textStyle: { color: T.value.ink1, fontSize: 12.5 },
})

const radarOption = computed(() => ({
  animationDuration: 520,
  animationEasing: 'cubicOut' as const,
  tooltip: {
    trigger: 'item',
    ...tooltipBox(),
    formatter: () =>
      [
        '<b>这一份画像的形状</b>',
        ...props.dims
          .slice()
          .sort((a, b) => b.value - a.value)
          .map(
            (d) =>
              `<span style="display:inline-block;width:7px;height:7px;border-radius:2px;background:${tierColor(d.value)};margin-right:6px"></span>` +
              `${d.name} <b>${d.value.toFixed(2)}</b> · ${d.evidence} 条依据`,
          ),
        `<span style="color:${T.value.ink3}">顶点越远 = 这条越稳</span>`,
      ].join('<br/>'),
  },
  radar: {
    center: ['50%', '50%'],
    /* 半径按 min(宽,高) 算，所以这里给到 78% —— 再大顶点文字会顶出画布 */
    radius: '72%',
    indicator: props.dims.map((d) => ({ name: d.name, max: 1 })),
    splitNumber: 2,
    shape: 'polygon' as const,
    axisName: { color: T.value.ink3, fontSize: 12 },
    axisLine: { lineStyle: { color: T.value.line1 } },
    splitLine: { lineStyle: { color: T.value.line1 } },
    /* 平面纸：ECharts 默认的分区交替底色就是"数据大屏"味的来源之一，关掉 */
    splitArea: { show: false },
  },
  series: [
    {
      type: 'radar' as const,
      symbol: 'circle' as const,
      symbolSize: 7,
      lineStyle: { width: 2, color: T.value.green },
      itemStyle: { color: T.value.green, borderColor: T.value.paper, borderWidth: 2 },
      areaStyle: { color: 'rgba(37, 112, 64, 0.14)' },
      emphasis: { lineStyle: { width: 3 }, areaStyle: { color: 'rgba(37, 112, 64, 0.22)' } },
      data: [{ value: props.dims.map((d) => d.value), name: '把握' }],
    },
  ],
}))

const barOption = computed(() => ({
  animationDuration: 520,
  animationEasing: 'cubicOut' as const,
  grid: { left: 4, right: 46, top: 6, bottom: 4, containLabel: true },
  tooltip: {
    trigger: 'item',
    ...tooltipBox(),
    formatter: (p: { dataIndex: number }) => {
      const d = bars.value.list[p.dataIndex]
      if (!d) return ''
      return (
        `<b>${d.name}</b><br/>把握 <b>${d.value.toFixed(2)}</b> · ${d.evidence} 条依据` +
        `<br/><span style="color:${T.value.ink3}">点一下看这一条</span>`
      )
    },
  },
  xAxis: {
    type: 'value' as const,
    min: 0,
    max: 1,
    interval: 0.25,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: T.value.ink4, fontSize: 11, formatter: (v: number) => v.toFixed(2) },
    splitLine: { lineStyle: { color: T.value.line1 } },
  },
  yAxis: {
    type: 'category' as const,
    data: bars.value.names,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: T.value.ink2, fontSize: 12 },
  },
  series: [
    {
      type: 'bar' as const,
      barWidth: 11,
      itemStyle: { borderRadius: [0, 6, 6, 0] },
      emphasis: { itemStyle: { borderColor: T.value.ink1, borderWidth: 1 } },
      label: {
        show: true,
        position: 'right' as const,
        distance: 8,
        formatter: (p: { value: number }) => p.value.toFixed(2),
        color: T.value.ink3,
        fontSize: 11.5,
      },
      data: bars.value.values,
    },
  ],
}))

/**
 * 点条形 = 看这一条。
 *
 * 雷达上点不到具体顶点（ECharts 的 radar 系列整个是一"条"数据），
 * 所以雷达视图里点到哪儿都落到"最薄的那一条" —— 那正是最该先看的一条。
 */
function onChartClick(p: { dataIndex?: number }) {
  if (view.value === 'bar') {
    const key = bars.value.keys[p.dataIndex ?? -1]
    if (key) emit('select', key)
    return
  }
  const weakest = [...props.dims].sort((a, b) => a.value - b.value)[0]
  if (weakest) emit('select', weakest.key)
}
</script>

<template>
  <figure class="chart">
    <figcaption class="chart__bar">
      <span class="chart__t">
        <span class="label chart__k">维度分析</span>
        <span class="chart__hint">悬停看数值 · 点一下进那一条</span>
      </span>
      <div class="seg" role="group" aria-label="换一种看法">
        <button
          type="button" class="seg__b" :class="{ 'seg__b--on': view === 'radar' }"
          :aria-pressed="view === 'radar'" :disabled="!canRadar"
          @click="view = 'radar'"
        >雷达</button>
        <button
          type="button" class="seg__b" :class="{ 'seg__b--on': view === 'bar' }"
          :aria-pressed="view === 'bar'"
          @click="view = 'bar'"
        >条形</button>
      </div>
    </figcaption>

    <div class="chart__stage">
      <VChart
        v-if="view === 'radar' && canRadar"
        class="chart__cv"
        :option="radarOption"
        autoresize
        @click="onChartClick"
      />
      <VChart
        v-else
        class="chart__cv"
        :option="barOption"
        autoresize
        @click="onChartClick"
      />
    </div>

    <!--
      维度片：图上一共有哪几个顶点，写在这儿。
      它同时是**雷达视图的点击通道** —— 悬停高亮、点击进那一条。
    -->
    <ul class="chips">
      <li v-for="d in dims" :key="d.key">
        <button
          type="button"
          class="chip"
          :class="{ 'chip--on': d.key === selected }"
          @click="emit('select', d.key)"
        >
          <span class="chip__dot" :style="{ background: tierColor(d.value) }" aria-hidden="true" />
          {{ d.name }}
          <b>{{ d.value.toFixed(2) }}</b>
        </button>
      </li>
    </ul>
  </figure>
</template>

<style scoped>
.chart { margin: 0; display: grid; gap: var(--s3); min-width: 0; }

.chart__bar { display: flex; align-items: flex-end; gap: var(--s3); }
.chart__t { display: grid; gap: 2px; }
.chart__k { color: var(--ink-4); }
.chart__hint { font-size: var(--t-xs); color: var(--pt-faint, var(--ink-3)); }

/* 分段控件：全页只有这一套控件语法（和清单里的筛选片同一支） */
.seg {
  margin-left: auto;
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
  gap: 2px; padding: 3px;
  border-radius: var(--pt-r-sm, 8px);
  background: var(--pt-well, var(--c-sand-1));
}
.seg__b {
  height: 24px; padding: 0 12px; border-radius: 6px;
  font-size: var(--t-xs); font-weight: 500; color: var(--pt-muted, var(--ink-2));
  transition: background 160ms var(--ease-out), color 160ms var(--ease-out), box-shadow 160ms var(--ease-out);
}
.seg__b:hover:not(:disabled) { color: var(--pt-ink, var(--ink-1)); }
.seg__b:disabled { opacity: 0.4; cursor: not-allowed; }
.seg__b--on {
  background: var(--pt-surface, var(--c-paper)); color: var(--pt-ink, var(--ink-1));
  box-shadow: var(--e-1), var(--inner-hi);
}

.chart__stage { min-height: 0; }
.chart__cv { width: 100%; height: 348px; }

.chips {
  list-style: none; margin: 0; padding: 0;
  display: flex; flex-wrap: wrap; gap: 6px;
}
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  height: 26px; padding: 0 10px;
  border: 1px solid var(--pt-line, var(--line-2)); border-radius: var(--r-pill);
  background: var(--pt-surface, var(--c-paper)); color: var(--pt-muted, var(--ink-2));
  font-size: var(--t-xs);
  transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out),
              transform 160ms var(--ease-out), box-shadow 160ms var(--ease-out);
}
.chip:hover {
  border-color: var(--pt-line-strong, var(--line-3)); color: var(--pt-ink, var(--ink-1));
  transform: translateY(-1px); box-shadow: var(--e-1);
}
.chip--on { border-color: var(--pt-accent, var(--accent)); color: var(--pt-ink, var(--ink-1)); }
.chip b { font-weight: 600; color: var(--pt-faint, var(--ink-3)); font-variant-numeric: tabular-nums; }
.chip__dot { width: 7px; height: 7px; border-radius: 2px; flex: 0 0 auto; }
</style>
