import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/*
 * 画布拖拽 —— 平铺版。
 *
 * 平铺布局里没有"把窗口放在任意坐标"这回事（那会破坏自动铺满）。
 * 所以拖动改成了平铺窗口管理器的语义：**把这一块挪到另一块的位置上去**。
 *
 *   拎起来  块从网格里抽出来（其余块立刻铺满它让出的空间），跟着指针走
 *   拖动中  指针底下的那块会亮起虚线浮标 —— 告诉你"松手就和它换位"
 *   松手    换位 → 等新格位写进 DOM → 把位移补回"松手时指针在的地方" → 滑进格位
 *   原地松  它会用 CSS 过渡滑回自己的位置，什么都没发生
 *
 * 位移只用元素自己的内联 transform，且一定会被清掉：
 * 不用 gsap 做拖动与落位，因为 gsap 缓存里的 x/y 一旦被打断就会被重新写回元素上，
 * 让块"布局在家、看起来在别处"。同理，补位动画（Flip）的目标里必须排掉手上这一块 ——
 * 它在动画结束时会对自己那批目标 clearProps: 'transform'，那一下会把拖动写的位移一起擦掉，
 * 卡片会突然掉回画布左上角，直到下一次 pointermove 才回来。
 *
 * 坐标只有一套：**画布内的布局坐标**（也就是 offsetLeft/offsetTop 那一套）。
 * 预览位置由指针**增量**累加出来 —— 增量与坐标系无关，父级带 scale/zoom 也不会越拖越偏；
 * 命中检测与落位补偿都读 offsetLeft/offsetTop —— 它们不受 transform 影响，
 * 不会读到别的块落位动画中途的瞬时矩形。
 */

export interface DragHooks {
  /** 布局即将改变（块被拎起来 / 要换位） */
  before: () => void
  /** 布局已改变，去做补位动画 */
  after: () => void
  /**
   * 松手：把 from 挪到 to 的位置上（由外层重排，布局引擎自会重算尺寸）。
   * 返回 false = 这次换位并没有改动顺序（顺序里找不到其中一块）：
   * 那就不会有下一次渲染，调用方得当场收尾，不能等一个永远不来的更新。
   */
  reorder: (from: string, to: string) => boolean
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

  /** 拎在手上时它当前的位置（相对画布左上角，与 offsetLeft/offsetTop 是同一套坐标） */
  let posX = 0
  let posY = 0
  /**
   * 拎起来那一刻它在**画布坐标**里的位置。
   *
   * 拖动中的 `posX/posY` 只是**增量**（见 lift 的注释），而收尾时要和
   * `offsetLeft/offsetTop`（画布坐标）比较，所以那一个绝对值单独记一份。
   */
  let originX = 0
  let originY = 0

  let rafId = 0
  let moved = false
  let suppressClick = false
  let isPinned = false
  let startClientX = 0
  let startClientY = 0
  /** 指针最新位置：pointermove 只写这两个值，落点计算留给每帧的 tick */
  let pointerX = 0
  let pointerY = 0
  /** 上一次指针位置：用来算增量 */
  let lastMoveX = 0
  let lastMoveY = 0
  /** 指针底下是哪一块 —— 松手就和它换位 */
  let targetId: string | null = null

  /**
   * 松手之后还等着交还网格的那一块。
   *
   * 换位的新格位要等外层（Vue）下一次渲染才写进 DOM，拖动引擎看不到那一刻；
   * 所以先记下"松手时它看起来在哪"，等外层说"布局落定了"（finishDrop）再收尾。
   * 提前收尾的话，滑向的是**换位之前**的旧格位 —— 等新格位一到，卡片还得再跳一次，
   * 用户看到的就是"松开的位置和预览位置对不上"。
   */
  let pending: { el: HTMLElement; x: number; y: number } | null = null

