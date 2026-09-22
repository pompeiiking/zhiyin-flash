import { onBeforeUnmount, ref, shallowRef } from 'vue'
import { httpProvider } from './httpProvider'
import type { AiCitation, AiMeta, AiProgress, AiState, AiTask } from './types'

/*
 * 把"一次生成"包成一个可以在组件里直接用的东西。
 *
 * 它管四件事，组件不用再各写一遍：
 *   1. 状态机：idle → thinking → streaming → done / error
 *   2. 缓存：同一个 key 第二次打开直接用上次结果（cached 标记会亮），不重算
 *   3. 中断：组件卸载后到达的进度直接丢掉，不会去改一个已经不存在的界面
 *   4. 重算：invalidate 之后同一个 key 会重新生成（用户补了信息就该重算）
 */
export interface UseAiTaskOptions {
  /** 挂载后自动开始 */
  auto?: boolean
}

export function useAiTask<T>(make: () => AiTask<T>, options: UseAiTaskOptions = { auto: true }) {
  const state = ref<AiState>('idle')
  const data = shallowRef<T | null>(null)
  const citations = ref<AiCitation[]>([])
  const meta = ref<AiMeta | null>(null)
  const rationale = ref('')
  const pct = ref(0)
  const note = ref('')
  const streamed = ref('')
  const error = ref<string | null>(null)

  let alive = true
  let running = false

  const apply = (p: AiProgress) => {
    if (!alive) return
    pct.value = p.pct
    if (p.note) note.value = p.note
    if (p.text) streamed.value += p.text
  }

  async function run(force = false) {
    const task = make()
    if (running && !force) return
    running = true

    const provider = httpProvider
    const hit = force ? null : provider.cached<T>(task)
    if (hit) {
      // 命中缓存：直接到位，但仍然标一下"这是算过的"
      data.value = hit.data
      citations.value = hit.citations
      meta.value = { ...hit.meta, cached: true }
      rationale.value = hit.rationale ?? ''
      pct.value = 1
      state.value = 'done'
      running = false
      return
    }

    state.value = 'thinking'
    error.value = null
    streamed.value = ''
    pct.value = 0
    try {
      const res = await provider.run(task, apply)
      if (!alive) return
      data.value = res.data
      citations.value = res.citations
      meta.value = res.meta
      rationale.value = res.rationale ?? ''
      state.value = 'done'
    } catch (e) {
      if (!alive) return
      error.value = e instanceof Error ? e.message : String(e)
      state.value = 'error'
    } finally {
      running = false
    }
  }

  const retry = () => run(true)

  onBeforeUnmount(() => {
    alive = false
  })

  if (options.auto !== false) void run()

  return {
    state, data, citations, meta, rationale, pct, note, streamed, error,
    run, retry,
    streaming: () => state.value === 'thinking' || state.value === 'streaming',
  }
}
