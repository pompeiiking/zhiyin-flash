<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue'
import { PopoverRoot, PopoverAnchor, PopoverPortal, PopoverContent, PopoverClose } from 'reka-ui'
import UiIcon from './UiIcon.vue'
defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{ modelValue?: boolean; title: string; label?: string; side?: 'top' | 'bottom' | 'left' | 'right' }>(), { modelValue: undefined, label: '查看说明', side: 'bottom' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const localOpen = ref(false), pinned = ref(false)
const open = computed({ get: () => props.modelValue ?? localOpen.value, set: value => { localOpen.value = value; emit('update:modelValue', value) } })
const id = useId()
const trigger = ref<HTMLButtonElement | null>(null)
let restoringFocus = false
function focusOpen() { if (!restoringFocus) open.value = true }
function restoreFocus() { restoringFocus = true; trigger.value?.focus(); queueMicrotask(() => { restoringFocus = false }) }
let timer: ReturnType<typeof setTimeout> | undefined
function clear() { if (timer) clearTimeout(timer) }
function enter(event: PointerEvent) { if (event.pointerType !== 'mouse') return; clear(); timer = setTimeout(() => { open.value = true }, 180) }
function leave() { clear(); if (!pinned.value) timer = setTimeout(() => { open.value = false }, 280) }
async function toggle(event: MouseEvent) { clear(); if (pinned.value) { open.value = false; pinned.value = false } else { open.value = true; pinned.value = true; if (event.detail === 0) { await nextTick(); document.getElementById(id)?.querySelector<HTMLElement>('button,a[href]')?.focus() } } }
function update(value: boolean) { open.value = value; if (!value) pinned.value = false }
onBeforeUnmount(clear)
</script>
<template>
  <PopoverRoot :open="open" :modal="false" @update:open="update">
    <PopoverAnchor as-child>
      <button ref="trigger" v-bind="$attrs" type="button" class="detail-trigger" :aria-label="label" :aria-expanded="open" :aria-controls="open ? id : undefined" aria-haspopup="dialog" @pointerenter="enter" @pointerleave="leave" @focus="focusOpen" @click="toggle" @keydown.esc="update(false)">
        <slot name="trigger"><UiIcon name="info" :size="17" /></slot>
      </button>
    </PopoverAnchor>
    <PopoverPortal>
      <PopoverContent :id="id" class="detail-popover" :side="side" :side-offset="8" :collision-padding="16" :aria-label="title" @pointerenter="clear" @pointerleave="leave" @open-auto-focus.prevent @close-auto-focus.prevent @escape-key-down="restoreFocus">
        <header><h2>{{ title }}</h2><PopoverClose class="detail-popover__close" aria-label="关闭详情" @click="restoreFocus"><UiIcon name="close" :size="17" /></PopoverClose></header>
        <div class="detail-popover__body"><slot /></div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
