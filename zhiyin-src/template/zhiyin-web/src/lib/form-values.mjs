/** Format API timestamps for local form controls; malformed dates stay editable. */
export function localDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function reviewDraft(task) {
  return { text: task?.text ?? '', due: localDateTime(task?.due_date) }
}

/** Do not draw missing, invalid or out-of-range measurements as real scores. */
export function measurementPercent(measurement) {
  const { value, minimum = 0, maximum = 100 } = measurement
  if (![value, minimum, maximum].every(Number.isFinite) || maximum <= minimum || value < minimum || value > maximum) return null
  return (value - minimum) / (maximum - minimum) * 100
}
