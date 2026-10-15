import type { AgentKey } from './agents'

const labels: Record<string, string> = {
  '了解你情况的人': '信息采集顾问',
  '帮你判断方向的人': '职业分析顾问',
  '帮你排计划的人': '行动规划顾问',
  '陪你推进的人': '行动支持顾问',
  '帮你查行情的人': '就业资讯顾问',
}
export function consultantLabel(name?: string) { return labels[name ?? ''] ?? name ?? '咨询顾问' }

/**
 * 内部称呼 → 后端主理 key。
 *
 * 演示数据里 speaker 存的是「了解你情况的人」这种口语称呼，而后端的稳定身份是
 * `profile_analyst` 这类 key（见后端 `agents.json` 与 `KernelAgent` 枚举）。
 * 头像、切换说明、配色都要按 key 走，所以在这里做一次显式映射 ——
 * 不靠关键词猜，猜错会让头像认错人。
 */
const keys: Record<string, AgentKey> = {
  '了解你情况的人': 'profile_analyst',
  '帮你判断方向的人': 'career_advisor',
  '帮你排计划的人': 'path_planner',
  '陪你推进的人': 'companion_coach',
  '帮你查行情的人': 'info_scout',
  // 有些示例数据直接写了展示名，一并兜住
  '信息采集顾问': 'profile_analyst',
  '职业分析顾问': 'career_advisor',
  '行动规划顾问': 'path_planner',
  '行动支持顾问': 'companion_coach',
  '就业资讯顾问': 'info_scout',
}

export function agentKeyOf(name?: string | null): AgentKey {
  if (name && keys[name]) return keys[name]
  // 已经是合法 key 时原样返回
  if (name && ['profile_analyst', 'career_advisor', 'path_planner', 'companion_coach', 'info_scout'].includes(name)) {
    return name as AgentKey
  }
  return 'profile_analyst'
}
