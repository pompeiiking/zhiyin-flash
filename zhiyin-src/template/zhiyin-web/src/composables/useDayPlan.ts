import { computed, ref } from 'vue'
import { getCalendarNodes, type CalendarNode } from '@/api/client'
import { useSessionStore } from '@/stores/session'

/*
 * 按天索引：把"那一天有什么"算成一张表，日历的气泡和浮层读同一份。
 *
 * 为什么必须共用一份：气泡上画着点、点开那一天却是空的（或者反过来），
 * 是这种界面最典型的不信任来源。两边各自 fetch 一次就一定会漂 ——
 * 所以拉取与索引只在这里做一次，模块级缓存，谁先要谁触发。
 *
 * 三处来源都是**事实**，没有一处是算出来的：
 *   · 课表（学生自己从教务系统导进来的快照）—— 按星期几，每周重复；
 *   · 关键节点（规划师写进日历的）—— 按具体日期；
 *   · 行动任务（计划的产物）—— 按到期日。
 */

export interface DayCourse {
  name: string
  start: number
  span: number
  place: string
  teacher: string
}

export interface DayNode {
  title: string
  source: string
  task: string
}

export interface DayTask {
  text: string
  phase: string
  done: boolean
}

export interface DayPlan {
  date: string
  courses: DayCourse[]
  nodes: DayNode[]
  tasks: DayTask[]
  /** 自己写的待办（日历右键「这天记一条」的那批）—— 和计划任务分开摆 */
  myTodos: DayTask[]
}

