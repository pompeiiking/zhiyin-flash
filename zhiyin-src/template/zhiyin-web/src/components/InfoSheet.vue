<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import UiIcon from './UiIcon.vue'
import { vScrollFade } from '../lib/scroll-fade'

type Shape = 'dialog' | 'sheet' | 'panel'
let openSheets = 0
let previousBodyOverflow = ''

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  shape?: Shape
  draggable?: boolean
  description?: string
  /**
   * 非 dialog 形态下关闭时保留内容挂载：详情弹层由子组件里的 Teleport 打开时，
   * 子组件不能因为外层 sheet 关闭而被卸载（画像的“深入了解”就是这条路径）。
   */
  keepMounted?: boolean
}>(), { shape: 'dialog', draggable: true, description: '', keepMounted: false })

const emit = defineEmits<{ close: []; opened: [] }>()
const modal = ref<HTMLDialogElement | null>(null)
const card = ref<HTMLElement | null>(null)
const anchor = ref<HTMLElement | null>(null)
const cardStyle = ref<Record<string, string>>({})
const bodyId = `info-sheet-body-${Math.random().toString(36).slice(2, 8)}`
const isDialog = computed(() => props.shape === 'dialog')
let bodyLocked = false

function focusFallback() {
  const target = anchor.value
  queueMicrotask(() => {
    if (target && document.contains(target)) target.focus({ preventScroll: true })
    else {
      // `.ws-page` 通常是 div，没有 tabindex，focus() 是空操作；优先回到
      // 有 tabindex 的 main（路由层的 #main-content），否则不发焦点。
      const main = document.querySelector<HTMLElement>('#main-content, main[tabindex], [role="main"][tabindex]')
      main?.focus?.({ preventScroll: true })
    }
  })
}

function positionCard() {
  if (!props.open || isDialog.value || !card.value) return
  const viewportW = window.innerWidth
  const viewportH = window.innerHeight
  if (viewportW <= 767) {
    cardStyle.value = { left: '10px', right: '10px', bottom: 'calc(8px + env(safe-area-inset-bottom, 0px))', top: 'auto', maxHeight: 'calc(100dvh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px))' }
    return
  }
  const rect = anchor.value?.getBoundingClientRect()
  const width = Math.min(props.shape === 'panel' ? 680 : 460, viewportW - 32)
  const height = Math.min(card.value.offsetHeight || 620, 680, viewportH - 32)
  let left = viewportW - width - 18
  let top = 76
  if (rect) {
    const roomRight = viewportW - rect.right
    const roomLeft = rect.left
    if (roomRight >= width + 12) left = rect.right + 10
    else if (roomLeft >= width + 12) left = rect.left - width - 10
    else left = Math.max(16, Math.min(rect.right - width, viewportW - width - 16))
    top = Math.max(16, Math.min(rect.top, viewportH - height - 16))
  }
  cardStyle.value = { width: `${width}px`, left: `${Math.round(left)}px`, top: `${Math.round(top)}px`, right: 'auto', bottom: 'auto', maxHeight: `${Math.min(680, Math.max(260, viewportH - Math.max(16, top) - 16))}px` }
}

function onDocumentPointer(event: PointerEvent) {
  const target = event.target as Node | null
  if (!props.open || isDialog.value || !target) return
  if (card.value?.contains(target) || anchor.value?.contains(target)) return
  if (target instanceof Element && target.closest('.ws-expand-card,.detail-popover,.anchored-card,.skin__pop')) return
  emit('close')
}

function onDocumentKey(event: KeyboardEvent) {
  if (!props.open || isDialog.value) return
  if (event.key === 'Escape') { emit('close'); return }
  if (event.key !== 'Tab' || !card.value) return
  // Reka popovers are teleported outside the sheet and manage their own focus.
  if (document.querySelector('[data-reka-popper-content-wrapper],.detail-popover,.anchored-card,.skin__pop')) return
  const focusable = [...card.value.querySelectorAll<HTMLElement>(
    'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
  )].filter((element) => element.offsetParent !== null)
  if (!focusable.length) return
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  const active = document.activeElement
  if (event.shiftKey && (active === first || !card.value.contains(active))) {
    event.preventDefault(); last.focus()
  } else if (!event.shiftKey && (active === last || !card.value.contains(active))) {
    event.preventDefault(); first.focus()
  }
}

function lockBody() {
  if (openSheets === 0) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  openSheets++
  bodyLocked = true
}
function unlockBody() {
  if (!bodyLocked) return
  bodyLocked = false
  openSheets = Math.max(0, openSheets - 1)
  if (openSheets === 0) document.body.style.overflow = previousBodyOverflow
}

function addCardListeners() {
  document.addEventListener('pointerdown', onDocumentPointer, true)
  document.addEventListener('keydown', onDocumentKey)
  window.addEventListener('resize', positionCard)
  window.addEventListener('scroll', positionCard, true)
}

function removeCardListeners() {
  document.removeEventListener('pointerdown', onDocumentPointer, true)
  document.removeEventListener('keydown', onDocumentKey)
  window.removeEventListener('resize', positionCard)
  window.removeEventListener('scroll', positionCard, true)
}

