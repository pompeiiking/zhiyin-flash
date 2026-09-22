/**
 * 前端自己的**形状与界面文案**。
 *
 * 这里只留两类东西，其余一律归后端：
 *   · 类型：气泡 / 浮窗 / 对话这些界面构件长什么样；
 *   · 兜底文案：后端还没有数据时界面上说的那一句。
 *
 * 画像字段、报告维度、待办、时间轴、通知……**都不在这里** ——
 * 它们来自 `/app/workspace`、`/app/report/full-text`、`/app/notes`、
 * `/app/notifications/pending`。此前这个文件里放着整套演示数据
 * （维度得分、决策线、时间轴、匹配矩阵），后来被清成空数组继续留在代码里：
 * 既渲染不出东西，又让"哪份数据是真的"看不出来。已整体删除。
 */

export type StageId = 'explore' | 'aim' | 'sprint' | 'adapt' | 'relocate'

export interface Stage {
  id: StageId
  label: string
  question: string
}

/**
 * 五个处境。界面用它来说"你现在在哪一段"，
 * 具体的推进由后端编排器判定（`TurnView.stage`），这里不是判定来源。
 */
export const STAGES: Stage[] = [
  { id: 'explore', label: '探索自我', question: '我是谁，适合什么' },
  { id: 'aim', label: '验证定向', question: '这条路到底行不行' },
  { id: 'sprint', label: '冲刺行动', question: '窗口期里怎么推进' },
  { id: 'adapt', label: '适应成长', question: '入场之后怎么校准' },
  { id: 'relocate', label: '受挫再定位', question: '卡住了，是哪儿的问题' },
]

/**
 * 画像为空时画像气泡显示的占位。
 *
 * 它**不是**一份假画像：把握 0、没有维度、没有结论，只有一句话告诉用户
 * "还没有你的画像，去聊一轮"。真实画像一律来自 `session.profile`。
 */
export const PORTRAIT = {
  summary: '还没有你的画像 —— 聊两句就能建起来。',
  overall: 0,
  lastChange: '',
  dimensions: [] as never[],
  gaps: [] as never[],
} as any

/* ---------------------------------------------------------------- 浮窗 */

/**
 * 浮窗消息。它们"从旁边飘过来"，不占网格里的一格。
 *
 * 内容全部来自后端（`GET /app/notifications/pending`）—— 这里只定义形状。
 */
export type NoticeTone = 'alert' | 'intel' | 'coach' | 'handoff'

export interface Notice {
  id: string
  type: 'notice'
  kicker: string
  title: string
  body: string
  tone: NoticeTone
  /**
   * 这条消息带的一个动作。
   *
   * `kind` 是**动作去哪**，不是文案：`ask` = 集群判断的下一步（去它指定的地方），
   * `intel` = 外部情报（去工作台那块摊开）。新增一种动作要在这里加一个取值，
   * 免得组件里出现认不出来的字符串。
   */
  action?: {
    label: string
    kind: 'accept' | 'tasks' | 'report' | 'chat' | 'ask' | 'intel'
  }
}

/** AI 抛来的一个问题：回答完就消失，不留在界面上 */
export interface Question {
  id: string
  type: 'question'
  kicker: string
  question: string
  options: string[]
  reply: string
  /** 为什么问这一句 —— 回答完展示，让用户知道这不是随便搭话 */
  why: string
  tone: NoticeTone
}

export type FloatItem = Notice | Question

/* ---------------------------------------------------------------- 对话 */

export interface ChatTurn {
  id: number
  role: 'ai' | 'me'
  text: string
  /** 真后端联调时：这句是谁说的（主理展示名 / 编排器） */
  actor?: string
  /** AI 顺手给出的可点选项 —— 对话里也一样，先给选择再要求打字 */
  options?: string[]
  /** 一句话之后可以顺手做的动作 */
  ask?: { label: string; kind: 'tasks' | 'portrait' | 'report' }
  /**
   * 这一轮顺手给的图。
   *
   * 值全部来自**服务端实测数据**（画像各维把握、方案匹配度…），
   * 不是模型写的数字 —— 图上的每个点都能追回它来自哪条记录。
   */
  chart?: {
    kind: 'bars'
    title: string
    unit: string
    points: { label: string; value: number }[]
  }
  /** 这一轮用到的外部情报来源（可点回原页面）；没有就是空 */
  intelRefs?: { id: string; title: string; kind_label: string; source_name: string; source_url: string }[]
}

/** 对话的第一句：还没登录、还没跟后端说过话时，输入框上方那一行 */
export const CHAT_SEED = { id: 0, role: 'ai', text: '登录后由 AI 主理，随时开聊。' }
