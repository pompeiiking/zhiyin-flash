/** Shared authenticated transport for the retained developer module. */
import { BackendError } from './backend-client'
export const authToken = () => localStorage.getItem('zhiyin_token') || ''
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),60000)
  try {
    const headers=new Headers(options.headers)
    headers.set('Accept','application/json');headers.set('Authorization','Bearer '+authToken())
    if(options.body && !(options.body instanceof FormData))headers.set('Content-Type','application/json')
    const response=await fetch('/api/v1'+path,{...options,headers,signal:controller.signal})
    const body=await response.json()
    if(response.status===401||body.code===1004)window.dispatchEvent(new Event('zhiyin:unauthorized'))
    if(!response.ok||body.code!==0)throw new BackendError(body.message||'请求失败',body.code??response.status,body.trace_id)
    return body.data as T
  } finally {clearTimeout(timeout)}
}
