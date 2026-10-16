/** Shared authenticated transport for the retained developer module. */
import { BackendError } from './backend-client'
export const authToken = () => localStorage.getItem('zhiyin_token') || ''
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),60000)
  const requestToken=authToken()
  try {
    const headers=new Headers(options.headers)
    headers.set('Accept','application/json');headers.set('Authorization','Bearer '+requestToken)
    if(options.body && !(options.body instanceof FormData))headers.set('Content-Type','application/json')
    const response=await fetch('/api/v1'+path,{...options,headers,signal:controller.signal})
    if(authToken()!==requestToken)throw new BackendError('账号已变更，请重新读取。',1004)
    if(response.status===401)window.dispatchEvent(new Event('zhiyin:unauthorized'))
    const body=await response.json()
    if(authToken()!==requestToken)throw new BackendError('账号已变更，请重新读取。',1004)
    if(response.status!==401&&body.code===1004)window.dispatchEvent(new Event('zhiyin:unauthorized'))
    if(!response.ok||body.code!==0)throw new BackendError(body.message||'请求失败',body.code??response.status,body.trace_id)
    return body.data as T
  } catch (error) {
    if(error instanceof BackendError)throw error
    throw new BackendError(controller.signal.aborted?'请求超时，保存结果尚未确认。请重新读取记录后再决定是否重试。':'未收到完整的服务响应，保存结果尚未确认。请重新读取记录后再决定是否重试。',1007)
  } finally {clearTimeout(timeout)}
}
