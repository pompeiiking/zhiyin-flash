import { computed, reactive, readonly } from 'vue'
import { rememberSession } from './session-cache'
import type { AcademicPanelView, AcademicCourseView, AcademicGradeView, ConversationMaterialView, IntelItemView, MessageRequest, NoteView, TaskSessionView, DirectionPlanListView, ActionPlanView, WorkspacePageView, ProfileFieldView, CalendarNodeView, ReportFullTextView, AssetVersionView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'
import { CHAT_TURNS } from '../data/student'
import { DEMO_ACADEMIC, DEMO_SESSIONS, DEMO_NOTES, DEMO_INTEL, DEMO_HISTORIES } from '../data/demo-fixtures'
const now = () => new Date().toISOString()
let fresh = false
try { fresh = localStorage.getItem('zhiyin-demo-auth') === 'fresh' } catch { /* session-only */ }
const originalTurns = () => CHAT_TURNS.filter(t => t.from !== 'system').map(t => ({ ...t }))
const academicFixture: AcademicPanelView = DEMO_ACADEMIC
const sessionsFixture = (): TaskSessionView[] => fresh ? [] : structuredClone(DEMO_SESSIONS)
const notesFixture = (): NoteView[] => fresh ? [] : structuredClone(DEMO_NOTES)
const state = reactive({
  demoDataVersion: 0,
  freshAccount: fresh,
  dataMode: 'demo' as 'demo'|'service',
  assetChanges: { profileKeys: [] as string[], direction: false },
  liveAction: null as ActionPlanView | null,
  intelOrigin: 'sample' as 'sample' | 'live',
  liveWorkspace: null as WorkspacePageView | null,
  profileOriginals: {} as Record<string,ProfileFieldView>,
  liveCalendar: null as CalendarNodeView[] | null,
  liveNoteIds: [] as string[],
  notesOrigin: 'sample' as 'sample'|'live',
  profileEditSerial: 0,
  liveReport: null as ReportFullTextView | null,
  reportMetadata: null as AssetVersionView | null,
  academicOrigin: 'sample' as 'sample'|'local'|'live',
  liveDirections: null as DirectionPlanListView | null,
  drafts: {} as Record<string, { text: string; materials: { id: string; name: string }[]; scroll: number | null }>,
  currentSessionId: fresh ? 'session-new' : 'session-direction',
  sessions: sessionsFixture(),
  histories: { 'session-direction': originalTurns(), 'session-first': originalTurns().slice(0, 4), ...structuredClone(DEMO_HISTORIES) } as Record<string, ChatTurn[]>,
  notes: notesFixture(),
  academic: fresh ? null : structuredClone(academicFixture) as AcademicPanelView | null,
  materials: [] as ConversationMaterialView[],
  intel: (fresh ? [] : structuredClone(DEMO_INTEL)) as IntelItemView[],
  chsiChecked: false,
  reportAvailable: !fresh,
  directionsAvailable: !fresh,
  planAvailable: !fresh,
  messageRequests: [] as MessageRequest[],
  eventTimes: (fresh ? {} : { answer: '2026-09-12T02:00:00Z', task_done: '2026-09-20T02:00:00Z', review: '2026-09-24T02:00:00Z' }) as Record<string, string>,
})
rememberSession('data',state,Object.keys(state) as (keyof typeof state)[])
// Enrich older demo sessions once, preserving custom notes and edited/imported material.
if(state.demoDataVersion<1){
  if(!fresh&&state.dataMode==='demo'){
    for(const item of DEMO_NOTES)if(!state.notes.some(n=>n.id===item.id))state.notes.push(structuredClone(item))
    for(const item of DEMO_SESSIONS)if(!state.sessions.some(s=>s.task_id===item.task_id))state.sessions.push(structuredClone(item))
    for(const [id,turns] of Object.entries(DEMO_HISTORIES))if(!state.histories[id])state.histories[id]=structuredClone(turns)
    if(state.academicOrigin==='sample')state.academic=structuredClone(DEMO_ACADEMIC)
    if(state.intelOrigin==='sample')state.intel=structuredClone(DEMO_INTEL)
  }
  state.demoDataVersion=1
}
export const backendDemo = {
  state: readonly(state),
  isFresh: computed(()=>state.freshAccount),
  setDataMode(mode: 'demo'|'service') { if(state.dataMode===mode)return;state.dataMode=mode;state.liveWorkspace=null;state.liveReport=null;state.reportMetadata=null;state.liveDirections=null;state.liveAction=null;state.liveCalendar=null;state.profileOriginals={};state.liveNoteIds=[];state.notesOrigin='sample';if(mode==='demo'){state.academic=fresh?null:structuredClone(DEMO_ACADEMIC);state.academicOrigin='sample';state.notes=notesFixture();state.intel=fresh?[]:structuredClone(DEMO_INTEL);state.intelOrigin='sample'}else{state.academic=null;state.academicOrigin='local';state.intel=[]} },
  currentSession: computed(() => state.sessions.find(s => s.task_id === state.currentSessionId)),
  notesDone: computed(() => state.notes.filter(n => n.done).length),
  reset(account: string) {
    state.assetChanges = { profileKeys: [], direction: false }
    state.liveAction = null
    state.intelOrigin = 'sample'
    state.liveWorkspace = null
    state.profileOriginals = {}; state.liveCalendar = null
    state.liveNoteIds = [];state.notesOrigin = 'sample'
    state.profileEditSerial = 0
    state.liveReport = null;state.reportMetadata=null
    fresh = account === 'fresh'
    state.freshAccount=fresh
    state.academicOrigin = fresh ? 'local' : 'sample'
    state.sessions = sessionsFixture()
    state.currentSessionId = fresh ? 'session-new' : 'session-direction'
    state.histories = { 'session-direction': originalTurns(), 'session-first': originalTurns().slice(0, 4), ...structuredClone(DEMO_HISTORIES) }
    state.notes = notesFixture()
    state.academic = fresh ? null : structuredClone(academicFixture)
    state.materials = []; state.intel = fresh ? [] : structuredClone(DEMO_INTEL); state.chsiChecked = false
    state.drafts = {}
    state.liveDirections = null
    state.reportAvailable = !fresh; state.directionsAvailable = !fresh; state.planAvailable = !fresh
    state.messageRequests = []
    state.eventTimes = fresh ? {} : { answer: '2026-09-12T02:00:00Z', task_done: '2026-09-20T02:00:00Z', review: '2026-09-24T02:00:00Z' }
  },
  saveTurns(id: string, turns: readonly ChatTurn[]) {
    if (JSON.stringify(state.histories[id]) === JSON.stringify(turns)) return
    state.histories[id] = turns.map(t => ({ ...t }))
    const session = state.sessions.find(s => s.task_id === id)
    if (session) session.last_active_at = now()
    else if (turns.length) state.sessions.push({ task_id: id, task_name: '了解自己的第一段对话', stage: 'collect', stage_label: '了解自己', lead_agent_name: '了解你情况的人', last_active_at: now(), status: 'active' })
  },
  recordMessage(body: MessageRequest) { state.messageRequests.push(body) },
  setLiveDirections(plans: DirectionPlanListView) { state.liveDirections = plans },
  markProfileChange(key: string) { state.profileEditSerial++;if (!state.assetChanges.profileKeys.includes(key)) state.assetChanges.profileKeys.push(key) },
  markDirectionChange() { state.assetChanges.direction = true },
  setIntel(items: IntelItemView[]) { state.intel = items; state.intelOrigin = 'live' },
  setAction(plan: ActionPlanView) { state.liveAction = plan },
  setWorkspace(workspace: WorkspacePageView) { state.liveWorkspace = workspace; if (workspace.academic_panel !== undefined) { state.academic = workspace.academic_panel;state.academicOrigin=state.dataMode==='demo'?'sample':'live' } },
  rememberProfileOriginal(key: string) { const field=state.liveWorkspace?.profile_panel?.fields?.find(f=>f.key===key);if(field&&!state.profileOriginals[key])state.profileOriginals[key]=JSON.parse(JSON.stringify(field)) },
  setCalendar(nodes: CalendarNodeView[]) { state.liveCalendar = nodes },
  setReport(report: ReportFullTextView) { state.liveReport = report },
  setReportMetadata(metadata: AssetVersionView | null) { state.reportMetadata = metadata },
  upsertNote(note: NoteView) { const i=state.notes.findIndex(n=>n.id===note.id);if(i>=0)state.notes[i]=note;else state.notes.push(note);if(!state.liveNoteIds.includes(note.id))state.liveNoteIds.push(note.id) },
  setNotes(notes: NoteView[]) { state.notes=notes;state.notesOrigin='live';state.liveNoteIds=notes.map(n=>n.id) },
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
  loadAcademicSample() { state.academicOrigin='sample'; state.academic = { ...structuredClone(academicFixture), imported_at: now() } },
  academicSample() { return structuredClone(academicFixture) },
  setAcademic(courses: AcademicCourseView[], grades: AcademicGradeView[], school: string, term: string) {
    state.academicOrigin='local'
    state.academic = { courses, grades, school, term, source: '本人导入的表格快照', imported_at: now(), note: '本次已核对表格或JSON数据；未经正式学籍核验。' }
  },
  revokeAcademic() { state.academic = null; if(state.liveWorkspace)state.liveWorkspace.academic_panel=null },
  recordMaterial(file: File) {
    if (!file.size) throw new Error('这个文件是空的，请换一份。')
    if (file.size > 2_000_000) throw new Error('材料需小于 2MB，请截取相关的部分。')
    const item: ConversationMaterialView = { material_id: 'material-' + crypto.randomUUID(), name: file.name, size: file.size, chars: 0 }
    state.materials.push(item)
    return item
  },
  loadIntelSample() {
    state.intelOrigin = 'sample'
    state.intel = structuredClone(DEMO_INTEL)
  },
  verifySample() { state.chsiChecked = true },
  loadAssessmentSample() { state.reportAvailable = true; state.directionsAvailable = true },
  loadPlanSample() { state.planAvailable = true },
}
