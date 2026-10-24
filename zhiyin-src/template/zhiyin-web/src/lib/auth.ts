import { reactive, readonly } from 'vue'
import { BackendError, backendClient } from '../api/backend-client'
import type { BootstrapView } from '../api/backend-types'
import { demo } from '../store'

const state = reactive({ ready: false, bootstrap: null as BootstrapView | null, error: '' })
let boot: Promise<boolean> | null = null
let generation = 0
let retryTimer: ReturnType<typeof setTimeout> | undefined
let retryCount = 0
export function token() { try { return localStorage.getItem('zhiyin_token') ?? '' } catch { return '' } }

/**
 * 网络/服务暂时不可用 ≠ 未登录。
 *
 * 传输层把超时、断网、非 JSON 响应都收敛成 1007；服务端真正判定登录失效时会派发
 * `zhiyin:unauthorized`（并让 `generation` 前进），所以走到这里还保持 generation 的，
 * 只剩"服务暂时够不着"这一种情况。此时**不能清 token、不能退回门户未登录**。
 */
function transientFailure(error: unknown) {
  if (!(error instanceof BackendError)) return true
  return ![401, 403].includes(error.code)
}
function localAccount() {
  // 上次登录成功时 store 会把账号名落到 localStorage；用它原地恢复登录态，
  // 账号名没变时 `demo.signIn` 不会重置工作区数据（草稿、会话都保留）。
  return demo.state.account
}
function scheduleTransientRetry() {
  if (retryTimer || retryCount >= 2) return
  const delay = retryCount === 0 ? 4000 : 12000
  retryCount++
  retryTimer = setTimeout(async () => {
    retryTimer = undefined
    if (!token() || state.bootstrap) return
    const ok = await auth.restore()
    if (!ok || !state.bootstrap) { if (token()) scheduleTransientRetry(); return }
    retryCount = 0
    // 恢复成功后把壳层数据补上，页面不用等用户手动刷新。
    try {
      const { loadShell } = await import('./system-data')
      void loadShell()
    } catch { /* 壳层数据交给页面自己的重试入口 */ }
  }, delay)
}
function clearTransientRetry() {
  if (retryTimer) clearTimeout(retryTimer)
  retryTimer = undefined
  retryCount = 0
}

export const auth = { state: readonly(state),
  async restore() {
    if (!token()) { state.ready = true; return false }
    if (state.bootstrap) return true
    if (boot) return boot
    const requestToken=token()
    const requestGeneration=generation
    boot = (async () => {
      try {
        const bootstrap = await backendClient.bootstrap()
        if(token()!==requestToken || requestGeneration!==generation)return false
        state.bootstrap = bootstrap; state.error = ''
        demo.signIn(state.bootstrap.identity?.nickname || state.bootstrap.identity?.user_id || state.bootstrap.identity?.account || '当前用户', true)
        retryCount = 0
        return true
      } catch (e) {
        // 请求期间确实被登出（401/403）或被别的账号接管：按未登录处理。
        if (requestGeneration !== generation || token() !== requestToken) return false
        if (transientFailure(e)) {
          // 保留 token 与登录态，只把错误留在 state.error；壳层由页面自己展示可重试提示。
          state.error = '资料暂时读取失败：网络或服务暂时不可用。登录状态已保留，可重试。'
          demo.signIn(localAccount(), true)
          scheduleTransientRetry()
          return true
        }
        state.error = e instanceof Error ? e.message : '服务暂时不可用'
        return false
      }
      finally { if(requestGeneration===generation){state.ready = true; boot = null} }
    })()
    return boot
  },
  async login(mode: 'login' | 'register', account: string, password: string) {
    const result = await backendClient.authenticate(mode, { account, password })
    localStorage.setItem('zhiyin_token', result.token)
    generation++; boot=null
    state.bootstrap = null
    if (!await auth.restore()) throw new Error(state.error)
  },
  async logout() {
    // A failed revocation must not be presented as successful server logout.
    await backendClient.logout()
    auth.expire()
  },
  expire() {
    generation++
    clearTransientRetry()
    localStorage.removeItem('zhiyin_token'); localStorage.removeItem('zhiyin-demo-auth')
    state.bootstrap = null; state.ready = true;boot=null; state.error = ''
    window.dispatchEvent(new Event('zhiyin:session-cleared'))
    demo.signOut()
  },
}
window.addEventListener('zhiyin:unauthorized', () => auth.expire())
window.addEventListener('storage', event => { if (event.key === 'zhiyin_token') window.location.reload() })

/**
 * 开发者/管理员角色判定：工具页的开发者模块目录与 WorkflowRunner 共用这一份。
 * 学生账号看不到这些入口 —— 运行已发布流程是管理操作（流程编号要管理员给），
 * 模块目录与执行记录对 学生只有困惑没有动作（深度测试 D2 的结论）。
 */
export function isDeveloperRole(): boolean {
  return ['admin', 'developer'].includes(auth.state.bootstrap?.identity?.role ?? '')
}
