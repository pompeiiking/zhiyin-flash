<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { demo } from '../store'
import UiIcon from './UiIcon.vue'

const root = ref<HTMLElement | null>(null)
const route = useRoute()
const viewportHeight = ref(typeof window === 'undefined' ? 800 : window.innerHeight)
const viewportWidth = ref(typeof window === 'undefined' ? 1280 : window.innerWidth)
const y = ref(88)
let dragging = false
let moved = false
let suppressClick = false
let startY = 0
let startTop = 0
let hasSavedPosition = false
const positionKey = 'zhiyin-reminder-y-v2'

const mobile = computed(() => viewportWidth.value <= 767)
const minY = computed(() => mobile.value ? 136 : 72)
const maxY = computed(() => Math.max(minY.value, viewportHeight.value - (mobile.value ? 138 : 78)))
const triggerStyle = computed(() => ({ top: `${Math.min(maxY.value, Math.max(minY.value, y.value))}px` }))
const cardY = computed(() => {
  const height = mobile.value ? 356 : 390
  return y.value > viewportHeight.value / 2
    ? Math.max(72, y.value - height)
    : Math.min(y.value + 54, Math.max(72, viewportHeight.value - height))
})
const cardStyle = computed(() => ({ top: `${cardY.value}px` }))
const visibleNotices = computed(() => demo.state.noticeQueue.slice(0, 3))

function clamp(value: number) { return Math.min(maxY.value, Math.max(minY.value, value)) }
function resize() { viewportHeight.value = window.innerHeight; viewportWidth.value = window.innerWidth; y.value = clamp(y.value) }
function restore() {
  const raw = localStorage.getItem(positionKey)
  const saved = Number(raw)
  hasSavedPosition = raw !== null && Number.isFinite(saved)
  if (hasSavedPosition) y.value = clamp(saved)
  else y.value = clamp(mobile.value ? viewportHeight.value * .55 : 88)
}
function save() { localStorage.setItem(positionKey, String(Math.round(y.value))) }
function resetPosition() { y.value = mobile.value ? viewportHeight.value * .55 : 88; save() }
function pointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  dragging = true; moved = false; startY = event.clientY; startTop = y.value
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerUp, { once: true })
}
function pointerMove(event: PointerEvent) {
  if (!dragging) return
  const delta = event.clientY - startY
  if (Math.abs(delta) > 4) moved = true
  if (moved) { event.preventDefault(); y.value = clamp(startTop + delta) }
}
function pointerUp() {
  dragging = false
  window.removeEventListener('pointermove', pointerMove)
  if (moved) { suppressClick = true; save(); setTimeout(() => { suppressClick = false }, 0) }
}
function toggle() {
  if (suppressClick) return
  demo.state.noticeOpen ? demo.closeNotice() : demo.openNotice()
}
function outside(event: PointerEvent) {
  if (demo.state.noticeOpen && root.value && !root.value.contains(event.target as Node)) demo.closeNotice()
}
function escape(event: KeyboardEvent) { if (event.key === 'Escape') demo.closeNotice() }
onMounted(() => { restore(); resize(); window.addEventListener('resize', resize); document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape) })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); window.removeEventListener('pointermove', pointerMove); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) })
watch(() => route.path, () => { if (!hasSavedPosition) restore(); demo.closeNotice() })
</script>

<template>
  <div v-if="route.path !== '/reminders'" ref="root" class="floating-reminders">
    <button
      class="floating-reminders__trigger"
      :style="triggerStyle"
      type="button"
      :aria-expanded="demo.state.noticeOpen"
      :aria-label="`提醒，${demo.state.noticeQueue.length} 条待处理。可上下拖动位置`"
      @pointerdown="pointerDown"
      @click="toggle"
    >
      <UiIcon name="bell" :size="19" />
      <span v-if="demo.state.noticeQueue.length">{{ demo.state.noticeQueue.length > 99 ? '99+' : demo.state.noticeQueue.length }}</span>
    </button>

    <section v-if="demo.state.noticeOpen" class="floating-reminders__card" :style="cardStyle" aria-label="提醒快捷卡片">
      <header><div><strong>提醒</strong><span>{{ demo.state.noticeQueue.length }} 条待处理</span></div><button type="button" aria-label="关闭提醒" @click="demo.closeNotice()"><UiIcon name="close" :size="17" /></button></header>
      <div v-if="visibleNotices.length" class="floating-reminders__list">
        <article v-for="notice in visibleNotices" :key="notice.id">
          <span>{{ notice.kind }}</span><h2>{{ notice.title }}</h2><p>{{ notice.body }}</p>
          <button type="button" :disabled="demo.state.chatBusy" @click="demo.resolveNotice(notice.id)">{{ notice.action || '标为已读' }}</button>
        </article>
      </div>
      <p v-else class="floating-reminders__empty">目前没有待处理提醒。</p>
      <footer><RouterLink to="/reminders" @click="demo.closeNotice()">查看全部提醒</RouterLink><button type="button" @click="resetPosition">恢复默认位置</button></footer>
    </section>
  </div>
