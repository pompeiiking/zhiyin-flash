<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, onBeforeUpdate, onUpdated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import gsap from 'gsap'
import { Flip } from 'gsap/Flip'
import Bubble from '@/components/console/Bubble.vue'
import PortraitBubble from '@/components/console/PortraitBubble.vue'
import CalendarBubble from '@/components/console/CalendarBubble.vue'
import CalendarOverlay from '@/components/console/CalendarOverlay.vue'
import TodoBubble from '@/components/console/TodoBubble.vue'
import PeopleBubble from '@/components/console/PeopleBubble.vue'
import ReviewBubble from '@/components/console/ReviewBubble.vue'
import AgentRail from '@/components/console/AgentRail.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import BindOverlay from '@/components/console/BindOverlay.vue'
import TimetableOverlay from '@/components/console/TimetableOverlay.vue'
import MatchOverlay from '@/components/console/MatchOverlay.vue'
import PlansOverlay from '@/components/console/PlansOverlay.vue'
import ActionOverlay from '@/components/console/ActionOverlay.vue'
import SessionsOverlay from '@/components/console/SessionsOverlay.vue'
import ReviewOverlay from '@/components/console/ReviewOverlay.vue'
import CanvasMenu, { type MenuItem } from '@/components/console/CanvasMenu.vue'
import FloatLayer from '@/components/float/FloatLayer.vue'
import TalkBubble from '@/components/console/TalkBubble.vue'
import CollectBubble from '@/components/console/CollectBubble.vue'
import CollectOverlay from '@/components/console/CollectOverlay.vue'
import EvidenceDrawer from '@/components/console/EvidenceDrawer.vue'
import PortraitOverlay from '@/components/console/PortraitOverlay.vue'
import IntelOverlay from '@/components/console/IntelOverlay.vue'
import MarketBubble from '@/components/console/MarketBubble.vue'
import TasksOverlay from '@/components/console/TasksOverlay.vue'
import BriefOverlay from '@/components/console/BriefOverlay.vue'
import AccountMenu from '@/components/auth/AccountMenu.vue'
import { useSessionStore } from '@/stores/session'
import { useCanvasDrag } from '@/composables/useCanvasDrag'
import { shouldCompact, tileLayout, type TileInput } from '@/lib/tiling'
import { track } from '@/api/client'

gsap.registerPlugin(Flip)

/**
 * 核心页 —— 一屏之内，全是浮动块。
 *
 * 关闭一块时，其余块的补位用 **GSAP Flip** 做，而不是 CSS 过渡：
 *   · Flip 同时插值「位置」和「尺寸」，所以块从 6×6 变 6×2 也会一路长过去；
 *   · 缓动用 back.out，落位时有轻微过冲再收住 —— 这是"气泡感"的来源；
 *   · 每个块错开 45ms，不是一起动，所以看起来是逐块让位而不是整排平移；
 *   · 被关掉的那块先做 220ms 的收缩淡出，让位才发生，顺序读得出来。
 *
 * 其余规则：
 *   · 每个块都能关，关掉过一会儿自己飘回来；
 *   · 细节不开在这一页：画像走三级菜单，任务走覆盖层，单条溯源走抽屉；
 *   · 五环节、阶段名这些是我们的业务概念，不出现在用户界面上。
 */
const router = useRouter()
const session = useSessionStore()

/**
 * 顶栏那个人是谁 —— 必须来自登录态（/app/bootstrap 的 identity）。
 * 品牌与身份合成一颗按钮（AccountMenu），这里只留问候语要用到的名字。
 */
const whoName = computed(() => session.identity?.nickname || '你')

const canvas = ref<HTMLElement | null>(null)
const leaving = ref<Set<string>>(new Set())

/*
 * 平铺（Hyprland 那种）：
 * 块不再各占一个固定格子，而是按**权重**去分剩下的空间。
 * 少一块，其余块自动长大；画布变小，一起缩；永远不会留洞。
 * 权重就是"这块值多少地方"：画像和待办要 3，情报/交接/复盘只配 1。
 */
const TILE_WEIGHTS: Record<string, number> = {
  portrait: 3,
  todo: 3,
  /** 跟主理说清楚一件事，和画像、待办是同一个量级 —— 它不是边角入口 */
  talk: 2.4,
  greet: 1.1,
  people: 1,
  review: 1,
  /** 采集动线优先拿空间 —— 它还差着的东西挡着后面每一件事 */
  collect: 2.4,
  timetable: 2,
  /** 日历比课表重一点：课表看的是"每周重复的课"，日历看的是"这一天有什么" */
  calendar: 2.4,
  match: 2.2,
  /** ③ 方案与 ④ 计划都是"这一段的主事" —— 和画像/待办同量级 */
  plans: 2.8,
  action: 2.8,
  /** 外部情报：一眼扫过的量，和交接/复盘同一档 */
  market: 1.6,
}

/**
 * 学信网没核验之前只放一块「核验」。
 *
 * 核验之后**不直接换成课表与匹配**：那两块吃的是课程数据，
 * 而学信网不提供课程表与成绩单（它只有学籍 / 学历 / 学位）。
 * 所以它们要等"课程源"到位才出现 —— 否则点开只会撞上一句
 * "先绑定学信网导入课程"，把没接上的线说成接上了。
 */
const BLOCK_ORDER = ['talk', 'portrait', 'todo', 'collect', 'plans', 'action', 'calendar', 'timetable', 'match', 'market', 'greet', 'people', 'review']

/** 画布用的格子数：列要 12（拖动引擎按 12 列找落点），行给细一点，切分才平滑 */
const TILE_COLS = 12
const TILE_ROWS = 12

/** 画布尺寸：切分要按像素判断哪条边长，所以得跟着窗口变 */
const canvasSize = ref({ w: 0, h: 0 })
let ro: ResizeObserver | null = null

/*
 * 窄屏是单列流，平铺不成立 —— 那时退回 CSS 媒体查询里的单列。
 *
 * 这个判断必须**在首次渲染之前**就定下来：以前它写在 onMounted 里，
 * 结果宽屏判定先跑了一遍（块都拿到了格位），挂载后又翻成窄屏，
 * 于是同一帧里发生两次完全不同的布局 —— 补位动画跟着打两遍，
 * 被打断的那次会留下残余位移，块就看起来"乱跑、互相压"。
 */
const narrowQuery = '(max-width: 900px), (max-height: 620px)'
const tiled = ref(typeof window === 'undefined' ? true : !window.matchMedia(narrowQuery).matches)

/*
 * 平铺的**顺序**就是优先级：排在前面的先分到空间。
 * 拖动不再改变坐标，而是改变这个顺序 —— 这也是平铺窗口管理器的做法。
 */
const order = ref([...BLOCK_ORDER])

/*
 * 顺序由**后端的编排策略**决定（`data/registry/layout.json` → 工作台 layout_panel）。
 *
 * 前端这份 BLOCK_ORDER 只剩一个用途：策略还没到的时候别让画布空着。
 * 拖动仍然能临时改顺序（那是用户的手动操作），刷新后回到策略给的顺序。
 */
watch(
  () => session.layout.map((b) => b.id).join(','),
  (ids: string) => {
    if (ids) order.value = ids.split(',')
  },
  { immediate: true }
)

/*
 * 空间权重来自策略；策略没覆盖到的块退回本地默认。
 *
 * 再补一条**状态**判据：同一块在不同状态下值多少地方。
 *
 * 这条不是新发明的口径 —— 注册表自己写着（`layout.json` 里 portrait 的 why）：
 * "画像是一切的底；**有内容时**它值得占最大的一块"。但 weight 是一个固定值，
 * 没有把"有内容"算进去。于是新用户打开控制台，最大的一块是一张只有三行字的
 * 空画像，而底下真正能动手的采集与日历挤在小格子里 —— 一屏里最贵的地方
 * 给了一个还没有内容的块。
 *
 * 所以这里只补半条：空着的时候按 1.4 收，有内容时按注册表给的 3。
 * 判据与各自块里的渲染条件同源（画像看 dimensions、待办看 action_panel）。
 */
const EMPTY_WEIGHT: Record<string, number> = { portrait: 1.8, todo: 2.1 }
const isEmptyBlock = (id: string) => {
  if (id === 'portrait') return !(session.profile?.dimensions.length)
  if (id === 'todo') return !session.wsPanels?.action
  return false
}
const weightOf = (id: string) => {
  const base = session.layout.find((b) => b.id === id)?.weight ?? TILE_WEIGHTS[id] ?? 1
  return isEmptyBlock(id) ? (EMPTY_WEIGHT[id] ?? base) : base
}

