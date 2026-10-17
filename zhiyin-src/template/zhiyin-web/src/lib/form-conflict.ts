export function rebaseForm<T extends object>(draft:T, original:T, latest:T):T {
  const merged = {...latest}
  for(const key of Object.keys(draft) as (keyof T)[]) {
    if(JSON.stringify(draft[key])!==JSON.stringify(original[key]))merged[key]=draft[key]
  }
  return merged
}
export function conflictRows<T extends object>(draft:T, original:T, latest:T, labels:Record<string,string>) {
  const format=(value:unknown):string=>value===true?'开启':value===false?'关闭':value==null||value===''?'未填写':Array.isArray(value)?value.map(item=>typeof item==='object'?Object.values(item).join(' · '):String(item)).join('；'):String(value)
  return (Object.keys(draft) as (keyof T)[]).filter(key=>JSON.stringify(draft[key])!==JSON.stringify(original[key])).map(key=>({label:labels[String(key)]??'设置内容',mine:format(draft[key]),latest:format(latest[key])}))
}
