/** 当前用户要求：操作、说明与结果采用中性的书面表达。 */
export const PRODUCT = {
  name: '职引', title: '大学生生涯规划与就业指导智能支撑平台',
  slogan: '持续陪伴 · 专业牵引 · 行动落地 · 心想事成',
  for: '为大学生提供生涯规划与就业指导',
}
export const JOURNEY_STEPS = [
  { key: 'know', label: '个人信息', note: '逐项补充并保留来源' },
  { key: 'report', label: '诊断报告', note: '查看结论与支持依据' },
  { key: 'choose', label: '方向选择', note: '比较方案后自主选择' },
  { key: 'today', label: '行动任务', note: '查看任务、耗时与安排依据' },
  { key: 'review', label: '执行复盘', note: '分析任务、方法或方向' },
]
export const AUTH_COPY = {
  title: '选择工作空间',
  body: '当前展示预置场景，咨询与任务数据仅在本次页面会话中保留。进入后首先显示咨询对话。',
  action: '进入咨询',
  accountHint: '选择当前阶段，体验账号使用任意访问口令',
}
export const FALLBACK_COPY = {
  modelTimeout: '本次未能生成内容，请重新提交。',
  badContract: '本次生成内容不完整，请重新提交。',
  offline: '网络连接已中断，连接恢复后可重试。',
  noExternalFact: '本次未取得岗位数据，结论仅依据已有信息。',
  mock: '示例内容 · 尚未基于个人真实情况生成',
}
export const GUIDES = {
  home: '查看当前任务、预计耗时与安排依据。',
  homeEmpty: '暂无行动任务，可通过咨询明确方向与执行安排。',
  chat: '选择咨询主题或输入问题，必要时可补充材料。',
  profile: '管理个人信息，展开查看来源与可信度。',
  report: '查看个人特征、职业环境与决策条件的诊断结果。',
  plan: '查看阶段目标、执行任务与来源，支持任务拆分。',
  review: '结合执行记录分析原因，并制定调整任务。',
  path: '按年级查看使用场景及各步骤对应界面。',
}
export const EMPTY_COPY = {
  profileTitle: '暂无个人信息', profileBody: '完成咨询后，已采集的信息将在此展示。', profileAction: '开始咨询',
  reportTitle: '报告尚未生成', reportBody: '补充必要信息后，可生成诊断报告。',
  workbenchTitle: '暂无行动任务', workbenchBody: '明确方向后，可通过咨询生成执行安排。',
  chatTitle: '暂无咨询记录', chatBody: '选择咨询主题或直接输入问题。',
}
export function partialCopy(known: number, gap: number): string {
  return '已采集 ' + known + ' 条信息，待补充 ' + gap + ' 条。'
}
