import type { AgentKey } from './agents'

/**
 * 主理显示名。
 *
 * 后端注册表里存的是内部称呼（建档分析师/职业顾问/路径规划师/陪伴教练/信息侦查员），
 * 学生界面只应该看到统一的「顾问」身份名。**同一个主理在任何地方都必须用同一个名字**：
 * 气泡署名、交接说明、画像侧栏一旦各说各话，学生就以为是两个人。
 */
const labels: Record<string, string> = {
  '建档分析师': '信息采集顾问',
  '职业顾问': '职业分析顾问',
  '路径规划师': '行动规划顾问',
  '陪伴教练': '行动支持顾问',
  '信息侦查员': '就业资讯顾问',
  '了解你情况的人': '信息采集顾问',
  '帮你判断方向的人': '职业分析顾问',
  '帮你排计划的人': '行动规划顾问',
  '陪你推进的人': '行动支持顾问',
  '帮你查行情的人': '就业资讯顾问',
}

/** 后端稳定 key → 展示名，防止 frame 里直接传 key 时气泡露出英文。 */
const keyLabels: Record<string, string> = {
  profile_analyst: '信息采集顾问',
  career_advisor: '职业分析顾问',
  path_planner: '行动规划顾问',
  companion_coach: '行动支持顾问',
  info_scout: '就业资讯顾问',
}

export function consultantLabel(name?: string) {
  const key = name ?? ''
  return labels[key] ?? keyLabels[key] ?? name ?? '咨询顾问'
}

/**
 * 交接文案清洗。
 *
 * 交接说明是模型写出来的整句（"接下来由路径规划师接手……"），它引用的还是注册表原名，
 * 而气泡署名已经过 `consultantLabel`，于是同一屏出现两个名字（测试问题 27）。
 * 这里对整段文本做一次显示名替换，保证交接说明与署名一致。
 *
 * 只替换登记过的别名，不碰其它正文：模型自己写的称呼（例如"咨询顾问"）保持原样。
 */
export function cleanConsultantText(text?: string | null) {
  if (!text) return text ?? ''
  let result = text
  for (const [alias, shown] of Object.entries(labels)) {
    if (alias === shown || !result.includes(alias)) continue
    result = result.split(alias).join(shown)
  }
  return result
}

/**
 * 内部称呼 → 后端主理 key。
 *
 * 演示数据里 speaker 存的是「了解你情况的人」这种口语称呼，而后端的稳定身份是
 * `profile_analyst` 这类 key（见后端 `agents.json` 与 `KernelAgent` 枚举）。
 * 头像、切换说明、配色都要按 key 走，所以在这里做一次显式映射 ——
 * 不靠关键词猜，猜错会让头像认错人。
 */
const keys: Record<string, AgentKey> = {
  '建档分析师': 'profile_analyst',
  '职业顾问': 'career_advisor',
  '路径规划师': 'path_planner',
  '陪伴教练': 'companion_coach',
  '信息侦查员': 'info_scout',
  '了解你情况的人': 'profile_analyst',
  '帮你判断方向的人': 'career_advisor',
  '帮你排计划的人': 'path_planner',
  '陪你推进的人': 'companion_coach',
  '帮你查行情的人': 'info_scout',
  // 有些示例数据直接写了展示名，一并兜住
  '信息采集顾问': 'profile_analyst',
  '职业分析顾问': 'career_advisor',
  '知音': 'career_advisor',
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
