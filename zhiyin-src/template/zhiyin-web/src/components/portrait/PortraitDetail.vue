<script setup lang="ts">
import { computed } from 'vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import TrendLine from '@/components/charts/TrendLine.vue'
import type { DimensionReading } from '@/ai/registry'

/**
 * 一条字段的详情 —— 右边这一栏。
 *
 * 三段，顺序不能换：
 *   ① **记录到的内容**（他到底说过什么）；
 *   ② **这条凭什么**（把握度、来源、依据原样）；
 *   ③ **这意味着什么**（AI 解读，点开才算）。
 *
 * 顺序反过来的话，用户先看到的是一段分析，却不知道它从哪来 ——
 * 而这个产品最要紧的一条就是"每条结论都能追回去"。
 *
 * 版面上把**两种东西**分开：左边是系统记下的（内容与出处），右边是模型说的（一块
 * 换过材质的卡）。混在一列里读，用户很容易把模型写的那段当成系统记录。
 */
const props = defineProps<{
  field: {
    key: string
    label?: string
    confidence: number
    source: string
    updatedAt: string
    value: unknown
    evidence: string[]
  }
  sourceLabel: string
  readValue: (value: unknown) => string
  stamp: (value: string | null | undefined) => string
  task: () => unknown
}>()

const emit = defineEmits<{
  (e: 'evidence'): void
  (e: 'pick-trend', index: number): void
}>()

/** 把握度的三档：薄 / 中 / 稳 —— 与采集口径里的 0.6 / 0.85 对齐 */
const tier = computed(() =>
  props.field.confidence < 0.6 ? 'low' : props.field.confidence < 0.85 ? 'mid' : 'high',
)
const TIER_TEXT: Record<string, string> = { low: '还很薄', mid: '大概如此', high: '基本确定' }
</script>

<template>
  <section class="detail" :class="`tier-${tier}`">
    <header class="head">
      <div class="head__l">
        <span class="pill">{{ TIER_TEXT[tier] }}</span>
        <p class="meta">{{ sourceLabel }} · 更新于 {{ stamp(field.updatedAt) }}</p>
      </div>

      <div class="gauge">
        <span class="gauge__v">{{ field.confidence.toFixed(2) }}</span>
        <span class="gauge__bar" :title="`把握度 ${field.confidence.toFixed(2)}`">
          <i :style="{ width: `${Math.round(field.confidence * 100)}%` }" />
        </span>
        <span class="gauge__k">把握度</span>
      </div>
    </header>

    <div class="split">
      <div class="col">
        <!-- ① 记录到的内容：这一条的事实本身，字号最大 -->
        <section class="sec">
          <h4 class="sec__k">记录到的内容</h4>
          <p class="fact">{{ readValue(field.value) }}</p>
        </section>

        <!-- ② 这条凭什么：引用体，左边一条竖线 -->
        <section class="sec">
          <h4 class="sec__k">这条凭什么</h4>
          <ul v-if="field.evidence.length" class="ev">
            <li v-for="(item, i) in field.evidence" :key="i">{{ item }}</li>
          </ul>
          <p v-else class="muted">这条还没有留下原样依据 —— 它可能来自一次推断。</p>
          <button v-if="field.evidence.length" class="link" type="button" @click="emit('evidence')">
            看全部原样
            <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
              <path d="M4 2.4 7.6 6 4 9.6" fill="none" stroke="currentColor" stroke-width="1.6"
                    stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </section>
      </div>

      <!-- ③ 这意味着什么：模型说的话，装在一块换过材质的卡里 -->
      <section class="sec sec--ai">
        <h4 class="sec__k">这意味着什么</h4>
        <div class="ai">
          <AiFrame :key="field.key" :task="task as never">
            <template #default="{ data }">
              <div v-if="data" class="reading">
                <h5 class="reading__h">{{ (data as DimensionReading).conclusion }}</h5>
                <p class="reading__p">{{ (data as DimensionReading).reading }}</p>

                <div class="reading__figs">
                  <span>这条把握 <b>{{ (data as DimensionReading).score.toFixed(2) }}</b></span>
                  <span v-if="(data as DimensionReading).bench">
                    决策线 <b>{{ (data as DimensionReading).bench.toFixed(2) }}</b>
                  </span>
                  <span
                    :class="{
                      up: (data as DimensionReading).delta > 0,
                      down: (data as DimensionReading).delta < 0,
                    }"
                  >
                    {{
                      (data as DimensionReading).delta > 0
                        ? `比上次高了 ${(data as DimensionReading).delta.toFixed(2)}`
                        : (data as DimensionReading).delta < 0
                          ? `比上次低了 ${Math.abs((data as DimensionReading).delta).toFixed(2)}`
                          : '与上次持平'
                    }}
                  </span>
                </div>

                <TrendLine
                  v-if="(data as DimensionReading).trend.length"
                  :points="(data as DimensionReading).trend"
                  @pick="(i: number) => emit('pick-trend', i)"
                />

                <p class="reading__next"><span>接下来</span>{{ (data as DimensionReading).next }}</p>
              </div>
            </template>
          </AiFrame>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.detail { display: flex; flex-direction: column; gap: var(--s4); min-width: 0; }

/* ── 抬头 ───────────────────────────────────────────────────────── */
.head {
  display: grid; grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--s4); align-items: start;
  padding-bottom: var(--s4);
  border-bottom: 1px solid var(--line-1);
}
.head__l {
  display: flex;
  align-items: center;
  gap: var(--s3);
  min-width: 0;
}

