<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import SketchPath from '@/components/charts/SketchPath.vue'
import MapStopNode from '@/components/portal/MapStopNode.vue'
import { sCircle, sLine, sPath, sPolyline, sRect } from '@/lib/sketch'
import { MAP_PATH, mergeStops, type PortalStop, type StopCopy } from '@/data/portal'

/*
 * 地图上的文案不在这里 —— 由门户页（PortalView）从 `GET /app/portal` 取回后传进来。
 * 组件只负责"摆在哪儿、怎么画"，文案的唯一来源是动态资源。
 */
const props = withDefaults(defineProps<{ copy?: Record<string, StopCopy> }>(), { copy: () => ({}) })
const stops = computed(() => mergeStops(props.copy))

/*
 * 门户的墨层 —— 整张纸，不是某个栏目里的画布。
 *
 * ══ 性能（v14 重做） ═════════════════════════════════════════════
 *
 * 上一版卡在四个地方，全部改掉：
 *   ① 整页噪声遮罩 + 套在几百条笔画上的噪声滤镜 —— 每落一笔都要把整页重算一次。
 *      现在两者都拿掉：擦痕的毛边只留在静态的那一条上，写回来的笔画是干净的圆头。
 *   ② 几百条还原笔画各自成 <path>，还用下标当 key —— 数组一变整排重排。
 *      现在合并成**一条** path（一个 d 属性），而且不走数组响应式，直接拼字符串。
 *   ③ 每次 pointermove 都 getScreenCTM()（强制重排）+ 立刻写一笔。
 *      现在 CTM 缓存（只在尺寸变化时失效），并且每帧最多落一笔。
 *   ④ 笔尖小点每动一下都触发组件重渲染 —— 现在直接改 DOM 属性，不进响应式。
 * 笔迹的淡出也不再用几十个响应式节点：按透明度分四档，每档一条合并路径。
 *
 * ══ 线上不空（v14 加） ══════════════════════════════════════════
 *
 * 一条干净的线看着是空的。加了三种"制图痕迹"：
 *   · 底下一条虚线（同一条路径平移出去，虚线走）—— 手绘地图上常见的"足迹"
 *   · 沿线下缘一排长短不一的_**刻度**，像尺子，也像这条路的里程
 *   · 三枚很轻的箭头，标出方向（在空白最长的那几段）
 */
const W = 1512
const H = 950

/*
 * 擦痕：只擦过曲线中段这一截，垂直方向不再一路扯到纸边 ——
 * 上一版 reach=420，等于斜着把上半页也擦掉了，那一片看起来就"空"。
 */
const SWATH = { x: 1085, y: 460, angle: 49, half: 160, reach: 240 }

const STROKE_DIST = 12
/** 笔刷宽度：擦痕 480 宽，沿路横向两三笔就能整条扫回来 */
const RESTORE_W = 200
const PEN_W = 3.4
const INK_HOLD = 420
const INK_FADE = 780
const MAX_SEGMENTS = 360
const NODE_NEAR = 58
const STAY = 6000
/** 笔迹按新旧分四档：每档一条合并路径，比几十个节点便宜得多 */
const TRAIL_OPACITY = [1, 0.72, 0.44, 0.2]

const NODE_BLOB =
  'M -100 -6 C -96 -52, -54 -86, -4 -90 C 46 -94, 90 -64, 98 -18 ' +
  'C 106 30, 77 69, 27 84 C -21 98, -73 77, -94 36 C -102 19, -102 6, -100 -6 Z'

const ERASED = ['s6', 's7']

const svgEl = ref<SVGSVGElement | null>(null)
const nibEl = ref<SVGCircleElement | null>(null)

/* ── 不变的东西（响应式） ─────────────────────────────────────── */
const woken = ref<string[]>([])
const hoverId = ref<string | null>(null)
const writtenId = ref<string | null>(null)
const trail = ref<string[]>(['', '', '', ''])
/** 写回来的墨：一条合并路径。不走数组，直接拼字符串，省掉整排重排 */
const restoredD = ref('')

/* ── 会变但不该惊动 Vue 的东西（普通变量） ─────────────────────── */
let segments: string[] = []
let live: { d: string; born: number }[] = []
let raf = 0
let ctm: DOMMatrix | null = null
let ctmDirty = true
let activeUntil = 0
let last: { x: number; y: number } | null = null
let pressed = false

const isErased = (id: string) => ERASED.includes(id) && !woken.value.includes(id)
const byId = (id: string) => stops.value.find((s) => s.id === id)!
const wokenStops = computed(() => stops.value.filter((s) => woken.value.includes(s.id)))
const active = computed(() => hoverId.value ?? writtenId.value)
const current = computed(() => stops.value.find((s) => s.id === active.value) ?? null)

