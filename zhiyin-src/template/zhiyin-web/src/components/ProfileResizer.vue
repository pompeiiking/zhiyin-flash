<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
const props = defineProps<{ modelValue: number; max: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
const dragging = ref(false)
let startX = 0, startWidth = 0, handle: HTMLElement | null = null, pointer = 0
function setWidth(value: number) { emit('update:modelValue', Math.round(Math.max(260, Math.min(props.max, value)))) }
function start(event: PointerEvent) {
  if (event.button !== 0) return
  handle = event.currentTarget as HTMLElement; pointer = event.pointerId
  startX = event.clientX; startWidth = props.modelValue
  handle.setPointerCapture(pointer); handle.focus()
}
function move(event: PointerEvent) {
  if (!handle?.hasPointerCapture(event.pointerId)) return
  if (Math.abs(event.clientX - startX) > 4) dragging.value = true
  if (dragging.value) setWidth(startWidth + startX - event.clientX)
}
function end(cancel = false) {
  if (cancel && handle) setWidth(startWidth)
  if (handle?.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer)
  dragging.value = false; handle = null
}
function key(event: KeyboardEvent) {
  if (event.key === 'Escape') { end(true); return }
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    setWidth(event.key === 'Home' ? 260 : event.key === 'End' ? props.max : props.modelValue + (event.key === 'ArrowLeft' ? 16 : -16))
  }
}
onBeforeUnmount(() => end())
</script>
<template>
  <div class="profile-resizer" :class="{ 'is-dragging': dragging }" role="separator" tabindex="0" aria-label="调整个人画像宽度，方向键调整，双击恢复" aria-orientation="vertical" :aria-valuemin="260" :aria-valuemax="max" :aria-valuenow="modelValue" @pointerdown="start" @pointermove="move" @pointerup="end()" @pointercancel="end(true)" @lostpointercapture="dragging = false" @keydown="key" @dblclick="setWidth(300)"><i /></div>
</template>
<style scoped>
.profile-resizer { position:relative;width:12px;margin-inline:-6px;z-index:2;cursor:col-resize;touch-action:none;outline-offset:-4px; }
.profile-resizer i {position:absolute;inset:0 5px;background:transparent;transition:background .16s;}
.profile-resizer:hover i,.profile-resizer:focus-visible i,.is-dragging i {background:var(--c-primary);}
.profile-resizer::after {content:'';position:absolute;top:48%;left:4px;width:4px;height:28px;border-radius:4px;background:var(--c-border-strong);}
@media(prefers-reduced-motion:reduce) {.profile-resizer i {transition:none;}}
</style>
