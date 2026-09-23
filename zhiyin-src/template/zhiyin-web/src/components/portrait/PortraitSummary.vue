<script setup lang="ts">
import { computed } from 'vue'
import NumberFlow from '@number-flow/vue'
import { sCircle } from '@/lib/sketch'

/**
 * 画像总览 —— 这一页的抬头。
 *
 * 三件事，从左到右，一眼能读完：
 *   1. **覆盖到什么程度**：一支绿马克笔手绘的圈，圈里一个大号衬线百分数 ——
 *      不是仪表盘的进度环，是"老师在纸上把这个数圈出来"的那个动作；
 *   2. **这是几件事里的几件**：一排格子，一格 = 一个维度，亮的是已经记下的 ——
 *      圈给比例，格子给个数，两者回答的不是同一个问题；
 *   3. **这些结论从哪来**：一根堆叠条 + 图例，色是马克笔分类色。
 *
 * 数值都带等宽数字与固定小数位，切换字段时不会因为字宽变化而抖。
 */
const props = defineProps<{
  overall: number
  coverage: number
  fields: { key: string; label?: string; confidence: number; source: string }[]
  gapCount: number
  updatedAt: string | null
  /**
   * 这几条里，有几条是**判断**（兴趣 / 价值取向 / 经历…），其余是**档案**
   * （学校 / 专业 / 学籍…，从学信网抄下来的事实）。
   *
   * 为什么要单给一个数：抬头那句"9 项已记录 · 关键维度齐了"在只有档案的画像上
   * 是**假话** —— 学籍表填得再全，也还不认识这个人。口径见 lib/profile.ts。
   */
  judgmentCount?: number
}>()

const pct = computed(() => Math.round((props.coverage || 0) * 100))

/*
 * 马克笔圈：rough 手绘（seed 固定，数据变了也不抖）。
 * 颜色走 currentColor，由 .mark 上的 color 提供 —— SVG 属性里不放 CSS 变量。
 */
const circled = computed(() =>
  sCircle(38, 38, 34, { seed: 42, strokeWidth: 2.1, roughness: 1.25, bowing: 1.7 }),
)

/**
 * 格子数 = 已记录的 + 还差的。
 * 上限 24：再多每格不到 4px，就不再是"一格一件事"，退回一根进度条。
 */
const slots = computed(() => props.fields.length + props.gapCount)
const discrete = computed(() => slots.value > 0 && slots.value <= 24)

const SOURCE_LABEL: Record<string, string> = {
  resume: '简历',
  conversation: '对话',
  assessment: '测评',
  behavior_inference: '行为推断',
  mentor: '导师',
  record: '导入记录',
  chsi: '学信网核验',
  academic: '教务系统',
}

/** 来源分布：分类色只表达"来自哪里"，不表达好坏；图例带条数，不依赖颜色也能读 */
const bySource = computed(() => {
  const map = new Map<string, number>()
  for (const field of props.fields) map.set(field.source, (map.get(field.source) ?? 0) + 1)
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, n], index) => ({
      key,
      n,
      label: SOURCE_LABEL[key] ?? '记录',
      color: `var(--pt-src-${(index % 5) + 1})`,
      share: props.fields.length ? (n / props.fields.length) * 100 : 0,
    }))
})

const stamp = (value: string | null) =>
  value ? value.slice(0, 16).replace('T', ' ') : '尚未记录'
</script>

<template>
  <section class="vitals">
    <!-- 马克笔圈 + 数字 + 格子 -->
    <div class="mark" role="img" :aria-label="`画像覆盖 ${pct}%`">
      <svg class="mark__ink" viewBox="0 0 76 76" aria-hidden="true">
        <path
          v-for="(op, i) in circled"
          :key="i"
          :d="op.d"
          :stroke="op.stroke"
          :fill="op.fill"
          :stroke-width="op.strokeWidth"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="mark__num"><NumberFlow :value="pct" suffix="%" /></span>
    </div>

    <div class="cov">
      <p class="cov__k">画像覆盖</p>
      <div v-if="discrete" class="slots" :aria-label="`共 ${slots} 个维度，已记录 ${fields.length} 个`">
        <span
          v-for="i in slots"
          :key="i"
          class="slot"
          :class="{ 'slot--on': i <= fields.length }"
          :title="i <= fields.length ? '已记录' : '还缺一条'"
        />
      </div>
      <span v-else class="bar"><i :style="{ width: `${pct}%` }" /></span>
      <p class="cov__note">
        {{ fields.length }} 条记录
        <template v-if="judgmentCount === 0"> · 都是档案，还没有你的判断</template>
        <template v-else-if="judgmentCount">
          · 其中 <b>{{ judgmentCount }}</b> 条是你的判断
          <template v-if="gapCount"> · 还差 <b>{{ gapCount }}</b> 项</template>
          <template v-else> · 关键维度齐了</template>
        </template>
        <template v-else-if="gapCount"> · 还差 <b>{{ gapCount }}</b> 项</template>
        <template v-else> · 关键维度齐了</template>
      </p>
    </div>

    <div class="side">
      <div class="conf">
        <span class="conf__k">整体把握</span>
        <span class="conf__v">{{ overall.toFixed(2) }}</span>
        <span class="conf__bar" :title="`整体把握 ${overall.toFixed(2)}`">
          <i :style="{ width: `${Math.round(Math.min(1, Math.max(0, overall)) * 100)}%` }" />
        </span>
      </div>

      <div v-if="bySource.length" class="srcs">
        <span class="srcs__bar" aria-hidden="true">
          <i v-for="s in bySource" :key="s.key" :style="{ width: `${s.share}%`, background: s.color }" />
        </span>
        <ul class="srcs__legend">
          <li v-for="s in bySource" :key="s.key">
            <span class="dot" :style="{ background: s.color }" aria-hidden="true" />
            {{ s.label }} <b>{{ s.n }}</b>
          </li>
        </ul>
      </div>

      <p class="stamp">更新于 {{ stamp(updatedAt) }}</p>
    </div>
  </section>