/** Date → `YYYY-MM-DD`（**本地**时区：用户说的"那一天"是他手表上的那一天） */
export function ymd(value: Date): string {
  const m = String(value.getMonth() + 1).padStart(2, '0')
  const d = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${m}-${d}`
}

/** ISO 时间戳 → `YYYY-MM-DD`；解析不出来就返回空串（宁可没有，不要猜一天） */
export function isoDay(iso: string | null | undefined): string {
  if (!iso) return ''
  const dt = new Date(iso)
  return Number.isNaN(dt.getTime()) ? '' : ymd(dt)
}

/** 周一=1 … 周日=7（课表的写法和 JS 的 getDay 差一天，这里统一成课表口径） */
export const weekdayOf = (value: Date) => (value.getDay() === 0 ? 7 : value.getDay())

const nodes = ref<CalendarNode[]>([])
/** 日历里选中的那一天（气泡点某天 → 浮层打开的就是它） */
const selectedDay = ref<string>(ymd(new Date()))
let pulling: Promise<void> | null = null
/** 上次拉到的是哪个版本的数据（见 store 的 dataVersion） */
let pulledVersion = -1
/** 有没有成功拉过至少一次（拉到空也要算拉过：空不等于没拉） */
let everPulled = false

export function useDayPlan() {
  const session = useSessionStore()

  /*
   * 行动计划**只有一份**：store 里那份（`session.actionPlan`）。
   *
   * 这里原来自己取一次 `GET /app/plan/action`，于是同一份计划在前端有两个副本：
   * 待办卡片读 store 那份、日历读这份 —— 一次勾选要改两处，漏一处就出现
   * "卡片上勾掉了、日历上还在"。现在两边读的是同一个对象，改一处两处同时变，
   * 连重新取一次都不需要。
   */
  const plan = computed(() => session.actionPlan)

  /**
   * 拉关键节点 —— **按数据版本决定要不要重拉**。
   *
   * 读不到就当没有：日历上少几个点，比点开一天看到"加载失败"更像回事。
   * 失败**不缓存**（pulling 只在成功时留下结果），下一次打开还会再试一次。
   *
   * 版本这一条是后补的，补的是一个实测出来的症状：这张表**随画布一起挂载**，
   * 而这里原来是"拉过一次就再也不拉" —— 于是整页会话里它冻在进来那一刻：
   * 你聊了几轮、计划都重算过了，点开日历还是旧的任务与旧的月历点。
   * 现在 store 每次数据落定会把 `dataVersion` +1，这里对不上版本就重拉；
   * 传 `force=true`（动作之后）无条件重拉。
   */
  async function ensure(force = false) {
    if (pulling) return pulling
    if (!force && everPulled && pulledVersion === session.dataVersion) return
    pulling = (async () => {
      /*
       * 拉不到就**什么都不写**：留着上一次那几个点，也不记版本 ——
       * 抹成"这个月什么也没有"是把一次网络抖动显示成了"你没有安排"，
       * 下一次打开（或下一次联动）还会再试一次。
       */
      const fresh = await getCalendarNodes().catch(() => null)
      if (fresh) {
        nodes.value = fresh
        pulledVersion = session.dataVersion
        everPulled = true
      }
    })().finally(() => {
      pulling = null
    })
    return pulling
  }

  /** 那天到期还没做完的任务（含更早到期的：日历上它们仍然压在那一天） */
  const tasksByDay = computed(() => {
    const out = new Map<string, DayTask[]>()
    for (const phase of plan.value?.phases ?? []) {
      for (const task of phase.tasks ?? []) {
        const day = isoDay(task.due_date)
        if (!day) continue
        const list = out.get(day) ?? []
        list.push({ text: task.text, phase: phase.name, done: !!task.done })
        out.set(day, list)
      }
    }
    return out
  })

  const nodesByDay = computed(() => {
    const out = new Map<string, DayNode[]>()
    for (const node of nodes.value) {
      const day = isoDay(node.due_at)
      if (!day) continue
      const list = out.get(day) ?? []
      list.push({
        title: node.title,
        source: node.source ?? '',
        task: node.related_task_text ?? '',
      })
      out.set(day, list)
    }
    return out
  })

  /** 自己写的待办按天归堆：归属日存在本地（store.todoDue），后端不管这件事 */
  const myTodosByDay = computed(() => {
    const out = new Map<string, DayTask[]>()
    for (const todo of session.customTodos) {
      const day = todo.due
      if (!day) continue
      const list = out.get(day) ?? []
      list.push({ text: todo.label, phase: '自己记的', done: todo.done })
      out.set(day, list)
    }
    return out
  })

  /** 这一天的全部安排（课按星期几，节点与任务按日期） */
  function of(date: Date): DayPlan {
    const day = ymd(date)
    const weekday = weekdayOf(date)
    const courses = (session.academic?.courses ?? [])
      .filter((c) => c.weekday === weekday && c.start_period >= 1)
      .map((c) => ({
        name: c.name,
        start: c.start_period,
        span: Math.max(1, (c.end_period || c.start_period) - c.start_period + 1),
        place: c.place ?? '',
        teacher: c.teacher ?? '',
      }))
      .sort((a, b) => a.start - b.start)
    return {
      date: day,
      courses,
      nodes: nodesByDay.value.get(day) ?? [],
      tasks: tasksByDay.value.get(day) ?? [],
      myTodos: myTodosByDay.value.get(day) ?? [],
    }
  }

  /** 有没有课的日子：用来在月历上给"每周重复"的那几天画点 */
  const courseWeekdays = computed(
    () =>
      new Set(
        (session.academic?.courses ?? [])
          .filter((c) => c.weekday >= 1 && c.weekday <= 7)
          .map((c) => c.weekday),
      ),
  )

  /** 这一天有没有东西（月历上的点就是它） */
  const countOf = (date: Date) => {
    const p = of(date)
    return p.courses.length + p.nodes.length + p.tasks.length + p.myTodos.length
  }

  /**
   * 这一天的"点"该是什么颜色。
   *
   * 两个含义分开：`due` = 那天有**一次性的**事（截止 / 到期任务 / 自己记的待办），
   * `class` = 那天只是有课（每周重复的）。
   * 只用一个绿点的话，课表排满的学生会看到整月全是绿的，那天真正有截止的那一格
   * 就淹在里面了 —— 而"那天有事"恰恰是日历最该让人一眼看到的东西。
   */
  function markOf(date: Date): 'due' | 'class' | 'none' {
    const p = of(date)
    if (p.nodes.length || p.tasks.some((t) => !t.done) || p.myTodos.some((t) => !t.done)) return 'due'
    return p.courses.length ? 'class' : 'none'
  }

  return { ensure, of, countOf, markOf, courseWeekdays, nodes, plan, selectedDay }
}
