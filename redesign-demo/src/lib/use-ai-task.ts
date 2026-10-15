import { onUnmounted, ref, shallowRef, watch } from 'vue'
import { streamBackend } from '../api/backend-stream'
import { BackendError } from '../api/backend-client'
import type { AiResult } from '../api/ai-types'
import type operations from '../api/operations.json'
import { backendDemo } from './backend-demo'
import { validAiData } from '../api/validate-ai'
export function useAiTask<T>() {
  const result = shallowRef<AiResult<T> | null>(null), busy = ref(false), error = ref(''), progress = ref('')
  let controller: AbortController | null = null
  let serial = 0
  async function run(key: keyof typeof operations, options: { params?: Record<string, string>; arg?: string | number } = {}) {
    if (busy.value) return
    const request = ++serial
    controller = new AbortController(); busy.value = true; error.value = ''; progress.value = '正在核对已有资料…'
    try {
      const data = await streamBackend<AiResult<T>>(key, { ...options, signal: controller.signal }, frame => {
        if (request === serial) progress.value = frame.note || frame.text || '正在整理结果…'
      })
      if (!data || !validAiData(key,data.data) || !Array.isArray(data.citations) || !data.meta || !data.citations.every(c=>c&&typeof c.source==='string'&&typeof c.detail==='string')) throw new Error('Incomplete result')
      if (request === serial) { result.value = data; progress.value = '已取得本次结果。' }
      return data
    } catch (reason) {
      if (request === serial && !controller.signal.aborted) error.value = reason instanceof BackendError && (reason.code === 1004 || reason.code === 401) ? '登录已过期，请重新登录后重试。原内容仍保留。' : '暂时没有取得结果，请重试。已有内容和输入仍保留。'
    } finally { if (request === serial) busy.value = false }
  }
  function cancel() { serial++; controller?.abort(); busy.value = false; progress.value = '已停止本次生成，已有内容仍保留。' }
  watch(()=>backendDemo.state.dataMode,()=>{cancel();result.value=null;error.value=''})
  onUnmounted(cancel)
  return { result, busy, error, progress, run, cancel }
}