</template>

<style scoped>
/*
 * 抬头是一条**横带**，不是一张卡：它和下面的正文之间只隔一条发丝线。
 * 卡片套卡片是"色块堆叠"的典型来源 —— 层次应该由投影和留白给出，不是由盒子数量。
 */
.vitals {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(0, auto);
  align-items: center;
  gap: var(--s5);
  padding-bottom: var(--s4);
  border-bottom: 1px solid var(--line-1);
}

/* ── 马克笔圈 ───────────────────────────────────────────────────── */
.mark { position: relative; display: grid; place-items: center; width: 76px; height: 76px; }
.mark__ink {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  color: var(--mk-green);
  overflow: visible;
}
.mark__num {
  font-family: var(--font-editorial);
  font-size: 21px; font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--pt-ink);
  font-variant-numeric: tabular-nums;
}

/* ── 覆盖 ───────────────────────────────────────────────────────── */
.cov { display: grid; gap: 6px; min-width: 0; }
.cov__k { font-size: var(--t-xs); font-weight: 500; color: var(--pt-muted); }

.slots { display: flex; gap: 3px; height: 8px; max-width: 420px; }
.slot {
  flex: 1 1 0; min-width: 4px; border-radius: 3px;
  background: var(--pt-track);
  transition: background 420ms var(--ease-out);
}
.slot--on { background: var(--pt-accent); }

.bar {
  display: block; height: 8px; max-width: 420px; border-radius: var(--r-pill);
  background: var(--pt-track); overflow: hidden;
}
.bar i { display: block; height: 100%; background: var(--pt-accent); transition: width 620ms var(--ease-expo); }

.cov__note { font-size: var(--t-xs); color: var(--pt-faint); }
.cov__note b { color: var(--pt-warn); font-weight: 600; }

/* ── 右侧：把握 + 来源 ──────────────────────────────────────────── */
.side { display: grid; gap: var(--s2); min-width: 0; justify-items: end; }

.conf { display: grid; grid-template-columns: auto auto; gap: 5px var(--s3); align-items: center; }
.conf__k { font-size: var(--t-xs); color: var(--pt-muted); }
.conf__v {
  font-family: var(--font-editorial);
  font-size: 18px; font-weight: 600;
  color: var(--pt-ink); font-variant-numeric: tabular-nums; text-align: right;
}
.conf__bar {
  grid-column: 1 / -1; width: 150px; height: 5px; border-radius: var(--r-pill);
  background: var(--pt-track); overflow: hidden;
}
.conf__bar i { display: block; height: 100%; background: var(--pt-accent); transition: width 620ms var(--ease-expo); }

.srcs { display: grid; gap: 6px; justify-items: end; }
.srcs__bar { display: flex; width: 150px; height: 5px; border-radius: var(--r-pill); overflow: hidden; background: var(--pt-track); }
.srcs__bar i { display: block; height: 100%; }
.srcs__legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 10px; justify-content: flex-end; }
.srcs__legend li { display: inline-flex; align-items: center; gap: 5px; font-size: var(--t-xs); color: var(--pt-muted); }
.srcs__legend b { color: var(--pt-faint); font-weight: 500; }
.dot { width: 6px; height: 6px; border-radius: 2px; flex: 0 0 auto; }

.stamp { font-size: var(--t-xs); color: var(--pt-faint); }

@media (max-width: 1080px) {
  .vitals { grid-template-columns: auto minmax(0, 1fr); }
  .side { grid-column: 1 / -1; justify-items: start; }
  .srcs { justify-items: start; }
  .srcs__legend { justify-content: flex-start; }
}
</style>
