/*
 * 后端 BFF 客户端。
 *
 * 两条规矩，别的都从它们长出来：
 *
 * 1. **类型不是手写的。** 所有视图类型都从 `./types.ts`（`npm run gen:api` 按
 *    `../contracts/openapi.json` 生成）取。此前这里手抄了一份同名接口，
 *    后端改字段时两边都不会报错，只是界面上某个格子永远空着。
 * 2. **失败要看得见。** 后端不可达 / 返回 1007（依赖不可用）抛
 *    `BackendUnavailableError`，1004 抛 `UnauthorizedError`（拉起登录浮层），
 *    其余 `code != 0` 如实抛出错误文案 —— 不回落本地假数据：
 *    "看起来都对、其实没实现"正是最难发现的一种坏。
 *
 * 基地址是相对路径 `/api/v1`：开发期由 vite 代理、部署形态由 nginx 反代，
 * 两种形态同一条路径，产物里不需要编译进后端地址。
 */

import type { components } from './types'

type Schema = components['schemas']

/* ---- 视图类型：一律取生成物，不在前端重抄一遍 ---- */

export type BootstrapInfo = Schema['BootstrapView']
export type WorkspaceInfo = Schema['WorkspacePageView']
export type TurnView = Schema['ConversationTurnView']
export type TaskSessionInfo = Schema['TaskSessionView']
export type UserNote = Schema['NoteView']
export type CoachNotification = Schema['CoachNotificationView']
export type ReportFullText = Schema['ReportFullTextView']
export type DirectionPlans = Schema['DirectionPlanListView']
export type DirectionPlan = Schema['DirectionPlanView']
export type ActionPlan = Schema['ActionPlanView']
export type ActionPhase = Schema['ActionPhaseView']
export type ActionTask = Schema['ActionTaskView']
export type CalendarNode = Schema['CalendarNodeView']
export type AssetVersion = Schema['AssetVersionView']
export type SessionList = Schema['SessionListView']
export type SessionItem = Schema['TaskSessionView']
export type TurnHistoryItem = Schema['ConversationMessageView']
export type TrackEvent = Schema['TrackEventView']
export type PortalContent = Schema['PortalView']
export type TheoryCard = Schema['TheoryCardView']
export type AcademicImportAck = Schema['AcademicImportAck']
export type TheoryRef = Schema['TheoryRefView']
export type ProfileField = Schema['ProfileFieldView']
export type ProfileGap = Schema['ProfileGapView']
/** 对话里摆出来的一块可视件（图 / 时间线 / 对比表…）—— 前端按 `kind` 分发渲染 */
export type RenderableView = Schema['RenderableView']
export type AchievementListView = Schema['AchievementListView']

export class BackendUnavailableError extends Error {}
export class UnauthorizedError extends Error {}

/*
 * 错误码：数字从后端 `ErrorCode` 枚举来（`api/dto/common.py`）。
 * 类型标注 `Schema['ErrorCode']` 是编译期的一半守卫——后端删掉某个码，
 * `npm run typecheck` 立刻红；数值对不对由 `tests/test_frontend_alignment.py` 比对。
 */
const CODE_UNAUTHORIZED: Schema['ErrorCode'] = 1004
const CODE_DEPENDENCY_UNAVAILABLE: Schema['ErrorCode'] = 1007
const CODE_OK: Schema['ErrorCode'] = 0

export const authToken = () => localStorage.getItem('zhiyin_token') || ''
export const saveToken = (t: string) => localStorage.setItem('zhiyin_token', t)
export const clearToken = () => localStorage.removeItem('zhiyin_token')

interface Envelope<T> {
  code: number
  message: string
  data: T | null
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'application/json' }
    const token = authToken()
    if (token) headers.Authorization = `Bearer ${token}`
    res = await fetch(`/api/v1${path}`, { headers, ...init })
  } catch (cause) {
    throw new BackendUnavailableError(String(cause))
  }
  return unwrap<T>(res)
}

/**
 * 信封解析：JSON 与上传两条路共用。
 *
 * 抽出来不是为了少写几行 —— 上传之后如果各写一份判定，就会出现"某一条路上
 * 1004 没被认成未登录"这种只在一半场景里发作的偏差。
 */