/**
 * 画布上**真的渲染出来**的块有哪些。
 *
 * 这个清单必须与模板里的 v-if 一一对应 —— 它是"分格"的唯一判据。
 *
 * 【为什么这件事值得单独抽出来】此前分格的口径是"后端编排策略里有的块"，
 * 渲染的口径却是"模板里写了 v-if 的块"。两者不一致时，多出来的那块会掉进
 * `tileStyle` 的兜底格位（10/10/span 2/span 3，右下角一块 380×146 的小格子）：
 *
 *   · 它太小，内容被 overflow: hidden 裁掉 —— 用户看到的是"半句话"，
 *     报的是"文本排布的 bug"；
 *   · 它压在那个位置上本来就该有的块上面，谁的点击都不可靠 ——
 *     报的是"各种组件重叠"。
 *
 * 这个坑此前踩过至少三次（课表入口卡、方向方案、行动计划），每次的修法都是
 * "把漏掉的那一块补进列表"。补了三次说明修的不是地方：判据不该是策略，
 * 该是**渲染**。所以现在反过来 —— 先列出渲染，再让策略决定**顺序与权重**。
 */
const renderedIds = computed(() => {
  const ids: string[] = []
  const push = (id: string, on: boolean) => {
    if (on) ids.push(id)
  }
  /* 与模板顺序一致，便于对照检查 */
  push('portrait', visible('portrait'))
  push('talk', visible('talk'))
  push('todo', visible('todo'))
  push('collect', visible('collect'))
  push('plans', inStrategy('plans') && visible('plans'))
  push('action', inStrategy('action') && visible('action'))
  push('timetable', showTimetable.value)
  push('calendar', inStrategy('calendar') && visible('calendar'))
  push('match', session.chsiBound)
  push('market', inStrategy('market') && visible('market'))
  push('greet', visible('greet'))
  push('people', visible('people'))
  push('review', visible('review'))
  return ids
})

/**
 * 分格用的清单 = **渲染出来的块**，顺序取编排（order）。
 *
 * 编排负责"先看哪一块"（顺序与权重），渲染负责"有没有这一块"。
 * 策略里没登记、但确实渲染了的块追加到末尾 —— 它仍然有格位，只是排在后面。
 */
const visibleIds = computed(() => {
  const rendered = renderedIds.value
  const ordered = order.value.filter((id) => rendered.includes(id))
  const rest = rendered.filter((id) => !ordered.includes(id))
  return [...ordered, ...rest]
})

/**
 * 这块在不在**后端编排**里。
 *
 * 与 `visible()` 是两件事：`visible` 说的是"用户有没有把它挪开"，
 * 这里说的是"策略认为它该不该出现"。两块都要满足才渲染 ——
 * 只按 `visible` 渲染会掉进与 `tileStyle` 兜底格位同一类的坑：
 * 块画出来了、没有格位、压在别人身上（课表入口卡踩过一次，
 * 新加的"方向方案 / 行动计划"又踩了一次：新用户画布上凭空多出两块）。
 */
const inStrategy = (id: string) =>
  !session.layout.length || session.layout.some((b) => b.id === id)

/** 把 from 挪到 to 的位置上（其余块顺序不变，布局自己重算） */
function reorder(from: string, to: string) {
  const list = [...order.value]
  const i = list.indexOf(from)
  const j = list.indexOf(to)
  if (i < 0 || j < 0 || i === j) return
  list.splice(i, 1)
  list.splice(j, 0, from)
  order.value = list
}

const tiles = computed<Record<string, { c: number; r: number; w: number; h: number }>>(() => {
  if (!tiled.value) return {}
  const items: TileInput[] = visibleIds.value.map((id) => ({ id, weight: weightOf(id) }))
  const cellAspect =
    canvasSize.value.h > 0
      ? canvasSize.value.w / TILE_COLS / (canvasSize.value.h / TILE_ROWS)
      : 1.7
  return tileLayout(items, TILE_COLS, TILE_ROWS, cellAspect)
})

/** 这块的格子 → 实际像素尺寸，用来判断要不要进紧凑形态 */
const compactIds = computed(() => {
  const set = new Set<string>()
  const { w, h } = canvasSize.value
  if (!w || !h) return set
  for (const [id, t] of Object.entries(tiles.value)) {
    const pxW = (t.w / TILE_COLS) * w
    const pxH = (t.h / TILE_ROWS) * h
    if (shouldCompact(pxH, pxW)) set.add(id)
  }
  return set
})

/**
 * 更小的一档：**矮到放不下完整形态了**。
 *
 * 为什么需要两档：`is-compact` 只回答"要不要收起来"（h<460），
 * 但在 1024×720 这种画布上，个别块实测只有 143px 高 —— 收起来之后
 * 仍然差 20px，字照样被裁。一档不够用，所以补一档更硬的：
 * 高度低于 200px 时，只留"这一块是什么 + 一个动作"，说明句整句收掉。
 *
 * 判据同样是**像素**，而且和第二档一样由外层算 —— 组件不猜自己的尺寸。
 */
const tinyIds = computed(() => {
  const set = new Set<string>()
  const { w, h } = canvasSize.value
  if (!w || !h) return set
  for (const [id, t] of Object.entries(tiles.value)) {
    if ((t.h / TILE_ROWS) * h < 200) set.add(id)
  }
  return set
})

/** 一块的 grid-area 与它现在的格位跨度（拖动引擎要靠这个找落点） */
function tileStyle(id: string) {
  const t = tiles.value[id]
  if (!t) {
    /*
     * 兜底：都在宽屏模式了却没算到格位（理论上不该发生）。
     * 那就把它放到右下角，而不是让网格自动塞到左上角 ——
     * 左上角是最糟的位置：它会和别人叠在一起，看起来像整页坏了。
     */
    return tiled.value ? { gridArea: '10 / 10 / span 2 / span 3' } : undefined
  }
  return { gridArea: `${t.r + 1} / ${t.c + 1} / span ${t.h} / span ${t.w}` }
}
const tileSpan = (id: string) => {
  const t = tiles.value[id]
  return t ? `${t.w}x${t.h}` : undefined
}
let flipState: ReturnType<typeof Flip.getState> | null = null
let flipEls: HTMLElement[] = []
let prevIds = new Set<string>()
/** 捕获时刻每个块的位置，用来判断这次更新到底有没有移动过任何块 */
let flipRects = new Map<HTMLElement, DOMRect>()
let ticker: ReturnType<typeof setInterval> | null = null
/** window.setInterval 在浏览器里返回 number，不是 Node 的 Timeout */
let watchdog = 0

/**
 * 补位动画只作用于还留在网格流里的块。
 * 被拎在手上的（.pinned）和被 CSS transition 收尾的（.settling）都不参与：
 * 前者是绝对定位，后者正在自己滑向新位置 —— 一起插值会打架。
 */
const flowEls = () =>
  [...(canvas.value?.querySelectorAll<HTMLElement>('.bubble:not(.pinned):not(.settling)') ?? [])]

function captureLayout() {
  if (!canvas.value || reduced()) return
  /*
   * 拖动 / 落位期间不起补位动画。
   * 补位用的是 Flip（写 transform），拖动也在写 transform ——
   * 两套动画叠在一起，块会停在"布局在家、看起来在别处"的中间态，读起来就是两块气泡重叠。
   */
  if (drag.isBusy()) {
    flipState = null
    flipEls = []
    return
  }
  flipEls = flowEls()
  prevIds = new Set(flipEls.map((el) => el.dataset.block ?? ''))
  flipRects = new Map(flipEls.map((el) => [el, el.getBoundingClientRect()]))
  flipState = flipEls.length ? Flip.getState(flipEls) : null
}