async function syncOpen(open: boolean, previous?: boolean) {
  if (open) {
    const active = document.activeElement
    if (active instanceof HTMLElement && active !== document.body) anchor.value = active
    await nextTick()
    if (isDialog.value) {
      if (modal.value && !modal.value.open) modal.value.showModal()
    } else {
      positionCard()
      addCardListeners()
      lockBody()
      card.value?.querySelector<HTMLElement>('input, textarea, select, button, [tabindex="0"]')?.focus()
    }
    emit('opened')
    return
  }
  removeCardListeners()
  if (!isDialog.value) unlockBody()
  if (modal.value?.open) modal.value.close()
  if (previous) focusFallback()
}

watch(() => props.open, syncOpen, { immediate: true })
onBeforeUnmount(() => {
  removeCardListeners()
  if (props.open && !isDialog.value) unlockBody()
  if (modal.value?.open) modal.value.close()
})
</script>

<template>
  <dialog
    v-if="isDialog"
    ref="modal"
    class="ws-confirm-dialog"
    :aria-label="title"
    :aria-describedby="description ? `${bodyId}-desc` : undefined"
    @cancel.prevent="emit('close')"
    @click="($event.target === modal) && emit('close')"
  >
    <div class="ws-expand-card__inner">
      <header class="ws-expand-card__head">
        <h2>{{ title }}</h2>
        <button class="ws-icon-button" type="button" aria-label="关闭" @click="emit('close')"><UiIcon name="close" /></button>
      </header>
      <p v-if="description" :id="`${bodyId}-desc`" class="ws-expand-card__desc">{{ description }}</p>
      <div :id="bodyId" v-scroll-fade class="ws-expand-card__body"><slot /></div>
    </div>
  </dialog>

  <Teleport v-else to="body">
    <Transition name="expand-card">
      <section
        v-if="open || keepMounted"
        v-show="open"
        ref="card"
        class="ws-expand-card"
        :class="`ws-expand-card--${shape}`"
        :style="cardStyle"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        :aria-describedby="description ? `${bodyId}-desc` : undefined"
      >
        <div class="ws-expand-card__inner">
          <header class="ws-expand-card__head">
            <div>
              <span>{{ shape === 'panel' ? '当前操作' : '补充信息' }}</span>
              <h2>{{ title }}</h2>
            </div>
            <button class="ws-icon-button" type="button" :aria-label="`收起${title}`" @click="emit('close')"><UiIcon name="close" /></button>
          </header>
          <p v-if="description" :id="`${bodyId}-desc`" class="ws-expand-card__desc">{{ description }}</p>
          <div :id="bodyId" v-scroll-fade class="ws-expand-card__body"><slot /></div>
        </div>
      </section>
    </Transition>
  </Teleport>
</template>

<style>
.ws-confirm-dialog {
  width:min(520px,calc(100vw - 32px)); max-height:calc(100dvh - 48px); padding:0; overflow:hidden;
  border:1px solid var(--c-border); border-radius:18px; background:var(--c-surface); color:var(--c-text); box-shadow:var(--e-3);
}
.ws-confirm-dialog::backdrop { background:var(--overlay-mask); }
.ws-expand-card {
  position:fixed; z-index:150; display:flex; flex-direction:column; overflow:hidden;
  width:min(460px,calc(100vw - 32px)); max-height:calc(100dvh - 32px);
  border:1px solid color-mix(in srgb,var(--c-primary) 18%,var(--c-border)); border-radius:18px;
  background:var(--c-surface); color:var(--c-text);
  box-shadow:0 24px 70px rgb(18 36 61 / 21%),0 4px 14px rgb(18 36 61 / 9%);
}
.ws-expand-card--panel { width:min(680px,calc(100vw - 32px)); }
.ws-expand-card__inner { display:flex; flex-direction:column; min-height:0; max-height:inherit; }
.ws-expand-card__head { display:flex; flex:none; align-items:center; justify-content:space-between; gap:20px; min-height:62px; padding:8px 10px 8px 20px; border-bottom:1px solid var(--c-border); }
.ws-expand-card__head>div { min-width:0; }
.ws-expand-card__head span { display:block; margin-bottom:2px; color:var(--c-primary); font-size:12px; font-weight:600; }
.ws-expand-card__head h2 { margin:0; font-size:16px; font-weight:650; line-height:1.4; }
.ws-expand-card__desc { flex:none; margin:0; padding:12px 20px 0; color:var(--c-text-2); font-size:13px; line-height:1.65; }
.ws-expand-card__body { min-height:0; padding:16px 20px 20px; overflow:auto; overscroll-behavior:contain; }
.expand-card-enter-active,.expand-card-leave-active { transition:opacity .16s ease,transform .16s ease; transform-origin:top right; }
.expand-card-enter-from,.expand-card-leave-to { opacity:0; transform:translateY(-5px) scale(.975); }
@media (max-width:767px) {
  .ws-expand-card,.ws-expand-card--panel { width:auto; border-radius:18px; }
  .ws-expand-card__head { min-height:56px; padding-left:16px; }
  .ws-expand-card__desc { padding:10px 16px 0; }
  .ws-expand-card__body { padding:14px 16px 18px; }
}
@media (prefers-reduced-motion:reduce) { .expand-card-enter-active,.expand-card-leave-active { transition:none; } }
</style>
