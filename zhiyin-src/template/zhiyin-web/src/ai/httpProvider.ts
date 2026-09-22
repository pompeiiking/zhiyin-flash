import type { AiProgress, AiProvider, AiResult, AiTask } from './types'
import { aiPath } from './registry'
import { authToken } from '@/api/client'

/*
 * 真后端 Provider —— 联调用。
 *
 * 传输约定（与后端 /api/v1 对齐，见 docs/职引-完整设计文档.md）：
 *   POST {aiPath(key)}   Accept: text/event-stream
 *   SSE 事件流：data: {"pct":..,"note":..,"text":..}   ← 进度/中间态/流式增量
 *              data: {"result": {data, citations, meta, rationale}}  ← 终帧
 *   响应信封遵循 ApiResponse：{ code, message, data, trace_id }，
 *   code !== 0 视为业务错误，走 error。
 *
 * **不回落本地假数据**：服务不可达或任务失败时如实抛出，界面显示错误。
 * 之前的回落会在服务挂掉时端出一份像模像样的假内容 ——
 * 那正是"看起来都对、其实没依据"的来源。
 */

/**
 * 一次会话里的产出缓存。
 *
 * 键必须带上 `arg`：学信网核验的 key 恒为 `bind.chsi`，而变化的是用户填的
 * 那串在线验证码。只按 key 存，换了验证码再核一次会**直接端出上一次的结果** ——
 * 用户看到"核验通过"却是别人的／上一次的学籍，这是本仓最不能有的那种错。
 */
const memory = new Map<string, AiResult<unknown>>()

const cacheKey = (task: AiTask<unknown>) =>
  task.arg ? `${task.key}|${task.arg}` : task.key

async function* sseEvents(res: Response): AsyncGenerator<any> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (line) yield JSON.parse(line.slice(5).trim())
    }
  }
}

export const httpProvider: AiProvider = {
  name: 'http',

  cached<T>(task: AiTask<T>) {
    return (memory.get(cacheKey(task)) as AiResult<T> | undefined) ?? null
  },

  async run<T>(task: AiTask<T>, emit: (p: AiProgress) => void): Promise<AiResult<T>> {
    const started = performance.now()
    let res: Response
    const token = authToken()
    /*
     * 请求必须可超时。
     * 之前这条 fetch 没有超时：后端挂住（网关黑洞 / LLM 不回）时连接永远不落，
     * 界面停在"正在生成"—— 用户看到的就是"点开就卡死"。
     * 90 秒足够任何正常生成跑完；到点如实报错，给"重算一次"让路。
     */
    const abort = new AbortController()
    const timer = window.setTimeout(() => abort.abort(), 90_000)
    try {
      res = await fetch(aiPath(task.key), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          // 鉴权打开之后 AI 端点同样要带令牌，否则一律 401
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        // arg 是给需要用户输入的端点用的（目前只有学信网核验：在线验证码）
        body: JSON.stringify({ key: task.key, arg: task.arg ?? '' }),
        signal: abort.signal,
      })
    } catch (cause) {
      throw new Error((cause as Error)?.name === 'AbortError' ? '生成等了太久，先放弃了 —— 稍后再试一次。' : '暂时连不上服务，请稍后再试。')
    } finally {
      window.clearTimeout(timer)
    }
    if (!res.ok) {
      throw new Error(`这一步没成功（HTTP ${res.status}），请稍后再试。`)
    }
    // 非流式响应 = 后端返回了 ApiResponse JSON（如 code=1007 facade 未装配），
    // 这是业务错误，如实抛出，不回落 mock —— 联调期要看见真实失败
    if (!(res.headers.get('content-type') ?? '').includes('text/event-stream')) {
      const env = await res.json().catch(() => null)
      throw new Error(env?.message || `这一步没成功（HTTP ${res.status}），请稍后再试。`)
    }

    let out: AiResult<T> | null = null
    // 流式读取的**空闲看门狗**：只要还有帧进来就续期；彻底没声了 60 秒就掐线报错。
    let watchdog = window.setTimeout(() => abort.abort(), 60_000)
    try {
      for await (const ev of sseEvents(res)) {
        window.clearTimeout(watchdog)
        watchdog = window.setTimeout(() => abort.abort(), 60_000)
        // 流里的 error 帧（如 code=1002 画像中没有该缺口）同样如实抛出，
        // 不能悄悄吞掉 —— 吞掉就变成"点了没反应"。
        if (ev.error) throw new Error(ev.error.message || '这一步没成功，请稍后再试。')
        if (ev.result) {
          out = ev.result
        } else {
          emit({ pct: ev.pct ?? 0, note: ev.note, text: ev.text })
        }
      }
    } catch (cause) {
      if ((cause as Error)?.name === 'AbortError') {
        throw new Error('生成中途没了响应 —— 稍后再试一次。')
      }
      throw cause
    } finally {
      window.clearTimeout(watchdog)
    }
    if (!out) throw new Error('这一步没有得到结果，请重试。')

    /*
     * 时长用**后端算的那一个**（`meta.ms` 是它真正花在生成上的毫秒）。
     * 拿浏览器这边的往返时间顶上去会把"命中缓存"写成一次几百毫秒的"刚算完"——
     * 界面上就出现了明明是缓存、却谎报"1 条依据 · 0s"的徽标。
     * 后端没给（老版本回包）才退回本地计时，并且这时候不能说它命中了缓存。
     */
    const elapsed = Math.round(performance.now() - started)
    out.meta = out.meta?.ms
      ? out.meta
      : { ...out.meta, ms: elapsed, cached: false }
    memory.set(cacheKey(task), out)
    return out
  },
}