</template>

<style scoped>
.floating-reminders { position:relative; z-index:calc(var(--z-drawer) - 1); }
.floating-reminders__trigger { position:fixed; right:18px; z-index:calc(var(--z-drawer) - 1); display:grid; place-items:center; width:46px; height:46px; padding:0; border:1px solid var(--c-primary-border); border-radius:15px; background:color-mix(in srgb,var(--c-surface) 92%,transparent); color:var(--c-primary); box-shadow:var(--e-2); backdrop-filter:blur(16px); cursor:grab; touch-action:none; }
.floating-reminders__trigger:active { cursor:grabbing; }
.floating-reminders__trigger>span { position:absolute; top:-5px; right:-5px; display:grid; place-items:center; min-width:21px; height:21px; padding:0 5px; border:2px solid var(--c-bg); border-radius:999px; background:var(--c-attention); color:var(--c-on-attention); font-size:11px; font-weight:700; font-variant-numeric:tabular-nums; }
.floating-reminders__card { position:fixed; right:18px; z-index:calc(var(--z-drawer) - 1); width:min(360px,calc(100vw - 36px)); max-height:min(520px,calc(100dvh - 96px)); overflow:auto; border:1px solid var(--c-border); border-radius:16px; background:var(--c-surface); box-shadow:var(--e-3); }
.floating-reminders__card>header { position:sticky; top:0; z-index:1; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:15px 16px; border-bottom:1px solid var(--c-border); background:color-mix(in srgb,var(--c-surface) 94%,transparent); backdrop-filter:blur(14px); }
.floating-reminders__card>header div { display:flex; align-items:baseline; gap:8px; }
.floating-reminders__card>header strong { font-size:16px; }
.floating-reminders__card>header span { color:var(--c-text-3); font-size:12px; }
.floating-reminders__card>header button { display:grid; place-items:center; width:36px; height:36px; border-radius:10px; color:var(--c-text-2); }
.floating-reminders__list { padding:4px 16px 0; }
.floating-reminders__list article { padding:15px 0; border-bottom:1px solid var(--c-border); min-width:0; }
.floating-reminders__list article>span { color:var(--c-primary); font-size:11px; font-weight:600; }
.floating-reminders__list h2 { margin:4px 0; font-size:14px; font-weight:600; overflow-wrap:anywhere; }
.floating-reminders__list p { margin:0; color:var(--c-text-2); font-size:13px; line-height:1.65; overflow-wrap:anywhere; }
.floating-reminders__list article>button { min-height:36px; margin-top:9px; padding:6px 10px; border-radius:8px; background:var(--c-primary-weak); color:var(--c-primary); font-size:12px; }
.floating-reminders__empty { padding:28px 16px; text-align:center; color:var(--c-text-2); }
.floating-reminders__card>footer { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:13px 16px; }
.floating-reminders__card>footer :is(a,button) { min-height:36px; display:inline-flex; align-items:center; color:var(--c-primary); font-size:12px; }
.floating-reminders__card>footer button { color:var(--c-text-3); }
@media (max-width:767px) {
  .floating-reminders__trigger { right:6px; width:44px; height:44px; border-radius:14px; }
  .floating-reminders__card { right:12px; width:calc(100vw - 24px); max-height:min(56dvh,440px); }
}
@media (prefers-reduced-motion:reduce) { .floating-reminders__trigger { transition:none; } }
</style>
