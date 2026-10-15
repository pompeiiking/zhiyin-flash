import { ref, watch } from 'vue'
export const sessionCacheAvailable = ref(true)
const failedCaches = new Set<string>()
function availability(key: string, failed: boolean) { if(failed)failedCaches.add(key);else failedCaches.delete(key);sessionCacheAvailable.value=failedCaches.size===0 }
function identity() {
  try { let hash=0;for(const c of localStorage.getItem('zhiyin_token')??'')hash=(hash*31+c.charCodeAt(0))>>>0;return String(hash) }
  catch { return '' }
}
// Retain editable context over a failed lazy-load/reload; never restore authentication or busy flags.
export function rememberSession<T extends object>(key: string, state: T, keys: (keyof T)[]) {
  const storageKey='zhiyin-production-context-'+key
  try {
    const raw=sessionStorage.getItem(storageKey)
    if(raw){const saved=JSON.parse(raw);if(saved.identity===identity()&&saved.data&&typeof saved.data==='object')for(const k of keys){if(!Object.hasOwn(saved.data,k))continue;const value=saved.data[k],current=state[k];if(current===null ? value!==undefined : Array.isArray(current) ? Array.isArray(value) : typeof value===typeof current)state[k]=value}}
  } catch { availability(storageKey,true) }
  watch(state,()=>{
    try{sessionStorage.setItem(storageKey,JSON.stringify({identity:identity(),data:Object.fromEntries(keys.map(k=>[k,state[k]]))}));availability(storageKey,false)}
    catch{availability(storageKey,true)}
  },{deep:true,flush:'sync',immediate:true})
}
