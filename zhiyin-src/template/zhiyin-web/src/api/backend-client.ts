/** Formal BFF transport for integration. Demo data never silently replaces a failed request. */
import operations from './operations.json'
import type { AuthRequest, CoachNotificationView, ExportResultView, LoginResult, PortalView, WorkspacePageView } from './backend-types'
import type { AcademicImportAck, AcademicImportRequest, ActionPlanView, ActionTaskDoneRequest, AchievementListView, AssetVersionView, BootstrapView, CalendarNodeView, CapabilitiesView, ConversationMaterialView, ConversationMessageView, ConversationTurnView, DirectionPlanListView, IntelListView, MessageRequest, NoteCreateRequest, NoteView, ProfileConflictView, ProfileFieldView, ReportFullTextView, SessionListView, TaskSessionView, TheoryCardView, TrackEventView } from './backend-types'
export class BackendError extends Error {
  constructor(message: string, public code: number, public traceId = '') { super(message) }
}
type Envelope<T> = { code: number; message: string; data: T; trace_id?: string }
type Options = { fresh?: boolean; params?: Record<string, string>; query?: Record<string, string | number>; body?: unknown; timeout?: number; form?: FormData; signal?: AbortSignal }
export { request as backendRequest }
/** 技术性异常（英文 JSON/校验/解析）不直接念给用户听，统一换成可操作的中文。 */
const TECHNICAL_ERROR = /(Expected property name|Unexpected token|Unexpected end of JSON|is not valid JSON|JSON\.parse|SyntaxError|TypeError|ReferenceError|Traceback|ValidationError|String should|Input should)/i
function userFacingMessage(message: string | undefined | null) {
  const text = (message ?? '').trim()
  if (!text) return ''
  if (TECHNICAL_ERROR.test(text)) return ''
  if (!/[\u4e00-\u9fa5]/.test(text)) return ''
  return text
}
function statusMessage(status: number) {
  if (status === 413) return '材料超过大小限制（最多 2MB），请截取相关的那一段后再上传。'
  if (status === 422) return '提交的内容不符合要求，请检查后重试。'
  if (status === 401) return '登录状态已失效，请重新登录后再试。'
  if (status === 403) return '当前账号没有执行这一步的权限。'
  if (status === 404) return '要操作的内容不存在，可能已被更新；请刷新后重试。'
  if (status === 429) return '操作太频繁了，请稍后再试。'
  if (status >= 500) return '服务暂时不可用，请稍后重试。'
  return '这次请求没有成功，请稍后重试。'
}
type Operation = { method: string; path: string }
/**
 * GET 请求的短缓存 + 并发去重。
 *
 * 工作台/壳层/各页面会同时请求同一个 GET（workspace 被 10+ 页面各拉一次），
 * 既慢又容易在写后读到互相覆盖的旧快照。这里只缓存 **GET 800ms**，任何
 * 非 GET（保存/勾选/选方向等）都会清空，避免拿写入前的旧值。
 */
const GET_CACHE_TTL_MS = 800
const getCache = new Map<string, { at: number; promise: Promise<unknown> }>()
function cacheKeyOf(key: string, options: Options) {
  let token = ''
  try { token = localStorage.getItem('zhiyin_token') ?? '' } catch { /* 匿名 */ }
  return [key, JSON.stringify(options.params ?? {}), JSON.stringify(options.query ?? {}), token].join('|')
}
function clearGetCache() { getCache.clear() }
/**
 * 会话历史管理（PATCH/DELETE /app/sessions/{task_id}）与能力清单（GET /app/capabilities）
 * 由这一轮新增，尚未写进 `operations.json`（该文件不在本次改动范围）。这里用显式
 * Operation 描述直接发请求：路径与方法是当前约定的最终形态，联调时只需核对。
 */
