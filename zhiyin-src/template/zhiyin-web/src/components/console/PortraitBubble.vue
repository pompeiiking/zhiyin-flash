<script setup lang="ts">
import Bubble from '@/components/console/Bubble.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import { PORTRAIT } from '@/data/content'
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'

/**
 * 画像气泡 —— 第一眼要看到自己。
 * 这里只给"结论 + 把握程度"，详细分析点进多级菜单看，不在这块里堆。
 *
 * 【字与色】摘要是这一块的标题戏，用衬线排（纸上的结论句）；
 * 维度条一根一个马克笔色相 —— 分类色是这套语言里本来就有的标点。
 */
const session = useSessionStore()
const emit = defineEmits<{ (e: 'close'): void }>()
const P = computed(() => {
  const p = session.profile
  if (!p) return PORTRAIT
  return {
    ...PORTRAIT,
    overall: Math.round(p.overall * 100) / 100,
    summary: p.updatedAt
      ? `${p.dimensions.length} 个方面 · 覆盖 ${Math.round(p.coverage * 100)}%`
      : PORTRAIT.summary,
    dimensions: p.dimensions.length ? p.dimensions : PORTRAIT.dimensions,
    gaps: p.gaps.length
      ? p.gaps.map((g) => ({ id: g.id, name: g.name, confidence: 0.5, question: g.question }))
      : PORTRAIT.gaps,
    lastChange: p.updatedAt ? `更新于 ${p.updatedAt.slice(0, 16).replace('T', ' ')}` : PORTRAIT.lastChange,
  }
})

/* 维度条逐根换马克笔色相：绿起手（签名色），其余按序轮转 */
const HUES = ['green', 'purple', 'orange', 'pink', 'blue', 'teal', 'yellow'] as const
const hueOf = (i: number) => `var(--mk-${HUES[i % HUES.length]})`
</script>

<template>
  <Bubble
    size="lg"
    tone="raised"
    interactive
    :tilt="0.3"
    label="你的画像"
    @click="session.openOverlay('portrait')"
    @close="emit('close')"
  >
    <header class="head">
      <span class="label">你的画像</span>
      <span class="label head__meta">把握 <b class="head__num">{{ P.overall }}</b></span>
    </header>

    <p class="summary">{{ P.summary }}</p>

    <ul v-if="P.dimensions.length" class="dims" aria-hidden="true">
      <li v-for="(dim, i) in P.dimensions" :key="dim.id">
        <span class="dims__name">{{ dim.name }}</span>
        <span class="dims__bar"><i :style="{ width: dim.value * 100 + '%', background: hueOf(i) }" /></span>
      </li>
    </ul>

    <!--
      画像还是空的时候：**摆一排空槽**，而不是留一片白。
      这些槽不是"占位骨架"，它就是这个空状态本身要说的话 ——
      "这里会被一条条填起来"。空白看着像加载中，空槽看着像还没写。
    -->
    <div v-else class="slots">
      <span class="label slots__k">对话之后，这里会一条条填起来</span>
      <ul aria-hidden="true">
        <li v-for="n in 3" :key="n"><i /></li>
      </ul>
      <span class="label slots__d">每一条都写着它从哪来、有多大把握。</span>
    </div>

    <div class="change">
      <span class="label">最近变化</span>
      <p>{{ P.lastChange }}</p>
    </div>

    <footer class="foot">
      <!--
        缺口本来就只能靠对话补。
        所以 AI 有话说的时候，这里给的是它此刻真正想问的那一句；
        没有的时候退回原来的入口（看完整分析也在这一行，不丢）。
      -->
      <NextAsk v-if="session.nextAsk" compact />
      <button
        v-else
        class="chip"
        :class="{ risk: P.gaps.length }"
        type="button"
        @click.stop="session.openOverlay('portrait', 'gaps')"
      >
        还缺 {{ P.gaps.length }} 条 · 现在补
      </button>
      <span class="label foot__cta">看完整分析 →</span>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__meta { color: var(--ink-faint); }
.head__num {
  font-family: var(--font-editorial);
  font-size: 14px; font-weight: 600; color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
/* 结论句：衬线是这块气泡的声音 —— 纸上手写的一句判断，不是一行仪表读数 */
.summary {
  font-family: var(--font-editorial);
  font-size: clamp(18px, 1.6vw, 21px);
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: -0.008em;
  color: var(--ink);
  max-width: 30ch;
}
.dims { list-style: none; margin: auto 0 0; padding: 0; display: grid; gap: 7px; }
.dims li { display: grid; grid-template-columns: 64px 1fr; align-items: center; gap: var(--s3); }
.dims__name { font-size: var(--fs-label); color: var(--ink-faint); }
.dims__bar { height: 3px; background: var(--line-1); position: relative; border-radius: 3px; }
.dims__bar i { position: absolute; inset: 0 auto 0 0; border-radius: 3px; transition: width 420ms var(--ease-out); }

/*
 * 空画像的三个空槽：虚线 + 一句说明。
 *
 * 槽的高度固定 30px（不是按内容长），因为它的职责是"占住位置、
 * 说明这里将来有什么"，而不是模拟真实数据的样子 —— 做成灰色假柱子
 * 反而会被当成"把握度很低"，那是错的读法。
 */
.slots { display: grid; gap: var(--s2); margin: auto 0 0; }
.slots__k { color: var(--ink-3); }
.slots ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.slots li {
  height: 30px; border-radius: var(--r-sm);
  border: 1px dashed var(--line-2);
  background: var(--fill-subtle);
}
.slots__d { color: var(--ink-4); }

/*
 * 空槽跟着格位收：格位一矮，先收槽数，再收整块。
 * 空状态可以少说一句，但绝不能被切掉半句。
 */
.bubble.is-compact .slots li:nth-child(n + 2) { display: none; }
.bubble.is-compact .slots__d { display: none; }
.bubble.is-tiny .slots { display: none; }
.bubble.is-compact .summary {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.change {
  display: flex; flex-direction: column; gap: 4px;
  /*
   * "最近变化"是一句**批注**，不是输入框。
   * 上一版它是一整块带描边的浅灰方框 —— 长得和输入框一模一样，
   * 用户会去点它（点不动）。现在改成左侧一道细绿线 + 无边框，
   * 读起来就是"纸边上写的一行字"。
   */
  padding: 2px 0 2px var(--s3);
  border-left: 2px solid var(--accent);
}
.change p { font-size: var(--fs-small); color: var(--ink-dim); }
/* 同上：页脚要贴在气泡底部，不能跟在正文后面 */
.foot { display: flex; align-items: center; justify-content: space-between; gap: var(--s3); margin-top: auto; }
.chip.risk { border-color: var(--warn); color: var(--warn); transition: background var(--dur-fast) var(--ease-out); }
.chip.risk:hover { background: rgba(154, 74, 30, 0.1); }
.foot__cta { color: var(--ink-faint); transition: color var(--dur-fast) var(--ease-out); }
.bubble:hover .foot__cta { color: var(--accent); }
</style>
