/** AI endpoints return progress/result/error frames, not JSON page data. */
import operations from './operations.json'
import { BackendError } from './backend-client'
export type StreamProgress = { pct?: number; note?: string; text?: string; agent?: string; stage?: string; protocol?: number; type?: string; step_id?: string; sequence?: number; run_id?: string }
export async function streamBackend<T>(
  key: keyof typeof operations,
  options: { params?: Record<string, string>; arg?: string | number; body?: unknown; signal?: AbortSignal },
  onProgress: (frame: StreamProgress) => void,
): Promise<T> {
  const operation = operations[key]
  if (!('stream' in operation && operation.stream)) throw new Error('This operation is not an SSE task.')
  const path = operation.path.replace(/\{(\w+)\}/g, (_match, name: string) => {
    const value = options.params?.[name]
    if (value === undefined) throw new Error('Missing path parameter: ' + name)
    return encodeURIComponent(value)
  })
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (options.signal?.aborted) controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  let timedOut = false
  const timeoutAbort = () => { timedOut = true; controller.abort() }
  let idle = setTimeout(timeoutAbort, 20_000)
  const total = setTimeout(timeoutAbort, 180_000)
  const headers: Record<string, string> = { Accept: 'text/event-stream', 'Content-Type': 'application/json' }
  try { const token = localStorage.getItem('zhiyin_token'); if (token) headers.Authorization = 'Bearer ' + token } catch { /* request without a persisted token */ }
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  const ensureSameAccount = () => {
    if (headers.Authorization !== (localStorage.getItem('zhiyin_token') ? 'Bearer ' + localStorage.getItem('zhiyin_token') : undefined)) throw new BackendError('账号已变更，请重新生成。', 1004)
  }
  try {
    const arg = options.arg ?? (key === 'dayAdvice' ? -new Date().getTimezoneOffset() : '')
    const response = await fetch('/api/v1' + path, { method: operation.method, headers, signal: controller.signal, body: JSON.stringify(options.body ?? { arg }) })
    ensureSameAccount()
    if (!response.ok || !response.headers.get('content-type')?.includes('text/event-stream')) {
      const body = await response.json().catch(() => null) as { code?: number; message?: string; trace_id?: string } | null
      ensureSameAccount()
      if (response.status === 401 || body?.code === 1004) window.dispatchEvent(new Event('zhiyin:unauthorized'))
      throw new BackendError(body?.message || '这次生成没有接上，请稍后重试。', body?.code ?? response.status, body?.trace_id)
    }
    reader = response.body?.getReader()
    if (!reader) throw new BackendError('这次没有收到生成结果，请重试。', 1007)
    const decoder = new TextDecoder()
    let buffer = ''
    let result: T | undefined
    let finished = false
    function consume(block: string) {
      ensureSameAccount()
      const data = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
      if (!data) return
      const frame = JSON.parse(data) as StreamProgress & { error?: { code: number; message: string }; result?: T }
      if (frame.error) { if (frame.error.code === 1004) window.dispatchEvent(new Event('zhiyin:unauthorized')); throw new BackendError(frame.error.message, frame.error.code, response.headers.get('X-Trace-Id') ?? '') }
      if (Object.hasOwn(frame, 'result')) { result = frame.result; finished = true }
      else onProgress(frame)
    }
    while (true) {
      const chunk = await reader.read()
      clearTimeout(idle); idle = setTimeout(timeoutAbort, 60_000)
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''
      blocks.forEach(consume)
      if (chunk.done) { if (buffer.trim()) consume(buffer); break }
    }
    if (!finished) throw new BackendError('生成结束了，但没有收到完整结果，请重试。', 1007)
    if (headers.Authorization !== (localStorage.getItem('zhiyin_token') ? 'Bearer ' + localStorage.getItem('zhiyin_token') : undefined)) throw new BackendError('账号已变更，请重新生成。', 1004)
    return result as T
  } catch (error) {
    if (error instanceof BackendError) throw error
    throw new BackendError(
      timedOut
        ? '生成超时了，本次没有收到完整结果，请重试。'
        : controller.signal.aborted
          ? '生成已停止，可保留输入后重试。'
          : '生成中途断开了，请重新尝试。',
      1007,
    )
  } finally {
    clearTimeout(idle); clearTimeout(total)
    options.signal?.removeEventListener('abort', abort)
    await reader?.cancel().catch(() => undefined)
  }
}
