/*
 * 门户的**排版参数** —— 文案不在这里。
 *
 * 这一页的文案（主张、按钮、地图上八站各自的标签与说明）全部来自后端
 * `GET /app/portal`（动态资源 `data/registry/copies.json` 的 `portal.*` 键）：
 * 改一句主张只改动态资源，不发前端版本。
 *
 * 这里留的是**只有前端才知道的东西**：每个点画在纸上的哪个坐标、
 * 字挂在圆圈的哪一边、倾斜多少度、圈多大、用什么色。
 * 把坐标也塞进后端，等于让文案编辑去调像素 —— 分工就乱了。
 */

export interface StopLayout {
  id: string
  x: number
  y: number
  /** 字放在圆圈的哪一边：相邻两站交替，字才不会挤在一起 */
  side?: 'above' | 'below'
  /** 圈的大小分档：起点要重、终点次之、路上其余轻 */
  rank?: 'anchor' | 'end' | 'plain'
  /** 批注离圈多远：不写死，按周围有什么东西来定 */
  off?: number
  /** 批注随曲线方向倾斜多少度（手写在纸上不会字字水平） */
  tilt?: number
  /** 这一点的法向（右下为正）：曲线每个点的方向都不一样，批注要跟着各自的方向挂 */
  nx?: number
  ny?: number
  tone: string
}

/** 手绘地图上的八站（用户视角，不是我们的业务流程）。文案按 id 从后端合并。 */
export const STOP_LAYOUT: StopLayout[] = [
  { id: 's1', x: 146, y: 828, side: 'below', rank: 'anchor', off: 54, tilt: -4, nx: 0.3, ny: 0.95, tone: 'var(--mk-green)' },
  { id: 's2', x: 392, y: 712, side: 'below', off: 62, tilt: 3, nx: 0.565, ny: 0.825, tone: 'var(--mk-orange)' },
  /* s3 / s4 落在被擦掉的那条带里：它们不是"被盖住"，是墨被擦没了 */
  { id: 's3', x: 556, y: 626, side: 'above', off: 66, tilt: -3, nx: 0.357, ny: 0.934, tone: 'var(--mk-blue)' },
  { id: 's4', x: 700, y: 578, side: 'below', off: 46, tilt: 2, nx: 0.196, ny: 0.981, tone: 'var(--mk-purple)' },
  { id: 's5', x: 856, y: 604, side: 'above', off: 58, tilt: -5, nx: -0.461, ny: 0.887, tone: 'var(--mk-teal)' },
  { id: 's6', x: 1010, y: 520, side: 'below', off: 44, tilt: 2, nx: 0.707, ny: 0.707, tone: 'var(--mk-orange)' },
  { id: 's7', x: 1160, y: 400, side: 'above', off: 52, tilt: -4, nx: 0.605, ny: 0.796, tone: 'var(--mk-pink)' },
  { id: 's8', x: 1330, y: 236, side: 'below', rank: 'end', off: 56, tilt: 3, nx: 0.719, ny: 0.694, tone: 'var(--mk-green)' },
]

/**
 * 那条线。坐标是**页面坐标**（1512×950），不是某个栏目的画布坐标。
 *
 * 它不是直线 —— 直线是制图，不是画画。这条线有四段呼吸：
 *   起：从左边缘偏下进来，斜率很缓（事情刚开始，走得慢）
 *   承：中段逐渐变陡（开始有节奏）
 *   转：在 700→856 之间**向下陷一次**（对应"方案被否了一次"）
 *   合：之后一路抬升，从右上角附近出去
 *
 * 两端都冲出纸面，而且都不在角上：入口在左边缘偏下，出口在右上角之外一点点。
 */
export const MAP_PATH =
  'M -80 900 C 40 868, 120 838, 215 812 C 300 788, 340 748, 392 712 ' +
  'C 448 674, 500 648, 556 626 C 610 606, 650 588, 700 578 ' +
  'C 760 566, 806 578, 856 604 C 906 630, 956 574, 1010 520 ' +
  'C 1064 466, 1108 440, 1160 400 C 1216 358, 1272 296, 1330 236 ' +
  'C 1380 186, 1442 -10, 1500 -140'

/** 圈第几行的第几个词 —— 版式判断，不是文案 */
export const CIRCLED = { line: 1, word: 1 }

/** 一条站点的**文案**（来自后端 `portal.stop.<id>.*`）。 */
export interface StopCopy {
  at?: string
  label?: string
  more?: string
}

/** 排版 + 文案合起来才是渲染要的那份。文案缺了就留空 —— 不编一句顶上。 */
export type PortalStop = StopLayout & { at: string; label: string; more: string }

export function mergeStops(copy: Record<string, StopCopy> = {}): PortalStop[] {
  return STOP_LAYOUT.map((layout) => ({
    ...layout,
    at: copy[layout.id]?.at ?? '',
    label: copy[layout.id]?.label ?? '',
    more: copy[layout.id]?.more ?? '',
  }))
}
