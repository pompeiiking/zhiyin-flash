import { computed, reactive, readonly } from 'vue'
import { rememberSession } from './session-cache'
import type { AcademicPanelView, AcademicCourseView, AcademicGradeView, ConversationMaterialView, IntelItemView, MessageRequest, NoteView, TaskSessionView, DirectionPlanListView, ActionPlanView, WorkspacePageView, ProfileFieldView, CalendarNodeView, ReportFullTextView, AssetVersionView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'
const now = () => new Date().toISOString()
/** 待办/目标统一口径：最新在前（与后端 DESC 一致），新增与刷新前后的顺序不再矛盾（STU-004）。 */
const newestFirst = (a: NoteView, b: NoteView) => {
  const ta = Date.parse(a.created_at ?? ''), tb = Date.parse(b.created_at ?? '')
  return Number.isFinite(ta) && Number.isFinite(tb) ? tb - ta : 0
}
const emptyState = () => ({
  freshAccount: true, dataMode: 'service' as 'demo'|'service',
  assetChanges: {profileKeys: [] as string[], direction: false}, reportReviewRequested: false,
  liveAction: null as ActionPlanView|null, liveWorkspace: null as WorkspacePageView|null,
  liveCalendar: [] as CalendarNodeView[]|null, liveReport: null as ReportFullTextView|null,
  liveDirections: null as DirectionPlanListView|null, reportMetadata: null as AssetVersionView|null,
  profileOriginals: {} as Record<string,ProfileFieldView>, profileEditSerial: 0,
  intelOrigin: 'live' as 'sample'|'live', notesOrigin: 'live' as 'sample'|'live', academicOrigin: 'live' as 'sample'|'local'|'live',
  liveNoteIds: [] as string[], drafts: {} as Record<string,{text:string;materials:{id:string;name:string}[];scroll:number|null}>,
  currentSessionId: '', sessions: [] as TaskSessionView[], histories: {} as Record<string,ChatTurn[]>,
  notes: [] as NoteView[], academic: null as AcademicPanelView|null, materials: [] as ConversationMaterialView[],
  intel: [] as IntelItemView[], chsiChecked:false, reportAvailable:false,directionsAvailable:false,planAvailable:false,
  messageRequests: [] as MessageRequest[], eventTimes: {} as Record<string,string>,
})
const state = reactive(emptyState())
// Only editable drafts are cached; server data is fetched afresh after authentication.
rememberSession('production-drafts', state, ['drafts'])
export const backendDemo = {
  state: readonly(state),
  chsiVerified: computed(()=>state.liveWorkspace?.profile_panel?.fields?.some(f=>f.source==='record'&&f.verification==='verified'&&f.evidence?.some(e=>{try{const host=new URL(e).hostname;return host==='chsi.com.cn'||host.endsWith('.chsi.com.cn')}catch{return false}}))??false),
  isFresh: computed(()=>state.freshAccount),
  setDataMode(_mode: 'demo'|'service') { state.dataMode='service' },
  currentSession: computed(() => state.sessions.find(s => s.task_id === state.currentSessionId)),
  notesDone: computed(() => state.notes.filter(n => n.done).length),
  reset(_account: string) { Object.assign(state, emptyState()) },
  setSessions(sessions: TaskSessionView[], current = '') { state.sessions=sessions; if(current)state.currentSessionId=current },
  setCurrentSession(session: TaskSessionView) { const i=state.sessions.findIndex(s=>s.task_id===session.task_id);if(i<0)state.sessions.unshift(session);else state.sessions[i]=session;state.currentSessionId=session.task_id },
  saveTurns(id: string, turns: readonly ChatTurn[]) {
    if (JSON.stringify(state.histories[id]) === JSON.stringify(turns)) return
    state.histories[id] = turns.map(t => ({ ...t }))

  },
  recordMessage(body: MessageRequest) { state.messageRequests.push(body) },
  setLiveDirections(plans: DirectionPlanListView) { state.liveDirections = plans },
  markProfileChange(key: string) { state.profileEditSerial++;if (!state.assetChanges.profileKeys.includes(key)) state.assetChanges.profileKeys.push(key) },
  markDirectionChange() { state.assetChanges.direction = true },
  /** 用户核对版本后确认本次变更不需要重算：清掉展示提示，不动任何资产结论。 */
  clearAssetChanges() { state.assetChanges.profileKeys.splice(0); state.assetChanges.direction = false },
  requestReportReview() { state.reportReviewRequested = true },
  setIntel(items: IntelItemView[]) { state.intel = items; state.intelOrigin = 'live' },
  setAction(plan: ActionPlanView) { state.liveAction = plan },
  setWorkspace(workspace: WorkspacePageView) { state.liveWorkspace = workspace; if (workspace.academic_panel !== undefined) { state.academic = workspace.academic_panel;state.academicOrigin=state.dataMode==='demo'?'sample':'live' } },
  rememberProfileOriginal(key: string) { const field=state.liveWorkspace?.profile_panel?.fields?.find(f=>f.key===key);if(field&&!state.profileOriginals[key])state.profileOriginals[key]=JSON.parse(JSON.stringify(field)) },
  setCalendar(nodes: CalendarNodeView[]) { state.liveCalendar = nodes },
  setReport(report: ReportFullTextView) { state.liveReport = report },
  setReportMetadata(metadata: AssetVersionView | null) { state.reportMetadata = metadata },
  upsertNote(note: NoteView) { const i=state.notes.findIndex(n=>n.id===note.id);if(i>=0)state.notes[i]=note;else state.notes.unshift(note);state.notes.sort(newestFirst);if(!state.liveNoteIds.includes(note.id))state.liveNoteIds.push(note.id) },
  setNotes(notes: NoteView[]) { state.notes=[...notes].sort(newestFirst);state.notesOrigin='live';state.liveNoteIds=state.notes.map(n=>n.id) },
  getDraft(id: string) { return state.drafts[id] ?? { text: '', materials: [], scroll: null } },
  saveDraft(id: string, text: string, materials: { id: string; name: string }[], scroll: number | null) { state.drafts[id] = { text, materials: materials.map(m => ({ ...m })), scroll } },
  recordEvent(event: string) { if (!state.eventTimes[event]) state.eventTimes[event] = now() },
  newSession(name = '新的咨询对话') {
    const id = 'session-' + crypto.randomUUID()
    state.sessions.unshift({ task_id: id, task_name: name, stage: 'collect', stage_label: '了解自己', lead_agent_name: '了解你情况的人', status: 'active', progress: 0, last_active_at: now() })
    state.histories[id] = []
    state.currentSessionId = id
  },
  selectSession(id: string) { state.currentSessionId = id; return (state.histories[id] ?? []).map(t => ({ ...t })) },
  addNote(text: string, kind: 'todo' | 'goal') {
    const cleaned = text.trim()
    if (!cleaned || cleaned.length > 200) throw new Error('请写下 1–200 个字。')
    if (state.notes.some(n => n.kind === kind && n.text === cleaned)) return false
    state.notes.unshift({ id: 'note-' + crypto.randomUUID(), kind, text: cleaned, done: false, created_at: now() })
    return true
  },
  setNoteDone(id: string, done: boolean) { const note = state.notes.find(n => n.id === id); if (note) note.done = done },
  removeNote(id: string) { state.notes = state.notes.filter(n => n.id !== id) },
  loadAcademicSample() { throw new Error('请导入自己的学业资料') },
  academicSample(): AcademicPanelView { return {courses:[],grades:[]} },
  setAcademic(courses: AcademicCourseView[], grades: AcademicGradeView[], school: string, term: string) {
    state.academicOrigin='local'
    state.academic = { courses, grades, school, term, source: '本人导入的表格快照', imported_at: now(), note: '本次已核对表格或JSON数据；未经正式学籍核验。' }
  },
  revokeAcademic() { state.academic = null; if(state.liveWorkspace)state.liveWorkspace.academic_panel=null },
  revokeAcademicCourses() {
    if (!state.academic) return
    state.academic = state.academic.grades?.length ? { ...state.academic, courses: [], note: '' } : null
    if (state.liveWorkspace) state.liveWorkspace.academic_panel = state.academic
  },
  revokeAcademicGrades() {
    if (!state.academic) return
    state.academic = state.academic.courses?.length ? { ...state.academic, grades: [] } : null
    if (state.liveWorkspace) state.liveWorkspace.academic_panel = state.academic
  },
  recordMaterial(file: File) {
    if (!file.size) throw new Error('这个文件是空的，请换一份。')
    if (file.size > 2_000_000) throw new Error('材料需小于 2MB，请截取相关的部分。')
    const item: ConversationMaterialView = { material_id: 'material-' + crypto.randomUUID(), name: file.name, size: file.size, chars: 0 }
    state.materials.push(item)
    return item
  },
  loadIntelSample() {
    state.intel = []
  },
  verifySample() { state.chsiChecked = true },
  loadAssessmentSample() { state.reportAvailable = true; state.directionsAvailable = true },
  loadPlanSample() { state.planAvailable = true },
}
