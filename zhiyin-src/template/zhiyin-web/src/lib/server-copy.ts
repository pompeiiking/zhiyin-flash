import {auth} from './auth'
export function profileLabel(key:string,fallback:string){return auth.state.bootstrap?.copy_bundle?.[`profile.field.${key}`] || fallback}
export function badgeCopy(key:string,part:'label'|'how',fallback:string){return auth.state.bootstrap?.copy_bundle?.[`badge.${key}.${part}`] || fallback}
/**
 * 仓库词表登记过的画像字段键集合（不含别名）。
 *
 * 模型写的报告依据里会把裸键（interest、values、skills…）当普通词带出来；
 * 只有"键在词表里"的单词才该翻译成中文名，其余英文原样保留。
 */
export function knownProfileKeys(): Set<string> {
  const bundle = auth.state.bootstrap?.copy_bundle ?? {}
  return new Set(Object.keys(bundle)
    .filter(code => code.startsWith('profile.field.'))
    .map(code => code.slice('profile.field.'.length)))
}
/**
 * 模型文本里的画像裸键 → 中文名（两层：下划线键 + 词表内的单词键）。
 * 顺序约束：调用方应**先**做 studentizeRefs（消费 field:/evidence: 等带前缀
 * 记号），再调这里 —— 否则记号里的键会被这一层先拆坏。
 */
export function translateFieldKeys(text: string): string {
  const keys = knownProfileKeys()
  return text
    .replace(/\b[a-z]+(?:_[a-z]+)+\b/g, key => profileLabel(key, key))
    .replace(/\b[a-z][a-z0-9_]*\b/g, word => keys.has(word) ? profileLabel(word, word) : word)
}
