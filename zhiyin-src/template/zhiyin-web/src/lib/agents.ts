/**
 * 主理身份表。
 *
 * 为什么单独放一个文件：头像组件、对话流、交接说明、侧栏都要用同一份
 * 「谁是主理、叫什么、什么颜色、什么造型」。散在各自组件里，改一个名字要改四处，
 * 而且后端 key 与展示名一旦对不上，交接提示就会出现"给 XXX 接手"而头像是别人。
 *
 * 后端契约里稳定的是 key（5 个主理 + me + system），中文名是我们这边的展示层，
 * 所以这里只做单向映射：key → 展示信息，绝不反向猜。
 */

/** 后端稳定标识：5 个主理 + 学生自己 + 系统。 */
export type AgentKey =
  | 'profile_analyst'
  | 'career_advisor'
  | 'path_planner'
  | 'companion_coach'
  | 'info_scout'
  | 'me'
  | 'system'

/** 头部轮廓：每个主理一种，靠形状而不是只靠颜色区分。 */
export type AgentShape = 'round' | 'square' | 'shield' | 'capsule' | 'flower' | 'person' | 'panel'

/**
 * 眼睛画法。
 *
 * 【2026-10-14 · P0-3】卡通形体（c2-hbu）定下来之后，眼睛**不再按主理换画法**：
 * 全部是"眼白 + 瞳 + 偏左上的高光"这一种 —— 眼睛是角色的主角，它一变，
 * 五个头像就各自成了另一套插画，而不是同一个角色换个人。
 * 身份区分整体交给 shape（轮廓/比例）与 hue（色相）两层，见 HUES 的说明。
 * 这个类型与字段保留：它是"这个主理的眼睛是什么性格"的登记位，
 * 将来若要给学生本人（me）另做一种画法，改的是这里，不是组件。
 */
export type AgentEyes = 'round' | 'tall' | 'line' | 'single' | 'scan' | 'dot' | 'dash'

/** 头下方的识别件：这个主理"手里拿的那件东西"。 */
export type AgentMark = 'ring' | 'layers' | 'steps' | 'leaf' | 'lens' | 'none' | 'bars'

export interface AgentIdentity {
  key: AgentKey
  /** 中文展示名 */
  name: string
  /** 一句话职责：用于切换说明与 tooltip */
  role: string
  /** 该主理的标识色（CSS 颜色值） */
  hue: string
  /** 造型标识 */
  shape: AgentShape
  eyes: AgentEyes
  mark: AgentMark
}

/**
 * 5 个标识色：**同一亮度、同一饱和度档**，只换色相。
 *
 * 逐条说明为什么是这五个值：
 *   1. 项目令牌（styles/tokens.css）只给了蓝（主）、红（注意）、灰（结构）三支色相，
 *      并且明确禁止再引入"荧光/高饱和"的第四第五色。主理身份色属于**图形色**，
 *      不是状态色，所以不能直接复用红（会读成"出问题了"）。
 *   2. 因此这里只在 HSL 亮度 40–43% / 饱和度 10–24% 的窄带里取五支色相，
 *      亮度几乎相同 → 一屏并排不会有的跳出来、有的沉下去；饱和度压到很低 → 克制。
 *   3. profile_analyst 用离校徽蓝最近的石板蓝、career_advisor 用同源的青蓝：
 *      前两位最常主持开场，颜色上先接住既有品牌色，另外三支再散开。
 *   4. 造型本来就各不相同（见 AgentShape），颜色只是第二层线索 ——
 *      这样在色觉障碍下也不会"五个头像长得一样"。
 *
 * 【2026-10-14 · P0-3】卡通形体进来之后，这五支色的分工更明确了：
 *   它们是**人物色**（谁是这个人），不是**主题色**（这是哪个学校/哪套主色）。
 *   主题色那一层由 styles/dialogue.css 的 --ag-ink / --ag-eye / --ag-line 承担，
 *   接的是 --c-text / --c-surface / --c-primary —— 换深浅主题、切"河大红"时，
 *   瞳色/眼白/识别件与说话的涟漪跟着动，而"五个人"不会因此变成同一张脸。
 *   组件里没有任何写死的色值：形状色由本文件内联，结构色由页面局部变量给。
 */
const HUES = {
  slate: '#40608F',
  teal: '#3D6B6A',
  rose: '#8A5B62',
  iris: '#5E5480',
  graph: '#5F6570',
  me: '#5A6270',
  system: '#7C8087',
} as const

/**
 * 身份表。
 * 职责写成"他负责哪一步"，不写职称 —— 学生在交接提示里看到的是"接下来谁管这件事"。
 */