function playFlip() {
  if (!canvas.value || reduced()) return
  const state = flipState
  const movers = flipEls
  flipState = null

  if (state && movers.length) {
    /*
     * 只保留**还挂在文档上**的块。
     * 捕获状态时被关掉的那个块还在 DOM 里，如果把它一起传给 targets，
     * GSAP 会因为拿到一个已脱离文档的节点而让整条补位动画失效（块会瞬移）。
     */
    const alive = movers.filter((el) => el.isConnected)
    if (!alive.length) return

    /*
     * 先掐掉可能还在跑的动画（尤其是上一次落位后的"回弹"）。
     * 回弹 tween 也在写同一个 transform，不掐掉它会盖住这次的补位动画，
     * 表现就是"块瞬间跳过去"。
     */
    gsap.killTweensOf(alive)
    /*
     * 这里**不再**清 transform。
     *
     * 原来写的是 gsap.set(alive, { clearProps: 'transform' })：本意是清掉被打断的
     * tween 留下的残影，但它对**全体**执行 —— 上一段补位还没跑完的那些块，会被瞬间
     * 拽回布局位置，于是"有的块闪一下"（实测最差一帧 33.5ms 就出在这里）。
     *
     * 现在的做法：只 kill，不清。块保持它当前的视觉位置，Flip 从"它现在所在的地方"
     * 接管，滑向新格子 —— 残影由动画本身覆盖，不再有硬切。
     * 真正的清理留在 onComplete 里（那时动画已经结束，清是安全的）。
     */

    /*
     * 判断这次更新有没有真的移动过块。
     * 关闭分两步：先加 leaving 类（布局没变），220ms 后才真正移除。
     * 如果对没变的布局也跑一次 Flip，落位回弹会被白白触发，然后和真正的补位打架。
     */
    const moved = alive.some((el) => {
      const before = flipRects.get(el)
      if (!before) return true
      const now = el.getBoundingClientRect()
      return (
        Math.abs(now.left - before.left) > 1 ||
        Math.abs(now.top - before.top) > 1 ||
        Math.abs(now.width - before.width) > 1
      )
    })
    if (!moved) return

    Flip.from(state, {
      targets: alive,
      /*
       * 必须是数字。Flip 不接受函数式 duration —— 传进去会变成 NaN，
       * 整条动画退化成瞬移（这个坑踩过一次）。错落感由 stagger 提供。
       */
      duration: 0.6,
      ease: 'back.out(1.08)',   // 轻微过冲（再大会顶出画布边界）
      stagger: 0.055,
      prune: true,
      onComplete: () => {
        gsap.set(alive, { clearProps: 'transform' })
        /*
         * 落位后只让**被拖的那一块**呼吸一下（放大 2.5% → 回收 → 归位）。
         *
         * 原来这里对 alive 全体做同一段回弹：8 块 × 3 个关键帧 = 24 条补间，
         * 而且它们和"补位"动画在同一批元素上叠加写 transform —— 落位那一下的卡顿
         * 主要就出在这里。真正需要"落下来还在颤"的只有手上这一块。
         */
        const landed = drag.lastDragged()
        if (!landed) return
        gsap.to(landed, {
          keyframes: [
            { scale: 1.025, duration: 0.22 },
            { scale: 0.994, duration: 0.2 },
            { scale: 1, duration: 0.24 },
          ],
          ease: 'power2.inOut',
          clearProps: 'transform',
        })
      },
    })
  }

  // 新出现的块单独显影（Flip 的 onEnter 需要 absolute: true，会破坏网格流）
  const fresh = [...canvas.value.querySelectorAll<HTMLElement>('[data-block]')].filter(
    (el) => !prevIds.has(el.dataset.block ?? ''),
  )
  if (fresh.length) {
    /*
     * 用 CSS 动画而不是 gsap.from：
     * gsap.from 会把起始值写成内联样式，一旦被打断就永远停在起始帧（元素停在 opacity:0）。
     * CSS 动画自带结束态，跑完自动回到默认样式，不可能留下残留。
     */
    fresh.forEach((el, i) => {
      el.style.animationDelay = `${i * 50}ms`
      el.classList.add('entering')
      window.setTimeout(
        () => {
          el.classList.remove('entering')
          el.style.animationDelay = ''
        },
        560 + i * 50,
      )
    })
  }

  prevIds = new Set(
    [...canvas.value.querySelectorAll<HTMLElement>('[data-block]')].map((el) => el.dataset.block ?? ''),
  )
}

/** 拖动引擎：抽离网格 → 其余块补位 → 松手吸附 */
const drag = useCanvasDrag(canvas, { before: captureLayout, after: playFlip, reorder })

/*
 * 一块现在该不该藏起来。两件事都算：
 *   · `hiddenBlocks`：被关掉/解决过，过一会儿自己回来（那是刻意的，用户需要能清走挡视线的块）；
 *   · `ackedBlocks`：已经被"知道了"认下来的，本会话**不再回来** —— 交接提醒读过一次
 *     就不该再提醒第二次（见 store.ackBlock）。
 */
const hidden = (id: string) =>
  session.ackedBlocks.includes(id) || (session.hiddenBlocks[id] ?? 0) > Date.now()
/** 正在收缩淡出的块还要留在 DOM 里，动画播完才真的移除 */
const visible = (id: string) => !hidden(id) || leaving.value.has(id)
const isLeaving = (id: string) => leaving.value.has(id)

const reduced = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** 先收缩淡出，再让它消失 —— 这样"让位"的先后顺序读得出来 */
function closeBlock(id: string) {
  if (leaving.value.has(id)) return
  leaving.value = new Set(leaving.value).add(id)
  window.setTimeout(() => {
    session.hideBlock(id)
    const next = new Set(leaving.value)
    next.delete(id)
    leaving.value = next
  }, reduced() ? 0 : 220)
}

/*
 * 解决：把一件事办完。
 *
 * 三层，全部贴在**这块气泡自己**身上，不往屏幕上另加东西：
 *   1. 表层蒙一层绿膜 + 内描边（.veil）
 *   2. 手绘的对勾一笔画出来
 *   3. 画完这块才开始收缩、退场，其余块补上来
 *
 * 上一版这里盖的是一个 260×260 的预渲染片段 —— 那是错的：
 * 它自带底色和方形边界，压在白卡上就是一块补丁。
 * 片段机制留着（src/lib/clip.ts 里 resolve 那条已改成 kind: 'css'），
 * 但"已解决"必须长在气泡表层上。
 */
const resolvedBlocks = ref<Set<string>>(new Set())

/**
 * 右上那片浮层有没有话要说（AgentRail 的播报）。
 * 有话说就自动现身 —— 它平时是整条收起的，藏着说话谁也看不见。
 */
const railAnnouncing = ref(false)

/**
 * 课表这块什么时候出现。
 *
 * 以前它是"绑了学信网就出现" —— 那是个错的前提：学信网没有课程表。
 * 现在两个来源分开：已经有课表（教务系统取过）就展示；
 * 还没有、但这条能取，也给一个入口（点进去是"还没授权 + 去取"）。
 * 两者都不成立（这条源头没接通）时它不出现 —— 不摆一块点不动的砖。
 */
const showTimetable = computed(
  () =>
    session.academicBound ||
    (session.collection?.items ?? []).some(
      (item) => item.key === 'courses' && !item.got && item.available,
    ),
)

function resolveBlock(id: string) {
  if (resolvedBlocks.value.has(id)) return
  resolvedBlocks.value = new Set(resolvedBlocks.value).add(id)

  // 留够时间看完对勾（膜 140ms + 画 280ms + 停一下），然后才让位
  window.setTimeout(() => {
    closeBlock(id)
    const after = new Set(resolvedBlocks.value)
    after.delete(id)
    resolvedBlocks.value = after
  }, reduced() ? 0 : 560)
}

/*
 * 右键功能栏。
 *
 * 主力交互是"AI 把该做的事推到你面前"，但人总有想自己找东西的时候 ——
 * 右键就是那个"我想自己来"的入口：空白处叫出块，块上右键处理它。
 */
const menu = ref<{ x: number; y: number; block: string | null } | null>(null)

/*
 * 右键菜单里的块清单**就是后端那份编排策略**（`/app/workspace` 的 layout_panel，
 * 来自 `data/registry/layout.json`）。
 *
 * 这里不再抄一份"有哪些块、各叫什么"：抄一份的代价实测过 —— 后端改了块的说明，
 * 前端那份还停在旧数字上，界面上就出现两句对不上的话，而且没有任何测试会报错。
 */
const blockList = computed(() =>
  session.layout
    .map((b) => ({ id: b.id, label: b.label, hint: b.hint })),
)

const menuTitle = computed(() => (menu.value?.block ? '对这块做什么' : '把什么放到画布上'))

/*
 * 每一块自己的右键动作。
 *
 * 之前所有块共用一份通用菜单（解决/挪开/依据），右键任何块都长一样 ——
 * 右键的意义本就是"对**这个**东西做事"，所以每块的第一段是它自己的业务动作
 * （画像块跳缺口、日历块开日历、待办块记一条……），通用动作垫在后面。
 * 块的策略清单来自后端 layout_panel，名字查不到时退回这份本地称呼表。
 */
const BLOCK_LABELS: Record<string, string> = {
  talk: '和主理聊聊', portrait: '你的画像', todo: '待办', collect: '采集动线',
  plans: '方向方案', action: '行动计划', calendar: '日历', timetable: '本周课表',
  match: '匹配与推荐', greet: '今日简报', people: '交接', review: '上周复盘',
  market: '外部情报',
}

const BLOCK_MENUS: Record<string, MenuItem[]> = {
  portrait: [
    { id: 'open:portrait', label: '看完整分析', hint: '逐条依据', tone: 'accent' },
    { id: 'focus-gaps', label: '还缺什么', hint: '直接跳到缺口' },
  ],
  talk: [
    { id: 'talk', label: '开一次对话', hint: '说一句就行', tone: 'accent' },
    { id: 'open:sessions', label: '会话记录', hint: '开过哪些' },
  ],
  todo: [
    { id: 'open:tasks', label: '记一条待办', hint: '进任务清单', tone: 'accent' },
  ],
  collect: [
    { id: 'open:collect', label: '看完整清单', hint: '还差什么去哪取', tone: 'accent' },
  ],
  plans: [
    { id: 'open:plans', label: '看这三套方案', hint: '主攻/平行/保底', tone: 'accent' },
  ],
  action: [
    { id: 'open:action', label: '打开行动计划', hint: '阶段与任务', tone: 'accent' },
  ],
  calendar: [
    { id: 'open:calendar', label: '打开日历', hint: '按天看', tone: 'accent' },
    { id: 'open:tasks', label: '记一条待办', hint: '落到某一天' },
  ],
  timetable: [
    { id: 'open:timetable', label: '看课表与空档', hint: '可投入时间', tone: 'accent' },
  ],
  match: [
    { id: 'open:match', label: '看匹配矩阵', hint: '拿职业比对课程', tone: 'accent' },
  ],
  market: [
    { id: 'open:intel', label: '看这一批情报', hint: '按你的方向取回的公开信息', tone: 'accent' },
    { id: 'intel-fetch', label: '现在去取一次', hint: '真的去打一次外部站点' },
  ],
  greet: [
    { id: 'open:brief', label: '看今日简报', hint: '为什么是这两件', tone: 'accent' },
  ],
  people: [
    { id: 'open:sessions', label: '看交接记录', hint: '谁交给了谁', tone: 'accent' },
  ],
  review: [
    { id: 'open:review', label: '打开复盘', hint: '上周哪做得好', tone: 'accent' },
  ],
}