async function unwrap<T>(res: Response): Promise<T> {
  if (res.status >= 500) throw new BackendUnavailableError(`HTTP ${res.status}`)
  const body = (await res.json().catch(() => null)) as Envelope<T> | null
  if (!body) throw new BackendUnavailableError('empty body')
  if (body.code === CODE_DEPENDENCY_UNAVAILABLE) throw new BackendUnavailableError(body.message)
  if (body.code === CODE_UNAUTHORIZED) throw new UnauthorizedError(body.message)
  if (body.code !== CODE_OK) throw new Error(body.message || `code=${body.code}`)
  return body.data as T
}

/**
 * 带文件的上传（multipart/form-data）。
 *
 * 与 `api()` 分的唯一一件事是**不设 Content-Type**：multipart 的 boundary 必须由浏览器
 * 自己写，手写一个 `application/json` 会让后端连文件都收不到（那是"传了但读不出来"
 * 最容易踩的一脚）。其余（令牌、信封、错误分类）与 `api()` 完全一致。
 */
async function upload<T>(path: string, form: FormData): Promise<T> {
  let res: Response
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    const token = authToken()
    if (token) headers.Authorization = `Bearer ${token}`
    res = await fetch(`/api/v1${path}`, { method: 'POST', headers, body: form })
  } catch (cause) {
    throw new BackendUnavailableError(String(cause))
  }
  return unwrap<T>(res)
}

/* ---- 会话与对话 ---- */

/**
 * 登录 / 注册。
 *
 * 两条**独立**的后端路径，不在前端拼 `mode` 再去替换路径段 ——
 * 拼出来的路径跨语言比对时看不出来（守卫只能看到 `/app/auth/{}`），
 * 后端改名也不会有任何东西报警。
 */
export function authenticate(mode: 'login' | 'register', account: string, password: string) {
  const path = mode === 'login' ? '/app/auth/login' : '/app/auth/register'
  return api<Schema['LoginResult']>(path, {
    method: 'POST',
    body: JSON.stringify({ account, password }),
  })
}

/** 退出登录：后端撤令牌。撤不掉不阻塞本地退出（见 stores/session.ts） */
export function signOutRemote() {
  return api<{ revoked: boolean }>('/app/auth/logout', { method: 'POST' })
}

export function enterTask(taskCode: string) {
  return api<TaskSessionInfo>('/app/task/enter', {
    method: 'POST',
    body: JSON.stringify({ task_code: taskCode }),
  })
}

/** 任务会话清单：任务名、当前环节、主理、进度、最近活动。 */
export function listSessions() {
  return api<SessionList>('/app/sessions')
}

/**
 * 一条会话的逐轮原文（用户与主理各算一轮），按时间正序。
 *
 * 这条链路此前是断的：库里只存累积摘要，**用户自己说的话一个字都没有** ——
 * 会话列表能列出来，点进去却是空的。
 */
export function listSessionTurns(taskId: string, limit = 200) {
  return api<TurnHistoryItem[]>(
    `/app/sessions/${encodeURIComponent(taskId)}/turns?limit=${limit}`,
  )
}

/**
 * 跟踪时间线：⑤ 复盘环节的载体。
 *
 * 它是"这段时间发生过什么"的事实清单（里程碑 / 提醒 / 警告 / 学期复盘 / 教练消息），
 * 与对话原文分开 —— 对话是过程，这里是结果。此前只有写、没有读。
 */
export function listTrackEvents(limit = 50) {
  return api<TrackEvent[]>(`/app/track/events?limit=${limit}`)
}

/**
 * 发一轮话。
 *
 * `option` 是"这一轮点的是哪个选项"（后端上一轮 `guide.options` 里那一条）。
 * 带上它，后端才分得清"用户明确选了这一条"和"用户随口说了这几个字"——
 * 只发 label 的话，同一个问题可能被再问一遍（见 stores/session.ts 的 chatOptions）。
 */
export function sendMessage(
  taskId: string,
  message: string,
  option?: { option_id?: string; value?: unknown },
  materialIds: string[] = [],
) {
  return api<TurnView>('/app/conversation/message', {
    method: 'POST',
    body: JSON.stringify({
      task_id: taskId,
      message,
      client_msg_id: `c${Date.now()}`,
      option_id: option?.option_id ?? null,
      option_value: option?.value ?? null,
      material_ids: materialIds,
    }),
  })
}

