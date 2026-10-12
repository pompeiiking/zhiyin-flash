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
</script>
<template>
  <dialog ref="el" class="ws-sheet" :class="{ 'ws-sheet--wide': wide, 'ws-sheet--inspector': inspector }" :aria-label="title" @cancel.prevent="emit('close')" @click="($event.target === el) && emit('close')">
    <div class="ws-sheet__inner">
      <header class="ws-sheet__head"><h2>{{ title }}</h2><button class="ws-icon-button" aria-label="关闭面板" @click="emit('close')"><UiIcon name="close" /></button></header>
      <div class="ws-sheet__body"><slot /></div>
    </div>
  </dialog>
</template>
