/** Formal BFF transport for integration. Demo data never silently replaces a failed request. */
import operations from './operations.json'
import type { AuthRequest, CoachNotificationView, ExportResultView, LoginResult, PortalView, WorkspacePageView } from './backend-types'
import type { AcademicImportAck, AcademicImportRequest, ActionPlanView, ActionTaskDoneRequest, AchievementListView, AssetVersionView, BootstrapView, CalendarNodeView, ConversationMaterialView, ConversationMessageView, ConversationTurnView, DirectionPlanListView, IntelListView, MessageRequest, NoteCreateRequest, NoteView, ProfileFieldView, ReportFullTextView, SessionListView, TaskSessionView, TheoryCardView, TrackEventView } from './backend-types'
export class BackendError extends Error {
  constructor(message: string, public code: number, public traceId = '') { super(message) }
}
type Envelope<T> = { code: number; message: string; data: T; trace_id?: string }
type Options = { params?: Record<string, string>; query?: Record<string, string | number>; body?: unknown; timeout?: number; form?: FormData; signal?: AbortSignal }
export { request as backendRequest }
async function request<T>(key: keyof typeof operations, options: Options = {}): Promise<T> {
  const operation = operations[key]
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
  try {
    const response = await fetch('/api/v1' + path, { method: operation.method, headers, signal: controller.signal, body: options.form ?? (options.body === undefined ? undefined : JSON.stringify(options.body)) })
    if (headers.Authorization !== (localStorage.getItem('zhiyin_token') ? 'Bearer ' + localStorage.getItem('zhiyin_token') : undefined)) throw new BackendError('账号已变更，请重新读取。', 1004)
    if (response.status === 401 && key !== 'login' && key !== 'register') window.dispatchEvent(new Event('zhiyin:unauthorized'))
    const result = await response.json() as Envelope<T>
    if (headers.Authorization !== (localStorage.getItem('zhiyin_token') ? 'Bearer ' + localStorage.getItem('zhiyin_token') : undefined)) throw new BackendError('账号已变更，请重新读取。', 1004)
    if ((response.status !== 401 && result.code === 1004) && key !== 'login' && key !== 'register') window.dispatchEvent(new Event('zhiyin:unauthorized'))
    if (!response.ok || result.code !== 0) throw new BackendError(result.message || '这次请求没有接上，请稍后重试。', result.code ?? response.status, result.trace_id)

    return result.data
  } catch (error) {
    if (error instanceof BackendError) throw error
    if (controller.signal.aborted) throw new BackendError('等待超时，输入内容已保留，请重新尝试。', 1007)
    throw new BackendError('后端暂时连不上，请确认服务地址后重试。', 1007)
  } finally { clearTimeout(timeout); options.signal?.removeEventListener('abort', abort) }
}
export const backendClient = {
  portal: () => request<PortalView>('portal'),
  authenticate: (mode: 'login' | 'register', body: AuthRequest) => request<LoginResult>(mode, { body }),
  logout: () => request<{ logged_out: boolean }>('logout'),
  bootstrap: () => request<BootstrapView>('bootstrap'),
  sessions: () => request<SessionListView>('sessions'),
  turns: (task_id: string) => request<ConversationMessageView[]>('sessionTurns', { params: { task_id } }),
  enter: (task_code: string) => request<TaskSessionView>('enterTask', { body: { task_code } }),
  message: (body: MessageRequest, signal?: AbortSignal) => request<ConversationTurnView>('message', { body, timeout: 90_000, signal }),
  material: (file: File) => { const form = new FormData(); form.append('file', file); return request<ConversationMaterialView>('material', { form, timeout: 60_000 }) },
  workspace: () => request<WorkspacePageView>('workspace'),
  correct: (key: string, value: string, expected_updated_at: string | null) => request<ProfileFieldView>('correctProfile', { params: { key }, body: { value, expected_updated_at } }),
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
