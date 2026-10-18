<script setup lang="ts">
import { computed } from 'vue'
import type { Confidence } from '../data/types'
import { normalize01 } from './charts/MeterRow.vue'
import { formatPercent } from '../lib/format'

/* =============================================================================
 * ConfidenceBadge —— 可信度的**唯一**印法
 * -----------------------------------------------------------------------------
 * 【为什么要有这个组件】审计（COVERAGE.md:180 / :197 / :273）指出同一套后端字段
 * 在三处三种视觉重量：
 *   ① `/report` 报告页的维度头：`<ConfidenceBadge :value="d.confidence"/>`
 *      → 3 格徽标（AssessmentView.vue:87，数据来自 data/student.ts 的
 *      `{level,label,bars}`）。这是"印得最重"的一处。
 *   ② 同一个页面的"门槛解释"：`<p class="ws-muted">{{ d.threshold }}</p>`
 *      → 灰字（AssessmentView.vue:87 同一行的后半段）。同一份判断的两个部分，
 *      一个有三格徽标，一个只是一行灰字。
 *   ③ 版本记录里的 `needs_recompute`：`<span class="ws-attention">待更新</span>` 与
 *      `<span class="ws-muted">当前记录无需重算</span>` 两种 span 混用
 *      （ReportHistory.vue:22），而同一个 `needs_recompute` 在 StudentView.vue:1059
 *      又是一种形态（`.p7-recompute`：红底 + 左红条 + 14/12px 两级字）。
 *      同一字段三种重量，用户无法横向比较"哪一版更可信"。
 * 收敛成这一个组件之后，"这份认识有多结实"才**可以横向比较**——
 * 比较的前提是同一把尺子，三种印法连尺子都不是同一把。
 *
 * 【量纲】只接受 0–1（后端口径，见 backend-types.ts:99 `confidence?: number`）。
 * 未知用 `undefined` / `null` 表达，**必须与"很低"分开**：
 *   未知   → 虚线方框 + 「还没有依据」   （形状：空心虚线 = 这里还没有量）
 *   很低   → 一格**空心**条 + 「依据很少」（形状：有格子，但里面是空的）
 * 两者的差别写在**文字**上（不只靠颜色/形状），读屏和灰度截图都不丢信息。
 * 为兼容既有调用点（AssessmentView.vue:87、SpecView.vue:435-437 传的是
 * `data/types.ts` 的 `{level,label,bars}` 对象），本组件同时接受旧对象形状，
 * 但**内部一律折算成 0–1**，再走同一条渲染路径 —— 不存在第二条尺子。
 * ========================================================================== */

/** 旧形状（data/types.ts:15 的 Confidence）→ 0–1 的中点值。只为兼容，不新增口径。 */
const LEGACY_SCORE: Record<Confidence['level'], number> = { high: 0.9, mid: 0.6, low: 0.2 }

type Level = 'unknown' | 'low' | 'mid' | 'high'

interface Dial {
  level: Level
  /** 界面上的字。**这是主要信号**，颜色与格子只是辅助 */
  label: string
  /** 0–3 格：控制实心格数 */
  bars: number
  /** 括号里的解释，给"未知"与"很低"用 */
  hint: string
}

/**
 * 分档。界面上不给小数（data/types.ts:14「L1 不给数字，只给三档文字」）。
 * 「未知」单独一档且**排在最低档之下**：它不是"低"，是"还没有"。
 */
const DIALS: Record<Level, Dial> = {
  unknown: { level: 'unknown', label: '还没有依据', bars: 0, hint: '这项还没有可用于判断的材料' },
  low: { level: 'low', label: '依据很少', bars: 1, hint: '只有零星线索，先按参考看' },
  mid: { level: 'mid', label: '还需要再核对', bars: 2, hint: '有依据，但还不足以定下来' },
  high: { level: 'high', label: '记录较明确', bars: 3, hint: '置信度不代表材料已核验，来源请查看具体资料' },
}

const props = withDefaults(
  defineProps<{
    /** 0–1（后端口径）。undefined / null = 未知 —— 未知不是 0 */
    confidence?: number | null
    /** 兼容旧调用点：data/types.ts 的 {level,label,bars} */
    value?: Confidence | null
    size?: 'sm' | 'md'
    /** 展开粒度时才打开：把 0–1 原值印出来（默认关，L1 不给数字） */
    showValue?: boolean
  }>(),
  { confidence: undefined, value: null, size: 'sm', showValue: false },
)

/** 唯一的 0–1 入口：新旧两种输入都先折算到这里 */
const score = computed<number | undefined>(() => {
  if (props.value && typeof props.value === 'object') {
    // 旧对象只取它的档位，不取 bars（bars 是旧的三格口径，可能已漂移）
    return LEGACY_SCORE[props.value.level] ?? undefined
  }
  return normalize01(props.confidence, 'ConfidenceBadge')
})

const dial = computed<Dial>(() => {
  const s = score.value
  if (s == null) return DIALS.unknown
  if (s < 0.34) return DIALS.low
  if (s < 0.67) return DIALS.mid
  return DIALS.high
})

