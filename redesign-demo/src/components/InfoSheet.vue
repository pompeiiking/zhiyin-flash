<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import UiIcon from './UiIcon.vue'
const props = defineProps<{ open: boolean; title: string; wide?: boolean; inspector?: boolean }>()
const emit = defineEmits<{ close: []; opened: [] }>()
const el = ref<HTMLDialogElement | null>(null)
async function sync() {
  await nextTick()
  if (props.open && el.value && !el.value.open) {
    el.value.showModal()
    emit('opened')
  }
  if (!props.open && el.value?.open) el.value.close()
}
watch(() => props.open, sync)
onMounted(sync)
function trapTab(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !el.value?.open) return
  const targets = [...el.value.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]')].filter(e => e.getClientRects().length)
  const first = targets[0], last = targets[targets.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
</script>
<template>
  <dialog ref="el" class="ws-sheet" :class="{ 'ws-sheet--wide': wide, 'ws-sheet--inspector': inspector }" :aria-label="title" @keydown="trapTab" @cancel.prevent="emit('close')" @click="($event.target === el) && emit('close')">
    <div class="ws-sheet__inner">
      <header class="ws-sheet__head"><h2>{{ title }}</h2><button class="ws-icon-button" aria-label="关闭面板" @click="emit('close')"><UiIcon name="close" /></button></header>
      <div class="ws-sheet__body"><slot /></div>
    </div>
  </dialog>
</template>
<style scoped>
.ws-sheet { max-height: calc(100dvh - 32px); overflow: hidden; }
.ws-sheet__inner { display: flex; flex-direction: column; max-height: calc(100dvh - 36px); }
.ws-sheet__head { flex: none; }
.ws-sheet__body { overflow-y: auto; overscroll-behavior: contain; min-height: 0; }
</style>
