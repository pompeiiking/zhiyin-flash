import { defineStore } from 'pinia'
import { CHAT_SEED, type ChatTurn, type FloatItem, type StageId } from '@/data/content'
import { buildAsk, type Ask, type BehaviorGuide, type GuideOption } from '@/lib/asks'
import { readFetched, readIntelText } from '@/lib/intel'
import {
  BackendUnavailableError,
  UnauthorizedError,
  authToken,
  clearToken,
  saveToken,
  enterTask,
  sendMessage,
  track,
  getWorkspace,
  getIntel,
  refreshIntel,
  type IntelItem,
  getReportFullText,
  getPendingNotifications,
  markNotificationRead,
  getBootstrap,
  getActionPlan,
  listNotes,
  addNote,
  setNoteDone,
  removeNote,
  authenticate,
  signOutRemote,
  type ActionPlan,
  type ReportFullText,
  type ProfileField,
  type TheoryRef,
  type TurnView,
} from '@/api/client'

/** 把网络与服务的失败翻成一句用户看得懂的话，而不是把堆栈丢到界面上 */
function messageOf(cause: unknown): string {
  if (cause instanceof UnauthorizedError) return '账号或密码不对。'
  if (cause instanceof BackendUnavailableError) return '暂时连不上服务，请稍后再试。'
  return cause instanceof Error ? cause.message : String(cause)
}

/**
 * 对话里一轮没成功时给用户看的那一句。
 *
 * 为什么不直接把后端那句话贴进气泡：那是层间消息，会带上内部标识与实现细节
 * （"任务会话不存在：s-31f2"、"缺少提示词配置：coach.clarify"）。
 * 用户看不懂，也不该看到。所以这里只给一句能行动的话，
 * 原始错误进控制台 —— 排查要看的东西在那里，不在用户的对话框里。
 */
function chatFailure(cause: unknown): string {
  if (cause instanceof UnauthorizedError) return '登录状态过期了，重新登录后接着说。'
  if (cause instanceof BackendUnavailableError) return '暂时连不上服务，稍后再试一次。'
  console.warn('[chat] 这一轮没成功：', cause)
  return '这一轮没接上，再说一句试试。'
}

/**
 * 主画布上的浮动块，关掉之后多久自己回来（毫秒）。
 *
 * 「可以关掉」和「关了还会回来」是同一件事的两面：
 * 用户需要能清走挡视线的东西，但产品也得记得自己还有话要说。
 * 不同的块给不同的安静时长 —— 状态类的回来快一点，欢迎语类的回来慢一点。
 */
export const BLOCK_RETURN_MS: Record<string, number> = {
  greet: 120000,
  portrait: 55000,
  todo: 45000,
  market: 52000,
  people: 40000,
  review: 68000,
}

/**
 * 通知渠道 → 界面上的署名。
 *
 * 后端给的是 `channel`（in_app / email / sms），不是"谁发的"——
 * 此前前端按一个不存在的 `by` 字段取名，于是每条通知的署名永远是空的。
 */
const NOTIFY_CHANNEL_LABEL: Record<string, string> = {
  in_app: '教练提醒',
  email: '邮件通知',
  sms: '短信通知',
}

/*
 * 自建待办的"归属日"只存本地（后端 NoteView 没有哪一天这个字段）：
 * 日历右键"这天记一条"写进来，日历与待办读出去。id 换成服务端 id 时跟着换键。
 */