/**
 * 交一份材料（上传文件，不在浏览器里读成文本）。
 *
 * 回执里**没有正文**：正文留在服务端，只在用到它的那一轮进模型输入。
 * 之前是把文件读成一大段文本直接发成一条消息 —— 对话框里当场铺开几百行，
 * 用户要读的是主理的回话，不是自己刚交上去的原文。
 */
export function uploadMaterial(file: File) {
  const form = new FormData()
  form.append('file', file, file.name)
  return upload<Schema['ConversationMaterialView']>('/app/conversation/material', form)
}

/* ---- 埋点（体验型事件，channel=frontend；事件码见 data/registry/track_events.json） ---- */

/*
 * 埋点。
 *
 * 失败**静默**是有意的：埋点是体验型事件，不该因为它把用户的动作卡住。
 * 但"服务端不认这个事件码"是**配置错**，不是网络抖动 —— 它必须留痕，
 * 否则前端埋点会整片失效而没人知道（实测就发生过：前端自己发明了一个
 * `talk_open`，服务端按注册表拒收，`accepted: false` 被前端完全忽略，
 * 库里那条事件一直是 0 行）。
 */
const warnedEvents = new Set<string>()

export function track(event: string, payload: Record<string, unknown> = {}) {
  api<{ accepted: boolean; event: string }>('/app/track', {
    method: 'POST',
    body: JSON.stringify({ event, payload }),
  })
    .then((res) => {
      if (res && res.accepted === false && !warnedEvents.has(event)) {
        warnedEvents.add(event)
        console.warn(
          `[track] 事件码「${event}」被拒收。` +
            '前端埋点的事件码必须先在 data/registry/track_events.json 登记（channel=frontend）。',
        )
      }
    })
    .catch(() => {
      /* 网络原因导致的埋点失败仍然静默：不阻塞交互 */
    })
}

/* ---- 启动装配与工作台 ---- */

export function getBootstrap() {
  return api<BootstrapInfo>('/app/bootstrap')
}

/**
 * 门户内容（**公开接口，未登录也能读**）。
 *
 * 门户是访客第一眼看到的一页，内容全是产品自己的话（文案 / 信任块 / 横幅 /
 * FAQ / 任务入口 / 开关）。此前这些写死在前端 `data/portal.ts` ——
 * 改一句主张要发一次前端版本，是"文案不进代码"这条底线上的最后一处例外。
 */
export function getPortal() {
  return api<PortalContent>('/app/portal')
}

export function getWorkspace() {
  return api<WorkspaceInfo>('/app/workspace')
}

/** 陪伴教练主动介入通知出队（浮窗轮询，后端在线才有效） */
export function getPendingNotifications() {
  return api<CoachNotification[]>('/app/notifications/pending')
}

/**
 * 把一条通知标成已读（浮窗关掉时调）。
 *
 * 不回执的话，"未读"出队会在每次进页面时把它再推一遍 ——
 * 用户看到的是"这条我明明关过，怎么又来了"。
 */