const menuItems = computed<MenuItem[]>(() => {
  const at = menu.value
  if (!at) return []
  if (at.block) {
    const name = blockList.value.find((b) => b.id === at.block)?.label ?? BLOCK_LABELS[at.block] ?? '这块'
    return [
      ...(BLOCK_MENUS[at.block] ?? []),
      { id: 'resolve', label: `解决「${name}」`, hint: '办完，让位' },
      { id: 'close', label: '先挪开', hint: '过一会儿自己回来' },
      { id: 'evidence', label: '看它的依据', hint: '溯源' },
    ]
  }
  // 空白处：列出被解决掉/还收着的块 + 整体操作
  const hiddenOnes = blockList.value.filter((b) => !visible(b.id))
  return [
    ...hiddenOnes.map((b) => ({ id: `summon:${b.id}`, label: `叫出「${b.label}」`, hint: b.hint, tone: 'accent' as const })),
    { id: 'summon-all', label: '全部叫出来', hint: `${hiddenOnes.length} 块不在画布上`, disabled: !hiddenOnes.length },
    { id: 'reset', label: '全部重排', hint: '回到整齐的网格' },
    { id: 'report', label: '打开完整报告', hint: '每个维度都展开的完整版' },
    { id: 'sessions', label: '我的任务会话', hint: '开过哪些、各自走到哪' },
  ]
})

function openMenu(e: MouseEvent) {
  /*
   * 浮层里发生的右键**不归画布管**。
   *
   * 这里踩过一个很贵的坑：画布的右键菜单是一层全屏的透明帘子
   * （`.menu-veil`，z-index 79），而浮层 `.layer` 的层级是 60 ——
   * 于是日历浮层里右键日期格时，事件冒泡到画布把帘子掀了起来，
   * 帘子**盖在浮层上面**，浮层里那张日历菜单点不动、整个浮层也点不动。
   * 用户报的"日历点击 bug"就是这个。
   *
   * 判据用 `.layer`（浮层）与抽屉：它们有自己的菜单与帘子。
   */
  if ((e.target as HTMLElement | null)?.closest('.layer, .evidence, .float-card')) return
  const el = (e.target as HTMLElement)?.closest<HTMLElement>('[data-block]')
  menu.value = { x: e.clientX, y: e.clientY, block: el?.dataset.block ?? null }
}

function runMenu(id: string) {
  const at = menu.value
  menu.value = null
  if (!at) return

  if (id.startsWith('summon:')) return summon(id.slice(7))
  if (id === 'summon-all') return blockList.value.forEach((b) => summon(b.id))
  if (id === 'report') return void router.push('/report')
  if (id === 'sessions') return session.openOverlay('sessions')
  if (id === 'reset') {
    // 清掉格位与拖动残留，让所有块回到网格
    drag.releaseAll()
    return
  }
  if (!at.block) return
  if (id.startsWith('open:')) return session.openOverlay(id.slice(5) as never)
  if (id === 'intel-fetch') return void session.loadIntel(true)
  if (id === 'focus-gaps') return session.openOverlay('portrait', 'gaps')
  if (id === 'talk') return void session.callTalk()
  if (id === 'resolve') return resolveBlock(at.block)
  if (id === 'close') return closeBlock(at.block)
  if (id === 'evidence') {
    const el = canvas.value?.querySelector<HTMLElement>(`[data-block="${at.block}"]`)
    session.openDrawer(
      `${blockList.value.find((b) => b.id === at.block)?.label ?? '这块'}凭什么这么说`,
      '这一块背后的依据',
      [
        { source: '数据来源', detail: el?.innerText?.replace(/\s+/g, ' ').trim().slice(0, 120) ?? '', confidence: 0.84, at: '今天' },
        { source: '生成方式', detail: '这一段由职业顾问基于你的画像与外部原文生成，依据可逐条追溯。', confidence: 0.9, at: '规则' },
      ],
    )
  }
}

/** 叫回一块（它可能被解决掉了，也可能还在等自己回来） */
function summon(id: string) {
  if (session.hiddenBlocks[id]) {
    const next = { ...session.hiddenBlocks }
    delete next[id]
    session.hiddenBlocks = next
  }
}

onBeforeUpdate(() => {
  captureLayout()
})

onUpdated(() => {
  playFlip()
})

/*
 * 浮层的"展开"有两条路：指针进来，或者焦点进来。
 *
 * 键盘那条**必须**留着 —— 收起状态下整块是 visibility: hidden，里面的控件本来
 * 就退出了 Tab 顺序，全靠这条把键盘用户接回来。
 * 但鼠标点完里面的控件之后，焦点也留在里面，于是指针走了它还挂着，
 * 看上去就成了"面板不跟手"。所以只在"确实是用鼠标点进去的"这一种情况下，
 * 指针一离开就松手；键盘进来的用户不受影响。
 */
let byPointer = false
const onDocPointerDown = () => { byPointer = true }
/* 只认 Tab：那是"我在用键盘走界面"。按 Esc、打字都不算，鼠标点完照样跟手收回。 */
const onDocKeyDown = (e: KeyboardEvent) => { if (e.key === 'Tab') byPointer = false }
function onChromeLeave(e: MouseEvent) {
  const root = e.currentTarget as HTMLElement | null
  const active = document.activeElement as HTMLElement | null
  if (byPointer && root && active && root.contains(active)) active.blur()
}

onMounted(() => {
  // 进工作台：注册表里 wb_enter 是 frontend 通道的事件（此前声明了但没人发）
  track('wb_enter', { blocks: visibleIds.value.length })
  ticker = setInterval(() => session.sweep(), 1000)
  document.addEventListener('pointerdown', onDocPointerDown, true)
  document.addEventListener('keydown', onDocKeyDown, true)

  /*
   * 画布尺寸变了就要重新算切分（像素判断依赖它）。
   * 尺寸一变，之前拖动/动画写下的位移就全部失效了 ——
   * 所以算完新布局之后清一遍残留，块只会"啪"地对齐到新格位，
   * 不会停在两个布局中间，更不会叠在一起。
   */
  ro = new ResizeObserver(([entry]) => {
    const r = entry.contentRect
    const changed = Math.abs(r.width - canvasSize.value.w) > 1 || Math.abs(r.height - canvasSize.value.h) > 1
    canvasSize.value = { w: r.width, h: r.height }
    if (changed) requestAnimationFrame(() => drag.releaseAll())
  })
  if (canvas.value) ro.observe(canvas.value)

  // 跨过断点时切换模式（进窄屏退回单列，回宽屏重新切分）
  const mq = window.matchMedia(narrowQuery)
  const onChange = (e: MediaQueryListEvent) => (tiled.value = !e.matches)
  mq.addEventListener('change', onChange)
  onBeforeUnmount(() => mq.removeEventListener('change', onChange))

  /*
   * 自检兜底（每 1.5 秒一次）。
   *
   * 平铺布局本身不可能让两块重叠 —— 重叠只可能来自"动画写到一半被打断"留下的位移。
   * 与其指望每一种打断都被考虑到，不如让它不可能存活：
   * 一旦真的看到两块压在一起（而且它们没在被拖、也没在落位），就把所有残留位移清掉。
   * 代价是每 1.5 秒做一次 6 元素的成对比较，可以忽略。
   */
  watchdog = window.setInterval(() => {
    const els = [...(canvas.value?.querySelectorAll<HTMLElement>('[data-block]') ?? [])]
    if (els.length < 2) return
    if (els.some((el) => el.classList.contains('pinned') || el.classList.contains('settling'))) return
    const rects = els.map((el) => el.getBoundingClientRect())
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i]
        const b = rects[j]
        const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left)
        const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
        if (ox > 6 && oy > 6) {
          drag.releaseAll()
          return
        }
      }
    }
  }, 1500)
})

onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker)
  window.clearInterval(watchdog)
  ro?.disconnect()
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  document.removeEventListener('keydown', onDocKeyDown, true)
})
</script>

