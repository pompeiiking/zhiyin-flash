import { reactive, readonly } from 'vue'
import { backendClient } from '../api/backend-client'
import type { BootstrapView } from '../api/backend-types'

const state = reactive({ ready: false, bootstrap: null as BootstrapView | null, error: '' })
let boot: Promise<boolean> | null = null
export function token() { try { return localStorage.getItem('zhiyin_token') ?? '' } catch { return '' } }
export const auth = { state: readonly(state),
  async restore() {
    if (!token()) { state.ready = true; return false }
    if (state.bootstrap) return true
    if (boot) return boot
    const requestToken=token()
    boot = (async () => {
      try {
        state.bootstrap = await backendClient.bootstrap(); state.error = ''
        const { demo } = await import('../store')
        if(token()!==requestToken)return false
        demo.signIn(state.bootstrap.identity?.nickname || state.bootstrap.identity?.user_id || state.bootstrap.identity?.account || '当前用户', true)
        return true
      } catch (e) { state.error = e instanceof Error ? e.message : '服务暂时不可用'; return false }
      finally { state.ready = true; boot = null }
    })()
    return boot
  },
  async login(mode: 'login' | 'register', account: string, password: string) {
    const result = await backendClient.authenticate(mode, { account, password })
    localStorage.setItem('zhiyin_token', result.token)
    state.bootstrap = null
    if (!await auth.restore()) throw new Error(state.error)
  },
  async logout() {
    // A failed revocation must not be presented as successful server logout.
    await backendClient.logout()
    auth.expire()
  },
  expire() {
    localStorage.removeItem('zhiyin_token'); localStorage.removeItem('zhiyin-demo-auth')
    state.bootstrap = null; state.ready = true;boot=null
    void import('./system-data').then(({clearSystemData})=>clearSystemData())
    void import('../store').then(({ demo }) => demo.signOut())
  },
}
window.addEventListener('zhiyin:unauthorized', () => auth.expire())
window.addEventListener('storage', event => { if (event.key === 'zhiyin_token') window.location.reload() })
