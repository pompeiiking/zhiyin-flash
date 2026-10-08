import { ref } from 'vue'
import rough from 'roughjs'

/*
 * 手绘图形生成器。
 *
 * 全部图表都从这里取形状：rough 会把手画的抖动、不闭合、粗细不匀算好，
 * 我们只拿它算出来的 path，交给 Vue 去渲染（不在组件里命令式操作 DOM）。
 *
 * 关键一点：**seed 固定**。rough 默认每次调用都重新随机，
 * 数据一变重渲染，整张图会跟着抖一次 —— 那不是手绘感，是闪烁。
 */

const gen = rough.generator()

/*
 * 手绘系数 —— 全站手绘只有这一个总闸。
 *
 * `roughness` 本来是每个调用点各写各的（那是每张图自己的笔触性格，**不要动**），
 * 这里是在它外面再乘一层：**所有** op 的 roughness 都乘这个系数
 * （sLine / sRect / sCircle / sPath → sPolyline 最终也落到 sLine）。
 * 所以一次 setRoughnessScale() 就能把全站手绘从"手抖"变成"工程线"。
 *
 * 谁改它：`lib/theme.ts` 的「线条：手绘 ↔ 精确」轴 —— 切完 data-draw 之后
 * 读回 `--sketch-rough`（默认档没有文件、读不到，就是 1），再调这里。
 * 改完一定要 bumpSketch()，否则算在 setup 顶层的 ops 不会重算。
 */
let roughScale = 1

/** 设定手绘系数：非有限值或负数一律落回 1（与"认不出的档落回默认档"同一口径） */
export function setRoughnessScale(scale: number) {
  roughScale = Number.isFinite(scale) && scale >= 0 ? scale : 1
}

/** 当前系数，供调试/断言用 */
export function roughnessScale(): number {
  return roughScale
}

/*
 * 手绘系数的变化版本号。
 *
 * 有些组件的形状是**算一次就定住**的（原先是 setup 顶层的 `const road = sPath(...)`），
 * 系数变了它们不会自己重算。那些组件把这一组 ops 包进 computed 并 `void sketchTick.value`，
 * 再由这里 bump 一下 —— 当场生效，不用刷新。
 */
export const sketchTick = ref(0)

/** 系数变了就 bump 一次；顶层算 ops 的组件会跟着重算 */
export function bumpSketch() {
  sketchTick.value++
}

export interface SketchOpts {
  seed?: number
  stroke?: string
  fill?: string
  strokeWidth?: number
  roughness?: number
  bowing?: number
  fillStyle?: 'hachure' | 'solid' | 'zigzag' | 'cross-hatch' | 'dots' | 'dashed'
  hachureGap?: number
  fillWeight?: number
  curveStepCount?: number
  disableMultiStroke?: boolean
}

/** 一条可以直接塞进 <path d> 的绘制指令 */
export interface SketchOp {
  d: string
  stroke: string
  fill: string
  strokeWidth: number
}

interface RawPath {
  d: string
  stroke?: string
  fill?: string
  strokeWidth?: number
}

const DEFAULTS: Required<Pick<SketchOpts, 'seed' | 'stroke' | 'fill' | 'strokeWidth' | 'roughness' | 'bowing'>> = {
  seed: 7,
  stroke: 'currentColor',
  fill: 'none',
  strokeWidth: 1.7,
  roughness: 1.15,
  bowing: 1.4,
}

function toOps(raw: RawPath[], opts: SketchOpts): SketchOp[] {
  return raw.map((p) => ({
    d: p.d,
    stroke: p.stroke ?? opts.stroke ?? DEFAULTS.stroke,
    fill: p.fill ?? opts.fill ?? DEFAULTS.fill,
    strokeWidth: p.strokeWidth ?? opts.strokeWidth ?? DEFAULTS.strokeWidth,
  }))
}