<template>
  <div class="console" @contextmenu.prevent="openMenu">
    <!--
      **没有顶栏了。**

      之前这里是一条 51px 的壳（渐变底 + 下边框），装着三件东西。壳本身不产生任何价值，
      却把画布上下各吃掉一截 —— 而这一屏要表达的是"事情浮在桌面上"，
      一条横贯全宽的实心带子恰好把那个感觉压掉了。设计判断里"minimal chrome"
      的反面就是这个：Heavy chrome。

      现在装在上面的两件东西自己浮着：
        · 左上：品牌 + 身份（同一个账号入口，只是不再有底）；
        · 右上：谁在替你干活、轮到你没有。
      它们和画布上的气泡是同一套材质与层级 —— 整屏只有一种东西：浮片。

      "看完整报告"从壳里撤了：它本来就只是目的地，导览便签的索引里有它一行。
      壳一散，这种"顺手放一个入口"的位置也就没有了，这是好事。
    -->
    <div class="chrome chrome--left" @mouseleave="onChromeLeave">
      <button class="chrome__hit" type="button" aria-label="展开账号与设置" />
      <div class="chrome__body"><AccountMenu /></div>
    </div>
    <div class="chrome chrome--right" :class="{ 'is-announcing': railAnnouncing }" @mouseleave="onChromeLeave">
      <button class="chrome__hit" type="button" aria-label="展开：谁在替你干活" />
      <div class="chrome__body"><AgentRail @announce="railAnnouncing = $event" /></div>
    </div>

    <main class="stage">
      <!-- 不用 TransitionGroup：位移与尺寸插值全部交给 GSAP Flip -->
      <!--
        行数只在平铺模式下写死；窄屏单列时必须让 CSS 管（否则 12 条 1fr 行
        在自适应高度里会各自撑成内容高度，画布白白长到几千像素）。
      -->
      <div
        ref="canvas"
        class="canvas"
        @dblclick.self="session.summonAll()"
        :style="tiled ? { gridTemplateRows: `repeat(${TILE_ROWS}, minmax(0, 1fr))` } : undefined"
      >
        <!--
          顺序是有讲究的：网格按 DOM 顺序自动排布，
          两块 6×6 必须排在前面，底部四个 3×2 才能严丝合缝地填满最后两条。
        -->
        <PortraitBubble
          v-if="visible('portrait')"
          data-block="portrait"
          class="b-portrait"
          :class="{
            leaving: isLeaving('portrait'),
            'is-compact': compactIds.has('portrait'),
            'is-next': session.nextBlockId === 'portrait',
          }"
          :style="tileStyle('portrait')"
          :data-span="tileSpan('portrait')"
          resolvable
          :resolved="resolvedBlocks.has('portrait')"
          @resolve="resolveBlock('portrait')"
          @close="closeBlock('portrait')"
        />

        <!--
          跟主理说清楚一件事。它和画像、待办一样是画布上的一块 ——
          位置由平铺算法按权重分，不写死；权重给到 2.4，
          是因为"说不清楚"是所有流程的共同入口：用户卡住时第一反应是问一句，
          而不是先去做个任务。
        -->
        <TalkBubble
          v-if="visible('talk')"
          data-block="talk"
          class="b-talk"
          :class="{
            leaving: isLeaving('talk'),
            'is-compact': compactIds.has('talk'),
            'is-next': session.nextBlockId === 'talk',
          }"
          :style="tileStyle('talk')"
          :data-span="tileSpan('talk')"
          :resolved="resolvedBlocks.has('talk')"
          @resolve="resolveBlock('talk')"
          @close="closeBlock('talk')"
        />

        <TodoBubble
          v-if="visible('todo')"
          data-block="todo"
          class="b-todo"
          :class="{
            leaving: isLeaving('todo'),
            'is-compact': compactIds.has('todo'),
            'is-tiny': tinyIds.has('todo'),
            'is-next': session.nextBlockId === 'todo',
          }"
          :style="tileStyle('todo')"
          :data-span="tileSpan('todo')"
          resolvable
          :resolved="resolvedBlocks.has('todo')"
          @resolve="resolveBlock('todo')"
          @close="closeBlock('todo')"
        />

        <!--
          采集动线：还缺什么、去哪儿取。
          它取代了原来那块固定写死"核验学籍"的气泡 ——
          那块不管你是谁都说同一句话；这块是照画像算出来的，补完自己会变。

          第三档（is-tiny）必须一起给。CollectBubble 自己写了 `.bubble.is-tiny`
          的收法（矮格位里先把"其余几条"和来源胶囊收掉），可是这里以前没传这个类 ——
          于是它永远停在第二档：1440×900 实测这一格 194px、内容要 238px，
          底下两行被 overflow: hidden 裁掉，用户看到的是"半句话的绿块"。
        -->
        <CollectBubble
          v-if="visible('collect')"
          data-block="collect"
          class="b-collect"
          :class="{
            leaving: isLeaving('collect'),
            'is-compact': compactIds.has('collect'),
            'is-tiny': tinyIds.has('collect'),
            'is-next': session.nextBlockId === 'collect',
          }"
          :style="tileStyle('collect')"
          :data-span="tileSpan('collect')"
          :resolved="resolvedBlocks.has('collect')"
          @resolve="resolveBlock('collect')"
          @close="closeBlock('collect')"
        />

        <!--
          ③ 决策：三套方向方案。
          这块只在**方案资产存在**时出现（策略里的 has_direction_plans）——
          没走到决策环节时摆一块"点开是空的"入口，比不摆更让人困惑。
        -->
        <Bubble
          v-if="inStrategy('plans') && visible('plans')"
          data-block="plans"
          class="b-plans"
          :class="{ leaving: isLeaving('plans'), 'is-compact': compactIds.has('plans') }"
          :style="tileStyle('plans')"
          :data-span="tileSpan('plans')"
          :resolved="resolvedBlocks.has('plans')"
          size="sm"
          tone="raised"
          interactive
          resolvable
          label="方向方案"
          :tilt="-0.3"
          @click="session.openOverlay('plans')"
          @resolve="resolveBlock('plans')"
          @close="closeBlock('plans')"
        >
          <span class="label bindcard__k">决策 · 职业顾问</span>
          <h3 class="bindcard__t">主攻 / 平行 / 保底，选一套</h3>
          <p class="bindcard__d">
            三套方案来自「决策」这一步：每套带匹配度、契合依据与主要风险。
            选择可撤回 —— 再选另一套就是撤回。
          </p>
          <span class="label bindcard__cta">看这三套怎么比 →</span>
        </Bubble>

        <!--
          ④ 行动：行动计划。
          和"待办"分开摆：待办是**你自己的清单 + AI 建议**，
          行动计划是 ④ 环节产出的**资产**（阶段、任务、关键节点）。
          两件事混在一块，用户就分不清"这是计划里的"还是"我自己写的"。
        -->
        <Bubble
          v-if="inStrategy('action') && visible('action')"
          data-block="action"
          class="b-action"
          :class="{ leaving: isLeaving('action'), 'is-compact': compactIds.has('action') }"
          :style="tileStyle('action')"
          :data-span="tileSpan('action')"
          :resolved="resolvedBlocks.has('action')"
          size="sm"
          tone="raised"
          interactive
          resolvable
          label="行动计划"
          :tilt="0.35"
          @click="session.openOverlay('action')"
          @resolve="resolveBlock('action')"
          @close="closeBlock('action')"
        >
          <span class="label bindcard__k">行动 · 路径规划师</span>
          <h3 class="bindcard__t">分阶段的任务，今天勾得掉</h3>
          <p class="bindcard__d">
            计划来自「行动」这一步：阶段里程碑 + 每一条能勾掉的小任务，
            关键节点同时写进日历。
          </p>
          <span class="label bindcard__cta">看我接下来做什么 →</span>
        </Bubble>

        <Bubble
          v-if="showTimetable"
          data-block="timetable"
          class="b-timetable"
          :style="tileStyle('timetable')"
          :data-span="tileSpan('timetable')"
          :class="{ 'is-compact': compactIds.has('timetable') }"
          size="sm"
          tone="plain"
          interactive
          resolvable
          label="本周课表"
          :tilt="-0.3"
          @click="session.openOverlay('timetable')"
          @resolve="resolveBlock('timetable')"
          @close="closeBlock('timetable')"
        >
          <span class="label bindcard__k">行动 · 路径规划师</span>
          <h3 class="bindcard__t">这周的可投入时间</h3>
          <p class="bindcard__d">
            课表来自你学校的教务系统（学信网没有课表）。点开按你的课表算空档；还没导入就先导一份。
          </p>
          <span class="label bindcard__cta">看课表与空档 →</span>
        </Bubble>

        <!--
          日历：按天看。
          和「本周课表」不是一回事 —— 课表看的是每周重复的那几门课，
          日历看的是"这一天有什么、这一天怎么用"。
          它不依赖课表就能出现：到期的事、到期没做完的任务，本来就不需要课表。
        -->
        <CalendarBubble
          v-if="inStrategy('calendar') && visible('calendar')"
          data-block="calendar"
          class="b-calendar"
          :class="{ leaving: isLeaving('calendar'), 'is-compact': compactIds.has('calendar') }"
          :compact="compactIds.has('calendar')"
          :style="tileStyle('calendar')"
          :data-span="tileSpan('calendar')"
          @close="closeBlock('calendar')"
        />

        <!--
          外部情报：从公开渠道按你的方向取回的一批事实。

          它和日历一样**由策略决定出不出现**（注册表里 `show_when: reached_analysis`）——
          还没走到分析这一步时，外面那些"对口职业/校友案例"和你没有关系，
          摆一块出来只会让新用户觉得答非所问。到了那一步它自己会出现在画布上。
        -->
        <MarketBubble
          v-if="inStrategy('market') && visible('market')"
          data-block="market"
          class="b-market"
          :class="{
            leaving: isLeaving('market'),
            'is-compact': compactIds.has('market'),
            'is-tiny': tinyIds.has('market'),
          }"
          :style="tileStyle('market')"
          :data-span="tileSpan('market')"
          @close="closeBlock('market')"
          @resolve="resolveBlock('market')"
        />

        <Bubble
          v-if="session.chsiBound"
          data-block="match"
          class="b-match"
          :style="tileStyle('match')"
          :data-span="tileSpan('match')"
          :class="{ 'is-compact': compactIds.has('match') }"
          size="sm"
          tone="raised"
          interactive
          resolvable
          label="匹配与推荐"
          :tilt="0.5"
          @click="session.openOverlay('match')"
          @resolve="resolveBlock('match')"
          @close="closeBlock('match')"
        >
          <span class="label bindcard__k">诊断 · 职业顾问</span>
          <h3 class="bindcard__t">方向匹配与推荐</h3>
          <p class="bindcard__d">拿职业条目比对你的课程与成绩。点开就按你有的东西比一遍。</p>
          <span class="label bindcard__cta">看匹配矩阵 →</span>
        </Bubble>

        <Bubble
          v-if="visible('greet')"
          data-block="greet"
          class="b-greet"
          :class="{
            leaving: isLeaving('greet'),
            'is-compact': compactIds.has('greet'),
            'is-tiny': tinyIds.has('greet'),
          }"
          :style="tileStyle('greet')"
          :data-span="tileSpan('greet')"
          size="sm"
          tone="quiet"
          interactive
          resolvable
          :resolved="resolvedBlocks.has('greet')"
          label="今天为什么是这两件"
          :tilt="-0.35"
          @click="session.openOverlay('brief')"
          @resolve="resolveBlock('greet')"
          @close="closeBlock('greet')"
        >
          <h1 class="greet__hi">你好，{{ whoName }}。</h1>
          <p v-if="session.wsPanels?.action" class="greet__line">今天该做的是：{{ session.wsPanels.action }}</p>
          <p v-else class="greet__line">今天要做的事还没排出来 —— 先开一次对话。</p>

          <footer class="greet__foot">
            <NextAsk compact />
            <span class="label greet__cta">详情 →</span>
          </footer>
        </Bubble>

        <!--
          外部情报不再占画布上的一块：它归队到右上轨道的实时播报体系
          （AgentRail 的 pops，轮询也搬了过去）。同一套材质、同一个角落。
        -->
        <PeopleBubble
          v-if="visible('people')"
          data-block="people"
          class="b-people"
          :class="{
            leaving: isLeaving('people'),
            'is-compact': compactIds.has('people'),
            'is-tiny': tinyIds.has('people'),
          }"
          :style="tileStyle('people')"
          :data-span="tileSpan('people')"
          :resolved="resolvedBlocks.has('people')"
          @resolve="resolveBlock('people')"
          @close="closeBlock('people')"
        />

        <ReviewBubble
          v-if="visible('review')"
          data-block="review"
          class="b-review"
          :class="{
            leaving: isLeaving('review'),
            'is-compact': compactIds.has('review'),
            'is-tiny': tinyIds.has('review'),
          }"
          :style="tileStyle('review')"
          :data-span="tileSpan('review')"
          :resolved="resolvedBlocks.has('review')"
          @resolve="resolveBlock('review')"
          @close="closeBlock('review')"
        />
      </div>
    </main>

    <!-- 消息与提问：直接盖在内容上，半透明，随时可以关 -->
    <FloatLayer />

    <!--
      这里原来的「演示 · 探索自我 / 验证定向 / …」整条删掉了。

      它是设计期用来预览五个阶段长什么样的调试控件，现在两件事都不成立：
        · 处境本来就该由后台推断（阶段是隐性轴，用户不该、也不需要自己选）；
        · 它的存在让人以为"阶段是个可以手动切的东西"——那是错的引导。
      产品里留着调试入口，比留着一处没实现的空白更糟：它会被当成功能。
    -->
    <PortraitOverlay v-if="session.overlay === 'portrait'" />
    <TasksOverlay v-if="session.overlay === 'tasks'" />
    <BriefOverlay v-if="session.overlay === 'brief'" />
    <BindOverlay v-if="session.overlay === 'bind'" />
    <CollectOverlay v-if="session.overlay === 'collect'" />
    <IntelOverlay v-if="session.overlay === 'intel'" />
    <TimetableOverlay v-if="session.overlay === 'timetable'" />
    <MatchOverlay v-if="session.overlay === 'match'" />
    <PlansOverlay v-if="session.overlay === 'plans'" />
    <ActionOverlay v-if="session.overlay === 'action'" />
    <CalendarOverlay v-if="session.overlay === 'calendar'" />
    <SessionsOverlay v-if="session.overlay === 'sessions'" />
    <ReviewOverlay v-if="session.overlay === 'review'" />
    <EvidenceDrawer />

    <!-- 右键功能栏：空白处叫块，块上处理它 -->
    <CanvasMenu
      v-if="menu"
      :x="menu.x"
      :y="menu.y"
      :title="menuTitle"
      :items="menuItems"
      @pick="runMenu"
      @close="menu = null"
    />
    <button v-if="menu" class="menu-veil" type="button" aria-label="关闭菜单" @click="menu = null" />
  </div>