/* ── 那条线：三遍画出来 ─────────────────────────────────────────── */
const roadHalo = sPath(MAP_PATH, {
  seed: 2002, stroke: 'rgba(22,19,30,0.055)', strokeWidth: 14, roughness: 1.8, disableMultiStroke: true,
})
const road = sPath(MAP_PATH, { seed: 2001, stroke: 'var(--ink-1)', strokeWidth: 3.4, roughness: 1.15 })
const roadAgain = sPath(MAP_PATH, { seed: 2099, stroke: 'var(--ink-1)', strokeWidth: 1.9, roughness: 2.1, bowing: 2.2 })
/** 底下那条虚线：同一条路平移出去一点，就是"走过之后留下的足迹" */
const roadDash = sPath(MAP_PATH, { seed: 2033, stroke: 'var(--ink-1)', strokeWidth: 1.5, roughness: 2.4, disableMultiStroke: true })

/** 沿线下缘的一排刻度（长短不一，像手画的里程） */
const ticks = [
  ...sLine(141.6, 835.8, 145.0, 846.2, { seed: 2610, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(301.7, 786.7, 305.4, 797.0, { seed: 2611, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(472.2, 672.5, 476.9, 682.4, { seed: 2612, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(631.0, 596.9, 633.2, 607.7, { seed: 2613, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(769.2, 575.0, 767.4, 585.8, { seed: 2614, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(932.4, 574.4, 937.7, 584.1, { seed: 2615, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(1093.2, 451.9, 1100.1, 460.5, { seed: 2616, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sLine(1253.5, 323.7, 1261.0, 331.7, { seed: 2617, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
]

/** 三枚很轻的箭头，安在最长的那几段空白上 */
const arrows = [
  ...sPolyline([[328.2, 777.0], [336.6, 767.6], [324.2, 765.8]], { seed: 2620, stroke: 'var(--ink-3)', strokeWidth: 1.8 }),
  ...sPolyline([[617.3, 602.7], [626.9, 594.6], [614.9, 590.9]], { seed: 2621, stroke: 'var(--ink-3)', strokeWidth: 1.8 }),
  ...sPolyline([[899.4, 552.2], [906.2, 541.6], [893.6, 541.6]], { seed: 2622, stroke: 'var(--ink-3)', strokeWidth: 1.8 }),
].flat()

/*
 * 擦痕里原来还有三道很宽很淡的"橡皮拖痕"（想表现擦过的感觉）。
 * 实际读出来就是三道莫名其妙的浅色粗线，去掉 —— 一个人用手擦过纸，
 * 纸上是不会留下三道等距宽线的。
 */
const crumbs = [
  ...sPath('M -240 -140 C -230 -146, -218 -142, -222 -134', { seed: 2411, stroke: 'rgba(120,105,80,0.3)', strokeWidth: 1.8 }),
  ...sPath('M 120 145 C 130 139, 142 143, 138 151', { seed: 2412, stroke: 'rgba(120,105,80,0.26)', strokeWidth: 1.7 }),
  ...sPath('M 300 -142 C 310 -148, 322 -144, 318 -136', { seed: 2413, stroke: 'rgba(120,105,80,0.22)', strokeWidth: 1.6 }),
]

/* ── 挂在线上、散在纸上的东西 ───────────────────────────────────── */
const card = [
  ...sRect(505, 554, 190, 104, { seed: 2140, stroke: 'var(--mk-green)', strokeWidth: 2.4, fill: 'var(--n-1)' }),
  ...sLine(527, 596, 660, 596, { seed: 2141, stroke: 'var(--ink-2)', strokeWidth: 2 }),
  ...sLine(527, 622, 618, 622, { seed: 2142, stroke: 'var(--line-3)', strokeWidth: 1.6 }),
  ...sPath('M 640 616 L 652 628 L 672 600', { seed: 2143, stroke: 'var(--mk-green)', strokeWidth: 3 }),
]
const bubble = [
  ...sPath(
    'M 155 232 C 155 222, 163 216, 175 216 L 255 216 C 267 216, 275 222, 275 232 ' +
      'L 275 292 C 275 302, 267 308, 255 308 L 195 308 L 172 328 L 177 308 L 175 308 ' +
      'C 163 308, 155 302, 155 292 Z',
    { seed: 2160, stroke: 'var(--mk-teal)', strokeWidth: 2.2, fill: 'var(--n-1)' },
  ),
  ...sLine(173, 240, 255, 240, { seed: 2161, stroke: 'var(--mk-teal)', strokeWidth: 1.6 }),
  ...sLine(173, 260, 228, 260, { seed: 2162, stroke: 'var(--mk-teal)', strokeWidth: 1.6 }),
]
const timetable = [
  ...sRect(515, 438, 110, 64, { seed: 2101, stroke: 'var(--mk-blue)', strokeWidth: 2 }),
  ...sLine(515, 466, 625, 466, { seed: 2102, stroke: 'var(--mk-blue)', strokeWidth: 1.4 }),
  ...sLine(552, 438, 552, 502, { seed: 2103, stroke: 'var(--mk-blue)', strokeWidth: 1.4 }),
  ...sLine(589, 438, 589, 502, { seed: 2104, stroke: 'var(--mk-blue)', strokeWidth: 1.4 }),
]
const review = [
  ...sPolyline([[130, 196], [204, 142], [262, 172], [332, 86], [404, 120]], { seed: 2130, stroke: 'var(--mk-pink)', strokeWidth: 2.8 }),
  ...sCircle(404, 120, 5, { seed: 2131, stroke: 'none', fill: 'var(--mk-pink)' }),
]
const flag = [
  ...sLine(250, 640, 250, 716, { seed: 2110, stroke: 'var(--mk-orange)', strokeWidth: 2.4 }),
  ...sPath('M 252 642 L 326 658 L 252 682 Z', { seed: 2111, stroke: 'var(--mk-orange)', strokeWidth: 2, fill: 'var(--mk-orange-soft)' }),
]
const doc = [
  ...sPath('M 120 430 L 178 430 L 206 458 L 206 534 L 120 534 Z', { seed: 2150, stroke: 'var(--mk-orange)', strokeWidth: 2.2, fill: 'var(--n-1)' }),
  ...sLine(178, 430, 178, 458, { seed: 2151, stroke: 'var(--mk-orange)', strokeWidth: 1.8 }),
  ...sLine(178, 458, 206, 458, { seed: 2152, stroke: 'var(--mk-orange)', strokeWidth: 1.8 }),
  ...sLine(134, 476, 186, 476, { seed: 2153, stroke: 'var(--ink-2)', strokeWidth: 1.5 }),
  ...sLine(134, 494, 172, 494, { seed: 2154, stroke: 'var(--line-3)', strokeWidth: 1.4 }),
  ...sPath('M 134 512 L 142 520 L 160 500', { seed: 2155, stroke: 'var(--mk-green)', strokeWidth: 2.6 }),
]
const portfolio = [
  ...sRect(620, 264, 86, 104, { seed: 2120, stroke: 'var(--mk-purple)', strokeWidth: 2 }),
  ...sRect(630, 254, 86, 104, { seed: 2121, stroke: 'var(--mk-purple)', strokeWidth: 2 }),
  ...sRect(640, 244, 86, 104, { seed: 2122, stroke: 'var(--mk-purple)', strokeWidth: 2, fill: 'var(--n-1)' }),
  ...sLine(656, 274, 708, 274, { seed: 2123, stroke: 'var(--mk-purple)', strokeWidth: 1.6 }),
  ...sLine(656, 294, 692, 294, { seed: 2124, stroke: 'var(--mk-purple)', strokeWidth: 1.6 }),
]
const branch = [
  ...sPath('M 516 322 L 556 300', { seed: 2170, stroke: 'var(--mk-orange)', strokeWidth: 2.4 }),
  ...sPath('M 556 300 L 598 278', { seed: 2171, stroke: 'var(--mk-orange)', strokeWidth: 2.4 }),
  ...sPath('M 556 300 L 602 328', { seed: 2172, stroke: 'rgba(120,105,80,0.45)', strokeWidth: 2, disableMultiStroke: true }),
  ...sCircle(556, 300, 4.5, { seed: 2173, stroke: 'none', fill: 'var(--mk-orange)' }),
]
/*
 * 收藏：一枚书签。上一版这里是三根柱子（岗位对比），
 * 它是整页唯一一个图表形状，和手绘语言不搭 —— 换成书签，
 * 也正好对上旁边那句话"你收藏过，材料一直没交"。
 */
const bookmark = [
  ...sPath('M -19 -32 L 19 -32 L 19 32 L 0 17 L -19 32 Z', {
    seed: 2189, stroke: 'var(--mk-orange)', strokeWidth: 2.2, fill: 'var(--mk-orange-soft)',
  }),
]
/** 近两周的节奏：14 个格子，亮着的 5 格是有动作的那几天（左下角那一块） */
const week = Array.from({ length: 14 }, (_, i) =>
  sRect(-106 + (i % 7) * 30, -26 + Math.floor(i / 7) * 30, 22, 22, {
    seed: 2500 + i,
    stroke: [1, 4, 5, 9, 12].includes(i) ? 'var(--mk-green)' : 'var(--ink-4)',
    strokeWidth: 1.7,
    fill: [1, 4, 5, 9, 12].includes(i) ? 'var(--mk-green-soft)' : 'none',
  }),
).flat()
/** 已迈出第一步：一枚实心标记，把左下角压住（那一块原来全是浅色线条，看着空） */
const stamp = [
  ...sCircle(0, 0, 26, { seed: 2194, stroke: 'var(--mk-green)', strokeWidth: 2, fill: 'var(--mk-green)' }),
  ...sPath('M -12 2 L -3 11 L 13 -9', { seed: 2194, stroke: 'var(--n-0)', strokeWidth: 4 }),
]
/** 材料清单：三条，勾了两条（也在下半页，给左下那条边配重） */
const checklist = [
  ...sRect(-72, -22, 14, 14, { seed: 2180, stroke: 'var(--mk-green)', strokeWidth: 1.7 }),
  ...sPath('M -69 -15 L -65 -11 L -59 -20', { seed: 2181, stroke: 'var(--mk-green)', strokeWidth: 2.2 }),
  ...sLine(-46, -15, 44, -15, { seed: 2182, stroke: 'var(--ink-2)', strokeWidth: 1.5 }),
  ...sRect(-72, -2, 14, 14, { seed: 2183, stroke: 'var(--mk-green)', strokeWidth: 1.7 }),
  ...sPath('M -69 5 L -65 9 L -59 0', { seed: 2184, stroke: 'var(--mk-green)', strokeWidth: 2.2 }),
  ...sLine(-46, 5, 22, 5, { seed: 2185, stroke: 'var(--ink-2)', strokeWidth: 1.5 }),
  ...sRect(-72, 18, 14, 14, { seed: 2186, stroke: 'var(--line-3)', strokeWidth: 1.7 }),
  ...sLine(-46, 25, -6, 25, { seed: 2187, stroke: 'var(--line-3)', strokeWidth: 1.4 }),
]
/** 今天：一张小日历，日子被圈住（左下角那一簇里的"重物"） */
const today = [
  ...sRect(-40, -34, 80, 68, { seed: 2195, stroke: 'var(--mk-purple)', strokeWidth: 2, fill: 'var(--n-1)' }),
  ...sLine(-40, -14, 40, -14, { seed: 2196, stroke: 'var(--mk-purple)', strokeWidth: 1.5 }),
  ...sCircle(-8, 10, 15, { seed: 2197, stroke: 'var(--mk-green)', strokeWidth: 2.4 }),
  ...sLine(-18, 8, 2, 8, { seed: 2198, stroke: 'var(--ink-3)', strokeWidth: 1.5 }),
  ...sLine(-18, 20, -6, 20, { seed: 2199, stroke: 'var(--ink-3)', strokeWidth: 1.5 }),
]
const specks = [
  sCircle(248, 172, 8, { seed: 2201, stroke: 'var(--mk-teal)', strokeWidth: 1.8 }),
  sCircle(760, 118, 7, { seed: 2202, stroke: 'var(--mk-yellow)', strokeWidth: 1.8 }),
  sCircle(1080, 780, 6, { seed: 2203, stroke: 'var(--mk-purple)', strokeWidth: 1.8 }),
  sCircle(1428, 620, 6, { seed: 2204, stroke: 'var(--mk-teal)', strokeWidth: 1.8 }),
  sCircle(30, 140, 6, { seed: 2205, stroke: 'var(--mk-blue)', strokeWidth: 1.8 }),
  sCircle(980, 884, 6, { seed: 2206, stroke: 'var(--mk-pink)', strokeWidth: 1.8 }),
  sLine(640, 300, 690, 282, { seed: 2207, stroke: 'var(--mk-blue)', strokeWidth: 1.8 }),
  sLine(700, 880, 750, 862, { seed: 2208, stroke: 'var(--mk-orange)', strokeWidth: 1.8 }),
  sPolyline([[1250, 520], [1275, 502], [1300, 520]], { seed: 2209, stroke: 'var(--mk-yellow)', strokeWidth: 1.8 }),
  sPolyline([[860, 884], [884, 868], [908, 884]], { seed: 2210, stroke: 'var(--mk-teal)', strokeWidth: 1.8 }),
].flat()

const doodles = computed(() => [
  /* 上方那一片：复盘折线、一次对话、岗位对比、作品集 —— 原来这里只有空白 */
  { key: 'review', ops: review, at: 0.42, cx: 266, cy: 150, tx: 740, ty: 170, rot: -6, scale: 0.8 },
  { key: 'bubble', ops: bubble, at: 0.48, cx: 215, cy: 262, tx: 1000, ty: 150, rot: -8, scale: 1 },
  { key: 'bookmark', ops: bookmark, at: 0.54, cx: 0, cy: 0, tx: 1180, ty: 132, rot: 4, scale: 1 },
  { key: 'portfolio', ops: portfolio, at: 0.6, cx: 673, cy: 304, tx: 1420, ty: 380, rot: -5, scale: 1 },
  /* 左下角：起点那一站的旁边，插上截止旗 */
  { key: 'week', ops: week, at: 0.6, cx: 0, cy: 0, tx: 156, ty: 706, rot: -2, scale: 1.05 },
  { key: 'today', ops: today, at: 0.63, cx: 0, cy: 0, tx: 310, ty: 706, rot: 3, scale: 1 },
  { key: 'flag', ops: flag, at: 0.66, cx: 288, cy: 678, tx: 200, ty: 800, rot: -3, scale: 1.1 },
  { key: 'stamp', ops: stamp, at: 0.7, cx: 0, cy: 0, tx: 360, ty: 848, rot: -6, scale: 1 },
  { key: 'checklist', ops: checklist, at: 0.72, cx: 0, cy: 0, tx: 620, ty: 770, rot: 2, scale: 1 },
  { key: 'doc', ops: doc, at: 0.75, cx: 163, cy: 482, tx: 470, ty: 838, rot: 6, scale: 1 },
  /* 擦痕里：写过去才会出现的两件 */
  { key: 'card', ops: card, at: 0.82, cx: 600, cy: 606, tx: 783, ty: 703, rot: -16, scale: 1 },
  { key: 'timetable', ops: timetable, at: 0.88, cx: 570, cy: 470, tx: 1196, ty: 588, rot: 5, scale: 1 },
  { key: 'branch', ops: branch, at: 0.94, cx: 558, cy: 310, tx: 960, ty: 720, rot: -4, scale: 1 },
])

const still = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const swathTransform = `translate(${SWATH.x} ${SWATH.y}) rotate(${SWATH.angle})`

/*
 * 擦痕的形状：在 JS 里算成一条**静态路径**，不用 SVG 滤镜。
 *
 * 上一版这里挂的是 feTurbulence + feDisplacementMap：每落一笔，
 * 浏览器都要在整页范围重算一次噪声位移 —— 实测掉到 1 帧/秒。
 * 现在把毛边直接算进点里（两个正弦叠加一层细噪声），一次算好，之后不再动。
 */
const swathPath = (() => {
  const halfW = SWATH.reach
  const halfH = SWATH.half
  const edge = (t: number, phase: number) =>
    (Math.sin(t * 6.1 + phase) * 0.5 + Math.sin(t * 13.7 + phase * 2.3) * 0.3 + Math.sin(t * 27.3 + phase * 3.7) * 0.2)
  const pts: string[] = []
  const long = 34
  const short = 14
  // 一条长边 → 一条短边 → 一条长边 → 一条短边，闭合成形
  for (let i = 0; i <= long; i++) {
    const t = i / long
    pts.push(`${(-halfW + 2 * halfW * t).toFixed(1)} ${(-halfH + edge(t, 0.7) * 11).toFixed(1)}`)
  }
  for (let i = 1; i <= short; i++) {
    const t = i / short
    pts.push(`${(halfW + edge(t, 2.1) * 11).toFixed(1)} ${(-halfH + 2 * halfH * t).toFixed(1)}`)
  }
  for (let i = 1; i <= long; i++) {
    const t = i / long
    pts.push(`${(halfW - 2 * halfW * t).toFixed(1)} ${(halfH + edge(t, 3.9) * 11).toFixed(1)}`)
  }
  for (let i = 1; i < short; i++) {
    const t = i / short
    pts.push(`${(-halfW + edge(t, 5.3) * 11).toFixed(1)} ${(halfH - 2 * halfH * t).toFixed(1)}`)
  }
  return 'M ' + pts.join(' L ') + ' Z'
})()

/** 屏幕坐标 → 纸上的坐标。CTM 只在尺寸变化时重算，不再每次移动都问一次 */
function toPaper(x: number, y: number) {
  const svg = svgEl.value
  if (!svg) return null
  if (ctmDirty || !ctm) {
    ctm = svg.getScreenCTM()
    ctmDirty = false
  }
  if (!ctm) return null
  const inv = ctm.inverse()
  return { x: inv.a * x + inv.c * y + inv.e, y: inv.b * x + inv.d * y + inv.f }
}

function onPaper(e: PointerEvent) {
  const el = e.target as Element | null
  if (!el || typeof el.closest !== 'function') return false
  if (!el.closest('.paper')) return false
  return !el.closest('.wordmark, .kicker, .claim, .lede, .cta, .tip, button')
}

/*
 * 把还没干的笔墨按新旧分成四档（一档一条合并路径）。
 * 写的时候立刻算一次（rAF 被节流时也能马上看到笔迹），之后由帧循环继续推。
 */
function rebucket(now: number) {
  const buckets = ['', '', '', '']
  live = live.filter((s) => {
    const age = now - s.born
    if (age > INK_HOLD + INK_FADE) return false
    const k = age <= INK_HOLD ? 0 : Math.min(3, 1 + Math.floor(((age - INK_HOLD) / INK_FADE) * 3))
    buckets[k] += s.d
    return true
  })
  trail.value = buckets
}

/** 每帧：让笔迹继续变淡，并让写到的那一站到点说话 */
function tick() {
  const now = performance.now()
  if (!still()) rebucket(now)
  if (writtenId.value && now > activeUntil) writtenId.value = null
  raf = live.length || writtenId.value ? requestAnimationFrame(tick) : 0
}

function wake() {
  if (still()) return
  if (!raf) raf = requestAnimationFrame(tick)
}

function writeAt(p: { x: number; y: number }, force = false) {
  const now = performance.now()
  if (!last) {
    last = p
    return
  }
  if (!force && Math.hypot(p.x - last.x, p.y - last.y) < STROKE_DIST) return

  const seg = `M ${last.x.toFixed(1)} ${last.y.toFixed(1)} L ${p.x.toFixed(1)} ${p.y.toFixed(1)} `
  segments.push(seg)
  if (segments.length > MAX_SEGMENTS) segments.shift()
  restoredD.value = segments.join('')      // 一条 path，不排数组
  live.push({ d: seg, born: now })
  rebucket(now)
  last = p

let near: PortalStop | null = null
  let best = NODE_NEAR
    for (const s of stops.value) {
    const dist = Math.hypot(p.x - s.x, p.y - s.y)
    if (dist < best) {
      best = dist
      near = s
    }
  }
  if (near && isErased(near.id)) {
    if (!woken.value.includes(near.id)) woken.value = [...woken.value, near.id]
    writtenId.value = near.id
    activeUntil = now + STAY
  } else if (writtenId.value && Math.hypot(p.x - byId(writtenId.value).x, p.y - byId(writtenId.value).y) > 220) {
    writtenId.value = null
  }
  wake()
}

/*
 * 落笔是同步的 —— 不做 rAF 节流。
 * 一开始我按"每帧最多一笔"写，结果在 rAF 被节流的窗口里（浏览器对不可见/被遮挡的
 * 窗口会把 rAF 压到 1Hz）用户几乎写不出字。现在的单次代价已经很小：
 * 一次字符串拼接 + 一次属性更新，画画本身由浏览器合并到帧里。
 */
function handleMove(e: PointerEvent) {
  if (!onPaper(e)) {
    if (nibEl.value) nibEl.value.setAttribute('opacity', '0')
    last = null
    return
  }
  const p = toPaper(e.clientX, e.clientY)
  if (!p) return
  /* 笔尖直接改 DOM，不进响应式 —— 每动一下重渲染整块模板太贵 */
  const n = nibEl.value
  if (n) {
    n.setAttribute('cx', p.x.toFixed(1))
    n.setAttribute('cy', p.y.toFixed(1))
    n.setAttribute('r', pressed ? '3.1' : '2.4')
    n.setAttribute('opacity', '1')
  }
  writeAt(p)
}

function onMove(e: PointerEvent) {
  handleMove(e)
}

function onDown(e: PointerEvent) {
  if (!onPaper(e)) return
  pressed = true
  const p = toPaper(e.clientX, e.clientY)
  if (!p) return
  last = { x: p.x - 2, y: p.y - 2 }
  writeAt(p, true)
}

function onUp() {
  pressed = false
  last = null
}

function onLeaveWindow() {
  onUp()
  if (nibEl.value) nibEl.value.setAttribute('opacity', '0')
}

function onEnter(s: PortalStop) {
  if (isErased(s.id)) {
    if (!woken.value.includes(s.id)) woken.value = [...woken.value, s.id]
    writtenId.value = s.id
    activeUntil = performance.now() + STAY
    wake()
  } else {
    hoverId.value = s.id
  }
}

function onLeaveStop(s: PortalStop) {
  if (!isErased(s.id)) hoverId.value = null
}

function pick(s: PortalStop) {
  if (isErased(s.id)) {
    if (!woken.value.includes(s.id)) woken.value = [...woken.value, s.id]
    writtenId.value = s.id
    activeUntil = performance.now() + STAY
    wake()
  } else {
    hoverId.value = hoverId.value === s.id ? null : s.id
  }
}

/* 监听挂在 window 上（纸上的任何移动都是一笔），但每帧只处理一次 */
let ro: ResizeObserver | null = null
onMounted(() => {
  window.addEventListener('pointermove', onMove, { passive: true })
  window.addEventListener('pointerdown', onDown, { passive: true })
  window.addEventListener('pointerup', onUp, { passive: true })
  window.addEventListener('blur', onLeaveWindow)
  if (svgEl.value) {
    ro = new ResizeObserver(() => (ctmDirty = true))
    ro.observe(svgEl.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerdown', onDown)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('blur', onLeaveWindow)
  ro?.disconnect()
  if (raf) cancelAnimationFrame(raf)
})
</script>

<template>
  <div class="ink">
    <svg
      ref="svgEl"
      class="ink__svg"
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="整张纸上的一条路：从左边偏下进来，一路弯到右上角。中间那一段被擦掉了，用笔写过去就会回来。"
    >
      <defs>
        <!--
          被擦掉的那一片：白 = 墨留着，黑 = 墨没了。
          边界是一条算好的静态路径（没有滤镜）。

          注意 mask 的范围必须是整页：上一版为了省渲染把它收到擦痕那一块，
          结果遮罩区域**外**的内容全被裁掉了 —— 曲线左半段整个消失。
          滤镜拿掉之后，整页遮罩的代价已经可以接受（只在落笔时重算，不是每帧）。
        -->
        <mask id="erased" maskUnits="userSpaceOnUse" x="0" y="0" :width="W" :height="H">
          <rect :width="W" :height="H" fill="#fff" />
          <g :transform="swathTransform">
            <path :d="swathPath" fill="#000" />
          </g>
          <!-- 写回来的墨：一条合并路径，没有任何滤镜 -->
          <path
            :d="restoredD"
            :stroke-width="RESTORE_W"
            fill="none"
            stroke="#fff"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            v-for="s in wokenStops"
            :key="`wk-${s.id}`"
            :transform="`translate(${s.x} ${s.y})`"
            :d="NODE_BLOB"
            fill="#fff"
          />
        </mask>

        <clipPath id="swathClip" clipPathUnits="userSpaceOnUse">
          <rect
            :transform="swathTransform"
            :x="-SWATH.reach" :y="-SWATH.half"
            :width="SWATH.reach * 2" :height="SWATH.half * 2"
          />
        </clipPath>

      </defs>

      <!-- 会留墨的一切：擦痕盖住的地方不画 -->
      <g mask="url(#erased)">
        <SketchPath :ops="roadHalo" />
        <SketchPath :ops="road" class="road" />
        <g class="repass"><SketchPath :ops="roadAgain" /></g>
        <g class="trail-marks">
          <SketchPath :ops="roadDash" class="dash" />
          <SketchPath :ops="ticks" />
          <SketchPath :ops="arrows" />
        </g>

        <g
          v-for="d in doodles"
          :key="d.key"
          class="doodle"
          :style="{ animationDelay: `${0.5 + d.at}s` }"
        >
          <g :transform="`translate(${d.tx} ${d.ty}) rotate(${d.rot}) scale(${d.scale}) translate(${-d.cx} ${-d.cy})`">
            <SketchPath :ops="d.ops" />
          </g>
        </g>

        <g class="specks"><SketchPath :ops="specks" /></g>

        <MapStopNode
          v-for="(s, i) in stops"
          :key="s.id"
          :stop="s"
          :index="i"
          :active="active === s.id"
          :erased="isErased(s.id)"
          :interactive="!isErased(s.id)"
          :nx="s.nx"
          :ny="s.ny"
          @enter="onEnter(s)"
          @leave="onLeaveStop(s)"
          @pick="pick(s)"
        />
      </g>

      <!--
        纸上的小字批注：是真的数据，不是装饰。
        （原来这一组里还有一条"呈现 0.77 → 0.83"压在复盘折线旁边 ——
        那是七维评分，读者在这一页还不需要它，拿掉。）
      -->
      <g class="notes">
        <text class="note" x="300" y="848">后天截止</text>
        <text class="note" x="360" y="700">近两周 · 5 天有动作</text>
      </g>

      <!-- 擦不干净的印子 -->
      <g class="residue" clip-path="url(#swathClip)">
        <path class="residue__road" :d="MAP_PATH" fill="none" stroke="var(--ink-1)" stroke-width="3" />
      </g>

      <!-- 笔尖上还没干的那条线：四档透明度 = 四条路径，不再有几十个节点 -->
      <g class="pen">
        <path
          v-for="(d, i) in trail"
          :key="`t-${i}`"
          :d="d"
          :stroke-width="PEN_W"
          :opacity="TRAIL_OPACITY[i]"
          fill="none"
          stroke="var(--ink-1)"
          stroke-linecap="round"
        />
        <circle ref="nibEl" class="pen__nib" r="2.4" opacity="0" />
      </g>

      <g class="crumbs" :transform="swathTransform"><SketchPath :ops="crumbs" /></g>
    </svg>

    <!-- 写到哪一站，那一站说一句 -->
    <transition name="tip">
      <p v-if="current" class="tip" :style="{ color: current.tone }">
        <span class="tip__at">{{ current.at }}</span>
        {{ current.more }}
      </p>
    </transition>
  </div>
</template>

<style scoped>
/*
 * 墨层铺满整张纸，但**不吃指针**：只有站点自己重新打开指针事件。
 * 写字用的是 window 上的监听，所以纸上的空白处照样能写。
 */
.ink { position: absolute; inset: 0; pointer-events: none; z-index: 1; }
.ink__svg { width: 100%; height: 100%; display: block; overflow: visible; }
.ink :deep(.stop) { pointer-events: auto; }
.ink :deep(.stop[data-erased]) { pointer-events: none; }

.road :deep(path) {
  stroke-dasharray: 1; stroke-dashoffset: 1;
  animation: road-draw 2800ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes road-draw { to { stroke-dashoffset: 0; } }
/* 复笔：后画、淡一点，和主笔错开的地方就是手画的痕迹 */
.repass { opacity: 0; animation: repass-in 900ms var(--mo-out) 2.6s forwards; }
.repass :deep(path) { opacity: 0.42; }
@keyframes repass-in { from { opacity: 0 } to { opacity: 1 } }
/* 线上的"制图痕迹"：虚线足迹 + 里程刻度 + 方向箭头 */
.trail-marks { opacity: 0; animation: repass-in 900ms var(--mo-out) 1.4s forwards; }
.trail-marks .dash :deep(path) { opacity: 0.22; stroke-dasharray: 1.5 8; }
.trail-marks :deep(path) { opacity: 0.7; }

.doodle, .specks { opacity: 0; animation: pop-in 700ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
.specks { animation-delay: 1.2s; }
@keyframes pop-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }

.notes { opacity: 0; animation: pop-in 700ms var(--mo-out) 1.6s forwards; }
/*
 * 纸上的批注（"后天截止""近两周 · 5 天有动作"）。
 * 12px 的中文在这个尺度上偏小：笔画密的字会糊。提到 12.5px、字重 500、
 * 颜色从 --ink-3 提到 --ink-2 —— 它压在擦痕和曲线旁边，本来就不容易看清。
 */
.note {
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 500;
  fill: var(--ink-2);
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

.residue { opacity: 0; animation: residue-in 900ms var(--mo-out) 2s forwards; }
.residue__road { opacity: 0.15; }
@keyframes residue-in { from { opacity: 0 } to { opacity: 1 } }

.pen__nib { fill: var(--ink-1); }
.crumbs { opacity: 0; animation: pop-in 700ms var(--mo-out) 2.3s forwards; }

.tip {
  /* 底栏拿掉之后，这一句可以坐到纸的下边缘上（原来要给它让出 96px） */
  position: absolute; right: var(--s7); bottom: var(--s5);
  max-width: 34ch; text-align: right;
  display: flex; align-items: baseline; gap: var(--s3); justify-content: flex-end;
  /* 它是一整句要说的话，不是标签：15px 起，行高放松 */
  font-size: 15px; letter-spacing: 0.01em; line-height: 1.8;
}
/*
 * 站点说话时左边那个时间标记（"现在""周三""08:40"）。
 * 它原来吃 .mono（等宽）：数字好看，中文落到新宋体 —— 一屏两个字体。
 * 现在字体交给 --font-mono 里的中文字族，尺寸跟着正文小一档、字重实一点。
 */
.tip__at {
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--ink-2);
  flex: 0 0 auto;
}
.tip-enter-active { transition: opacity 240ms var(--mo-out), transform 300ms var(--mo-spring); }
.tip-leave-active { transition: opacity 140ms var(--mo-in); }
.tip-enter-from, .tip-leave-to { opacity: 0; transform: translateY(6px); }

@media (prefers-reduced-motion: reduce) {
  .road :deep(path), .doodle, .specks, .notes, .residue, .crumbs, .repass, .trail-marks { animation: none; opacity: 1; stroke-dashoffset: 0; }
}
</style>