const TODO_DUE_KEY = 'zhiyin_todo_due'
function loadTodoDue(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(TODO_DUE_KEY) ?? '{}') as Record<string, string>
  } catch {
    return {}
  }
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    portalSeen: false,
    stage: 'sprint' as StageId,

    /* 选择与推进 */
    chosenOption: null as string | null,
    stageChoice: null as string | null,
    doneTasks: {} as Record<string, boolean>,

    /*
     * 学信网接入与用户自建的东西。
     *
     * 为什么要放在会话里：绑定一旦完成，整个控制台的内容会换一批
     * （课表、匹配推荐都依赖它）。所以它是"用户状态"的一部分，不是某个组件的局部状态。
     */
    chsiBound: false,
    /**
     * 学生自己导入的课表与成绩单（后端快照）。
     *
     * null = 还没导入过。它和 `chsiBound` 是两个独立的事实：
     * 学籍来自学信网，课表成绩来自学校的教务系统 —— 学信网根本没有后两者。
     */
    academic: null as null | {
      school: string
      source: string
      term: string
      imported_at: string
      note: string
      courses: {
        name: string
        teacher: string
        weekday: number
        start_period: number
        end_period: number
        weeks: string
        place: string
        credit: string
        category: string
      }[]
      grades: {
        term: string
        name: string
        credit: string
        score: string
        point: string
        category: string
        kind: string
      }[]
    },
    academicBound: false,
    /**
     * 掀开绑定浮层时先停在哪个页签。
     *
     * 采集清单有两种下一步：核学籍（学信网）与取课表（教务系统）——
     * 点哪一条就该落在哪一页，而不是让用户在浮层里再找一次。
     */
    bindMode: 'chsi' as 'chsi' | 'academic',
    /** 用户自己写的待办 —— 和智能体给的待办长在一起，但来源要能分清 */
    customTodos: [] as { id: string; label: string; done: boolean; due?: string }[],
    /*
     * 自建待办归属的那一天（待办 id → `YYYY-MM-DD`，本地持久化）。
     * 日历右键「这天记一条」写进来，日历格子上的点与那一天的清单读出去。
     */
    todoDue: loadTodoDue(),
    /**
     * 这些待办有没有进到后端。
     *
     * 后端读不到它们，采集策略就用不上他的原话 —— 那正是"因为你写了…"说不出口的原因。
     * 所以这件事要能被界面说出来，而不是静默地只存在本地。
     */
    todoSynced: true as boolean,
    /** 采纳 / 忽略过的智能体建议 */
    acceptedSuggestions: [] as string[],
    dismissedSuggestions: [] as string[],

    /* 覆盖层与抽屉 */
    drawer: null as { title: string; subtitle: string; items: unknown[] } | null,
    overlay: null as null
      | 'portrait'
      | 'tasks'
      | 'brief'
      | 'bind'
      | 'timetable'
      | 'match'
      | 'talk'
      | 'collect'
      /* ③ 决策：三套方向方案（资产正文 + 选择） */
      | 'plans'
      /* ④ 行动：行动计划（阶段/任务/现在这一件） */
      | 'action'
      /* 日历：按天看那一天的安排与建议 */
      | 'calendar'
      /* 任务会话清单（可拆可续的载体） */
      | 'sessions'
      /* ⑤ 复盘：这段时间发生过什么 */
      | 'review'
      /* 外部情报：从公开渠道按你的方向取回的一批事实 */
      | 'intel',
    portraitFocus: null as 'gaps' | null,

    /*
     * 外部情报（`GET /app/intel`）。
     *
     * 为什么放在 store 而不是让每个组件自己取：同一批情报有三个地方要读 ——
     * 画布上那块、情报浮层、右上轨道的播报。三处各取一次的结果是：
     * 三份时间戳对不上、轮询频率翻三倍、一处刷新另两处不知道。
     * 所以取数只在这里发生一次，其余地方只读。
     *
     * `topic` 是"按什么方向去取"：有画像时用画像里的专业，没有就用一句兜底。
     * 情报是爬公开数据的，**取数本身不依赖登录**，兜底主题总比空手说"取不到"有用。
     */
    intel: null as null | { items: IntelItem[]; fetchedAt: string; topic: string },
    intelTopic: '',
    intelBusy: false,
    intelError: '',
    /**
     * 行动计划的正文（`GET /app/plan/action`）。
     *
     * 待办卡片的"为什么这一件"必须回答"为什么是这件、不是别的"，
     * 而那个答案只能来自**这一版计划本身**（阶段、截止、下一条）。
     * 让组件点一下再去取，按钮就少了那一下的反馈；所以跟着工作台一起取进来。
     */
    actionPlan: null as null | ActionPlan,
    /** 从别处（对话里的引用）跳进来时，要停在**哪一条**上 */
    intelFocus: '' as string,
    /**
     * 预填进对话输入框的那一句。
     *
     * 用途只有一个：情报浮层里点"拿去问主理" —— 用户看到的是**问题已经写好了**，
     * 他可以改，也可以直接发。不自动发送：替他按下发送键，就是在替他做决定。
     */
    chatDraft: '',

    /* 浮窗 */
    floats: [] as FloatItem[],
    /** 已经塞过浮窗的"下一步"（按 ask id 去重：同一件事只提醒一次） */
    askFloatSeen: [] as string[],
    acceptedNotices: [] as string[],
    answered: {} as Record<string, string>,

    /* 被用户关掉的主画布块：id -> 什么时候该回来 */
    hiddenBlocks: {} as Record<string, number>,
    /**
     * 已经"知道/读过"的块：本会话内不再飘回来。
     *
     * 和 `hiddenBlocks` 是两件事：关掉只是**让位**（过一会儿还回来，那是刻意的），
     * 而"知道"是**认了这件事**——交接提醒读过一次就不该再提醒第二次。
     * 之前这两件事共用一个行为，于是"知道"按下去等于"暂时收起"，
     * 用户分不出它到底生效没有。
     */
    ackedBlocks: [] as string[],

    /*
     * 业务对话。
     *
     * 它是画布上的一块（和画像、待办并列），不是角落里一个聊天窗 ——
     * "跟主理把话说清楚"本来就是一件要动手的事，凭什么它得挤在边上。
     */
    chatTurns: [CHAT_SEED] as ChatTurn[],
    chatSeq: 1 as number,
    chatTyping: false,

    /*
     * 后端联调状态（真实 /api/v1 优先，不可达回落本地演示）。
     * rail 系列来自对话回包（TurnView）：AgentRail 的"谁在干活、走到哪一环、
     * 为什么换人"以它为准——这是后端编排器的权威状态，不再用本地脚本推演。
     */
    backendTaskId: null as string | null,
    rail: null as {
      stage: string
      leadName: string
      disclosure: string | null
      /** 这一轮主理的依据（可点开看理论卡正文）。来自回包 badge.theory_refs。 */
      theories: TheoryRef[]
    } | null,
    railCards: [] as { stage: string; title: string; active: boolean; status: string }[],

    /* 真实画像（/app/workspace）：无后端时为 null，气泡回落本地演示常量 */
    taskEntries: [] as { code: string; label: string; lead: string | null }[],
    appName: '' as string,
    /**
     * 文案包（key → text）。
     *
     * 画像字段的中文名有两个来源：字段自带的 `label`（模型写画像时一起给），
     * 以及这里的对照表（老数据没有 label 时兜底）。两个都没有才回落到字段键 ——
     * 那时画面上是一串 `interest_direction`，正是要避免的样子。
     */
    copyBundle: {} as Record<string, string>,
    identity: null as null | { nickname: string; role: string },

    /*
     * 登录浮层。
     *
     * 它不是"一个页面"，是随时能掀起来的一层 —— 门户点开始时掀起来，
     * 令牌过期时也掀起来，关掉还在原地。所以状态放在会话里，不放某个页面里。
     */
    authOpen: false,
    authMode: 'login' as 'login' | 'register',
    authBusy: false,
    authError: '',

    /*
     * 编排器给的"下一步"。
     *
     * 后端每一轮回复都带着 BehaviorGuide（追问 / 选项 / 小任务 / 提醒）——
     * 那是 AI 在说"现在该做什么"。之前前端把它整个丢掉了，
     * 于是 AI 的引导只留在对话框里，用户离开对话框就再也看不见。
     * 现在它进状态，由 nextAsk 统一收成一个动作，各处都指向同一个。
     */
    guide: null as BehaviorGuide | null,

    /* 对话里"正在等用户回答的那一句" —— 从某个动作点进来时带过来的 */
    chatPrompt: '' as string,
    /**
     * 此刻可以点的选项 —— **带着身份**，不是一串显示文字。
     *
     * 之前这里存的是 `string[]`（只有 label）。后果很具体：
     * 用户点"我先把代码传上去"，发回去的只是一句文本，后端分不清
     * "他选了上一轮那个选项"和"他随口说了这几个字"，于是同一个问题
     * 连同同一组选项又问了一遍 —— 用户看到的是"点了没反应"。
     * 现在原样留着 `option_id` / `value`（见 `sendChat`）。
     */
    chatOptions: [] as GuideOption[],
    /**
     * 这一轮**已经点过**的那个选项。
     *
     * 用途只有一个：后端没能推进时（又问了同一句、同一组选项），
     * 界面上那一条要显示成"已答"，并给出明确的澄清 —— 不能让用户
     * 对着一模一样的问题再点一次，那看起来就是坏了。
     */
    chatAnswered: null as null
      | { question: string; optionId: string; label: string; optionLabels: string[] },
    /** 后端没能推进这一轮时，界面上那句明白话 */
    chatClarify: '',
    authNotice: '',
    wsPanels: null as null | {
      action: string
      review: string
      report: string
    },
    profile: null as null | {
      overall: number
      coverage: number
      /** 后端原样的字段（key / value / confidence / source / updated_at / evidence） */
      fields: ProfileField[]
      /** 上面那批字段的紧凑视图，给只用得着分数的地方（气泡、排序） */
      dimensions: { id: string; name: string; value: number }[]
      gaps: { id: string; name: string; question: string; suggested: string }[]
      updatedAt: string | null
    },

    /*
     * 采集动线（后端算的，不是前端猜的）。
     *
     * 它是"动态采集策略"在前端的唯一落点：还缺什么、去哪儿取、为什么。
     * 页面上任何一处说"还差 N 条"，数字都从这里来 ——
     * 前端不自己数缺口，因为"什么算缺"是策略层的事，不是渲染层的事。
     */
    collection: null as null | {
      missing: number
      bySource: Record<string, number>
      blocked: string[]
      nextSource: string | null
      items: {
        key: string
        label: string
        source: string
        why: string
        /** 这条缺口对应的那一句追问（只有 conversation 源有）。空 = 没有可点的直接动作 */
        ask: string
        got: boolean
        available: boolean
      }[]
    },

    /*
     * 气泡编排（后端算好的顺序）。
     *
     * 谁排第一、哪块占多大、哪块根本不该出现 —— 全在这里。
     * 前端只负责摆位：**顺序本身就是产品判断**，它依赖用户处在哪一步，
     * 而这一步只有后端知道。写死在前端，就只能靠发版改，而且所有人一个样。
     */
    layout: [] as {
      id: string
      label: string
      hint: string
      weight: number
      priority: number
      why: string
    }[],

    /*
     * 报告正文（只读资产版本）。
     *
     * null = 还没取过；`sections` 为空 = 后端还没有报告资产。
     * 这两个状态在界面上必须是两句话，所以不在这里替后端编一份空报告。
     */
    report: null as ReportFullText | null,
  }),

  getters: {
    /**
     * 外部情报按什么方向去取。
     *
     * 三级：用户手填的（他明确说了想查什么）→ 画像里的专业/方向 → 一句兜底。
     *
     * 为什么拿画像里的专业当主题：情报的价值全在"和你有关"上。没有主题时
     * 后端只能按一句泛泛的"大学生 求职 就业"去取，回来的东西跟谁都不挨着；
     * 有了专业，它才拿得到"这个专业对口哪些职业"。
     */
    intelQuery(state): string {
      const typed = state.intelTopic.trim()
      if (typed) return typed
      const fields = state.profile?.fields ?? []
      const major = fields.find((f) => /专业|major|方向|职业/.test(`${f.key} ${f.label ?? ''}`))
      const value = major ? String(major.value ?? '').trim() : ''
      return value || '大学生 求职 就业'
    },

    /**
     * 此刻 AI 想让你做的那一件事 —— 全站唯一的一个。
     *
     * 只给一个，是刻意的：同一时刻在各个气泡里塞三条不同的"下一步"，
     * 用户不知道该听谁的，等于没编排。优先级口径见 `lib/asks.ts`。
     */
    nextAsk(state): Ask | null {
      return buildAsk({
        guide: state.guide,
        leadName: state.rail?.leadName ?? '',
        profile: state.profile ? { gaps: state.profile.gaps } : null,
        hasAnyProfile: (state.profile?.dimensions.length ?? 0) > 0,
      })
    },

    /**
     * 「现在该点哪一块」—— 画布上对应哪个气泡。
     *
     * 一整屏都是能点的块，光靠读文字找下一步太难了，新手用户的第一句话往往是
     * "我该点哪儿"。这里是**唯一**一处把"下一步"翻成画布位置的映射：
     * 映射散在组件里，迟早出现"提示说去对话、高亮却在采集"这种自相矛盾的引导。
     */
    nextBlockId(state): string | null {
      const ask = this.nextAsk
      if (!ask) return null
      if (ask.target.to === 'chat') return 'talk'
      if (ask.target.to === 'tasks') return 'todo'
      // 缺口：补缺口既能在采集动线里看全貌，也能在画像里逐条看 —— 去采集动线，
      // 那里写着"这条挡着哪一步、去哪儿取"。
      if (ask.id.startsWith('gap.')) return 'collect'
      return null
    },
  },

  actions: {
    /** 挂载时拉真实工作台数据；失败静默（演示回落），成功后画像气泡换真数据 */
    async loadBackend() {
      // 没登录就别去敲这些端点：它们按登录态返回 401，
      // 敲一遍只会得到一串"缺少登录令牌"，然后靠 try/catch 咽掉。
      if (!authToken()) return
      try {
        const [ws, boot, notes, report] = await Promise.all([
          getWorkspace(),
          getBootstrap().catch(() => null),
          listNotes().catch(() => null),
          getReportFullText().catch(() => null),
        ])
        this.report = report
        /*
         * 行动计划：待办卡片的"为什么这一件"要用它。
         *
         * 读不到就是 null（还没到 ④），界面据此说"这一件还没定下来"，
         * 而不是拿阶段固定文案顶上 —— 那句文案回答了"这个阶段在做什么"，
         * 回答不了"为什么是这一件"。
         */
        this.actionPlan = await getActionPlan().catch(() => null)
        /*
         * 他写下过的东西要跟着账号回来。
         *
         * 读得到就用服务端那份**覆盖**本地：采集策略读的是服务端那一份，
         * 两边不一致时，界面上看到的和 AI 引用的就会是两句不同的话。
         */
        if (notes) {
          this.customTodos = notes.map((n) => ({ id: n.id, label: n.text, done: !!n.done, due: this.todoDue[n.id] }))
          this.todoSynced = true
        }
        if (boot) {
          this.appName = boot.app_name ?? ''
          this.copyBundle = (boot.copy_bundle ?? {}) as Record<string, string>
          const id = (boot as { identity?: Record<string, string> }).identity
          if (id?.nickname) this.identity = { nickname: id.nickname, role: id.role ?? 'student' }
          this.taskEntries = (boot.task_entries ?? []).map((t) => ({
            code: t.code, label: t.label ?? t.code, lead: t.lead_agent_name ?? null,
          }))
        }
        this.wsPanels = {
          action: ws.action_panel?.evaluation || '',
          review: ws.review_panel?.evaluation || '',
          report: ws.report_panel?.evaluation || '',
        }
        // 采集动线：缺什么、去哪取、为什么 —— 只搬形状，不重算
        const cp = ws.collection_panel
        if (cp) {
        this.collection = {
            missing: cp.missing ?? 0,
            bySource: cp.by_source ?? {},
            blocked: cp.blocked ?? [],
            nextSource: cp.next_source ?? null,
            items: (cp.items ?? []).map((it) => ({
              key: it.key,
              label: it.label ?? it.key,
              source: it.source ?? '',
              why: it.why ?? '',
              ask: it.ask ?? '',
              got: !!it.got,
              available: it.available !== false,
            })),
          }
        }
        /*
         * 教务系统的课表与成绩单。
         *
         * 没授权过就是 null（后端不编一份空的给你）——
         * "还没授权"和"这学期没课"在界面上必须是两句话。
         */
        const ap = ws.academic_panel
        this.academic = ap
          ? {
              school: ap.school ?? '',
              source: ap.source ?? '',
              term: ap.term ?? '',
              imported_at: ap.imported_at ?? '',
              note: ap.note ?? '',
              courses: (ap.courses ?? []).map((c) => ({
                name: c.name,
                teacher: c.teacher ?? '',
                weekday: c.weekday ?? 0,
                start_period: c.start_period ?? 0,
                end_period: c.end_period ?? 0,
                weeks: c.weeks ?? '',
                place: c.place ?? '',
                credit: c.credit ?? '',
                category: c.category ?? '',
              })),
              grades: (ap.grades ?? []).map((g) => ({
                term: g.term ?? '',
                name: g.name,
                credit: g.credit ?? '',
                score: g.score ?? '',
                point: g.point ?? '',
                category: g.category ?? '',
                kind: g.kind ?? '',
              })),
            }
          : null
        this.academicBound = !!ws.academic_panel
        // 气泡编排：后端已经把顺序算好了，前端照读
        this.layout = (ws.layout_panel ?? []).map((b) => ({
          id: b.id,
          label: b.label ?? b.id,
          hint: b.hint ?? '',
          weight: b.weight ?? 0,
          priority: b.priority ?? 0,
          why: b.why ?? '',
        }))
        const pp = ws.profile_panel
        this.profile = pp
          ? {
              overall: pp.overall_confidence ?? 0,
              coverage: pp.coverage ?? 0,
              fields: pp.fields ?? [],
              dimensions: (pp.fields ?? []).map((f) => ({
                id: f.key,
                name: f.label || this.copyBundle[`profile.field.${f.key}`] || f.key,
                value: f.confidence ?? 0,
              })),
              gaps: (pp.gaps ?? []).map((g) => ({
                id: g.key,
                name: g.label || this.copyBundle[`profile.gap.${g.key}`] || g.key,
                question: g.reason ?? '',
                suggested: g.suggested_next_action ?? '',
              })),
              updatedAt: pp.updated_at ?? null,
            }
          : null
        const notices = await getPendingNotifications().catch(() => [])
        for (const n of notices) {
          if (this.acceptedNotices.includes(n.id)) continue
          this.pushFloat({
            id: n.id,
            type: 'notice',
            kicker: NOTIFY_CHANNEL_LABEL[n.channel ?? ''] ?? '教练提醒',
            title: n.title,
            body: n.body || '',
            // 外部情报用 intel（会自己淡出），其余是教练提醒（留着手动关）
            tone: n.action && (n.action as { kind?: string }).kind === 'intel' ? 'intel' : 'coach',
            action: n.action
              ? {
                  label: String((n.action as { label?: string }).label || '看看'),
                  kind: 'intel',
                }
              : undefined,
          } as FloatItem)
        }
        // 集群判断的"下一步"也进同一叠（初次进入时就能看到）
        this.syncAskFloat()
      } catch (cause) {
        if (cause instanceof UnauthorizedError) {
          /*
           * 令牌过期或被伪造：清掉它、把登录浮层掀起来。
           *
           * 只在控制台打一行日志是不够的 —— 用户看到的是一个"什么都没有"的今天，
           * 既不知道出了什么事，也不知道该做什么（页面看上去像坏了）。
           */
          clearToken()
          // 身份也要一起清：只清令牌的话，顶栏还挂着那个已经失效的旧名字。
          this.identity = null
          this.authError = '登录状态过期了，重新登录后接着说。'
          this.authOpen = true
          return
        }
        if (!(cause instanceof BackendUnavailableError)) console.warn('[workspace] 业务错误：', cause)
      }
    },

    enterPortal() {
      this.portalSeen = true
    },

    /**
     * 切到另一条任务会话，并把它的历史轮次灌进对话层。
     *
     * 会话是"可拆可续"的载体：换一件事可以另开一条，停几天再回来接着走。
     * 这里的 `history` 来自**逐轮落库**（`/app/sessions/{id}/turns`）——
     * 在补上那条落库之前，切换会话只能得到一个空对话框。
     */
    switchSession(
      taskId: string,
      history: { role: 'ai' | 'me'; text: string; actor?: string }[],
    ) {
      this.backendTaskId = taskId
      this.chatTyping = false
      this.clearChatPrompt()
      const seed = history.length
        ? history
        : [{ role: 'ai' as const, text: '这条会话还没有逐轮记录 —— 说一句就开始了。' }]
      this.chatTurns = seed.map((item) => ({
        id: this.chatSeq++,
        role: item.role,
        text: item.text,
        actor: item.actor,
      }))
    },

    /* ---- 登录浮层 ---- */

    openAuth(mode: 'login' | 'register' = 'login') {
      this.authMode = mode
      this.authError = ''
      this.authOpen = true
    },
    closeAuth() {
      if (this.authBusy) return
      this.authOpen = false
      this.authError = ''
    },
    switchAuthMode() {
      this.authMode = this.authMode === 'login' ? 'register' : 'login'
      this.authError = ''
    },

    /**
     * 登录 / 注册并登录。
     *
     * 成功后顺手把工作台数据拉起来 —— 登录和"这一屏能用"是同一件事，
     * 分成两步做就会出现"进来了但全是空的"那种中间态。
     * 返回是否成功，跳转交给调用方。
     */
    async signIn(account: string, password: string): Promise<boolean> {
      const who = account.trim()
      if (!who || !password) {
        this.authError = '账号和密码都要填。'
        return false
      }
      this.authBusy = true
      this.authError = ''
      try {
        const res = await authenticate(this.authMode, who, password)
        saveToken(res.token)
        this.identity = { nickname: res.user_id || who, role: res.role || 'student' }
        await this.loadBackend()
        this.authOpen = false
        return true
      } catch (cause) {
        this.authError = messageOf(cause)
        return false
      } finally {
        this.authBusy = false
      }
    },

    /**
     * 退出登录。
     *
     * 后端撤令牌失败**不阻塞**本地退出：用户按下退出就该立刻退出，
     * 撤不掉的那一枚到点自然失效，不能拿它把人留在登录态里。
     */
    signOut() {
      signOutRemote().catch(() => {})
      clearToken()
      this.$reset()
    },

    setStage(stage: StageId) {
      this.stage = stage
      this.stageChoice = null
    },
    chooseStage(option: string) {
      this.stageChoice = this.stageChoice === option ? null : option
    },

    choose(id: string) {
      this.chosenOption = this.chosenOption === id ? null : id
    },
    toggleTask(id: string) {
      this.doneTasks[id] = !this.doneTasks[id]
      if (this.doneTasks[id]) track('task_done_click', { task_id: id })
    },

    /* ---- 学信网 ---- */
    bindChsi() {
      this.chsiBound = true
    },
    unbindChsi() {
      this.chsiBound = false
    },
    /** 导入完成（课表与成绩单已经落到后端快照里） */
    bindAcademic() {
      this.academicBound = true
    },

    /* ---- 自建待办 ---- */
    /**
     * 写下一条待办。
     *
     * 先落界面、再落库：写下来的东西必须**立刻**出现在他眼前；
     * 后端不可达时它仍然留在本地（这一版不会假装已经存好）。
     *
     * 但它必须往服务端走一趟 —— 采集策略要靠这些原话把该取的数据顶到前面，
     * 只存在浏览器里，后端就永远读不到"他写了想冲秋招"。
     */
    async addTodo(label: string, due?: string) {
      const text = label.trim()
      if (!text) return
      const localId = `u${Date.now()}`
      this.customTodos = [...this.customTodos, { id: localId, label: text, done: false, due }]
      this.assignTodoDue(localId, due)
      try {
        const saved = await addNote(text)
        // 换成服务端的 id：状态要跟着服务端走，否则勾选/删除会打在一条本地临时 id 上
        this.customTodos = this.customTodos.map((t) =>
          t.id === localId ? { id: saved.id, label: saved.text, done: !!saved.done, due } : t,
        )
        this.assignTodoDue(localId, undefined)
        this.assignTodoDue(saved.id, due)
      } catch (cause) {
        if (cause instanceof UnauthorizedError || cause instanceof BackendUnavailableError) {
          this.todoSynced = false
        }
      }
    },

    /** 待办 ↔ 那一天的归属，写 state 的同时落 localStorage（id 变更时先删旧键） */
    assignTodoDue(id: string, due?: string) {
      const next = { ...this.todoDue }
      if (due) next[id] = due
      else delete next[id]
      this.todoDue = next
      localStorage.setItem(TODO_DUE_KEY, JSON.stringify(next))
    },
    async toggleCustomTodo(id: string) {
      this.customTodos = this.customTodos.map((t) => (t.id === id ? { ...t, done: !t.done } : t))
      const next = this.customTodos.find((t) => t.id === id)
      if (!next) return
      try {
        await setNoteDone(id, next.done)
      } catch {
        // 后端不可达：界面上的勾选状态先保留，不回滚 —— 回滚比没同步更让人费解
      }
    },
    async removeCustomTodo(id: string) {
      this.customTodos = this.customTodos.filter((t) => t.id !== id)
      try {
        await removeNote(id)
      } catch {
        // 同上：本地已经删掉，就不把它弹回来
      }
    },

    /* ---- 智能体建议 ---- */
    acceptSuggestion(id: string) {
      if (!this.acceptedSuggestions.includes(id)) this.acceptedSuggestions = [...this.acceptedSuggestions, id]
      this.dismissedSuggestions = this.dismissedSuggestions.filter((x) => x !== id)
      track('todo_suggestion_accept', { suggestion_id: id })
    },
    dismissSuggestion(id: string) {
      if (!this.dismissedSuggestions.includes(id)) this.dismissedSuggestions = [...this.dismissedSuggestions, id]
      this.acceptedSuggestions = this.acceptedSuggestions.filter((x) => x !== id)
      track('todo_suggestion_dismiss', { suggestion_id: id })
    },

    openDrawer(title: string, subtitle: string, items: unknown[]) {
      this.drawer = { title, subtitle, items }
    },
    closeDrawer() {
      this.drawer = null
    },
    openOverlay(
      name:
        | 'portrait'
        | 'tasks'
        | 'brief'
        | 'bind'
        | 'timetable'
        | 'match'
        | 'talk'
        | 'collect'
        | 'plans'
        | 'action'
        | 'calendar'
        | 'sessions'
        | 'review'
        | 'intel',
      focus: 'gaps' | null = null,
    ) {
      this.overlay = name
      this.portraitFocus = name === 'portrait' ? focus : null
    },
    closeOverlay() {
      this.overlay = null
      this.portraitFocus = null
    },

    /* ---- 浮窗 ---- */
    pushFloat(item: FloatItem) {
      if (this.floats.some((f) => f.id === item.id)) return
      this.floats = [item, ...this.floats]
    },
    dismissFloat(id: string) {
      // 关掉 = 读过。不回执的话，下次进页面同一条还会再飘一次。
      if (!id.startsWith('ask:')) markNotificationRead(id).catch(() => {})
      this.floats = this.floats.filter((f) => f.id !== id)
    },
    dismissAllFloats() {
      for (const item of this.floats) {
        if (!item.id.startsWith('ask:')) markNotificationRead(item.id).catch(() => {})
      }
      this.floats = []
    },
    acceptNotice(id: string) {
      if (!this.acceptedNotices.includes(id)) this.acceptedNotices = [...this.acceptedNotices, id]
    },
    answerQuestion(id: string, option: string) {
      this.answered = { ...this.answered, [id]: option }
    },

    /* ---- 主画布块：关掉 + 自己回来 ---- */
    hideBlock(id: string) {
      const wait = BLOCK_RETURN_MS[id] ?? 45000
      this.hiddenBlocks = { ...this.hiddenBlocks, [id]: Date.now() + wait }
    },
    /**
     * "知道了" —— 认下这件事，本会话不再提醒。
     *
     * 与 `hideBlock` 的区别是语义：那个是"让位，过会儿还回来"（时间到了自己飘回），
     * 这个是"我读过了，别再问了"。交接提醒（谁在帮你）按下"知道"就该是后者，
     * 否则 40 秒后同一张卡又回来，用户只会以为刚才那一下没生效。
     */
    ackBlock(id: string) {
      if (!this.ackedBlocks.includes(id)) this.ackedBlocks = [...this.ackedBlocks, id]
      const next = { ...this.hiddenBlocks }
      delete next[id]
      this.hiddenBlocks = next
    },
    /** 每秒扫一次：到点的块自己飘回来 */
    sweep() {
      const now = Date.now()
      let changed = false
      const next: Record<string, number> = {}
      for (const [key, until] of Object.entries(this.hiddenBlocks)) {
        if (until > now) next[key] = until
        else changed = true
      }
      if (changed) this.hiddenBlocks = next
    },

    /** 把被关掉的块一次叫回来（右键菜单的"全部叫出来"、双击空白画布） */
    summonAll() {
      this.hiddenBlocks = {}
    },

    /* ---- 对话 ---- */
    /**
     * 从某处动作进入对话：把"要回答的那一句"一起带过去。
     *
     * 这是整个"AI 指哪打哪"的落点：用户不用先找到对话入口、再想一遍该说什么，
     * 点完就已经站在问题上了。
     */
    askChat(prompt = '', options: GuideOption[] = []) {
      this.chatPrompt = prompt
      this.chatOptions = options
      this.chatAnswered = null
      this.chatClarify = ''
      this.overlay = 'talk'
    },

    /**
     * 在任意地方把对话叫出来。
     *
     * 先收掉当前这一层：对话是"我现在要说清楚一件事"，
     * 叠在别的东西上面就变成了"一边看一边说"，两件都做不好。
     */
    callTalk() {
      this.drawer = null
      this.overlay = 'talk'
      track('talk_open', { from: 'anywhere' })
    },

    /**
     * 把"智能体集群判断你现在最该做的那件事"塞进浮窗叠。
     *
     * 这是用户要的那条口径：**下一步不是让他自己找，而是集群判断完往前面塞**。
     * 每一条 ask 只塞一次（按 id 去重，关掉就不再回来）—— 反复弹同一件事，
     * 比不弹更让人烦。
     */
    syncAskFloat() {
      const ask = this.nextAsk
      if (!ask) return
      const id = `ask:${ask.id}`
      if (this.askFloatSeen.includes(id)) return
      this.askFloatSeen = [...this.askFloatSeen, id]
      this.pushFloat({
        id,
        type: 'notice',
        kicker: ask.who ? `${ask.who}的建议` : '下一步',
        title: ask.label,
        body: ask.why,
        tone: 'coach',
        action: { label: ask.cta, kind: 'ask' },
      })
    },

    /** 点浮窗里的"下一步"：按它要去的目标把人送过去（不猜、不硬跳）。 */
    goToNextAsk() {
      const ask = this.nextAsk
      if (!ask) return
      if (ask.target.to === 'chat') {
        // 选项原样带过去（含 option_id / value），点下去之后才知道用户选的是哪一个
        this.askChat(ask.target.prompt, ask.target.options)
        return
      }
      if (ask.target.to === 'tasks') {
        this.openOverlay('tasks')
        return
      }
      this.openDrawer(ask.target.title, '', [
        { source: '下一步', detail: ask.target.body, confidence: 1, at: '现在' },
      ])
    },

    /**
     * 取一批外部情报。
     *
     * 两个入口共用它：画布上那一块（打开时读缓存）与"现在去取一次"（真的去打外部站点）。
     * `force=false` 时，**同一个主题下已经有这一批就不再取** —— 打开一次浮层就打一次
     * 外部站点，既慢又对人家不礼貌。
     *
     * 失败不抛错到界面：情报是锦上添花，取不到就如实说"这次没取到"，不编。
     */
    async loadIntel(force = false, topic?: string) {
      if (topic !== undefined) this.intelTopic = topic
      /*
       * **只有用户自己填的方向才当成主题发下去**；没填就发空，
       * 由后端按画像推（`intel_topic`）。
       *
       * 为什么不在这里替它推：编排器喂给模型的那一批也是后端推的。
       * 前端再推一次，两边一旦差一点（"计算机" vs "计算机科学与技术"），
       * 就是两个缓存桶、两批数据 —— 用户会看到面板一批、主理引用的另一批，
       * 而这两批都叫"外部情报"。
       */
      const query = this.intelTopic.trim()
      if (this.intelBusy) return
      if (!force && this.intel && this.intel.topic === query) return
      this.intelBusy = true
      this.intelError = ''
      try {
        const res = force ? await refreshIntel(query) : await getIntel(query)
        this.intel = {
          items: res?.items ?? [],
          fetchedAt: String(res?.fetched_at ?? ''),
          topic: query,
        }
        if (!this.intel.items.length) {
          /*
           * **空结果不是错误**：空态自己有文案（"填一个方向就能试" + 三个可点的起点），
           * 这里再补一句"没取到"只是把同一句话说两遍。留空。
           */
          this.intelError = ''
        }
      } catch (cause) {
        /* 出错才说话，且说人话：原始报错（HTTP 500 / 超时）进控制台，不进界面 */
        console.warn('[intel] 取数失败：', cause)
        this.intelError = '这次没能连上外部渠道，过一会儿再试。'
      } finally {
        this.intelBusy = false
      }
    },

    /**
     * 单条情报的"凭什么这么说" —— 还是走全站统一的溯源抽屉。
     *
     * 浮层里每条卡已经把原文摊开了，所以这个入口只留给"想再核对一层"的人：
     * 抽屉里是**字段化的原文 + 来源名 + 原页面**，和报告、画像用的是同一种读法。
     */
    openIntelItem(item: IntelItem) {
      const reading = readIntelText(item.text ?? '', item.title ?? '')
      const at = readFetched(item.fetched_at ?? '')
      this.openDrawer(item.title || item.kind_label || '外部情报', item.source_name || '公开渠道', [
        ...(reading.intro
          ? [{ source: '原文摘录', detail: reading.intro, confidence: 1, at }]
          : []),
        ...reading.fields.map((f) => ({ source: f.label, detail: f.value, confidence: 1, at })),
        ...reading.loose.map((line) => ({ source: '原文', detail: line, confidence: 1, at })),
        { source: '来源', detail: item.source_name || '公开渠道', confidence: 1, at },
        { source: '原页面', detail: item.source_url || '—', confidence: 1, at },
      ])
    },

    /**
     * 从别处打开情报浮层，并停在某一条上。
     *
     * 对话里那条"依据的外部信息"点进来就走这里：看到的是**同一条**，
     * 而不是又开一个抽屉把同一段话再说一遍。两处界面认的是同一个 id，
     * 这才叫"打通"，否则只是"两个地方都能看到情报"。
     */
    openIntelAt(id = '') {
      this.intelFocus = id
      this.overlay = 'intel'
    },

    /**
     * 把一条外部事实带进对话。
     *
     * 这是情报与 AI 之间**用户看得见的那一次交接**：他点"拿去问主理"，
     * 问题已经写好在输入框里，那一句里带着这条情报的关键词 ——
     * 于是编排器这一轮真的会去取数，回答里也会带回来源。
     */
    askAboutIntel(text: string) {
      this.chatDraft = text
      this.overlay = 'talk'
    },

    /** 回答完就把待答提示收掉 —— 它是一次性的，不该一直挂在输入框上 */
    clearChatPrompt() {
      this.chatPrompt = ''
      this.chatOptions = []
      this.chatClarify = ''
    },

    /**
     * 发一轮话。
     *
     * `option` 是"这一轮点的是哪个选项"。带它的时候，**选项的身份一起发下去**
     * （`sendMessage` 的 option_id / value），而不是只把它当一句话 ——
     * 只发 label 的话后端认不出这是"选了上一轮的那个选项"，
     * 于是可能把同一个问题再问一遍（见 store.chatOptions 的说明）。
     *
     * `materials` 是"这一轮一起交上去的材料"（已经上传完成、拿到 id 的）。
     * 只发 id：正文在服务端，发 `text` 里就等于把文件又摊开在对话里 ——
     * 那正是用户抱怨过的那件事。气泡上显示的是一枚材料卡。
     */
    async sendChat(
      text: string,
      option?: GuideOption,
      materials: { material_id: string; name: string; chars: number }[] = [],
    ) {
      const value = text.trim()
      // 只交材料、不写字也是完整的一轮（"这是我传的材料"本身就是一句话）
      if (!value && !materials.length) return
      const names = materials.map((m) => m.name).join('、')
      // 一个字都没打时替他补一句短的：**不补正文**，补的是"我交了什么"
      const spoken = value || `我传了一份材料：${names}`
      // 记住"这一轮答的是哪一句、答的哪一条"：后端若原地打转，界面要靠它说清楚
      this.chatAnswered = option
        ? {
            question: this.chatPrompt,
            optionId: option.option_id ?? option.label,
            label: option.label,
            optionLabels: this.chatOptions.map((o) => o.label),
          }
        : null
      // 用户已经在答了，那句话的使命就结束了
      this.clearChatPrompt()
      this.chatTurns = [
        ...this.chatTurns,
        {
          id: this.chatSeq++,
          role: 'me',
          text: spoken,
          material: materials.length
            ? { name: names, chars: materials.reduce((sum, m) => sum + m.chars, 0) }
            : undefined,
        },
      ]
      this.chatTyping = true
      try {
        // 真后端：free_chat 任务入口 → 编排器单轮骨架（判环节→选主理→产出→引导收尾）
        if (!this.backendTaskId) {
          const session = await enterTask('free_chat')
          this.backendTaskId = session.task_id
        }
        const turn = await sendMessage(
          this.backendTaskId as string,
          spoken,
          option,
          materials.map((m) => m.material_id),
        )
        this.applyTurn(turn, option)
      } catch (cause) {
        this.chatAnswered = null
        this.chatTyping = false
        this.chatTurns = [
          ...this.chatTurns,
          { id: this.chatSeq++, role: 'ai', text: chatFailure(cause) },
        ]
        return
      }
      this.chatTyping = false
    },

    /** 把一轮真实回包写进本地状态：对话气泡 + AgentRail 的权威状态 */
    applyTurn(turn: TurnView, chosen?: GuideOption) {
      for (const message of turn.messages ?? []) {
        if (message.role !== 'agent') continue
        this.chatTurns = [
          ...this.chatTurns,
          {
            id: this.chatSeq++,
            role: 'ai',
            text: message.text,
            actor: message.agent_name ?? turn.badge.name,
            chart: message.chart ?? undefined,
            intelRefs: message.intel_refs ?? [],
          } as ChatTurn,
        ]
      }
      if (turn.disclosure) {
        // 换主理必须显式告知——交接卡是 AgentRail"为什么换人"的权威来源
        this.chatTurns = [
          ...this.chatTurns,
          {
            id: this.chatSeq++,
            role: 'ai',
            text: `🔁 ${turn.disclosure.text}`,
            actor: '主理团',
          } as ChatTurn,
        ]
      }
      this.rail = {
        stage: turn.stage,
        leadName: turn.badge.name,
        disclosure: turn.disclosure?.text ?? null,
        // 主理的依据（理论标签）：点开取 /app/theory-cards/{id} 的正文
        theories: turn.badge.theory_refs ?? [],
      }
      this.railCards = (turn.pipeline_cards ?? []).map((c) => ({
        stage: c.stage,
        title: c.title ?? '',
        active: !!c.active,
        status: c.status ?? 'empty',
      }))
      /*
       * 一轮之后把工作台数据重拉一遍。
       *
       * 为什么必须重拉：这一轮可能刚改了画像（① 采集会把字段写进库）、缺口、
       * 资产版本或气泡编排 —— 那些都是**后端的事实**，前端手上那份是进页面那一刻的旧值。
       * 不重拉的样子很具体（端到端实测）：库里已经有 7 个画像字段，
       * 而界面上画像仍是空的、采集清单还在说"还缺 6 条"。
       *
       * 不 await：这是背景刷新，"回复已经出现"不该再等一轮网络。
       */
      void this.loadBackend()

      // 编排器给的下一步：进状态，交给 nextAsk 决定它出现在哪
      const guide = (turn.guide ?? null) as unknown as BehaviorGuide | null
      this.guide = guide && guide.kind ? guide : null

      /*
       * 追问与选项直接落到输入框上方 —— 这是"AI 问一句，用户答一句"的闭环。
       * 不这么做的话，AI 的问题只存在于回复正文里，用户读完就得自己记住、
       * 再想一遍怎么答；而它其实就应该待在那儿等着被回答。
       */
      if (this.guide && (this.guide.kind === 'question' || this.guide.kind === 'options')) {
        const question = this.guide.question || this.guide.text
        const options = this.guide.options ?? []
        this.chatPrompt = question
        this.chatOptions = options
        /*
         * 原地打转要说出来。
         *
         * 用户点了选项、回复也追加了，但回包又问回**同一句**（或同一组选项），
         * 其中还含着刚点过的那一条 —— 这一轮系统没有往前走。
         * 之前的界面在这种情况下静默地把一模一样的问题再摆一遍，
         * 用户只能得出"点了没用"的结论。现在：那条选项标成已答，
         * 并给一句能继续往下走的提示。
         *
         * 判据是"同一个选项又出现了"，不看措辞是否一字不差 ——
         * 模型复述问题时经常换标点或换个说法。
         */
        const answered = this.chatAnswered
        const repeated =
          !!chosen &&
          !!answered &&
          options.some((o) => (o.option_id ?? o.label) === answered.optionId) &&
          (question.trim() === answered.question.trim() ||
            (options.length > 0 &&
              options.length === answered.optionLabels.length &&
              options.every((o, i) => o.label === answered.optionLabels[i])))
        this.chatClarify = repeated && answered
          ? `「${answered.label}」这条我收到了，但这一轮没往前走。换一条，或者直接把你的情况补一句。`
          : ''
      } else {
        // 这一轮不是"等你回答"（小任务 / 提醒）：旧的选项与澄清都不能留在输入框上方
        this.chatPrompt = ''
        this.chatOptions = []
        this.chatClarify = ''
      }

      // 集群判断出的"下一步"同时塞进浮窗叠：用户可能没在看对话，
      // 但那条消息应该像便签一样飘过来（同一件事只提醒一次）。
      this.syncAskFloat()
    },
  },
})
