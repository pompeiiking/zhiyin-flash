<script setup lang="ts">
import { computed, ref, useId, onMounted, onBeforeUnmount } from 'vue'
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent, PopoverClose } from 'reka-ui'
import UiIcon from './UiIcon.vue'
import { vScrollFade } from '../lib/scroll-fade'
defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{ modelValue?: boolean; title: string; label?: string; side?: 'top' | 'bottom' | 'left' | 'right'; inlineOnNarrow?: boolean }>(), { modelValue: undefined, side: 'right', inlineOnNarrow: false })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const localOpen = ref(false)
const open = computed({ get: () => props.modelValue ?? localOpen.value, set: value => { localOpen.value = value; emit('update:modelValue', value) } })
const id = useId()
const trigger = ref<HTMLButtonElement | null>(null)
const inlineDetails = ref<HTMLDetailsElement | null>(null)
const narrowQuery = typeof window === 'undefined' ? null : window.matchMedia('(max-width: 600px)')
const narrow = ref(narrowQuery?.matches ?? false)
function updateNarrow(event: MediaQueryListEvent) { narrow.value = event.matches }
onMounted(() => narrowQuery?.addEventListener('change', updateNarrow))
onBeforeUnmount(() => narrowQuery?.removeEventListener('change', updateNarrow))
const placement = computed(() => narrow.value && (props.side === 'left' || props.side === 'right') ? 'bottom' : props.side)
// Native modal dialogs make the rest of the document inert. Keep a reading
// card inside its owning dialog so its links and controls remain operable.
const portalTarget = computed(() => trigger.value?.closest('dialog') ?? undefined)
// Use the library trigger for click/Enter/Space, Escape and focus restoration.
// Merely hovering or tabbing past an editor must not open or dismiss its form.
function escape(event: KeyboardEvent) { event.stopPropagation() }
function inlineToggle() { open.value = !!inlineDetails.value?.open }
</script>
<template>
  <details v-if="inlineOnNarrow && narrow" ref="inlineDetails" class="detail-inline" @toggle="inlineToggle">
    <summary v-bind="$attrs" class="detail-trigger detail-inline__trigger" :aria-label="label || title"><slot name="trigger"><UiIcon name="info" :size="17" /></slot></summary>
    <div class="detail-inline__content" role="region" :aria-label="title"><h2>{{ title }}</h2><div class="detail-inline__body"><slot /></div></div>
  </details>
  <PopoverRoot v-else v-model:open="open" :modal="false">
    <PopoverTrigger as-child>
      <button ref="trigger" v-bind="$attrs" type="button" class="detail-trigger" :aria-label="label || title" :aria-expanded="open" :aria-controls="open ? id : undefined" aria-haspopup="dialog">
        <slot name="trigger"><UiIcon name="info" :size="17" /></slot>
      </button>
    </PopoverTrigger>
    <PopoverPortal :to="portalTarget">
      <PopoverContent :id="id" class="detail-popover" :side="placement" :side-offset="8" :collision-padding="16" :aria-label="title" @escape-key-down="escape">
        <header><h2>{{ title }}</h2><PopoverClose class="detail-popover__close" aria-label="关闭详情"><UiIcon name="close" :size="17" /></PopoverClose></header>
        <div v-scroll-fade class="detail-popover__body"><slot /></div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style scoped>
.detail-inline { margin: 4px 0 12px; }
.detail-inline__trigger { width: fit-content; list-style: none; }
.detail-inline__trigger::-webkit-details-marker { display: none; }
.detail-inline__content { margin-top: 6px; padding: 14px 16px; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); color: var(--c-text); }
.detail-inline__content h2 { margin: 0 0 10px; font-size: 14px; font-weight: 600; }
.detail-inline__body { font-size: 13px; line-height: 1.7; }
</style>
