<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useAiTask } from '@/ai/useAiTask'
import type { AiCitation, AiTask } from '@/ai/types'

/**
 * 一块"由 AI 生成"的内容的通用外壳。
 *
 * 任何要生成的东西都套它：图表、解读、名单、报告段落。它负责四件事，
 * 让每个业务组件只用关心"内容长什么样"：
 *
 *   生成中 → 手绘虚线骨架 + 一行"它在干嘛"（推理中间态）
 *   完成   → 内容 + 一枚可点的 AI 标记（几条依据、花了多久、谁算的）
 *   出错   → 说清楚哪一步断了，给一个重算按钮
 *   缓存   → 标记成"已算过"，不假装又算了一遍
 *
 * 依据统一走抽屉：点标记就能看它凭什么 —— 这是全站唯一一种溯源方式。
 */
const props = defineProps<{ task: () => AiTask<unknown>; label?: string; compact?: boolean }>()
const session = useSessionStore()

const t = useAiTask<unknown>(() => props.task())

const badge = computed(() => {
  const n = t.citations.value.length
  const ms = t.meta.value ? Math.round(t.meta.value.ms / 100) / 10 : 0
  const who = t.meta.value?.by ?? 'AI'
  return `${who} 生成 · ${n} 条依据 · ${ms}s${t.meta.value?.cached ? ' · 已算过' : ''}`
})

function showCitations() {
  session.openDrawer(
    '这块内容是凭什么算出来的',
    t.rationale.value || '每一条都能点开看',
    t.citations.value.map((c: AiCitation) => ({ source: c.source, detail: c.detail, confidence: c.confidence, at: c.at })),
  )
}

/*
 * 暴露 run / retry 之外，也把 state 与 error 让出去：
 * 调用方常常需要在"算失败"时给一条自己的出路（例如学信网核验失败要能退回改验证码），
 * 而不是只有 AI 标记上那个通用的"重新算一次"。
 */
defineExpose({ run: t.run, retry: t.retry, state: t.state, error: t.error })
</script>

<template>
  <div class="ai" :class="{ 'ai--compact': props.compact }" :data-ai-state="t.state.value">
    <!-- 生成中：虚线骨架 + 这一句"它在干嘛" -->
    <div v-if="t.streaming()" class="wait" role="status" aria-live="polite">
      <span class="wait__sketch" aria-hidden="true" />
      <div class="wait__lines">
        <p class="wait__note">{{ t.note.value || props.label || '正在生成' }}</p>
        <span class="wait__bar"><i :style="{ width: `${Math.round(t.pct.value * 100)}%` }" /></span>
      </div>
      <span class="wait__pct mono">{{ Math.round(t.pct.value * 100) }}%</span>
    </div>

    <!-- 出错：说清哪一步断了，给一个重算 -->
    <div v-else-if="t.state.value === 'error'" class="err" role="alert">
      <p class="err__text">这一步没算完：{{ t.error.value }}</p>
      <button class="btn ghost" type="button" @click="t.retry()">重新算一次</button>
    </div>

    <!-- 完成：内容 + 可点的标记 -->
    <template v-else>
      <slot :data="t.data.value" :citations="t.citations.value" :rationale="t.rationale.value" />
      <button class="badge" type="button" @click="showCitations">
        <span class="badge__dot" aria-hidden="true" />
        <span class="label">{{ badge }}</span>
        <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M4 2.4 7.6 6 4 9.6" fill="none" stroke="currentColor" stroke-width="1.6"
                stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </template>
  </div>
</template>

<style scoped>
.ai { display: flex; flex-direction: column; gap: var(--s3); }
.ai--compact { gap: var(--s2); }

/* ── 生成中 ─────────────────────────────────────────────────────── */
.wait {
  display: grid; grid-template-columns: 46px minmax(0, 1fr) auto;
  align-items: center; gap: var(--s3);
  padding: var(--s3) var(--s4);
  border: 2px dashed var(--line-3);
  border-radius: var(--r-md);
  background: var(--fill-subtle);
}
/* 一个小小的手绘方块，代替转圈 —— 转圈是通用的，这个是我们的 */
.wait__sketch {
  width: 46px; height: 30px; border-radius: 8px;
  background: repeating-linear-gradient(115deg, var(--line-2) 0 6px, transparent 6px 12px);
  position: relative; overflow: hidden;
}
.wait__sketch::after {
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.85), transparent);
  animation: mo-shimmer 1.4s var(--mo-out) infinite;
}
.wait__lines { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.wait__note { font-size: var(--fs-small); color: var(--ink-2); }
.wait__bar { display: block; height: 3px; border-radius: 2px; background: var(--line-1); overflow: hidden; }
.wait__bar i { display: block; height: 100%; background: var(--accent); border-radius: 2px; transition: width var(--mo-base) var(--mo-out); }
.wait__pct { color: var(--ink-3); }

/* ── 出错 ───────────────────────────────────────────────────────── */
.err {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s4);
  padding: var(--s3) var(--s4);
  border: var(--bw) solid var(--warn); border-radius: var(--r-md);
  background: rgba(194, 90, 18, 0.06);
}
.err__text { font-size: var(--fs-small); color: var(--ink-1); }

/* ── 完成后的标记 ───────────────────────────────────────────────── */
.badge {
  display: inline-flex; align-items: center; gap: 7px;
  align-self: flex-start;
  padding: 4px 10px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  /*
   * 这枚标记常常落在薄片**外面**（AiFrame 的内容在薄片里，标记在它下面），
   * 浮层底板拿掉之后它就是一颗压在遮罩上的空壳 —— 给它自己一层纸。
   */
  background: var(--n-1);
  color: var(--ink-3);
  transition: color var(--mo-fast) var(--mo-out), border-color var(--mo-fast) var(--mo-out);
}
.badge:hover { color: var(--ink-1); border-color: var(--line-3); }
.badge__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--mk-purple); }
</style>