</template>

<style scoped>
/* 一屏之内：高度锁死，谁也不许把页面撑高 */
.console {
  position: relative;
  height: 100dvh;
  display: grid;
  /*
   * **只有一行。**
   *
   * 这里原来是 `auto 1fr` —— 那是给"顶栏 + 内容"两行准备的。顶栏删掉之后，
   * 两片浮层都是 absolute（不在流里），于是唯一的在流子元素 .stage 落进了
   * 那个 `auto` 行：高度由**内容**决定。表现就是——关掉一块、内容变矮、
   * 画布跟着缩，越关越小。
   *
   * 留下 `auto` 那一行的代价是一次很难查的连环 bug；栅格的行数要和真实的
   * 在流子元素数量对得上，这是硬约束，不是风格问题。
   */
  grid-template-rows: minmax(0, 1fr);
  overflow: hidden;
}


.bar {
  /*
   * 旧的顶栏已经删掉了（模板里有说明）。这一条留着会让人以为还有一条栏 ——
   * 与其留个空壳，不如让它彻底不存在。
   */
}

/*
 * 浮着的两片界面装饰。
 *
 * 三条规矩：
 *   1. **不占布局**（absolute）—— 壳不该参与排版，更不该决定内容从哪里开始；
 *   2. **平时缩上去**：它们不是内容，是"想用的时候才伸手去够"的两个入口。
 *      收起时屏幕上只剩一根 30×4 的小横杠（唯一的"这里有东西"的提示），
 *      指针进到横杠那一带、或者键盘 Tab 进来，整片才滑下来；
 *   3. **不抢画布**：让出的高度直接还给画布，所以 .stage 的顶部内边距很小。
 */
.chrome {
  position: absolute; top: 0; z-index: var(--z-float);
  display: flex; flex-direction: column; align-items: flex-start;
  /*
   * 17px = 7（横杠离顶）+ 4（横杠本身）+ 6（横杠与浮层之间的呼吸）。
   * 横杠现在是判定带里的装饰，不占布局了，这 17px 得自己留 ——
   * 少写它，浮层展开时就会贴在屏幕最上沿，像被裁掉了一截。
   */
  padding-top: 17px;
  /*
   * 容器本身不吃指针：它替隐藏的浮层留着一块布局空间，
   * 如果这块空间也能点，画布左上角/右上角就点不透了（用户会以为那里点不动）。
   * 接事件的只有两处：判定带（下面那条）与展开后的浮层本体。
   */
  pointer-events: none;
  /*
   * 判定带的高度：必须**盖过**浮层展开后的顶边（实测 17px）。
   * 剩下那点余量是给"缝隙"的 —— 提示条底边 11 到本体顶边 17 之间有 6px，
   * 少了这层覆盖，指针停在那 6px 里就会掉进"谁也没压住"的空档。
   */
  --chrome-hit: 22px;
}
.chrome--left { left: var(--s5); }
.chrome--right { right: var(--s5); }
.chrome--right { align-items: flex-end; }

