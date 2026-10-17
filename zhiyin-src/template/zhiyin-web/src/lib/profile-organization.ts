/** Default reading order follows career questions, not the order of imported records. */
export const PROFILE_TOPICS = [
  { key: 'career', title: '兴趣、能力与职业期待', keys: ['interest', 'skills', 'experience', 'values', 'internship', 'style', 'weakness', 'award'] },
  { key: 'expect', title: '期待与行动条件', keys: ['city', 'jobtype', 'salary', 'family', 'time', 'weekly_hours', 'pipeline', 'schedule'] },
  { key: 'study', title: '学籍与学习背景', keys: ['study_year', 'major', 'school', 'degree_level', 'grade', 'rank', 'enrollment_status', 'duration', 'study_mode', 'enrolled_at', 'expected_graduation', 'courses', 'scores'] },
]
export function profilePriority(key: string) {
  const group = PROFILE_TOPICS.findIndex(topic => topic.keys.includes(key))
  // Unclassified information remains discoverable before routine school records.
  return group < 0 ? 2 : group === 2 ? 3 : group
}
type Edge = { readonly to_asset: string; readonly via_profile_keys?: readonly string[] }
/** Aggregate asset links cannot establish the inputs of every individual conclusion. */
export function exactProfileKeys(edges: readonly Edge[], target: string): string[] {
  return [...new Set(edges.filter(edge => edge.to_asset === target).flatMap(edge => edge.via_profile_keys ?? []))]
}