  /**
   * 每个块自己的落位兜底定时器（key = 块）。
   *
   * 用一个全局变量会出事：连着在两块之间拖时，后一次的兜底会把前一次的定时器顶掉，
   * 于是前一块可能永远留着 .settling —— 它从此不再进补位动画（flowEls 会把它排除）。
   */
  const settleTimers = new Map<HTMLElement, number>()

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
    const cv = blockEl()
    if (cv) {
      /*
       * 画布矩形每帧现读一次，不再用"拖动开始时缓存的那一份"。
       *
       * 指针坐标必须先换算成画布内坐标，才能和 offsetLeft/offsetTop 相比 ——
       * 两者要么都新鲜，要么都不新鲜。缓存下来的那份只要画布挪过（窗口尺寸变了、
       * 外层留白变了），换算就整体偏掉，表现是"卡片跟手是对的，虚线浮标却亮在隔壁"。
       * 一帧一次和下面读 offsetLeft 是同一笔开销，不会多出一次强制同步布局。
       */
      const cr = cv.getBoundingClientRect()
      const over = under(pointerX, pointerY, cr)
      targetId = over?.el.dataset.block ?? null
      showGhost(over)
    }
    rafId = requestAnimationFrame(tick)
  }

  /**
   * 指针现在压在谁身上。
   * 用 offsetLeft/Top 而不是 getBoundingClientRect：补位动画期间其它块带着 transform，
   * 读到的会是动画中途的瞬时矩形 —— 命中的是"正在往哪儿去的路上"，不是它的格位。
   * 画布矩形由调用方传进来：这一帧已经读过一次了，再读一次就是多一次强制同步布局。
   */
  function under(
    cx: number,
    cy: number,
    cRect: DOMRect,
  ): { el: HTMLElement; x: number; y: number; w: number; h: number } | null {
    const cv = blockEl()
    if (!cv) return null
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

    if (active) {
      /*
       * 到这一步说明"用户真的又在按一块要拖的块了"，但上一次拖动还没收场。
       * 状态只有一份（active / posX / pending），被第二个指针覆盖之后，
       * 前一块就再没有人给它收尾：它会一直挂着 .pinned（绝对定位、脱离网格），
       * 表现是"有一块卡在画布左上角不动、还压着别的块"，而 sweep 也救不了它
       * （sweep 正是跳过 .pinned —— 那是给"正在拖"留的）。
       *
       * 非主指针（多指触摸的第二根手指）直接不接。
       */
      if (!e.isPrimary) return
      /* 主指针又按了一次：上一次拖动多半是没等到 pointerup 就断了，先把它交还网格 */
      const stuck = active
      endDrag()
      stuck.classList.remove('pinned', 'dragging', 'settling')
      clean(stuck)
    }

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
    /*
     * 这里**不**算预览位置、也不记增量基准：真正拎起来的那一刻（lift）才以元素当时的
     * 实际位置为准 —— 按下与拎起来之间指针可能已经走了几像素，提前算出来的基准只会是错的。
     *
     * 也不去动**按下的这一块自己**上一次落位的收尾（.settling 那一程）：只是按下、还没拎起来时，
     * 那点残局交给它自己的 transitionend / 兜底定时器收干净就好。在这里把定时器掐掉，
     * 反而会留下一个永远摘不掉的 .settling —— 从此这块再也不会进补位动画
     * （flowEls 会一直把它排除在外）。真正要接管它的是 lift()，那里会把这个元素名下的收尾作废。
     */

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  /** 走够距离，真的拎起来：冻结尺寸、抽离网格，其余块立刻铺满它让出的位置 */
  function lift(e: PointerEvent) {
    const el = active
    const cv = blockEl()
    if (!el || !cv) return
    const cRect = cv.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    /*
     * 预览位移从 **0** 起算，而不是从"这块到画布左缘的距离"起算。
     *
     * 原因在 `.pinned` 的定位：它是**绝对定位的网格项**，而按 CSS 规范，
     * 绝对定位的网格项其包含块是**它自己的网格区域**，不是网格容器的 padding box。
     * 也就是说 `left:0; top:0` 已经把它放回了原处，transform 只需要承担"指针走了多少"。
     * 把静态偏移也算进去，它就会被算两次 —— 实测：指针走 300px，卡片走 743px（2.48 倍，
     * 而这块到画布左缘正是 468px），越拖越离谱；这也解释了松手时"位置对不上"。
     * 真正需要那个绝对值的只有 settle()，所以单记一份 origin，不动它的换算。
     */
    originX = r.left - cRect.left
    originY = r.top - cRect.top
    /*
     * 已经走过的那一段要算进来（从按下点算起）：拎起来之前指针至少走了 DRAG_THRESHOLD，
     * 快的操作里第一帧就能走十几到几十像素。从 0 起算的话，那一段会被永远吃掉 ——
     * 卡片此后一直比指针少这么一截（实测少 25px，一步的距离）。
     */
    posX = e.clientX - startClientX
    posY = e.clientY - startClientY
    /* 增量基准：从"这一刻的指针位置"开始累加 */
    lastMoveX = e.clientX
    lastMoveY = e.clientY

    /*
     * 先捕"拎起来之前"的那一帧，再把它抽出网格 —— 顺序反了，其余块的起点就是错的
     * （那时读到的是"已经补好位"的位置，于是松手那一下会看到它们先跳回来再补出去）。
     *
     * 也正因为捕帧必须发生在抽离之前，这一刻它身上还没有 .pinned：
     * 外层要另想办法把它从补位动画的目标里排掉（见 ConsoleView 的 flowEls）。
     */
    hooks.before()

    /*
     * 上一次落位那一程（.settling 的 CSS 过渡）如果还没走完，就地截断：
     * 下面要给它套上 .dragging（transition: none）并自己接管 transform，
     * 留着 .settling 会让每一次 pointermove 的写入都被那条 620ms 过渡再滤一遍。
     *
     * 顺手把它名下的收尾也作废（清定时器 + 抹掉登记）：那次收尾要是晚一步回来，
     * 会对一个正在被拖着走的元素执行 clean()，把这一帧的位移擦掉。
     */
    el.classList.remove('settling')
    const stale = settleTimers.get(el)
    if (stale) {
      window.clearTimeout(stale)
      settleTimers.delete(el)
    }
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
     * **立刻跟手**：每一步都直接用最新指针位置写 transform，不经过帧循环。
     * 这里没有任何布局读 —— 画布矩形和格位都在别的时刻读过了。
     *
     * 前提是 CSS 那边在 .pinned/.dragging 上关掉了 transform 过渡（ConsoleView 的样式里写着为什么）：
     * 只要还留着过渡，这一行就不是"跟手"，而是"每一步往指针的方向追掉三成" ——
     * 指针一直走，它就永远追不上。
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

  /**
   * 收尾：把手上这块交还给网格，并从"松手时它看起来在哪"滑到它的最终格位。
   *
   * 三步，顺序一步都不能换：
   *   1. 摘掉 .pinned 交还网格 —— 进了网格，它才有**最终格位**；
   *   2. 用 offsetLeft/offsetTop 量这个格位，把差值补成"松手时指针在的地方"。
   *      这两个属性**与 transform 无关**，量到多少就是多少。
   *      换成 getBoundingClientRect 就含糊了：那一刻"已交出网格"这件事是不是已经算进布局、
   *      240ms 的过渡有没有起步、起步了走到第几帧，取决于这次读有没有触发样式重算 ——
   *      量到的可能是旧位置，也可能是过渡半路的值，补偿于是算错，
   *      卡片根本没被按在原地，交还网格的那一下就是"松手跳一下"；
   *   3. 量完、补偿完，才打开 .settling 的过渡并清掉位移：卡片从预览位置滑进格位。
   *
   * .dragging 一直留到第 3 步：它身上是 transition: none，是"量格位 + 写补偿"这两步
   * 不被过渡插一脚的保证 —— 第 2 步那次强制布局读本身就是一次样式重算，
   * 过渡要是这时候已经开起来，浏览器会把"补偿之前"的位置记成过渡起点。
   */
  function settle(el: HTMLElement, x: number, y: number) {
    el.classList.remove('pinned')
    clean(el)

    const dx = x - el.offsetLeft
    const dy = y - el.offsetTop
    el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`
    // 强制提交这一帧（此时仍是 transition: none，读到的一定是我们刚写的值）
    void el.offsetWidth

    el.classList.remove('dragging')
    el.classList.add('settling')
    el.style.transform = ''

    /*
     * transitionend 未必来：块被关掉、标签页切走、下一个人把它藏起来，都不会有那一下。
     * 所以两边都挂：事件到了立刻收，没到就由定时器兜底。
     */
    const prev = settleTimers.get(el)
    if (prev) window.clearTimeout(prev)
    const timer = window.setTimeout(done, SETTLE_MS + 200)
    function done() {
      el.removeEventListener('transitionend', done)
      // 之后又松过一次手（或者又把它拎起来了）：这次收尾已经作废，别去动它
      if (settleTimers.get(el) !== timer) return
      settleTimers.delete(el)
      window.clearTimeout(timer)
      el.classList.remove('settling')
      clean(el)
    }
    settleTimers.set(el, timer)
    el.addEventListener('transitionend', done)
  }

  /**
   * 换位的收尾。由外层在"新格位已经写进 DOM、动画还没开始"的那一刻调
   * （见 ConsoleView 的 playFlip 第一行）—— 只有外层知道那一轮渲染什么时候落定。
   */
  function finishDrop() {
    const p = pending
    if (!p) return
    pending = null
    settle(p.el, p.x, p.y)
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

    /*
     * isPinned 先落回 false，但 DOM 上的 .pinned 先留着。
     *
     * 外层的补位动画靠"这块还在不在网格流里"决定谁参与 Flip，而这一轮 Vue 更新马上就要发生：
     * 它要在这一刻把**其余块**（停在这块让出的空间里的位置）捕下来当起点。
     * 手上这块则必须一直待在指针那儿 —— 直到新格位落定（finishDrop）才交还网格。
     * 早交还一步，它会先跳回旧格位、再滑向新格位，就是"松手位置与预览位置对不上"。
     */
    isPinned = false

    // 预览位置换算回**画布坐标**（settle 里要和 offsetLeft/offsetTop 比）
    const x = originX + posX
    const y = originY + posY
    const id = el.dataset.block ?? ''
    /* 记下"刚放下的是谁"，落位动画用它决定只给谁做回弹 */
    droppedEl = el

    if (targetId && targetId !== id && hooks.reorder(id, targetId)) {
      // 换位：格位要等外层的下一次渲染，现在收尾只会滑向旧格位
      pending = { el, x, y }
      /*
       * 兜底：万一那一轮更新没有发生（顺序里其实没有这一块、组件正在卸载），
       * 不能让卡片永远停在"拎在手上"的状态 —— 下一帧按当时的格位收尾。
       * 正常路径上 playFlip 会先一步调 finishDrop，这里就空转了。
       */
      requestAnimationFrame(() => finishDrop())
    } else {
      /*
       * 没换位：布局不会变，当场收尾。
       *
       * 但其余块还停在这块让出的空间里，所以要**先捕一帧、再交还网格**，
       * 让它们滑回原位 —— 否则松手那一下七块一起瞬移回去（"松手就跳"）。
       *
       * 这里不用 rAF 推迟 after()：那样中间会多画一帧"其余块已经跳回原位"的画面，
       * 下一帧再被补位动画拽回起点，看起来是闪一下。捕帧、交还、补位要在同一帧里做完。
       */
      hooks.before()
      settle(el, x, y)
      hooks.after()
    }

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

  /**
   * 立刻结束这一次拖动：不落位、不补位，只把状态与监听清干净。
   */
  function endDrag() {
    if (!active && !isPinned && !pending) return
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
    cancelAnimationFrame(rafId)
    showGhost(null)
    blockEl()?.classList.remove('arming')
    pending = null
    isPinned = false
    active = null
    pointerId = null
    targetId = null
  }

  /** 窗口尺寸一变，格子尺寸就全变了 —— 布局引擎会重算，这里只要清干净拖动残留 */
  function releaseAll() {
    /*
     * 正在拖的那一次也要一并作废。
     * 只清样式、不清状态的话，主循环、window 上的监听、isPinned 都还留在原地，
     * 下一次 pointermove 会继续往一个已经回到网格里的元素上写位移（"松手后块乱跑/重叠"）。
     */
    endDrag()

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
    endDrag()
    for (const timer of settleTimers.values()) window.clearTimeout(timer)
    settleTimers.clear()
    ghost?.remove()
  })

  /**
   * 正在拖。
   * 补位动画（Flip）和拖动都会写同一批 transform，两套叠在一起块会停在中间态，
   * 所以拖动期间外层的补位动画不参与（见 ConsoleView 的 captureLayout）。
   * 落位那一程不必算进来：收尾走的是一块自己的 CSS 过渡，它已经被排除在 Flip 目标之外。
   */
  const isBusy = () => isPinned

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

  return {
    releaseAll,
    isBusy,
    lastDragged: () => droppedEl,
    markDropped,
    /** 手上正拎着的那一块 —— 外层靠它把这块从补位动画的目标里排掉 */
    activeBlock: () => active,
    /** 外层在"新格位已落定"的那一刻调，见 finishDrop */
    finishDrop,
  }
}
