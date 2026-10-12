import { computed, reactive, readonly } from 'vue'
import { SCENARIOS, scenarioOf } from './data/scenarios'
import { DIRECTION_PLANS, NOTICES, PROFILE_FIELDS, TASKS_BY_GRADE } from './data/student'
import type { Grade, Notice, TaskItem } from './data/types'

/**
 * 演示状态。
 *
 * 用一个模块级 reactive 单例：这是演示工程，不引 pinia，
 * 少一个依赖就少一处与真实项目对不上的地方。
 *
 * 这里刻意把「用户动了 → 系统里什么真的变了」做成真的：
 * 勾任务会改三组计数与"完成记录"，选方向会真的重算"还有几处跟着改"。
 * 演示的卖点就是行为闭环，界面上必须有变化。
 */

interface State {
  grade: Grade
  authed: boolean
  /** 演示账号：fresh / mid / stale */
  account: string
  tasks: TaskItem[]
  /** 任务被勾掉时的临时高亮（"看今天要做的事变化"） */
  lastDoneId: string | null
  /** 已选方向（null = 还没选，系统永不替用户选） */
  selectedDirectionId: string | null
  /** 上一次选的方向，用来出"变更说明" */
  previousDirectionId: string | null
  reportVersion: string
  /**
   * 这次对话里**新采集到**的画像条数。
   * 画像进度 = 年级自带的已知条数 + 这个数 —— 所以它是"随信息采集同步推进"的唯一来源，
   * 导航底部那条进度线与对话页侧栏都读同一个值，不会各说各话。
   */
  chatCollected: number
  /** 展开的画像字段 key */
  openField: string | null
  /** 浮窗：一次只跳一条 */
  noticeQueue: Notice[]
  noticeIndex: number
  noticeOpen: boolean
  /** 干预浮窗（stale 账号） */
  interventionOpen: boolean
  interventionDismissed: boolean
  /** 每个页面的操作引导是否已被用户收起 */
  guidesClosed: Record<string, boolean>
  /** 全局轻提示 */
  toast: string | null
  /** 结算"跟着改的地方"面板是否展开 */
  rippleOpen: boolean
}

/** 每个年级一份任务清单：切年级必须连"要做的事"一起换，否则场景化就是假的 */
function tasksFor(grade: Grade): TaskItem[] {
  return TASKS_BY_GRADE[grade].map((t) => ({ ...t }))
}

/**
 * 登录态持久化。
 *
 * 演示里**链接是评审的主要入口**：刷新一次、或在新标签页粘一条 URL，
 * 内存里的登录态就没了，内页随即被弹回门户 —— 看上去就是"这个链接打不开"。
 * 用 localStorage（不是 sessionStorage）：登一次，之后所有标签页与刷新都算已登录；
 * 「退出登录」会把它清掉，所以换账号的演示流程照旧。
 */
const AUTH_KEY = 'zhiyin-demo-auth'

function readStoredAccount(): string | null {
  try {
    return localStorage.getItem(AUTH_KEY)
  } catch {
    // 隐私模式 / 存储被禁用：当作没登录，但不能因此报错
    return null
  }
}

const storedAccount = readStoredAccount()

const state = reactive<State>({
  grade: 'junior',
  authed: storedAccount !== null,
  account: storedAccount ?? '',
  tasks: tasksFor('junior'),
  lastDoneId: null,
  selectedDirectionId: null,
  previousDirectionId: null,
  reportVersion: 'v3',
  chatCollected: 0,
  openField: null,
  noticeQueue: NOTICES.map((n) => ({ ...n })),
  noticeIndex: 0,
  noticeOpen: false,
  interventionOpen: false,
  interventionDismissed: false,
  guidesClosed: {},
  toast: null,
  rippleOpen: false,
})

let toastTimer: ReturnType<typeof setTimeout> | null = null

export function toast(message: string): void {
  state.toast = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    state.toast = null
  }, 3200)
}

