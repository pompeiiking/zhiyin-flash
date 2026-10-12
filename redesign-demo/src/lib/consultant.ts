const labels: Record<string, string> = {
  '了解你情况的人': '信息采集顾问',
  '帮你判断方向的人': '职业分析顾问',
  '帮你排计划的人': '行动规划顾问',
  '陪你推进的人': '行动支持顾问',
  '帮你查行情的人': '就业资讯顾问',
}
export function consultantLabel(name?: string) { return labels[name ?? ''] ?? name ?? '咨询顾问' }
