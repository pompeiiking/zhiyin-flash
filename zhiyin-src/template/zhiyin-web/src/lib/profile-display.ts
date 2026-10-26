/** 画像的纯展示口径（不依赖 Vue，便于 node:test 直接验证）。 */

export function humanProfileValue(value: unknown): string {
  if (value == null) return '尚待补充'
  if (Array.isArray(value)) return value.map(humanProfileValue).join('、')
  if (typeof value === 'object') return Object.values(value).map(humanProfileValue).join('；')
  return String(value)
}

/**
 * 画像一行显示什么。
 *
 * 兴趣/职业关注的 `value` 只放正向项；否定项留在 `attributes.items` 里（#40）。
 * 纯否定偏好的 value 是空数组，所以展示必须把 items 里不在 value 中的条目也列出来，
 * 否则用户刚说的"不喜欢…"在画像页上完全看不到。
 */
export function profileDisplayValue(
  value: unknown,
  attributes?: Readonly<Record<string, unknown>> | null,
): string {
  const rawItems = attributes?.items
  const items = Array.isArray(rawItems) ? rawItems : []
  if (!items.length) return humanProfileValue(value)
  const values = Array.isArray(value) ? value.map(String) : []
  const itemValues = items
    .map(item => item && typeof item === 'object' ? String((item as Record<string, unknown>).value ?? '') : '')
    .filter(itemValue => itemValue && !values.includes(itemValue))
  return [...values, ...itemValues].map(itemValue => {
    const attrs = items.find(item => item && typeof item === 'object' && (item as Record<string, unknown>).value === itemValue)
    return [
      itemValue,
      attrs ? profileAttributeSummary(Object.fromEntries(Object.entries(attrs).filter(([key]) => key !== 'value'))) : '',
    ].filter(Boolean).join('：')
  }).join('、')
}

export function profileAttributeSummary(attributes: Readonly<Record<string, unknown>>): string {
  const choices: Record<string, Record<string, string>> = {
    polarity: { like: '喜欢', dislike: '不喜欢', unsure: '还不确定' },
    state: { exploring: '正在了解', considering: '正在考虑', selected: '已选择' },
    evidence_kind: { exposed: '接触过', self_assessed: '本人自评', completed_once: '完成过一次', work_output: '有作品或成果', verified: '有核验依据' },
  }
  const labels: Record<string, string> = {
    context: '情境', outcome: '结果', scope: '适用范围', title: '说明',
    derived_from: '推算依据', derived_on: '推算日期',
  }
  return Object.entries(attributes).flatMap(([key, value]) => {
    if (['polarity', 'state'].includes(key) && Array.isArray(attributes.items) && attributes.items.length) return []
    if (key === 'items' && Array.isArray(value)) return value.flatMap(item => {
      if (!item || typeof item !== 'object') return []
      const labels = [choices.polarity?.[item.polarity], choices.state?.[item.state]].filter(Boolean)
      return labels.length ? [`${item.value}：${labels.join('，')}`] : []
    })
    if (typeof value !== 'string' || !value.trim()) return []
    const choice = choices[key]?.[value]
    return choice ? [choice] : labels[key] ? [`${labels[key]}：${value}`] : []
  }).join(' · ')
}