/* 档位胶囊：颜色 + 文字都说同一件事，不靠颜色单独传达 */
.pill {
  flex: 0 0 auto;
  padding: 2px 9px; border-radius: var(--r-pill);
  font-size: var(--t-xs); font-weight: 500;
  color: var(--pt-accent, var(--accent));
  background: var(--pt-soft, var(--accent-soft));
  border: 1px solid rgba(10, 88, 66, 0.22);
}
.tier-mid .pill { color: var(--mk-orange); background: rgba(164, 82, 47, 0.09); border-color: rgba(164, 82, 47, 0.26); }
.tier-low .pill { color: var(--mk-pink); background: rgba(140, 59, 82, 0.09); border-color: rgba(140, 59, 82, 0.26); }

/*
 * 这一行**不再重复字段名**。
 *
 * 名字与把握度已经写在浮层的抬头条上（那是"你在哪一条"），这里再写一遍，
 * 两行同名的字会挨在一起，读起来像屏幕上多了个标题。
 * 这一层只补抬头条没有的那两件事：这一条**算不算稳**，以及它**从哪来**。
 */
.meta { font-size: var(--t-sm); color: var(--pt-faint, var(--ink-3)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.gauge { display: grid; gap: 6px; justify-items: end; min-width: 132px; }
.gauge__v {
  font-family: var(--font-editorial);
  font-size: 21px; font-weight: 600; letter-spacing: -0.02em;
  color: var(--pt-ink, var(--ink-1)); font-variant-numeric: tabular-nums;
}
.gauge__bar {
  display: block; width: 132px; height: 6px; border-radius: var(--r-pill);
  background: var(--pt-track, var(--c-sand-1)); overflow: hidden;
}
/* 进度条也是平涂：一支色，不做左右渐变（"渐变块"是用户点名要清掉的东西） */
.gauge__bar i {
  display: block; height: 100%; border-radius: var(--r-pill);
  background: var(--pt-accent, var(--accent));
  transition: width 620ms var(--ease-expo);
}
.tier-mid .gauge__bar i { background: var(--mk-orange); }
.tier-low .gauge__bar i { background: var(--mk-pink); }
.gauge__k { font-size: var(--t-xs); color: var(--pt-faint, var(--ink-3)); }

/* ── 两栏 ───────────────────────────────────────────────────────── */
.split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--s5);
  align-items: start;
}
.col { display: grid; gap: var(--s4); min-width: 0; }

.sec { display: grid; gap: var(--s2); min-width: 0; }
.sec__k {
  display: flex; align-items: center; gap: 7px;
  font-size: var(--t-xs); font-weight: 600; color: var(--pt-muted, var(--ink-3));
}
.sec__k::before { content: ""; width: 3px; height: 3px; border-radius: 50%; background: currentColor; opacity: 0.5; }

.fact {
  /* 记录到的内容是这一页的主角：衬线、最大 —— 铅字排出来的"他说过的话" */
  font-family: var(--font-editorial);
  font-size: 21px; line-height: 1.5; letter-spacing: -0.008em;
  color: var(--pt-ink, var(--ink-1));
}

.ev {
  list-style: none; margin: 0; padding: 0 0 0 var(--s3);
  display: grid; gap: 7px;
  border-left: 2px solid var(--line-2);
}
.ev li { font-size: var(--t-sm); color: var(--pt-muted, var(--ink-2)); line-height: 1.7; }

.muted { font-size: var(--t-sm); color: var(--pt-faint, var(--ink-3)); line-height: 1.7; }

.link {
  justify-self: start;
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--t-xs); font-weight: 500; color: var(--pt-accent, var(--accent));
}
.link:hover { text-decoration: underline; }

/*
 * 解读卡：换一种材质（浅绿 → 白的渐变），而不是再放一块同色的白。
 * 左侧一道 3px 的绿：这是"这一段是模型给的"，一眼分得开。
 * 结论句用衬线 —— 模型的话在这页纸上读起来是一段"批注"，不是一条日志。
 */
.ai {
  border-radius: var(--pt-r-md, 12px);
  border: 1px solid var(--line-2);
  border-left: 3px solid var(--pt-accent, var(--accent));
  /* 平面浅绿纸：模型的话是一张便签，不是一块渐变玻璃 */
  background: var(--pt-soft, var(--accent-soft));
  padding: var(--s4);
  box-shadow: var(--e-2);
}

.reading { display: grid; gap: var(--s3); }
.reading__h {
  font-family: var(--font-editorial);
  font-size: 17px; font-weight: 600; line-height: 1.55; letter-spacing: -0.008em;
  color: var(--pt-ink, var(--ink-1));
}
.reading__p { font-size: var(--t-sm); color: var(--pt-muted, var(--ink-2)); line-height: 1.75; max-width: 60ch; }

.reading__figs { display: flex; flex-wrap: wrap; gap: 6px var(--s4); }
.reading__figs span { font-size: var(--t-xs); color: var(--pt-faint, var(--ink-3)); }
.reading__figs b { color: var(--pt-ink, var(--ink-1)); font-weight: 600; font-variant-numeric: tabular-nums; }
.reading__figs .up, .reading__figs .up b { color: var(--pt-accent, var(--accent)); }
.reading__figs .down, .reading__figs .down b { color: var(--mk-pink); }

.reading__next { font-size: var(--t-sm); color: var(--pt-muted, var(--ink-2)); line-height: 1.7; }
.reading__next span {
  display: inline-block; margin-right: var(--s2);
  font-size: var(--t-xs); font-weight: 600; color: var(--pt-faint, var(--ink-3));
}

@media (max-width: 1080px) {
  .split { grid-template-columns: minmax(0, 1fr); gap: var(--s4); }
}
</style>
