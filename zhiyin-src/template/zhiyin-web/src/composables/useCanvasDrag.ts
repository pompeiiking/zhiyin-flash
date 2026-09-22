import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/*
 * 画布拖拽 —— 平铺版。
 *
 * 平铺布局里没有"把窗口放在任意坐标"这回事（那会破坏自动铺满）。
 * 所以拖动改成了平铺窗口管理器的语义：**把这一块挪到另一块的位置上去**。
 *
 *   拎起来  块从网格里抽出来（其余块立刻铺满它让出的空间），跟着指针走
 *   拖动中  指针底下的那块会亮起虚线浮标 —— 告诉你"松手就和它换位"
 *   松手    换位 → 布局重算 → Flip 把移动的过程补成动画
 *   原地松  它会用 CSS 过渡滑回自己的位置，什么都没发生
 *
 * 位移只用元素自己的内联 transform，且一定会被清掉：
 * 不用 gsap 做拖动与落位，因为 gsap 缓存里的 x/y 一旦被打断就会被重新写回元素上，
 * 让块"布局在家、看起来在别处"。
 */

export interface DragHooks {
  /** 布局即将改变（块被拎起来 / 要换位） */
  before: () => void
  /** 布局已改变，去做补位动画 */
  after: () => void
  /** 松手：把 from 挪到 to 的位置上（由外层重排，布局引擎自会重算尺寸） */
  reorder: (from: string, to: string) => void
}

/** 走够这么多像素才算"拖"，否则只当是一次点击 */
const DRAG_THRESHOLD = 4
/** 落位动画时长，与 CSS 里 .settling 的 transition 保持一致 */
const SETTLE_MS = 620