async function send<T>(operation: Operation, options: Options = {}, opts: { auth?: boolean } = {}): Promise<T> {
  // 任何写操作都让 GET 缓存失效：保存后马上回到报告/计划页时不能读旧快照。
  if (operation.method !== 'GET') clearGetCache()
  let path = operation.path.replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = options.params?.[key]
    if (value === undefined) throw new Error('Missing path parameter: ' + key)
    return encodeURIComponent(value)
  })
  if (options.query) path += '?' + new URLSearchParams(Object.entries(options.query).map(([k,v]) => [k,String(v)]))
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (options.signal?.aborted) abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => controller.abort(), options.timeout ?? 20_000)
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (!options.form && options.body !== undefined) headers['Content-Type'] = 'application/json'
  try { const token = localStorage.getItem('zhiyin_token'); if (token) headers.Authorization = 'Bearer ' + token } catch { /* anonymous request when storage is unavailable */ }
  const sameAccount = () => {
    if (headers.Authorization !== (localStorage.getItem('zhiyin_token') ? 'Bearer ' + localStorage.getItem('zhiyin_token') : undefined)) throw new BackendError('账号已变更，请重新读取。', 1004)
  }
  try {
    const response = await fetch('/api/v1' + path, { method: operation.method, headers, signal: controller.signal, body: options.form ?? (options.body === undefined ? undefined : JSON.stringify(options.body)) })
    sameAccount()
    if (response.status === 401 && !opts.auth) window.dispatchEvent(new Event('zhiyin:unauthorized'))
    let result: Envelope<T>
    try {
      result = await response.json() as Envelope<T>
    } catch {
      // 反向代理/网关的 413、502 等通常不是 JSON（HTML 错误页）。此前会落到
      // "后端暂时连不上"，把"文件太大"误报成服务故障（深度测试 DEF-DS-03）。
      sameAccount()
      throw new BackendError(statusMessage(response.status), response.status === 200 ? 1007 : response.status)
    }
    sameAccount()
    if ((response.status !== 401 && result.code === 1004) && !opts.auth) window.dispatchEvent(new Event('zhiyin:unauthorized'))
    if (!response.ok || result.code !== 0) throw new BackendError(userFacingMessage(result.message) || statusMessage(response.status), result.code ?? response.status, result.trace_id)

    return result.data
  } catch (error) {
    if (error instanceof BackendError) throw error
    if (controller.signal.aborted) throw new BackendError('等待超时，输入内容已保留，请重新尝试。', 1007)
    throw new BackendError('网络或服务暂时不可用，请稍后重试。', 1007)
  } finally { clearTimeout(timeout); options.signal?.removeEventListener('abort', abort) }
}
async function request<T>(key: keyof typeof operations, options: Options = {}): Promise<T> {
  const operation = operations[key]
  if (operation.method === 'GET' && !options.signal && !options.fresh) {
    const cacheKey = cacheKeyOf(key, options)
    const hit = getCache.get(cacheKey)
    if (hit && Date.now() - hit.at < GET_CACHE_TTL_MS) return hit.promise as Promise<T>
    const promise = send<T>(operation, options, { auth: key === 'login' || key === 'register' })
    getCache.set(cacheKey, { at: Date.now(), promise })
    promise.catch(() => {
      const current = getCache.get(cacheKey)
      if (current?.promise === promise) getCache.delete(cacheKey)
    })
    return promise
  }
  return send<T>(operation, options, { auth: key === 'login' || key === 'register' })
}
export const backendClient = {
  portal: () => request<PortalView>('portal'),
  authenticate: (mode: 'login' | 'register', body: AuthRequest) => request<LoginResult>(mode, { body }),
  logout: () => request<{ logged_out: boolean }>('logout'),
  bootstrap: () => request<BootstrapView>('bootstrap'),
  sessions: () => request<SessionListView>('sessions'),
  conversationRuntime: (id: string) => send<ConversationRuntimeState>({ method: 'GET', path: `/app/sessions/${encodeURIComponent(id)}/runtime` }, { fresh: true }),
  conversationSettings: (id: string, temporary: boolean) => send<ConversationRuntimeState>({ method: 'PATCH', path: `/app/sessions/${encodeURIComponent(id)}/settings` }, { body: { temporary } }),
  cancelConversationRun: (id: string, run: string) => send<Record<string, unknown>>({ method: 'POST', path: `/app/sessions/${encodeURIComponent(id)}/runs/${encodeURIComponent(run)}/cancel` }),
  /** 重命名会话：PATCH /app/sessions/{task_id} body { task_name }，返回最新会话列表。 */
  sessionRename: (task_id: string, task_name: string) => send<SessionListView>({ method: 'PATCH', path: `/app/sessions/${encodeURIComponent(task_id)}` }, { body: { task_name } }),
  /** 删除会话：DELETE /app/sessions/{task_id}。契约优先返回最新 SessionListView；也兼容 { removed }。 */
  sessionDelete: (task_id: string) => send<SessionListView | { removed?: string }>({ method: 'DELETE', path: `/app/sessions/${encodeURIComponent(task_id)}` }),
  /** 能力清单：GET /app/capabilities（可用/未启用 + 原因 + 替代）。 */
  capabilities: () => send<CapabilitiesView>({ method: 'GET', path: '/app/capabilities' }),
  turns: (task_id: string) => request<ConversationMessageView[]>('sessionTurns', { params: { task_id } }),
  enter: (task_code: string, new_session = false) => request<TaskSessionView>('enterTask', { body: { task_code, new_session } }),
  message: (body: MessageRequest, signal?: AbortSignal) => request<ConversationTurnView>('message', { body, timeout: 90_000, signal }),
  material: (file: File) => { const form = new FormData(); form.append('file', file); return request<ConversationMaterialView>('material', { form, timeout: 60_000 }) },
  workspace: () => request<WorkspacePageView>('workspace'),
  correct: (key: string, value: string, expected_updated_at: string | null) => request<ProfileFieldView>('correctProfile', { params: { key }, body: { value, expected_updated_at } }),
  /** 用户删除一条画像：DELETE /app/profile/fields/{key}，版本不符时后端返回冲突。 */
  deleteProfileField: (key: string, expected_updated_at?: string | null) => request<{ deleted: string }>('deleteProfileField', { params: { key }, query: expected_updated_at ? { expected_updated_at } : undefined }),
  /** 用户否认一条系统理解（待验证线索）：DELETE /app/profile/clues/{clue_id}。 */
  denyProfileClue: (clue_id: string) => request<{ denied: string }>('denyProfileClue', { params: { clue_id } }),
  /** 一条画像的历史版本（含冲突提案）：GET /app/profile/fields/{key}/history。 */
  profileHistory: (key: string) => request<ProfileConflictView[]>('profileFieldHistory', { params: { key } }),
  /** 裁定冲突：choice=revision 以新说法为准，current 保留当前记录。 */
  resolveProfileConflict: (revision_id: string, choice: 'revision' | 'current') => request<ProfileConflictView>('resolveProfileConflict', { params: { revision_id }, body: { choice } }),
  theory: (theory_id: string) => request<TheoryCardView>('theory', { params: { theory_id } }),
  report: (version?: number) => request<ReportFullTextView>('report', { query: version ? { version } : undefined }),
  versions: (asset_type: 'report' | 'direction_plan' | 'action_plan') => request<AssetVersionView[]>('versions', { params: { asset_type } }),
  directions: () => request<DirectionPlanListView>('directions'),
  selectDirection: (option_id: string) => request<DirectionPlanListView>('selectDirection', { params: { option_id } }),
  action: () => request<ActionPlanView>('action'),
  actionDone: (body: ActionTaskDoneRequest) => request<ActionPlanView>('actionDone', { body }),
  calendar: () => request<CalendarNodeView[]>('calendar'),
  notes: () => request<NoteView[]>('notes'),
  addNote: (body: NoteCreateRequest) => request<NoteView>('addNote', { body }),
  noteDone: (note_id: string, done: boolean) => request<NoteView>('noteDone', { params: { note_id }, body: { done } }),
  removeNote: (note_id: string) => request<{ removed: string }>('removeNote', { params: { note_id } }),
  academic: (body: AcademicImportRequest) => request<AcademicImportAck>('academicImport', { body }),
  academicFile: (form: FormData) => request<AcademicImportAck>('academicFile', { form, timeout: 60_000 }),
  revokeAcademic: () => request<{ revoked: boolean }>('academicRevoke'),
  revokeAcademicCourses: () => request<{ revoked: boolean }>('academicCoursesRevoke'),
  revokeAcademicGrades: () => request<{ revoked: boolean }>('academicGradesRevoke'),
  intel: (q = '') => request<IntelListView>('intel', { query: { q } }),
  refreshIntel: (q = '') => request<IntelListView>('intelRefresh', { query: { q } }),
  events: () => request<TrackEventView[]>('trackEvents'),
  achievements: () => request<AchievementListView>('achievements'),
  notifications: () => request<CoachNotificationView[]>('notifications'),
  notificationRead: (message_id: string) => request<{ read: boolean }>('notificationRead', { params: { message_id } }),
  exportAsset: (asset_type: 'report' | 'direction_plan' | 'action_plan', format: 'pdf' | 'docx') => request<ExportResultView>('export', { body: { asset_type, format } }),
}

export type ConversationAction = { id: string; operation: string; state: string; payload: Record<string, any>; expires_at: string; receipt?: Record<string, any> }
export type ConversationRuntimeState = { actions: ConversationAction[]; runs: {id: string; state: string; last_status?: string; events?: {type?: string; step_id?: string; note?: string}[]}[]; settings: {temporary?: boolean} }