/*
 * 判定带 —— **"浮窗乱跳"的正主**。
 *
 * 之前的判据是"指针压没压住提示条或浮层本体"。听起来天经地义，但它有个致命处：
 * 浮层收起时是从下往上**扫过**那一段的，而命中判定跟着它的实时位置走。
 * 于是指针只要停在它扫过的高度上（横杠上方那十几像素），就会：
 *   扫到指针 → 判为进入 → 落下来 → 指针又不在它身上了 → 收起 → 再扫到 → 再落下……
 * 一个不用手就能自转的死循环，观感就是"鼠标稍微往上挪一点，浮窗自己抖"。
 *
 * 修法不是调数值，而是把判据从"会动的东西"上拿开，钉在一块**永远不动**的区域上：
 * 指针在这条带里 = 展开，浮层怎么动都不改变这个判定，循环从机制上不存在了。
 *
 * 代价要交代清楚：这条带会吃掉覆盖范围内的指针事件。所以它只有 22px 高、
 * 只覆盖卡片自己的宽度，且整个 .stage 上沿留了 26px 内边距 —— 带子恰好落在
 * 那圈留白里，画布上的东西一个都不挡（实测 y=26 处点到的还是气泡本身）。
 *
 * 它同时是**键盘入口**：浮层收起时整块都不可见（visibility: hidden），
 * 于是里面那些控件也一并退出了 Tab 顺序 —— 不补这一步，键盘用户就再也够不到账号。
 * 做成真按钮，Tab 进来即展开（:focus-within），再 Tab 就进到面板里；
 * 这是"抽屉把手"该有的样子，不是一块装饰。
 */
.chrome__hit {
  position: absolute; left: 0; right: 0; top: 0; height: var(--chrome-hit);
  pointer-events: auto;
  appearance: none; padding: 0; margin: 0; border: 0; background: none;
  /* 它整条都是判据，不是按钮的样子 —— 光标不装成"可点"免得那片空白骗人 */
  cursor: default;
}

/*
 * 提示条：**完全收起**时唯一看得见的东西 —— 现在画在上面那条判据带里。
 *
 * 上一版是"浮层只露出下沿 20px"——那等于把一颗胶囊连同一行字切一半露在外面，
 * 读起来是"屏幕不够大、内容被遮住了"，而不是"上面有个东西可以拉下来"。
 *
 * 现在改成两条明确的分工：
 *   · 提示条 —— 一根 30×4 的小横杠，**专门设计成提示**，不是被裁的文字；
 *   · 浮层本体 —— 完全滑出视口（按自身高度上推，见下面 .chrome__body），
 *     要用的时候整块下来。
 * 这才是"抽屉把手 + 抽屉"的关系，而不是"抽屉没关严"。
 */
.chrome__hit::before {
  content: ''; position: absolute; top: 7px; left: 11px;
  width: 30px; height: 4px; border-radius: 2px;
  background: var(--line-3);
  transition: background var(--dur-micro) var(--ease-out),
              width var(--dur) var(--ease-spring);
}
.chrome--right .chrome__hit::before { left: auto; right: 11px; }
.chrome:hover .chrome__hit::before,
.chrome:focus-within .chrome__hit::before {
  background: var(--accent);
  width: 44px;
}
.chrome__hit:focus-visible::before {
  background: var(--accent); width: 44px;
  outline: 2px solid var(--accent); outline-offset: 3px;
}

.chrome__body {
  pointer-events: auto;
  /*
   * 按**自身高度 + 20px 余量**往上推。
   * 之前写的是 -140%，听起来够，实际算下来底部还会露出 3–4px ——
   * 那点边沿同样是"被遮住"的观感，等于把这个问题缩小了没解决。
   * 用 calc(100% + N) 就与高度无关：无论里面装几个控件都保证完全出画。
   */
  transform: translateY(calc(-100% - 20px));
  /*
   * visibility 跟着一起管：收起之后，浮层里那些绝对定位的下拉面板、播报气泡
   * 并不在 body 的高度里，body 自己滑走了它们还挂在屏幕上。一是难看，
   * 二是它们照样能被指针压住 —— 又一处会让浮窗自己抖的引信。收起即不可见、不可点。
   * 延迟到滑完再翻，收起动画本身才看得见。
   */
  visibility: hidden;
  transition: transform var(--dur-enter) var(--ease-expo),
              visibility 0s linear var(--dur-enter);
}
.chrome:hover .chrome__body,
.chrome:focus-within .chrome__body {
  transform: translateY(0);
  visibility: visible;
  transition: transform var(--dur-enter) var(--ease-expo), visibility 0s;
}
/* 有播报 = 自动现身（呼出条件与指针无关，所以放在 hover 规则之后覆盖它） */
.chrome.is-announcing .chrome__body {
  transform: translateY(0);
  visibility: visible;
  transition: transform var(--dur-enter) var(--ease-expo), visibility 0s;
}

/*
 * 顶部只留 26px：浮层默认缩在上面，画布要用满它让出来的高度。
 *
 * 底部 78px 是给导览便签的**净空**（便签本体 46px + 18px 呼吸 + 便签离底 18px）。
 *
 * 这一条是量出来的：上一稿留 56px，而便签从底边 18px 往上长到 64px ——
 * 于是便签压住画布最下面 8px，实测左下角那块（画像 / 采集）的底边被盖住一条。
 * 便签是常驻的，这种"永远压着一个角"的重叠会在每一屏出现一次，
 * 用户报的"组件重叠"里就有它。
 *
 * --stage-bottom 同时给 ::before 的网格用：两处口径必须是一个变量，
 * 否则改了一处，网格就会和画布错位（那比不画网格更糟）。
 */
.stage {
  --stage-bottom: 78px;
  position: relative; min-height: 0;
  padding: 26px var(--s5) var(--stage-bottom);
}

/*
 * 底板的两层底纹 ——「坐标纸」。
 *
 * 桌上铺一层极淡的方格纸：块压在上面有落点感，空着的地方也像
 * "还没画的草稿"而不是"没画完"。pointer-events: none —— 右键、双击要能穿透。
 */