const seedOf = (n: number, extra = 0) => Math.abs(Math.round(n * 31 + extra * 7 + 13)) % 900 + 11

export function sLine(x1: number, y1: number, x2: number, y2: number, o: SketchOpts = {}): SketchOp[] {
  const drawable = gen.line(x1, y1, x2, y2, {
    roughness: (o.roughness ?? DEFAULTS.roughness) * roughScale,
    bowing: o.bowing ?? DEFAULTS.bowing,
    stroke: o.stroke ?? DEFAULTS.stroke,
    strokeWidth: o.strokeWidth ?? DEFAULTS.strokeWidth,
    seed: o.seed ?? seedOf(x1 + y1 + x2 + y2),
    disableMultiStroke: o.disableMultiStroke,
  })
  return toOps(gen.toPaths(drawable) as RawPath[], o)
}

export function sRect(x: number, y: number, w: number, h: number, o: SketchOpts = {}): SketchOp[] {
  const drawable = gen.rectangle(x, y, w, h, {
    roughness: (o.roughness ?? 1) * roughScale,
    bowing: o.bowing ?? 1.6,
    stroke: o.stroke ?? DEFAULTS.stroke,
    fill: o.fill,
    fillStyle: o.fillStyle ?? 'solid',
    hachureGap: o.hachureGap,
    fillWeight: o.fillWeight,
    strokeWidth: o.strokeWidth ?? DEFAULTS.strokeWidth,
    seed: o.seed ?? seedOf(x + y + w + h),
  })
  return toOps(gen.toPaths(drawable) as RawPath[], o)
}

export function sCircle(cx: number, cy: number, r: number, o: SketchOpts = {}): SketchOp[] {
  const drawable = gen.circle(cx, cy, r * 2, {
    roughness: (o.roughness ?? 1.1) * roughScale,
    stroke: o.stroke ?? DEFAULTS.stroke,
    fill: o.fill,
    fillStyle: o.fillStyle ?? 'solid',
    fillWeight: o.fillWeight,
    hachureGap: o.hachureGap,
    strokeWidth: o.strokeWidth ?? DEFAULTS.strokeWidth,
    seed: o.seed ?? seedOf(cx + cy + r),
  })
  return toOps(gen.toPaths(drawable) as RawPath[], o)
}

export function sPath(d: string, o: SketchOpts = {}): SketchOp[] {
  const drawable = gen.path(d, {
    roughness: (o.roughness ?? 1.1) * roughScale,
    stroke: o.stroke ?? DEFAULTS.stroke,
    fill: o.fill,
    fillStyle: o.fillStyle ?? 'solid',
    fillWeight: o.fillWeight,
    strokeWidth: o.strokeWidth ?? DEFAULTS.strokeWidth,
    seed: o.seed ?? seedOf(d.length),
  })
  return toOps(gen.toPaths(drawable) as RawPath[], o)
}

/** 折线（不填充）：把点连成一条手画的线 */
export function sPolyline(points: [number, number][], o: SketchOpts = {}): SketchOp[] {
  return points.slice(1).flatMap((p, i) => {
    const prev = points[i]
    return sLine(prev[0], prev[1], p[0], p[1], { ...o, seed: (o.seed ?? 7) + i * 3 })
  })
}

/** 折线转成平滑路径（Catmull-Rom → 三次贝塞尔），手绘感更强 */
export function smoothPath(points: [number, number][], tension = 0.42): string {
  if (points.length < 2) return ''
  let d = `M${points[0][0]},${points[0][1]}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2] ?? p2
    const c1x = p1[0] + (p2[0] - p0[0]) * tension * 0.5
    const c1y = p1[1] + (p2[1] - p0[1]) * tension * 0.5
    const c2x = p2[0] - (p3[0] - p1[0]) * tension * 0.5
    const c2y = p2[1] - (p3[1] - p1[1]) * tension * 0.5
    d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`
  }
  return d
}
