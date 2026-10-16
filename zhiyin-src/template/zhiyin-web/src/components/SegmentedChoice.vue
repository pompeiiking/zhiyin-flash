<script setup lang="ts" generic="T extends string">
import { computed, ref } from 'vue'
const props = defineProps<{ modelValue: T; label: string; options: readonly { id: T; label: string }[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()
const root = ref<HTMLElement | null>(null)
const index = computed(() => Math.max(0, props.options.findIndex(option => option.id === props.modelValue)))
function key(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const count = props.options.length
  if (!count) return
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? count - 1 : (index.value + (event.key === 'ArrowRight' ? 1 : -1) + count) % count
  emit('update:modelValue', props.options[next].id)
  root.value?.querySelectorAll<HTMLButtonElement>('button')[next]?.focus()
}
</script>
<template>
  <div ref="root" class="segment-choice" role="radiogroup" :aria-label="label" :style="{ '--segments': options.length, '--selected': index }" @keydown="key">
    <span class="segment-choice__indicator" aria-hidden="true" />
    <button v-for="option in options" :key="option.id" type="button" role="radio" :aria-checked="modelValue === option.id" :tabindex="modelValue === option.id ? 0 : -1" @click="emit('update:modelValue', option.id)">{{ option.label }}</button>
  </div>
</template>
<style scoped>
.segment-choice {position:relative;display:grid;grid-template-columns:repeat(var(--segments),minmax(0,1fr));padding:4px;border:1px solid var(--c-border);border-radius:12px;background:var(--c-surface-2);isolation:isolate;}
.segment-choice__indicator {position:absolute;inset:4px auto 4px 4px;width:calc((100% - 8px) / var(--segments));background:var(--c-surface);border-radius:8px;box-shadow:0 1px 3px #00000012;transform:translateX(calc(var(--selected) * 100%));transition:transform .2s cubic-bezier(.2,.8,.2,1);z-index:-1;}
.segment-choice button {min-height:44px;padding:6px 12px;border:0;background:transparent;color:var(--c-text-2);font-size:13px;border-radius:8px;cursor:pointer;}
.segment-choice button[aria-checked=true] {color:var(--c-primary);font-weight:600;}
@media(prefers-reduced-motion:reduce) {.segment-choice__indicator {transition:none;}}
</style>
