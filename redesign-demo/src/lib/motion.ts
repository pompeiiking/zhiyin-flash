import { onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * 动效小工具。
 *
 * 两个原则写在最前面，因为它们决定了这里**没有**什么：
 *   1. 只用 CSS 能做好的，就用 CSS（见 base.css 的 .stagger / .just-changed，
 *      以及 MeterRow.vue 的 .mtr__fill —— 后者用 width + transition，无副作用）。
 *      这里只放 CSS 做不到的两件事：数字滚动、逐字流式。
 *      【2026-10-14 · wave2】这里原来引用的是 `base.css` 的 `.meter__fill`。那个零件已整段删除
 *      （8 处定义 / 0 处使用），而且它的写法本身就是坏范例：
 *      `transform: scaleX(var(--meter, 0))` 的**缺省值是 0** —— 任何拿到那个类名却没同时设
 *      `--meter` 的元素会被压成 0 宽，`getComputedStyle` 仍如实报 `width: 330px`，
 *      屏幕上什么都没有（现场证据见 `components/charts/MeterRow.vue:19-24`）。
 *      换成 `.mtr__fill` 不只是换个名字：`width` + `transition` 不会连带缩放
 *      `border-radius` 与 `background`，也不会在漏传变量时静默归零。
 *      读到这段的人请注意：**不要把 `.meter__fill` 当范例加回来**。
 *   2. 一天看几十次的东西不动（导航条、按钮、列表项自身）；动的是"数字变了""话正在出来"。
 */

const prefersReduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * 数字滚动。
 *
 * 用途：分值、条数、百分比 —— 让"这里变了"这件事被看见，而不是从 46 直接跳到 52。
 * 420ms + ease-out（和 --dur-4 / --ease-out 对齐）：
 * 再长就变成"等数字"，再短就等于没动。
 *
 * 减少动效时**直接给终值**，不做动画 —— 数字滚动对理解没有帮助，只是提示变化。
 */
export function useCountUp(target: Ref<number>, duration = 420) {
  const shown = ref(prefersReduced() ? target.value : 0)
  let raf = 0

  function animateTo(to: number) {
    if (prefersReduced()) {
      shown.value = to
      return
    }
    cancelAnimationFrame(raf)
    const from = shown.value
    if (from === to) return
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - (1 - p) ** 3 // ease-out cubic，与 --ease-out 同族
      shown.value = from + (to - from) * eased
      if (p < 1) raf = requestAnimationFrame(tick)
      else shown.value = to
    }
    raf = requestAnimationFrame(tick)
  }

  // 首次挂载也走一次（0 → 值），让"这一屏有数"这件事被注意到
  animateTo(target.value)
  watch(target, animateTo)
  onUnmounted(() => cancelAnimationFrame(raf))

  return { shown, animateTo }
}

/**
 * 流式逐字。
 *
 * 用途：主理的回答一段一段出来，而不是"啪"地整段出现。
 * 这不只是好看 —— 它让用户知道"系统在生成"，也就是把等待变得可理解。
 *
 * 时长按字数算（每字约 11ms，夹在 320–900ms 之间）：
 * 短句不该拖 900ms，长段也不该一闪而过。
 */
export function useStreaming(onComplete?: (id: string, text: string) => void) {
  /** turnId → 已显示到第几个字；没有键就是"已经出完" */
  const revealed = ref<Record<string, number>>({})
  const frames = new Map<string, number>()

  function stream(id: string, text: string) {
    const total = text.length
    if (prefersReduced()) {
      const next = { ...revealed.value }
      delete next[id]
      revealed.value = next
      onComplete?.(id, text)
      return
    }
    const duration = Math.min(900, Math.max(320, total * 11))
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - (1 - p) ** 3
      const next = { ...revealed.value, [id]: Math.floor(eased * total) }
      if (p >= 1) delete next[id]
      revealed.value = next
      if (p < 1) frames.set(id, requestAnimationFrame(tick))
      else {
        frames.delete(id)
        onComplete?.(id, text)
      }
    }
    const previous = frames.get(id)
    if (previous != null) cancelAnimationFrame(previous)
    revealed.value = { ...revealed.value, [id]: 0 }
    frames.set(id, requestAnimationFrame(tick))
  }

  onUnmounted(() => frames.forEach((frame) => cancelAnimationFrame(frame)))

  /** 模板里用它取"现在该显示多少字" */
  function textOf(id: string, full: string) {
    const n = revealed.value[id]
    return n == null ? full : full.slice(0, n)
  }

  function isStreaming(id: string) {
    return revealed.value[id] != null
  }

  return { stream, textOf, isStreaming }
}