export const demo = {
  state: readonly(state) as Readonly<State>,

  /** 页面用得到的选择器 */
  use: {
    scenario: computed(() => scenarioOf(state.grade)),
    scenarios: computed(() => SCENARIOS),
    now: computed(() => state.tasks.filter((t) => t.bucket === 'now')),
    waiting: computed(() => state.tasks.filter((t) => t.bucket === 'waiting')),
    done: computed(() => state.tasks.filter((t) => t.bucket === 'done')),
    /** 完成记录：只由行为日志驱动，不由"计划里写了"驱动 */
    doneCount: computed(() => state.tasks.filter((t) => t.bucket === 'done').length),
    /** 今天能勾掉的最小一件 */
    smallestNow: computed(() => {
      const now = state.tasks.filter((t) => t.bucket === 'now')
      return now.length ? now.reduce((a, b) => (a.minutes <= b.minutes ? a : b)) : null
    }),
    selectedDirection: computed(() =>
      state.selectedDirectionId
        ? DIRECTION_PLANS.find((d) => d.id === state.selectedDirectionId) ?? null
        : null,
    ),
    previousDirection: computed(() =>
      state.previousDirectionId
        ? DIRECTION_PLANS.find((d) => d.id === state.previousDirectionId) ?? null
        : null,
    ),
    plans: computed(() => DIRECTION_PLANS),
    activeNotice: computed(() => state.noticeQueue[state.noticeIndex] ?? null),
    noticeLeft: computed(() => Math.max(0, state.noticeQueue.length - state.noticeIndex - 1)),
    /**
     * 画像进度随年级走，**并随对话推进**。
     * 缺口不是另写一个数字，而是"画像池长度 - 已经了解" ——
     * 这样"已经了解 12 条"与实际列出的条数永远不会对不上。
     */
    profileProgress: computed(() => {
      const s = scenarioOf(state.grade)
      const total = PROFILE_FIELDS.length
      const known = Math.min(s.known + state.chatCollected, total)
      return { known, gap: total - known, total }
    }),
  },

  // ---- 年级（场景化设计的开关）----
  /** 切年级 = 换一整套内容：任务清单、画像进度、里程碑、报告重点都跟着换 */
  setGrade(grade: Grade, silent = false) {
    if (state.grade === grade) return
    state.grade = grade
    state.tasks = tasksFor(grade)
    state.lastDoneId = null
    state.chatCollected = 0
    if (!silent) toast(`已切换到${scenarioOf(grade).grade}的使用场景 —— 要做的事也换了`)
  },

  // ---- 登录 ----
  /**
   * silent 用于"分享直达链接"（?as=mid）：直接落到某个演示状态，
   * 不弹提示，方便截图与评审打开就看他关心的那一屏。
   */
  signIn(account: string, silent = false) {
    state.authed = true
    state.account = account
    // 落到磁盘：演示里链接经常被刷新或在新标签页打开，登录态只存内存就会变成"链接坏了"
    try {
      localStorage.setItem(AUTH_KEY, account)
    } catch {
      /* 隐私模式下写不进去就算了，不该因此登不上 */
    }
    // 'stale' 是"三天没动"的账号：登录后主动消息自己出现（第 9 幕）
    if (account === 'stale') {
      state.interventionOpen = true
      state.interventionDismissed = false
    }
    if (!silent) toast(`已登录：${account}`)
  },
  signOut() {
    state.authed = false
    state.account = ''
    state.interventionOpen = false
    try {
      localStorage.removeItem(AUTH_KEY)
    } catch {
      /* 同上 */
    }
    toast('已退出登录')
  },

  // ---- 任务：勾掉 = 行为日志 + 完成记录（第 8 幕）----
  completeTask(id: string) {
    const t = state.tasks.find((x) => x.id === id)
    if (!t || t.bucket === 'done') return
    t.bucket = 'done'
    t.doneAt = '刚刚'
    state.lastDoneId = id
    toast('记进完成记录了 —— 画像里的节奏跟着变了一条')
  },
  reopenTask(id: string) {
    const t = state.tasks.find((x) => x.id === id)
    if (!t) return
    t.bucket = 'now'
    t.doneAt = undefined
    toast('已放回"现在要做的"')
  },
  /** 建议可采纳可否决，否决回流也是数据（第 8 幕） */
  acceptSuggestion(id: string) {
    const t = state.tasks.find((x) => x.id === id)
    if (!t) return
    t.origin = '自己写的'
    toast('已采纳 —— 它现在是你的事，不是建议了')
  },
  rejectSuggestion(id: string) {
    state.tasks = state.tasks.filter((t) => t.id !== id)
    toast('已否决。否决也会记下来，下次不再推同一条')
  },
  /** 对话里那颗"排进今天"：按标题在当前年级的任务里找，找不到就新建一条 */
  /**
   * 对话答了一轮 → 画像多两条。
   * 由 ChatView 在 `send()` 里调用。上限由 profileProgress 自己夹住（不会超过画像池长度），
   * 所以这里不必判断"是不是问过了" —— 重复调用只会被 min() 吃掉。
   */
  noteCollected(n = 2) {
    state.chatCollected += n
  },

  planChatTask(title: string, minutes: number) {
    const exist = state.tasks.find((t) => t.title === title)
    if (exist) {
      if (exist.origin === '建议的') exist.origin = '自己写的'
      exist.bucket = 'now'
      exist.due = '今天'
    } else {
      state.tasks.unshift({
        id: `chat-${state.grade}-${Date.now()}`,
        title,
        minutes,
        why: '这是你在对话里答应下来的一件小事 —— 先做起来，比想清楚更管用',
        bucket: 'now',
        origin: '自己写的',
        due: '今天',
      })
    }
    toast('已排进今天 —— "现在要做的"多了一件')
  },
  /** 从提醒/建议里"排进今天"：它进"现在要做的"，并带上截止 */
  planToday(id: string) {
    const t = state.tasks.find((x) => x.id === id)
    if (!t) return
    if (t.origin === '建议的') t.origin = '自己写的'
    t.bucket = 'now'
    t.due = '今天'
    toast('已排进今天 —— "现在要做的"多了一件')
  },
  /** 做不动可以点"改小"：当场拆到 5 分钟（第 8 幕预案） */
  shrinkTask(id: string) {
    const t = state.tasks.find((x) => x.id === id)
    if (!t) return
    t.minutes = 5
    t.title = t.title.includes('（已改小）') ? t.title : `${t.title}（已改小）`
    t.why = '原来那一版要 40 分钟以上 —— 拆到 5 分钟，先动起来'
    toast('已改小到 5 分钟。改小不是失败，是设计好的')
  },

  // ---- 方向：选择是用户的，撤回是产品的（第 7 幕）----
  chooseDirection(id: string) {
    if (state.selectedDirectionId === id) return
    state.previousDirectionId = state.selectedDirectionId
    state.selectedDirectionId = id
    state.rippleOpen = true
    const plan = DIRECTION_PLANS.find((d) => d.id === id)
    toast(
      state.previousDirectionId
        ? `已改选为「${plan?.title}」—— 只重算受影响的 ${plan?.ripple ?? 0} 处，其余原样`
        : `已选定「${plan?.title}」—— 系统不会替你做这个选择，随时可以改`,
    )
  },
  /** 直达链接用：预置一个已选方向，不弹提示（?dir=d1） */
  preselectDirection(id: string) {
    state.previousDirectionId = null
    state.selectedDirectionId = id
    state.rippleOpen = true
  },
  closeRipple() {
    state.rippleOpen = false
  },

  // ---- 报告版本 ----
  setReportVersion(v: string) {
    state.reportVersion = v
  },

  // ---- 画像字段展开 ----
  toggleField(key: string) {
    state.openField = state.openField === key ? null : key
  },

  // ---- 浮窗：一次只跳一条（7.4）----
  openNotice() {
    state.noticeOpen = true
  },
  closeNotice() {
    state.noticeOpen = false
  },
  /** 点"还有 N 条 · 看下一条"：收起当前这条，下一条顶上来 */
  nextNotice() {
    if (state.noticeIndex < state.noticeQueue.length - 1) {
      state.noticeIndex += 1
    } else {
      state.noticeOpen = false
    }
  },
  resolveNotice() {
    const n = state.noticeQueue[state.noticeIndex]
    if (n) toast(`已${n.action}：写进"现在要做的"`)
    state.noticeOpen = false
  },

  // ---- 主动干预（第 9 幕）----
  /** 演示用：手动把"主动干预"这一幕掀起来 */
  openIntervention() {
    state.interventionOpen = true
    state.interventionDismissed = false
  },
  closeIntervention() {
    state.interventionOpen = false
    state.interventionDismissed = true
  },

  // ---- 操作引导 ----
  closeGuide(key: string) {
    state.guidesClosed[key] = true
  },
  resetGuide() {
    state.guidesClosed = {}
    toast('操作引导已恢复')
  },

  // ---- 演示辅助 ----
  resetDemo() {
    state.tasks = tasksFor(state.grade)
    state.chatCollected = 0
    state.selectedDirectionId = null
    state.previousDirectionId = null
    state.noticeIndex = 0
    state.noticeOpen = false
    state.interventionOpen = false
    state.reportVersion = 'v3'
    state.openField = null
    state.rippleOpen = false
    toast('演示数据已复位')
  },
}