export function useCanvasDrag(canvas: Ref<HTMLElement | null>, hooks: DragHooks) {
  let active: HTMLElement | null = null
  let pointerId: number | null = null
  let ghost: HTMLElement | null = null
  let observer: MutationObserver | null = null

  /** 拎在手上时它当前的位置（相对画布左上角） */
  let posX = 0
  let posY = 0

  let rafId = 0
  let settleTimer = 0
  let moved = false
  let suppressClick = false
  let isPinned = false
  let startClientX = 0
  let startClientY = 0
  /** 指针最新位置：pointermove 只写这两个值，落点计算留给每帧的 tick */
  let pointerX = 0
  let pointerY = 0
  /* 拖起来时缓存一次画布矩形：拖动期间它不会变，之后每步都不用再读布局 */
  let canvasRect: DOMRect | null = null
  /** 上一次指针位置：用来算增量 */
  let lastMoveX = 0
  let lastMoveY = 0
  let busyUntil = 0
  /** 指针底下是哪一块 —— 松手就和它换位 */
  let targetId: string | null = null

  const blockEl = () => canvas.value

  const reduced = () =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  /** 清掉拖动期间写在元素上的东西，只留 --tilt（Vue 绑的倾角） */
  function clean(el: HTMLElement) {
    const tilt = el.style.getPropertyValue('--tilt')
    const area = el.style.gridArea
    el.style.cssText = ''
    if (tilt) el.style.setProperty('--tilt', tilt)
    // grid-area 是布局引擎写的，不能跟着一起清掉
    if (area) el.style.gridArea = area
  }

  function ensureGhost() {
    const el = blockEl()!
    if (ghost && ghost.parentElement === el) return ghost
    ghost = document.createElement('div')
    ghost.className = 'snap-ghost'
    el.appendChild(ghost)
    return ghost
  }

  function showGhost(rect: { x: number; y: number; w: number; h: number } | null) {
    const g = ensureGhost()
    if (!rect) {
      g.style.opacity = '0'
      g.style.width = '0'
      g.style.height = '0'
      g.style.transform = 'translate3d(0, 0, 0)'
      return
    }
    g.style.transform = `translate3d(${rect.x}px, ${rect.y}px, 0)`
    g.style.width = `${rect.w}px`
    g.style.height = `${rect.h}px`
    g.style.opacity = '1'
  }

  /**
   * **1:1 跟随** —— 拖拽时这块是"粘在指针上"的，不是"被牵着走"。
   *
   * 这里原来是 `pos += (target - pos) * 0.28` 的阻尼跟随，理由是"有重量感"。
   * 那是把两件事搞混了：**跟手**是拖拽的全部意义，**重量感**该由落位动画去表达。
   * 0.28 意味着块永远落后指针十几帧（约 170ms），手一快它就明显掉在后面 ——
   * 用起来的感受不是"重"，是"不听话"。
   *
   * 循环仍然保留：pointermove 触发频率高于帧率，用它把写样式收在一帧一次，
   * 避免同一帧里反复写 transform 引起无谓的重排。
   */
  /*
   * 拖动的主循环：**一帧只做一次布局读**。
   *
   * 之前是每个 pointermove 都读一次画布矩形 + 一次 hover 命中测试
   * （那些 offsetLeft/offsetTop 也是布局属性，一样会强制同步布局）。
   * 高刷鼠标一秒能来 100+ 个 pointermove，于是每帧要同步布局两三次 ——
   * 这就是"拖起来很卡、位置还偶尔跳"的来源。现在读的部分全部收进这里。
   */
  /*
   * 这个循环只做"读"的部分：命中测试 + 浮标。
   * transform 的写入已经提前到 pointermove 里（见下面 onPointerMove），
   * 因为"跟手"要求的是**最新的指针位置**，而不是"这一帧开始时采到的位置" ——
   * 高刷鼠标一秒能来 100+ 个 pointermove，把它们压到帧节奏上就会明显滞后。
   */
  function tick() {
    if (!active) return
    const cr = canvasRect
    if (cr) {
      const over = under(pointerX, pointerY, cr)
      targetId = over?.el.dataset.block ?? null
      showGhost(over)
    }
    rafId = requestAnimationFrame(tick)
  }

  /**
   * 指针现在压在谁身上。
   * 用 offsetLeft/Top 而不是 getBoundingClientRect：补位动画期间其它块带着 transform，
   * 读到的会是动画中途的瞬时矩形。
   */
  /*
   * 传入画布矩形，而不是每次自己读一遍。
   * 拖动时这一帧已经读过一次了 —— 再读一次就是多一次强制同步布局。
   */
  function under(
    cx: number,
    cy: number,
    known?: DOMRect,
  ): { el: HTMLElement; x: number; y: number; w: number; h: number } | null {
    const cv = blockEl()
    if (!cv) return null
    const cRect = known ?? cv.getBoundingClientRect()
    const px = cx - cRect.left
    const py = cy - cRect.top
    let best: { el: HTMLElement; x: number; y: number; w: number; h: number } | null = null
    let bestDist = Infinity
    for (const el of cv.querySelectorAll<HTMLElement>('[data-block]')) {
      if (el === active) continue
      const x = el.offsetLeft
      const y = el.offsetTop
      const w = el.offsetWidth
      const h = el.offsetHeight
      // 落在谁的范围里就是谁；都不在范围内就取最近的一个
      const inside = px >= x && px <= x + w && py >= y && py <= y + h
      const d = Math.hypot(px - (x + w / 2), py - (y + h / 2))
      if (inside) return { el, x, y, w, h }
      if (d < bestDist) {
        bestDist = d
        best = { el, x, y, w, h }
      }
    }
    // 离得最近的也必须够近，否则算"扔在空白处"，那就只是滑回原位
    return best && bestDist < 260 ? best : null
  }

  function onPointerDown(e: PointerEvent) {
    if (reduced()) return
    const el = (e.target as HTMLElement)?.closest<HTMLElement>('[data-block]')
    if (!el || !blockEl()?.contains(el)) return
    /*
     * 落在交互元素上不起拖，避免和按钮、输入框抢事件。
     * 注意要排除块自身 —— 画像块与待办块的根元素本身就是 <button>，
     * 否则按它们的空白处也拖不动。
     */
    const hit = (e.target as HTMLElement).closest<HTMLElement>(
      'button, a, input, textarea, select, [role="button"]',
    )
    if (hit && hit !== el && el.contains(hit)) return
    if (el.classList.contains('leaving')) return

    /*
     * 这里不 preventDefault：在 pointerdown 上阻止默认行为会连带阻止浏览器把焦点
     * 交给这个块，"关掉覆盖层 → 焦点回到来源块"就无从谈起。
     * 拖动期间的文字选中改用 user-select 关掉（见 .canvas.arming）。
     */
    moved = false
    isPinned = false
    targetId = null
    active = el
    pointerId = e.pointerId
    startClientX = e.clientX
    startClientY = e.clientY
    pointerX = e.clientX
    pointerY = e.clientY
    el.setPointerCapture?.(e.pointerId)
    blockEl()!.classList.add('arming')

    const cRect = blockEl()!.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    /* 存下来：拖动期间每步都用它，不再重复读布局（增量算法本身不再需要抓取偏移） */
    canvasRect = cRect
    posX = r.left - cRect.left
    posY = r.top - cRect.top
    /* 增量基准：从"这一刻的指针位置"开始累加 */
    lastMoveX = e.clientX
    lastMoveY = e.clientY

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  /** 走够距离，真的拎起来：冻结尺寸、抽离网格，其余块立刻铺满它让出的位置 */
  function lift(e: PointerEvent) {
    const el = active
    if (!el) return
    const cRect = blockEl()!.getBoundingClientRect()
    canvasRect = cRect
    const r = el.getBoundingClientRect()
    posX = r.left - cRect.left
    posY = r.top - cRect.top
    lastMoveX = e.clientX
    lastMoveY = e.clientY

    hooks.before()
    el.classList.add('pinned', 'dragging')
    el.style.width = `${r.width}px`
    el.style.height = `${r.height}px`
    el.style.transform = `translate3d(${posX}px, ${posY}px, 0)`
    isPinned = true

    requestAnimationFrame(() => {
      hooks.after()
      rafId = requestAnimationFrame(tick)
    })
  }

  function onPointerMove(e: PointerEvent) {
    if (!active || e.pointerId !== pointerId) return
    if (!isPinned) {
      if (Math.hypot(e.clientX - startClientX, e.clientY - startClientY) < DRAG_THRESHOLD) return
      lift(e)
    }
    /*
     * 这里只记坐标，不读布局、不写样式。
     * 真正的落点计算与浮标更新在 tick 里（每帧一次）。
     */
    if (Math.abs(e.clientX - pointerX) > 3 || Math.abs(e.clientY - pointerY) > 3) moved = true
    pointerX = e.clientX
    pointerY = e.clientY
    /*
     * 立刻跟手：每一步都直接用最新指针位置写 transform，不经过帧循环。
     * 画布矩形用拖起来时缓存的那一份（拖动期间不会变），所以这里没有任何布局读。
     */
    /*
     * 用**增量**而不是绝对坐标。
     * 绝对算法 = 指针位置 − 画布位置 − 抓取偏移，只要这三者中任何一个的坐标系
     * 和元素自己的坐标系差一个比例（父级有 scale / zoom / 布局在拖中被影响），
     * 误差就会**每帧累加**，表现就是"越拖离指针越远"。
     * 增量算法只问"指针这一下走了多远"，与坐标系无关，天生不会累积。
     */
    if (active) {
      posX += e.clientX - lastMoveX
      posY += e.clientY - lastMoveY
      active.style.transform = `translate3d(${posX}px, ${posY}px, 0)`
    }
    lastMoveX = e.clientX
    lastMoveY = e.clientY
  }

  function onPointerUp(e: PointerEvent) {
    if (!active || e.pointerId !== pointerId) return
    const el = active

    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
    blockEl()?.classList.remove('arming')

    // 只是点了一下：什么都没拎起来，什么都不用还原（点击照常往下走）
    if (!isPinned) {
      active = null
      pointerId = null
      return
    }

    cancelAnimationFrame(rafId)
    showGhost(null)
    el.classList.remove('dragging')
    canvasRect = null
      /* 记下"刚放下的是谁"，落位动画用它决定只给谁做回弹 */
      droppedEl = el

    // 松手那一刻它视觉上在哪儿
    const before = el.getBoundingClientRect()

    /*
     * 先回网格：摘掉"拎在手上"的状态、清掉冻结尺寸与位移。
     * 此刻它在布局里已经回到自己的格子，但视觉上还停在指针那儿 ——
     * 所以补一段 transform 把它"按"在原地，再交给 Flip 去动画。
     */
    el.classList.remove('pinned')
    clean(el)
    const after = el.getBoundingClientRect()
    const dx = before.left - after.left
    const dy = before.top - after.top

    const id = el.dataset.block ?? ''
    if (targetId && targetId !== id) {
      // 换位：把这块挪到目标的位置上，布局重算、其余块跟着变
      el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`
      hooks.reorder(id, targetId)
      busyUntil = Date.now() + 760
    } else if (!reduced() && (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5)) {
      // 扔在空白处：滑回自己原来的位置
      el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`
      el.classList.add('settling')
      requestAnimationFrame(() => {
        el.style.transform = ''
      })
      window.clearTimeout(settleTimer)
      const done = () => {
        window.clearTimeout(settleTimer)
        el.removeEventListener('transitionend', done)
        el.classList.remove('settling')
        clean(el)
      }
      el.addEventListener('transitionend', done)
      settleTimer = window.setTimeout(done, SETTLE_MS + 200)
      busyUntil = Date.now() + SETTLE_MS + 160
    }

    isPinned = false
    active = null
    pointerId = null
    targetId = null

    // 拖过之后不要再触发"点击打开"那一下
    if (moved) {
      suppressClick = true
      window.setTimeout(() => (suppressClick = false), 0)
    }
  }

  /** 拖动结束的那一下 click 要吞掉，否则会顺带把覆盖层打开 */
  function onClickCapture(e: MouseEvent) {
    if (!suppressClick) return
    e.stopPropagation()
    e.preventDefault()
  }

  /** 双击：把自己挪到第一位（最想要空间的那块） */
  function onDoubleClick(e: MouseEvent) {
    const el = (e.target as HTMLElement)?.closest<HTMLElement>('[data-block]')
    if (!el) return
    if ((e.target as HTMLElement).closest('button, a, input, textarea, select, [role="button"]')) return
    const first = blockEl()?.querySelector<HTMLElement>('[data-block]')
    if (!first || first === el) return
    hooks.before()
    hooks.reorder(el.dataset.block ?? '', first.dataset.block ?? '')
    requestAnimationFrame(() => hooks.after())
  }

  /** 窗口尺寸一变，格子尺寸就全变了 —— 布局引擎会重算，这里只要清干净拖动残留 */
  function releaseAll() {
    let touched = false
    for (const el of blockEl()?.querySelectorAll<HTMLElement>('[data-block]') ?? []) {
      if (el.classList.contains('pinned') || el.classList.contains('settling') || el.style.transform) {
        el.classList.remove('pinned', 'dragging', 'settling')
        clean(el)
        touched = true
      }
    }
    if (touched) {
      hooks.before()
      requestAnimationFrame(() => hooks.after())
    }
  }

  /**
   * 块的进 / 出 —— 平铺靠这个自动重算：少一块，剩下的立刻长大。
   * 这里只负责在结构变化后接上补位动画。
   */
  function onDomChange(records: MutationRecord[]) {
    const structural = records.some((m) =>
      [...m.addedNodes, ...m.removedNodes].some(
        (n) => n.nodeType === 1 && (n as HTMLElement).hasAttribute?.('data-block'),
      ),
    )
    if (!structural) return
    requestAnimationFrame(() => hooks.after())
  }

  onMounted(() => {
    blockEl()?.addEventListener('pointerdown', onPointerDown)
    blockEl()?.addEventListener('dblclick', onDoubleClick)
    blockEl()?.addEventListener('click', onClickCapture, true)
    window.addEventListener('resize', releaseAll)
    observer = new MutationObserver(onDomChange)
    observer.observe(blockEl()!, { childList: true })
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
    blockEl()?.removeEventListener('pointerdown', onPointerDown)
    blockEl()?.removeEventListener('dblclick', onDoubleClick)
    blockEl()?.removeEventListener('click', onClickCapture, true)
    window.removeEventListener('resize', releaseAll)
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
    cancelAnimationFrame(rafId)
    window.clearTimeout(settleTimer)
    ghost?.remove()
  })

  /**
   * 正在拖 / 正在落位。
   * 补位动画（Flip）和拖动都会写同一批 transform，两套叠在一起块会停在中间态。
   */
  const isBusy = () => isPinned || Date.now() < busyUntil

  /**
   * 收尾清扫：把"上一次拖动没走完"的残渣擦掉。
   * 冻结的 width/height 和拖动写的 transform 只有拖动会写；
   * 所以一个块既没被拎着、也没在落位、gsap 也没在动它，身上却挂着这些，就是残渣。
   */
  function sweep() {
    for (const el of blockEl()?.querySelectorAll<HTMLElement>('[data-block]') ?? []) {
      if (el.classList.contains('pinned') || el.classList.contains('settling')) continue
      if (!el.style.width && !el.style.height && !el.style.transform) continue
      clean(el)
    }
  }

  let sweepTimer = 0
  onMounted(() => {
    sweepTimer = window.setInterval(sweep, 1000)
  })
  onBeforeUnmount(() => window.clearInterval(sweepTimer))

  /** 刚放下的那一块：落位动画只对它做"呼吸"，不必全场回弹 */
  let droppedEl: HTMLElement | null = null
  const markDropped = (el: HTMLElement | null) => (droppedEl = el)

  return { releaseAll, isBusy, lastDragged: () => droppedEl, markDropped }
}
