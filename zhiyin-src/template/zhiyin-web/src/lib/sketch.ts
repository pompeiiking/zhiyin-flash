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
    roughness: o.roughness ?? DEFAULTS.roughness,
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
    roughness: o.roughness ?? 1,
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
    roughness: o.roughness ?? 1.1,
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
    roughness: o.roughness ?? 1.1,
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