/** 旧调用点自带的文案优先（保留产品已定的措辞），否则用本组件的档位文字 */
const label = computed(() => props.value?.label?.trim() || dial.value.label)

const title = computed(() =>
  score.value == null
    ? dial.value.hint
    : `${dial.value.label} ${formatPercent(score.value)} · ${dial.value.hint}`,
)
</script>

<template>
  <span class="cf" :class="[`cf--${dial.level}`, `cf--${size}`]" :title="title">
    <!-- 格子：只负责"一眼的量级"。未知画的是**虚线方框**，不是三根空刻度 ——
         空刻度会被读成"已知，但很低"，而这里根本没有值。 -->
    <span class="cf__bars" aria-hidden="true">
      <template v-if="dial.level === 'unknown'">
        <i class="cf__bar cf__bar--unknown" />
      </template>
      <template v-else>
        <i
          v-for="n in 3"
          :key="n"
          class="cf__bar"
          :class="{ 'cf__bar--on': n <= dial.bars }"
        />
      </template>
    </span>

    <span class="cf__label">{{ label }}</span>

    <span v-if="showValue && score != null" class="cf__num t-num">{{ formatPercent(score) }}</span>

    <!-- 未知时补一句形状说明：读屏与灰度截图都不丢这条信息 -->
    <span v-if="dial.level === 'unknown'" class="cf__none">未评估</span>
  </span>
</template>

<style scoped>
.cf {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-12);
  line-height: var(--lh-snug);
  color: var(--c-text-3);
  white-space: nowrap;
  vertical-align: middle;
}

/* ---------- 格子 ---------- */
.cf__bars {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  flex: 0 0 auto;
}

.cf__bar {
  display: block;
  width: 4px;
  height: 5px;
  border-radius: 1px;
  background: var(--c-surface-3); /* 空格子：有格子，但里面是空的 */
}

/* 已成立的格子：第 2、3 格更高 —— 量级靠**高度**也读得出来，不只靠颜色 */
.cf__bar--on {
  background: var(--c-primary);
}
.cf__bars .cf__bar--on:nth-child(2) {
  height: 8px;
}
.cf__bars .cf__bar--on:nth-child(3) {
  height: 11px;
}

/* 未知：一根虚线描的方框，明确"这里还没有量" */
.cf__bar--unknown {
  width: 12px;
  height: 11px;
  background: transparent;
  border: var(--bw-1) dashed var(--c-border-strong);
  border-radius: 2px;
}

/* ---------- 文字 ---------- */
.cf__label {
  font-weight: var(--fw-medium);
}

/* 【2026-10-14 · 门禁 check-contrast 的 6 处红之一】下面三处原来都用 `--c-text-4`。
 * 那是**用错了登记用途**：tokens.css:253 写的是"只给图标/分隔符"，而这里三处都是文字 ——
 *   · .cf__num  = 展开粒度时印出来的 "46%"（一个真数字，用户要读的）
 *   · .cf__none = 「未评估」三个字（本组件靠**文字**把"未知"与"很低"分开，见文件头量纲注释）
 *   · .cf--unknown = 未知档容器色（后代里没有自己声明颜色的文字都继承它）
 * 对纸面 #a2a4a6 只有 2.50:1，连 4.5:1 的一半都不到。改用最小的正文档 `--c-text-3`
 * （对纸面 **5.80:1**，取自 check-contrast 的打印值；tokens.css 与 PortalClassicView 的注释里
 * 写的 5.69 是旧记录，实测是 5.80。它本身就是 check-contrast 里 must:true 的一条）。
 * 未知档仍然比已知档轻：它的标签是 --c-text-3 + 常规字重，已知档的标签是 --c-text-2 + 中等字重。 */
.cf__num {
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
}

.cf__none {
  color: var(--c-text-3);
}

/* 已知的三档：**只改文字色，不改底**（底一旦上色，一屏里就会出现三种色块） */
.cf--low .cf__label {
  color: var(--c-text-2);
}
.cf--mid .cf__label,
.cf--high .cf__label {
  color: var(--c-text-2);
}

/* 未知：整枚退到最轻的一档，避免和"依据充分"抢同一条视线的重量。
 * 【2026-10-14 · 门禁 6 处红的第三处】这里原来是 `--c-text-4`：它是**容器文字色**，
 * 后代里凡是没有自己声明颜色的文字都继承它 —— 一枚整身都是文字的徽标，容器色就是文字色。
 * 最轻的**可承载文字**的一档是 --c-text-3；再浅一档的 --c-text-4 只许画图形与分隔符。 */
.cf--unknown {
  color: var(--c-text-3);
}
.cf--unknown .cf__label {
  color: var(--c-text-3);
  font-weight: var(--fw-regular);
}

/* ---------- 两档尺寸 ---------- */
.cf--md {
  font-size: var(--fs-14);
  gap: var(--sp-2);
}
.cf--md .cf__bar {
  width: 5px;
  height: 6px;
}
.cf--md .cf__bars .cf__bar--on:nth-child(2) {
  height: 9px;
}
.cf--md .cf__bars .cf__bar--on:nth-child(3) {
  height: 12px;
}
.cf--md .cf__bar--unknown {
  width: 14px;
  height: 12px;
}
</style>
