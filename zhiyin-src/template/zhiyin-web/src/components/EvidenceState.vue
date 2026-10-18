<script setup lang="ts">
import { computed } from 'vue'
import { EVIDENCE_STATE_META, toEvidenceState, type EvidenceState } from '../lib/evidence-state'

/**
 * 证据状态徽标（F5）：已记录 / 待补充 / 待核对 / 已核验 / 按资料范围未使用。
 * 画像、报告、方向对比共用同一个组件，颜色与文案只在这里定义一次。
 */
const props = withDefaults(defineProps<{
  state?: EvidenceState | string | null
  /** 覆盖默认文案（一般不要用，统一口径才可比较） */
  label?: string
  /** 覆盖默认解释 */
  hint?: string
  size?: 'sm' | 'md'
}>(), { state: 'unverified', size: 'sm' })

const resolved = computed(() => toEvidenceState(props.state))
const meta = computed(() => EVIDENCE_STATE_META[resolved.value])
</script>

<template>
  <span class="ev-state" :class="[`ev-state--${meta.tone}`, `ev-state--${size}`]" :data-state="resolved" :title="hint || meta.hint">
    <i aria-hidden="true" />
    <span>{{ label || meta.label }}</span>
    <span class="sr-only">。{{ hint || meta.hint }}</span>
  </span>
</template>

<style scoped>
.ev-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border-radius: 999px;
  border: 1px solid var(--c-border);
  background: var(--c-surface-2);
  color: var(--c-text-2);
  font-size: var(--fs-12);
  line-height: 1.4;
  white-space: nowrap;
}
.ev-state--sm { padding: 2px 8px; }
.ev-state--md { padding: 4px 10px; }
.ev-state > i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: none; }
.ev-state--primary { border-color: var(--c-primary-border); color: var(--c-primary); background: var(--c-primary-weak); }
.ev-state--attention { border-color: var(--c-attention-border); color: var(--c-attention-strong); background: var(--c-attention-weak); }
</style>
