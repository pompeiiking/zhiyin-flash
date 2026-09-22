/*
 * AI 生成内容 · 契约层。
 *
 * 界面上绝大多数的文字和图表都是模型算出来的，不是写死的。所以"AI 生成"这件事
 * 必须有一个明确的接口，而不是每个组件各自写 loading：
 *
 *   一次生成 = 一个 AiTask
 *     · key      稳定标识（同一份内容不会重复生成、可以缓存、可以预取）
 *     · label    界面上显示的一句话："正在比对你的画像与岗位差距"
  *     · arg      要给后端的输入（只有需要用户填东西的端点用得上）
  *   进度文案（"想到哪了"）不在这里：它是后端的动态资源，按 key 取。
  *   前端不写 prompt、不拼依据、也不自备一份产出。
 *   一次生成的过程 = AiProgress 流
 *   一次生成的结果 = AiResult<T>（数据永远和依据绑在一起）
 *
 * 后端接上来的时候，只需要实现一个 AiProvider —— 前端一个组件都不用改。
 */

export type AiState = 'idle' | 'thinking' | 'streaming' | 'done' | 'error'

/** 一条依据。生成出来的任何结论都必须能挂上它 */
export interface AiCitation {
  source: string
  detail: string
  confidence?: number
  at?: string
  origin?: string
}

/** 生成过程中的一次播报 */
export interface AiProgress {
  /** 0–1 */
  pct: number
  /** 这一步在做什么（显示成一行小字） */
  note?: string
  /** 正在往外写的文字（流式） */
  text?: string
}

export interface AiMeta {
  /** 谁生成的（模型或角色名） */
  by: string
  at: string
  ms: number
  /** 命中缓存：同样的输入没必要重算 */
  cached: boolean
}

export interface AiResult<T> {
  data: T
  citations: AiCitation[]
  meta: AiMeta
  /** 一句话说清这次是怎么算出来的 */
  rationale?: string
}

export interface AiTask<T> {
  key: string
  label: string
  /**
   * 传给后端的参数。只有需要用户输入的端点才用得上 ——
   * 例如学信网核验要带那串在线验证码；其余任务为空。
   */
  arg?: string
}

export interface AiProvider {
  name: string
  run<T>(task: AiTask<T>, emit: (p: AiProgress) => void): Promise<AiResult<T>>
  /**
   * 同一个任务的上一份产出。**按 task 找，不按 key 找**：
   * 学信网核验这类任务的 key 是固定的、内容随 `arg`（那串验证码）变，
   * 只按 key 去找会把上一次的核验结果当成这一次的。
   */
  cached<T>(task: AiTask<T>): AiResult<T> | null
}
