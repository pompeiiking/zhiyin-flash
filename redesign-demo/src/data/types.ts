/**
 * 演示数据模型。
 *
 * 口径来自 docs/职引-完整设计文档.md：
 *   7.3 内部词 → 用户词对照表（界面上不出现环节名、维度名、内部词）
 *   7.4 逐屏文案稿（每个字段直接对应一个文案 key）
 *   14.2 十幕演示主线（每一幕要展示什么）
 *
 * 这里只放"用户看得见"的东西，不放任何内部概念。
 */

export type Grade = 'freshman' | 'sophomore' | 'junior' | 'senior'

/** 把握度：L1 不给数字，只给三档文字（7.3） */
export interface Confidence {
  level: 'high' | 'mid' | 'low'
  /** 用户在界面上看到的字：比较确定 / 还要再看看 / 还不好说 */
  label: string
  /** 0-3 格 */
  bars: number
}

export type FieldSource = '对话' | '学信网' | '教务系统' | '学校' | '行为记录' | '简历材料' | '综合分析' | '导师记录' | '本人填写'

/** 「对你的了解」里的一条 —— 带来源与把握（可被盘问） */
export interface ProfileField {
  key: string
  label: string
  value: string
  source: FieldSource
  confidence: Confidence
  /** 记于什么时候 —— 用户要能看出"这是哪次说的" */
  noted: string
}

/** 采集动线里的一条（还差什么、去哪取） */
export interface CollectItem {
  label: string
  from: FieldSource
  /** 能不能现在取到 */
  fetchable: boolean
  /** 取不到时为什么 —— 必须写清楚，不能不吭声 */
  blockedBy?: string
}

/** 报告里的一条维度：结论一句 + 有多大把握 + 门槛解释（7.4） */
export interface ReportDimension {
  key: string
  /** 用户语言的分区标题下的维度名 */
  label: string
  /** L1：结论一句 */
  conclusion: string
  confidence: Confidence
  /** L2：分值（点开才出现） */
  score?: number
  /** 门槛解释 —— 这份报告最值钱的一句话，必须是人话 */
  threshold?: string
  /** 依据：哪句话、哪条记录、哪份岗位要求 */
  evidence: string[]
}

export interface ReportSection {
  key: string
  /** 用户语言的分区标题（不用维度名） */
  title: string
  dimensions: ReportDimension[]
}

export type TaskBucket = 'now' | 'waiting' | 'done'

/** 任务必须"什么 + 多久 + 为什么是现在"三样齐全，缺一样就不合格（7.4） */
export interface TaskItem {
  id: string
  /** 什么 */
  title: string
  /** 多久 */
  minutes: number
  /** 为什么是现在 */
  why: string
  bucket: TaskBucket
  /** 谁放进来的：计划拆下来的 / 自己写的 / AI 建议的 —— 两本账要分得清 */
  origin: '计划拆下来的' | '自己写的' | '建议的' | '关键节点'
  due?: string
  /** 已完成时间 */
  doneAt?: string
}

export interface Milestone {
  dueAt?: string
  dependsOn?: string[]
  handoff?: string
  id: string
  title: string
  window: string
  progress: number
  note: string
}

export interface CalendarMark {
  day: number
  label: string
  kind: 'deadline' | 'action' | 'review'
}

/** 方向方案：主攻 / 平行 / 保底（系统永不替用户选） */
export interface DirectionPlan {
  id: string
  role: '主攻' | '平行' | '保底'
  title: string
  /** 界面上给"很大把握 / 还要再看看"，不给小数 */
  fit: Confidence
  fitScore: number
  evidence: string[]
  risk: string
  /** 选了它之后，还有几处会跟着改 */
  ripple: number
  ripplePoints: string[]
}

/** 对话里的一条消息 */
export interface ChatTurn {
  renderables?: import('../api/backend-types').RenderableView[]
  theory_refs?: import('../api/backend-types').TheoryRefView[]
  guideTask?: import('../api/backend-types').GuideTaskView
  reminder?: import('../api/backend-types').GuideReminderView
  id: string
  from: 'me' | 'host' | 'system'
  /** 主理的身份短语，例如「帮你判断方向的人」（不是职位名） */
  speaker?: string
  text: string
  /** 可点选项：能用点就不要让人打字 */
  options?: string[]
  /** 追问：一次只问一个问题 */
  question?: string
  /** 附带的动作任务（必须带时长） */
  task?: { title: string; minutes: number }
  /** 交接卡：谁、凭什么、为什么 —— 三件事齐全 */
  handoff?: { to: string; why: string; basedOn: string }
  /** 证据/来源，点开可见 */
  citations?: string[]
  materials?: { id: string; name: string }[]
  optionRefs?: { option_id: string; label: string; value: unknown }[]
}

/** 一次只跳一条的浮窗（7.4） */
export interface Notice {
  id: string
  kind: '提醒' | '干预' | '情报'
  /** 一句标题 */
  title: string
  /** 一句话说清 + 自带动作 */
  body: string
  /** 动作按钮 */
  action: string
  /** 次要动作 */
  secondary?: string
  deadline?: string
  /** 还有几条没显示 */
  queued: number
  task?: { title: string; minutes: number }
}

export interface ReviewItem {
  id: string
  when: string
  what: string
  result: 'done' | 'partial' | 'missed' | 'record'
  /** 归因三选一：任务太大 / 方法不对 / 方向要重估（不归到人） */
  attribution?: '任务太大' | '方法不对' | '方向要重估' | '其他' | '尚不确定'
}

/** 一个年级 = 一套使用场景（评审要求：按一年级到四年级设计内容） */
export interface Scenario {
  id: Grade
  grade: string
  /** 用户此刻的处境，一句话 */
  situation: string
  /** 这一年真正要解决的事 */
  focus: string
  /** 首页任务卡组：全是用户语言 */
  taskCards: string[]
  /** 画像进度：已经了解你 N 条（缺口 = 画像池长度 - N，唯一来源在 store 里） */
  known: number
  /** 首页那句"接下来" */
  nextStep: string
  /** 该年级报告最该看的分区 */
  reportFocus: string
  /** 该年级的里程碑 */
  milestones: Milestone[]
  /** 该年级的复盘关注点 */
  reviewFocus: string
  /** 该年级最常见的一句追问 */
  probe: string
}
