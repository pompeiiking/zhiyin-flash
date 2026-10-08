import { onBeforeUnmount, onMounted } from 'vue'
import { annotate } from 'rough-notation'
import { LOOK_EVENT, THEME_EVENT } from '@/lib/theme'

/*
 * 手绘记号 —— 用一支笔在**真元素**上标出"这一步你做到了"。
 *
 * 全站的手绘有两支笔，分工是清楚的：
 *   · `lib/sketch.ts`（roughjs）：自己算坐标、把 path 交给 Vue 去渲染，图表与门户地图用它；
 *   · 这里（rough-notation）：贴着真元素落笔（"圈住这一枚""划掉这一句"），
 *     形状由它量元素的包围盒自己算 —— 人手写这些坐标没有意义。
 *
 * 它有三个脾气，都收在这一处，免得每个消费方各踩一遍：
 *   · 颜色：它把颜色直接写成 SVG 的 stroke，**不认 CSS 变量** —— 令牌必须由 JS 取已解析的值再递进去；
 *   · 换皮肤：递进去的是取那一刻的字面量，令牌变了它不会自己跟，只能**重画**；
 *   · 卸载：它把 SVG 插在元素**旁边**的 DOM 里（不是画在元素身上），不 remove() 就留在那儿。
 */

/** 包只导出 annotate / annotationGroup，类型直接用它的返回值推（与 PortalView 同一口径） */
type RoughAnnotation = ReturnType<typeof annotate>

/** 我们真正会用的几笔：圈住（circle）、划掉（strike-through）、打叉（crossed-off） */
export type InkShape = 'circle' | 'strike-through' | 'crossed-off'

export interface InkMarkOptions {
  /**
   * 此刻该有记号的那几个元素 —— 每次重画都**重新取一次**。
   *
   * 返回空数组 = 这一刻没有该标记的东西（没解锁的那几枚、还没勾掉的那一条）。
   * 重取而不是把元素存下来，是因为列表会重排：Vue 换掉节点之后，
   * 记在旧节点上的位置就不作数了。
   */
  targets: () => HTMLElement[]
  shape: InkShape
  /** 用哪支笔：令牌名。颜色只能从令牌读（见文件头） */
  token: string
  /** 令牌读不到时的兜底色 —— 全站只有 JS 里允许出现这个值，样式表里一个色值都不许写 */
  fallback: string
  strokeWidth?: number
  /** 记号离元素多远：圈用它落在外面，划掉不用（划在中线上） */
  padding?: number
  /** 画几笔。1 = 一笔划掉 */
  iterations?: number
  /**
   * 折行的元素：一行画一笔，而不是在整块的包围盒上横一道 ——
   * 两行的句子被一道线斜着横穿，看着像划错了地方。
   */
  multiline?: boolean
  animationDuration?: number
}

export function useInkMark(options: InkMarkOptions) {
  /** 正画着的记号。重画前先全部摘掉，否则每换一次皮肤就多留一层 SVG */
  let drawn: RoughAnnotation[] = []

  const reduced = () =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  /** 令牌的已解析值（rough-notation 拿去生成 SVG，读不了 var()） */
  function readToken(name: string, fallback: string) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return value || fallback
  }

  function clear() {
    for (const mark of drawn) mark.remove()
    drawn = []
  }

  function redraw() {
    clear()
    /* 令牌取一次就够：一次重画里所有记号用的是同一支笔 */
    const color = readToken(options.token, options.fallback)
    for (const el of options.targets()) {
      /*
       * 元素还没挂进文档就画不了：annotate() 是当场把 SVG 插到它旁边的，
       * 插不进去（没有 parentElement）它会停在 "unattached"，之后 show() 静默地什么都不做 ——
       * 也就是说，这里放过去就是一个"什么也没发生"的记号。
       */
      if (!el.isConnected) continue
      const mark = annotate(el, {
        type: options.shape,
        color,
        strokeWidth: options.strokeWidth ?? 2.2,
        padding: options.padding ?? 5,
        iterations: options.iterations ?? 1,
        multiline: options.multiline,
        /*
         * 降低动效：直接给终态。
         * animate: false 时 show() 一次把笔画完整落成，不做那段落笔动画 ——
         * 记号说的是"这件事成了"，那是个**结果**，不该被一条系统偏好省掉；
         * 省掉的只是它出现的过程。
         */
        animate: !reduced(),
        animationDuration: options.animationDuration ?? 620,
      })
      mark.show()
      drawn.push(mark)
    }
  }

  /*
   * 换皮肤 / 换外观都要重画：rough-notation 拿的是取那一刻的**字面量**，令牌变了它不会跟。
   *
   * 两条事件都听，是因为会挪动记号的不止配色那一条轴：组件轴换密度、排版轴换字号，
   * 都会让那一行整体位移，而元素自身尺寸没变时它的 ResizeObserver 不会响。
   * 配色轴会**同时**抛这两条，所以这里并到一个微任务里 —— 否则一次换肤要重画两遍。
   */
  let queued = false
  function onLookChanged() {
    if (queued) return
    queued = true
    queueMicrotask(() => {
      queued = false
      redraw()
    })
  }

  onMounted(() => {
    document.addEventListener(LOOK_EVENT, onLookChanged)
    document.addEventListener(THEME_EVENT, onLookChanged)
    redraw()
  })

  onBeforeUnmount(() => {
    document.removeEventListener(LOOK_EVENT, onLookChanged)
    document.removeEventListener(THEME_EVENT, onLookChanged)
    // SVG 是插在页面里的真节点：不摘掉，组件没了它还留在那儿
    clear()
  })

  return { redraw }
}