export const AGENTS: Record<AgentKey, AgentIdentity> = {
  profile_analyst: {
    key: 'profile_analyst',
    name: '信息采集顾问',
    role: '把你的情况问清楚、建成可核对的能力与兴趣画像',
    hue: HUES.slate,
    shape: 'round',
    eyes: 'round',
    mark: 'ring',
  },
  career_advisor: {
    key: 'career_advisor',
    name: '职业分析顾问',
    role: '比较方向与差距，说明各项建议的依据',
    hue: HUES.teal,
    shape: 'square',
    eyes: 'tall',
    mark: 'layers',
  },
  path_planner: {
    key: 'path_planner',
    name: '行动规划顾问',
    role: '把选定的方向拆成有先后顺序、能排进日程的行动',
    hue: HUES.iris,
    shape: 'shield',
    eyes: 'line',
    mark: 'steps',
  },
  companion_coach: {
    key: 'companion_coach',
    name: '行动支持顾问',
    role: '跟进执行、复盘卡点，把中断接回可持续的节奏',
    hue: HUES.rose,
    shape: 'capsule',
    eyes: 'single',
    mark: 'leaf',
  },
  info_scout: {
    key: 'info_scout',
    name: '就业资讯顾问',
    role: '查找招聘与行业信息，核对来源与适用范围',
    hue: HUES.graph,
    shape: 'flower',
    eyes: 'scan',
    mark: 'lens',
  },
  me: {
    key: 'me',
    name: '我',
    role: '你自己：这里说的是你亲自提供的信息',
    hue: HUES.me,
    shape: 'person',
    eyes: 'dot',
    mark: 'none',
  },
  system: {
    key: 'system',
    name: '系统提示',
    role: '流程与规则说明，不是某位主理在说话',
    hue: HUES.system,
    shape: 'panel',
    eyes: 'dash',
    mark: 'bars',
  },
}

/** 兜底身份：key 缺失或后端加了新主理而前端还没登记时，用开场那位顶上。 */
const FALLBACK: AgentIdentity = AGENTS.profile_analyst

/** 运行时守卫：后端传来的 key 是 string，不能直接当 AgentKey 用。 */
function isAgentKey(key: string): key is AgentKey {
  return Object.prototype.hasOwnProperty.call(AGENTS, key)
}

/** 未知一律兜底到 profile_analyst（它负责开场，兜错了也不会说出越界的话）。 */
export function agentOf(key: string | undefined | null): AgentIdentity {
  if (!key) return FALLBACK
  return isAgentKey(key) ? AGENTS[key] : FALLBACK
}

/**
 * 由 key 派生的"节奏指纹"。
 *
 * 为什么需要：一屏里可能同时出现 3–5 个头像。如果所有头像共用同一套关键帧时长，
 * 它们会像仪仗队一样同时眨眼、同时转头 —— 那看着是幻灯片，不是"活着"。
 * 所以把 key 哈希成两个互相独立的位段，派生两项微调：
 *   · shift  → 负的 animation-delay（0–10s），相当于"入场时已经演到某一帧"，立刻错开；
 *   · period → 0–0.91s 的周期加量，且是**连续值**：档位相同的主理相对相位恒定、
 *     几十秒也不会分开，连续值才保证一定会慢慢错开。
 *
 * 用哈希而不是数组下标：主理切换导致顺序变化时，同一个主理的节奏不该跟着变。
 * 返回值只包含 CSS 变量，动画名保持静态字符串，避免 style 对象里出现计算属性名。
 */
export interface AgentVars {
  hue: string
  /** 周期加量：直接加在关键帧时长上，形如 "0.42s" */
  period: string
  /** 相位偏移：负 delay，形如 "-4100ms" */
  shift: string
}

export function agentVars(key: string | undefined | null): AgentVars {
  const agent = agentOf(key)

  // FNV-1a：短字符串上分布均匀，且不依赖任何库
  let hash = 2166136261
  for (let i = 0; i < agent.key.length; i += 1) {
    hash = Math.imul(hash ^ agent.key.charCodeAt(i), 16777619) >>> 0
  }

  // 取两个相互独立的位段：一个定相位，一个定周期微调。
  // 周期用连续值（0.00–0.91s）而不是 0/1/2/3 四档 —— 档位相同的主理，
  // 相对相位是恒定的，几十秒内不会分开；连续值则一定会慢慢错开。
  const phase = (hash % 4096) / 4096 // 0–1
  const drift = ((hash >>> 12) % 1024) / 1024 // 0–1

  return {
    hue: agent.hue,
    period: `${(drift * 0.91).toFixed(2)}s`,
    shift: `-${Math.round(phase * 10000)}ms`, // 负 delay 让初始相位就落在一个随机位置
  }
}

/** 派生量在组件里的写法（组件内联样式用这一串变量名，保持只有一处定义）。 */
export const AGENT_VAR_NAMES = {
  hue: '--ag-hue',
  period: '--ag-period',
  shift: '--ag-shift',
} as const