export function markNotificationRead(id: string) {
  return api<{ read: boolean }>(`/app/notifications/${encodeURIComponent(id)}/read`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

/* ---- 外部情报：按你的专业与方向取回的公开事实 ---- */

export interface IntelItem {
  id: string
  kind: string
  /** 类别的中文名 —— 界面显示它，不显示 kind */
  kind_label: string
  title: string
  text: string
  source_url: string
  /** 来源的中文称呼（如「学职平台 · 学信网」）—— 界面显示它，不显示网址 */
  source_name: string
  fetched_at: string
}

/**
 * 外部情报（`GET /app/intel`）。
 *
 * 内容来自公开渠道（学职平台：专业对口的职业、岗位要求、校友案例），
 * **每条都带来源链接** —— 这类信息"凭什么这么说"就是那个链接。
 * 没有来源的条目服务层不会返回，所以这里不需要再过滤一次。
 */
/**
 * 外部情报。
 *
 * **不需要登录令牌**：情报是爬公开数据的，登录只影响"能不能按你的画像收窄"。
 * `topic` 给了就按它取（未登录时的主要用法）。
 */
/**
 * 情报接口的路径。
 *
 * 拼在一个普通字符串里（而不是让 `api<>()` 直接吃模板串）：前端的接口对齐守卫
 * 是按字面量扫路径的，模板串会把它扫成 `/app/intel{}` 这种对不上的东西。
 */
function intelPath(topic: string, refresh = false): string {
  const base = refresh ? '/app/intel/refresh' : '/app/intel'
  return topic ? `${base}?q=${encodeURIComponent(topic)}` : base
}

export function getIntel(topic = '') {
  return api<{ items: IntelItem[]; fetched_at: string }>(intelPath(topic))
}

/** 现在去取一次（用户主动点；登录状态下后端会推一条通知，浮窗会冒出来）。 */
export function refreshIntel(topic = '') {
  return api<{ items: IntelItem[]; fetched_at: string }>(intelPath(topic, true), {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

/* ---- 理论卡正文：标签只给 id 与名字，正文按需取 ---- */

/**
 * 理论卡正文（`GET /app/theory-cards/{id}`）。
 *
 * 对话回包里的 `theory_refs` 只有 id / 展示名 —— 那是刻意的：一轮回复可能引三五个
 * 理论，正文一次性塞进回复里既啰嗦又过期得快。点开标签时来这里取正文，
 * 内容是**动态资源**（`data/registry/theory_cards.json`），改它不发版。
 * 取不到（1002）如实抛出，界面说"这张卡还没配"，而不是画一张只有标题的空卡。
 */
export function getTheoryCard(theoryId: string) {
  return api<TheoryCard>(`/app/theory-cards/${encodeURIComponent(theoryId)}`)
}

/* ---- 报告正文（只读资产版本，不重新生成） ---- */

/**
 * 完整报告正文：`sections` 里是按分组切开的 15 维（每维带结论与证据引用）。
 *
 * 为什么走资产而不是让前端拼：结论、维度名、证据都是后端产出的**版本化资产**，
 * 前端只渲染。没有报告资产时后端返回空 `sections`（version=0），
 * 前端据此说"报告还没生成"，而不是渲染一份看起来像报告的空壳。
 */
export function getReportFullText(version?: number) {
  return version
    ? api<ReportFullText>(`/app/report/full-text?version=${version}`)
    : api<ReportFullText>('/app/report/full-text')
}

/* ---- ③ 决策：三套方向方案（资产正文，只读；"选哪套"是用户动作） ---- */

/**
 * 三套方向方案（主攻 / 平行 / 保底）。
 *
 * 它们是 ③ 环节产出的**资产**：一次生成、落库、可追踪依赖字段。
 * 还没有方案时后端返回空列表（而不是编一套），界面据此说"还没到这一步"。
 */
export function getDirectionPlans() {
  return api<DirectionPlans>('/app/plan/directions')
}

/**
 * 选中一套方案。
 *
 * 选择**可撤回**：再选另一套就是撤回 —— 所以这里没有单独的"撤销"接口，
 * 界面上也不需要"取消选择"这种会留下"当前选的是哪套"歧义的状态。
 */
export function selectDirectionPlan(optionId: string) {
  return api<DirectionPlans>(
    `/app/plan/directions/${encodeURIComponent(optionId)}/select`,
    { method: 'POST' },
  )
}

/* ---- ④ 行动：行动计划（阶段 / 任务 / 现在这一件） ---- */

/** 行动计划正文。没有计划时 `has_plan=false` —— 与"有计划但任务为空"是两件事。 */
export function getActionPlan() {
  return api<ActionPlan>('/app/plan/action')
}

/**
 * 勾掉 / 取消勾选一个行动任务。
 *
 * `done=false` 是"勾错了要撤回"：只给单向勾选的话，用户点错一次就回不去。
 */
export function setActionTaskDone(taskId: string, done = true) {
  return api<ActionPlan>('/app/plan/action/tasks', {
    method: 'PATCH',
    body: JSON.stringify({ task_id: taskId, done }),
  })
}

/**
 * 关键节点日历。
 *
 * 节点是 ④ 行动环节写进去的（规划师写、教练读），这里读出来给界面看。
 * 此前只有写没有读：库里有节点，界面上一条也看不到。
 */
export function getCalendarNodes() {
  return api<CalendarNode[]>('/app/calendar')
}

/* ---- 完成记录 ---- */

/**
 * 完成记录（内部叫"成就"）。
 *
 * 它读的是**行为日志的推导结果**：做到过哪几件事、第一次是什么时候做的。
 * 没有"领奖"这个动作，也没有进度百分比 —— 解锁条件就是"做过一次某件事"，
 * 拆成刻度只会是编出来的数字。
 *
 * 名字与"怎么拿到"不在这里：规则 code 由界面按 `badge.<code>.label` / `.how`
 * 从文案包取（`/app/bootstrap` 已下发），运营改名字不发版。
 */
export function getAchievements() {
  return api<AchievementListView>('/app/achievements')
}

/* ---- 资产版本与导出 ---- */

/**
 * 资产的历史版本（含 depends_on 与 diff）。
 *
 * 报告页用它做版本切换：v1→v2 差在哪、这一版依赖画像里哪几个字段 ——
 * 这些都是资产自身的属性，不该由前端记录。
 */
export function listAssetVersions(assetType: 'report' | 'direction_plan' | 'action_plan') {
  return api<AssetVersion[]>(`/app/assets/${assetType}/versions`)
}

/**
 * 导出资产。
 *
 * 第一期后端**如实返回 available=false**（只预留入口）。界面据此说清楚
 * "现在只能走浏览器打印"，而不是给一个点了没反应的按钮。
 */
export function exportAsset(assetType: 'report' | 'direction_plan' | 'action_plan', format: 'pdf' | 'docx' = 'pdf') {
  return api<Schema['ExportResultView']>('/app/assets/export', {
    method: 'POST',
    body: JSON.stringify({ asset_type: assetType, format }),
  })
}

/* ---- 用户自己写下的东西 ---- */

/*
 * 采集策略跑在后端，它要靠**用户的原话**把某条数据顶到前面去
 * （"因为你写了想冲秋招，所以我先去取你的预计毕业时间"）。
 * 只存在浏览器里，策略读不到，那句回执就永远是空话。
 */

export function listNotes() {
  return api<UserNote[]>('/app/notes')
}

export function addNote(text: string, kind = 'todo') {
  return api<UserNote>('/app/notes', { method: 'POST', body: JSON.stringify({ text, kind }) })
}

export function setNoteDone(id: string, done: boolean) {
  return api<UserNote>(`/app/notes/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ done }),
  })
}

export function removeNote(id: string) {
  return api<Schema['NoteAck']>(`/app/notes/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/* ---- 教务系统取回来的课表与成绩单 ---- */

/**
 * 清空导入的课表与成绩。
 *
 * 连画像里那两条摘要一起删 —— 只删快照的话，采集清单会一直说"课程表已拿到"，
 * 用户再也回不到导入入口。
 */
export function revokeAcademic() {
  return api<Schema['AcademicRevokeAck']>('/app/academic', { method: 'DELETE' })
}

/**
 * 导入课表与成绩单（学生自己贴原文）。
 *
 * 这是一条**解析**接口：我们不替他登录任何学校系统，也不经手他校内账号的密码。
 * 他手上的东西（教务系统整页复制 / Excel 表格 / 接口 JSON）由后端读懂。
 */
export function importAcademic(body: {
  courses?: string
  grades?: string
  school?: string
  term?: string
}) {
  return api<AcademicImportAck>('/app/academic/import', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * 导入课表与成绩单（**文件的入口**）。
 *
 * 为什么文件要走上传、不在浏览器里读成文本再提交：
 *
 *   · **编码**。教务系统导出的 CSV / TXT 有一半是 GBK，浏览器按 UTF-8 读会得到乱码，
 *     而后端拿到乱码只能说"读不出这是课表"——用户的文件其实完全正确；
 *   · **看起来的样子**。在页面上把文件内容铺进一个文本框，用户看到的是"我选的文件
 *     被拆开摆出来了"，而那正是他不想看到的东西：他只想交给系统一个文件；
 *   · 上传之后"读不出来"的原因在后端只有一处（解码 + 解析），不会前后端各说各的。
 */
export function importAcademicFiles(form: FormData) {
  return upload<AcademicImportAck>('/app/academic/import/file', form)
}