.stage::before {
  content: ""; position: absolute; inset: 26px var(--s5) var(--stage-bottom);
  pointer-events: none;
  background-image:
    linear-gradient(var(--line-1) 1px, transparent 1px),
    linear-gradient(90deg, var(--line-1) 1px, transparent 1px);
  background-size: 26px 26px;
  opacity: 0.62;
  -webkit-mask-image: radial-gradient(130% 90% at 50% 40%, #000 46%, transparent 100%);
  mask-image: radial-gradient(130% 90% at 50% 40%, #000 46%, transparent 100%);
}
/*
 * 桌子角落里的涂鸦 —— **疯狂艺术家的那一笔**。
 *
 * 上一版这里是一支画得很"认真"的铅笔箭头 + 一颗规规矩矩的星：
 * 用户的判词是"你不应该想象成乖乖女认真写上课笔记，而是疯狂艺术家胡乱的草稿"。
 * 那句评语是对的：那个箭头的问题是它**太正确了** —— 一笔到位、角度舒服、
 * 构图讲究，那是插画，不是草稿。
 *
 * 现在换成一堆"没画好"的痕迹：涂掉的方框、来回描的圈、两头都是箭头的线、
 * 一颗星星被描了两次、一个打歪的叉。笔压不匀（粗细 1.4 与 3.2 混着用），
 * 线条互相压过去 —— 那才是草稿。
 *
 * 位置也改了：上一版画在右下角，正好压在「行动计划」那块的字上。
 * 现在它 **z-index: 0 沉到卡片底下**，只在块与块之间的缝里露出来 ——
 * 永远不会和任何一行字打架。
 */
.stage::after {
  content: ""; position: absolute; right: 5%; bottom: 8%;
  z-index: 0;
  width: 380px; height: 280px;
  pointer-events: none;
  opacity: 0.2;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 380 280' fill='none' stroke='%2312110e' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M28 232 C 92 214, 128 168, 176 118' stroke-width='3.2'/%3E%3Cpath d='M172 126 C 168 112, 180 104, 190 112' stroke-width='2.4'/%3E%3Cpath d='M18 226 L 84 244' stroke-width='2.6'/%3E%3Cpath d='M226 58 c 26 -14, 52 6, 44 30 c -8 26, -48 30, -58 8 c -10 -22, 12 -44, 40 -44' stroke-width='1.6'/%3E%3Cpath d='M214 70 c 30 -22, 66 4, 52 34 c -14 30, -62 26, -66 -2' stroke-width='1.4'/%3E%3Cpath d='M272 176 L 344 142' stroke-width='2.8'/%3E%3Cpath d='M344 142 l -14 -2' stroke-width='2.2'/%3E%3Cpath d='M272 176 l 6 14' stroke-width='2.2'/%3E%3Cpath d='M300 214 l 34 -20' stroke-width='1.6'/%3E%3Cpath d='M108 96 l 22 -30 M132 96 l -24 -30' stroke-width='2.6'/%3E%3Cpath d='M110 100 l 20 -34 M134 100 l -22 -34' stroke-width='1.4'/%3E%3Cpath d='M330 60 l3 8 9 2 -7 6 2 10 -8 -5 -8 5 2 -10 -7 -6 9 -2 z' stroke-width='2'/%3E%3Cpath d='M336 56 l4 9 10 2 -8 7 2 10 -8 -6 -9 6 2 -10 -8 -7 10 -2 z' stroke-width='1.3'/%3E%3Cpath d='M56 118 l 30 14 M58 132 l 26 -14 M62 124 l 22 0' stroke-width='2.4'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-size: contain;
}

/*
 * 块浮在一片画布上，靠大小与位置分层，并留出重叠感。
 * dense 流式排布 —— 关掉一块，后面的块会自动往上补。
 */
.canvas {
  position: relative;          /* 拖动后的块要相对它绝对定位 */
  /*
   * z-index: 1 —— 把它抬到桌子涂鸦（.stage::after，z-index: 0）之上。
   * 涂鸦是"桌子上的痕迹"，块是"摊在桌上的纸"：纸必须在痕迹上面。
   */
  z-index: 1;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-template-rows: repeat(8, minmax(0, 1fr));
  grid-auto-flow: row dense;
  gap: 12px;
  align-content: start;
}

/* ── 拖动 ─────────────────────────────────────────────────────────
   按住块的空白处即可拖；落在按钮、输入框上不起拖。
   拖起来时块被抽离网格（其余块自动补位），松手吸附到最近的空位。 */
/*
 * 光标先说清"这块是干嘛的"：
 * 能点开的块给 pointer（用户第一眼就知道点得动），能不能拖由右上角的把手暗示；
 * 纯展示的块给 grab，直接告诉你它只是个可以挪开的东西。
 */
.canvas [data-block] { cursor: grab; }
.canvas [data-block].interactive { cursor: pointer; }
.canvas [data-block].dragging { cursor: grabbing; }
/* 指针按住期间关掉文字选中（拖动不再靠 preventDefault 抢焦点） */
.canvas.arming { user-select: none; }
.canvas [data-block].pinned { position: absolute; left: 0; top: 0; }
/*
 * 松手时"落回纸面"要舒服，靠的是这条 transition。
 *
 * 原来 transition 只写在 .dragging 里面：类一被摘掉，transition 属性也一起没了，
 * 投影是**瞬间**弹回去的 —— 这就是落位那一下显得生硬的原因。
 * 放在基础态上，无论加类还是摘类，投影都走同一段缓出（和"关闭一个块"同一条曲线）。
 */
.canvas [data-block] {
  transition: transform var(--dur-exit) var(--ease-out);
}
.canvas [data-block].dragging {
  cursor: grabbing;
  /*
   * 拖起来时"抬高一层"**不用投影**：把套版线加深成墨色。
   * 一张纸被拎起来的样子，在印刷语言里就是"它被描粗了一圈边"。
   */
  transition: transform var(--dur-exit) var(--ease-out);
  border-color: var(--ink-1) !important;
}
/* 拖动时给块描一圈，随时知道手上拿着的是哪一块 */
.canvas [data-block].dragging::after {
  content: "";
  position: absolute; inset: -1px; border-radius: inherit;
  pointer-events: none;
  border: 2px solid var(--accent);
  opacity: 0.4;
}

/*
 * 落位：位置已经由网格定好了，这里只把"刚才差的那一段距离"滑完。
 * 用 CSS transition 而不是 JS 动画 —— 打断、跳过、后台标签页都不会留下残余位移，
 * 最坏的情况也只是少滑一段，块始终在正确的格位上。
 */
.canvas [data-block].settling {
  transition: transform 620ms cubic-bezier(0.34, 1.28, 0.64, 1),
              border-color var(--dur-exit) var(--ease-out);
  will-change: transform;
}

/*
 * 吸附落点提示。
 * 这个元素是 JS 动态创建的，拿不到 Vue 的 scoped 属性，
 * 所以必须用 :deep() 让样式命中它 —— 否则它既没有定位，也会作为网格项挤进布局。
 */
.canvas :deep(.snap-ghost) {
  position: absolute; left: 0; top: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 180ms var(--ease-out);
  border: 2px dashed rgba(10, 88, 66, 0.5);
  border-radius: var(--r-lg);
  background: rgba(10, 88, 66, 0.06);
  z-index: 1;
}

/*
 * 位置和大小现在由平铺引擎算（见 tileStyle / tiling.ts），
 * 这里只留两件事：紧凑形态的排版，和窄屏下的兜底。
 */

/* 紧凑形态：字数不变，但层级收起来 —— 标题小一档、说明压到两行、次要元信息隐掉 */
.bubble.is-compact { padding: var(--s4); gap: var(--s2); }
.bubble.is-compact .is-compact-hide { display: none; }

/* 新功能块的紧凑排版：一行小标 + 一句结论 + 一句解释 + 一个入口 */
.b-collect, .b-timetable, .b-match { gap: 6px; }
.bindcard__k { color: var(--violet); }
.bindcard__t {
  font-family: var(--font-display);
  font-size: var(--t-h4); font-weight: 400; line-height: 1.32;
}
/*
 * 三行而不是两行：两行会把"点开按你的课表算空档"这类句子拦腰切断
 * （实测用户看到的正是"点开按◻"这种半句）。三行放得下，就不再切。
 */
.bindcard__d {
  font-size: var(--fs-small); color: var(--ink-2); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.bindcard__cta { margin-top: auto; color: var(--accent); }

/*
 * 底部那排是紧凑块：350×200 左右，字号要收一档，行数要按住。
 * 收的是字号，不是信息 —— 每一块仍然"标题 + 一句为什么 + 动作"齐全。
 */
.b-greet .greet__hi { font-size: var(--t-h3); line-height: 1.34; }
.b-greet .greet__line { font-size: var(--fs-small); line-height: 1.55; }
.b-greet .greet__foot { gap: var(--s2); }
.b-greet .greet__rhythm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.b-greet .greet__cta { font-size: var(--t-label); }

/*
 * 1024×720 这类小画布上，今日简报只有 ~143px 高，完整形态差 6px ——
 * 那 6px 正好把"详情 →"那一行啃掉一半。第三档（is-tiny）在这里生效：
 * 标题收一档、正文压到两行，页脚保持原样（入口不能消失）。
 */
.b-greet.is-tiny .greet__hi { font-size: var(--t-h4); line-height: 1.3; }
.b-greet.is-tiny .greet__line {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

/* 被关掉的那块：先收缩淡出，再让出格子 */
.bubble.leaving {
  /* 退场也走动效库：换风格只改 motion.css 里的 mo-resolve */
  animation: mo-resolve 220ms var(--mo-in) both;
  pointer-events: none;
}

/* 右键菜单背后的透明帘子：点一下就收起来 */
.menu-veil {
  position: fixed; inset: 0; z-index: calc(var(--z-toast) - 1);
  background: none; cursor: var(--cursor-arrow);
}

/* 重新飘回来的块：入场走动效库的那一条（motion.css 里的 mo-rise） */
.bubble.entering {
  animation: mo-rise var(--mo-enter) var(--mo-out) both;
}

/* 问候语是整个界面里唯一一句"人话"，给它编辑体，和后面的数据语言分开 */
.greet__hi {
  font-family: var(--font-editorial);
  /*
   * 得意黑的字面比上一版的手绘字宽，而且这一档是"问候 + 名字"，
   * 名字是个没有空格的 token（reviewer_abaef4）—— 上限从 34 收到 30，
   * 并且允许在任意位置断行（overflow-wrap），长名字不再顶出卡片。
   */
  font-size: clamp(22px, 2vw, 30px); line-height: 1.24; letter-spacing: 0;
  overflow-wrap: anywhere;
}
.greet__line { color: var(--ink-2); margin-top: 2px; }

/* 底下一行：左边是节奏入口，右边写着整块点下去会发生什么 */
.greet__foot {
  margin-top: auto;
  display: flex; align-items: center; gap: var(--s3);
  min-width: 0;
}
.greet__rhythm {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px; margin-left: -9px;      /* 视觉上和正文左对齐 */
  border-radius: var(--r-pill);
  color: var(--ink-3);
  transition: color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out);
}
.greet__rhythm:hover { color: var(--ink-1); background: var(--fill-hover); }
.greet__cta { margin-left: auto; color: var(--ink-3); white-space: nowrap; }
/* 悬停整块时，那句"会发生什么"亮起来 —— 这是"点得动"的暗示 */
.b-greet:hover .greet__cta,
.b-greet:focus-within .greet__cta { color: var(--accent); }

/* 演示控件：浮在角落，不参与布局 */
/*
 * 窄屏或矮屏无法把全部块塞进一屏，硬撑只会把内容压烂。
 * 这里退化为可滚动单列 —— 物理限制，不是设计取向。
 */
@media (max-width: 900px), (max-height: 620px) {
  /* 窄屏是文档流，不是一屏：栅格的行数交给内容决定 */
  .console { height: auto; min-height: 100dvh; overflow: visible; grid-template-rows: none; }
  .bar { flex-wrap: wrap; row-gap: var(--s2); }
  .bar__right { gap: var(--s2); }
  .stage { padding: var(--s4); }
  .canvas {
    height: auto;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: none;
    gap: var(--s4);
  }
  .canvas > * { grid-column: auto; grid-row: auto; }
  /* 窄屏：浮层不再玩"缩上去"那套 —— 触屏没有悬停，
     收起来就等于永远够不到。直接平铺在顶部，让内容从它下面开始。 */
  .chrome {
    position: static; pointer-events: auto;
    flex-direction: row; align-items: center; gap: var(--s3);
    padding: var(--s3) var(--s4) 0;
  }
  .chrome__hit { display: none; }
  .chrome__body { transform: none; visibility: visible; transition: none; }
  .chrome--right { justify-content: flex-end; }
}
</style>
