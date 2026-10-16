import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { createScrollIntent } from './scroll-intent'

export function useConversationScroll(flow: Ref<HTMLElement | null>) {
  const intent = createScrollIntent()
  const followTail = ref(true)
  const showLatest = ref(false)
  let frame = 0
  let disposed = false
  function measure() {
    const el = flow.value
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    followTail.value = intent.update(distance, performance.now())
    showLatest.value = !followTail.value && distance > 120
  }
  function release() { intent.release(performance.now()); followTail.value = false }
  async function bottom(force = false) {
    if (force) { intent.pin(); followTail.value = true; showLatest.value = false }
    await nextTick()
    if (disposed || frame) return
    frame = requestAnimationFrame(() => {
      frame = 0
      if (intent.pinned && flow.value) flow.value.scrollTop = flow.value.scrollHeight
      measure()
    })
  }
  watch(flow, (el, _, cleanup) => {
    if (!el) return
    const wheel = (event: WheelEvent) => { if (event.deltaY < 0) release() }
    const key = (event: KeyboardEvent) => { if (['ArrowUp', 'PageUp', 'Home'].includes(event.key)) release() }
    const resize = new ResizeObserver(() => { if (intent.pinned) void bottom(); else measure() })
    const observeChildren = () => { resize.disconnect(); resize.observe(el); for (const child of el.children) resize.observe(child) }
    const mutation = new MutationObserver(observeChildren)
    observeChildren(); mutation.observe(el, { childList: true })
    el.addEventListener('wheel', wheel, { passive: true })
    el.addEventListener('touchstart', release, { passive: true })
    el.addEventListener('pointerdown', release, { passive: true })
    el.addEventListener('keydown', key)
    cleanup(() => {
      resize.disconnect(); mutation.disconnect()
      el.removeEventListener('wheel', wheel); el.removeEventListener('touchstart', release)
      el.removeEventListener('pointerdown', release); el.removeEventListener('keydown', key)
    })
  }, { flush: 'post' })
  onBeforeUnmount(() => { disposed = true; cancelAnimationFrame(frame) })
  return { followTail, showLatest, bottom, onScroll: measure }
}
