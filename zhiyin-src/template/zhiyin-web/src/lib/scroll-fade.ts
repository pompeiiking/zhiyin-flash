import type { ObjectDirective } from 'vue'

const cleanup = new WeakMap<HTMLElement, () => void>()
/** A small edge cue; only present where more content can actually be scrolled. */
export const vScrollFade: ObjectDirective<HTMLElement> = {
  mounted(el) {
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        el.style.setProperty('--fade-top', el.scrollTop > 4 ? '12px' : '0px')
        el.style.setProperty('--fade-bottom', el.scrollHeight - el.clientHeight - el.scrollTop > 4 ? '12px' : '0px')
      })
    }
    el.classList.add('scroll-edge-fade')
    const resize = new ResizeObserver(update)
    const observe = () => { resize.disconnect(); resize.observe(el); for (const child of el.children) resize.observe(child); update() }
    const mutation = new MutationObserver(observe)
    observe(); mutation.observe(el, { childList: true, subtree: true, characterData: true })
    el.addEventListener('scroll', update, { passive: true })
    cleanup.set(el, () => { resize.disconnect(); mutation.disconnect(); cancelAnimationFrame(frame); el.removeEventListener('scroll', update) })
  },
  beforeUnmount(el) { cleanup.get(el)?.(); cleanup.delete(el) },
}
