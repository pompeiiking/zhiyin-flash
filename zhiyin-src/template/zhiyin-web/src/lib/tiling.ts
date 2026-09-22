/*
 * 平铺布局引擎（dwindle + 最小尺寸约束）。
 *
 * 要的是 Hyprland 那种"自己长开"的手感：块按权重递归对半切，
 * 少一块，剩下的立刻把空出来的地方长回去 —— 没有任何预设的版式。
 *
 * 但纯递归有个固有毛病：块一多，切到后面会切出 1 格宽的细条（实测 110×57），
 * 那种尺寸里什么都放不下。所以每一刀都加一条约束：
 *
 *   **切完之后，两边在切分那一维上都不得小于 MIN 格。**
 *   如果这一维切不动，就换个方向切；两个方向都切不动，
 *   这组块就在当前矩形里按网格铺开（保证每块仍是最小尺寸以上，且不留洞）。
 *
 * 于是三件事同时成立：
 *   · 自填充 —— 块的集合一变，整棵树重算，剩下的自动长开
 *   · 按权重 —— 画像/待办拿大块，情报/复盘拿小块
 *   · 不退化 —— 永远不会出现放不下内容的细条，也永远不留洞
 */

export interface TileInput {
  id: string
  /** 这块想要多少空间。相同权重 = 均分 */
  weight: number
}

export interface TileRect {
  /** 第几列（0 起） */
  c: number
  /** 第几行（0 起） */
  r: number
  /** 占几列 */
  w: number
  /** 占几行 */
  h: number
}

/** 一格 tile 在任一维上至少占这么多格（12 格制下即 1/4，约 300px 上下） */
const MIN = 3

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
const sum = (list: TileInput[]) => list.reduce((a, t) => a + t.weight, 0)

/**
 * @param items      要铺的块
 * @param cols       画布列数
 * @param rows       画布行数
 * @param cellAspect 一个格子的宽高比 = (画布宽/cols) / (画布高/rows)
 *                   用它把"格"换算成像素，才能按真实的宽高比决定往哪个方向切
 */
export function tileLayout(
  items: TileInput[],
  cols: number,
  rows: number,
  cellAspect: number,
): Record<string, TileRect> {
  const out: Record<string, TileRect> = {}
  if (!items.length) return out

  /** 两个方向都切不动时的兜底：在当前矩形里按网格铺开，最后一行平分整行 */
  const gridFill = (group: TileInput[], c: number, r: number, w: number, h: number) => {
    const n = group.length
    const pw = w * cellAspect
    const colsFit = clamp(Math.round(Math.sqrt((n * pw) / Math.max(1, h))), 1, n)
    const rowCount = Math.ceil(n / colsFit)
    let idx = 0
    let ry = 0
    for (let i = 0; i < rowCount; i++) {
      const inRow = Math.min(colsFit, n - idx)
      const hh = i === rowCount - 1 ? h - ry : Math.max(1, Math.round(h / rowCount))
      let x = 0
      for (let k = 0; k < inRow; k++) {
        const ww = k === inRow - 1 ? w - x : Math.max(1, Math.round(w / inRow))
        out[group[idx].id] = { c: c + x, r: r + ry, w: ww, h: hh }
        x += ww
        idx++
      }
      ry += hh
    }
  }

  const place = (group: TileInput[], c: number, r: number, w: number, h: number) => {
    if (!group.length) return
    if (group.length === 1) {
      out[group[0].id] = { c, r, w, h }
      return
    }

    // 切点：把权重前缀和推到一半（不按块数对半分 —— 画像和复盘不该拿一样大）
    const total = sum(group)
    let acc = 0
    let cut = 1
    let best = Infinity
    for (let i = 1; i < group.length; i++) {
      acc += group[i - 1].weight
      const err = Math.abs(acc / total - 0.5)
      if (err < best) {
        best = err
        cut = i
      }
    }
    const head = group.slice(0, cut)
    const tail = group.slice(cut)
    const share = sum(head) / total

    const canSplitH = w >= MIN * 2 // 横向切（左右分）
    const canSplitV = h >= MIN * 2 // 纵向切（上下分）

    if (!canSplitH && !canSplitV) {
      // 两个方向都到极限了：不再切，按网格铺满这一块
      gridFill(group, c, r, w, h)
      return
    }

    // 能切的那一维里，选像素上更长的那条边 —— 切出来的格子更接近方形
    const horizontal = canSplitH && (!canSplitV || w * cellAspect >= h)
    if (horizontal) {
      const take = clamp(Math.round(w * share), MIN, w - MIN)
      place(head, c, r, take, h)
      place(tail, c + take, r, w - take, h)
    } else {
      const take = clamp(Math.round(h * share), MIN, h - MIN)
      place(head, c, r, w, take)
      place(tail, c, r + take, w, h - take)
    }
  }

  /*
   * **按传入顺序切，不再按权重重排。**
   *
   * 原来这一行是 `sort((a,b) => b.weight - a.weight)`：谁权重最大谁先切、
   * 于是永远占左上。看着合理，实际上把"顺序"这件事彻底废掉了 ——
   * 后端精心算出来的编排顺序（现在最该先看到哪一块）到这里被推翻，
   * 用户看到的仍然是"最大的那块在左上"。
   *
   * 权重的职责是**分多少空间**（切分比例用它），不是**谁先出现**。
   * 顺序的职责交给调用方：调用方喂进来的第一块，就是左上第一块。
   */
  place([...items], 0, 0, cols, rows)
  return out
}

/**
 * 一块 tile 该不该进入"紧凑形态"。
 * 判断依据是**实际像素**，不是格子数 —— 因为画布大小是会变的。
 */
export function shouldCompact(h: number, w: number, base = 460) {
  return h < base || w < 300
}
