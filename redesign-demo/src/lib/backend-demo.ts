import { computed, reactive, readonly } from 'vue'
import type { AcademicPanelView, AcademicCourseView, AcademicGradeView, ConversationMaterialView, IntelItemView, MessageRequest, NoteView, TaskSessionView } from '../api/backend-types'
import type { ChatTurn } from '../data/types'
import { CHAT_TURNS } from '../data/student'
const now = () => new Date().toISOString()
let fresh = false
try { fresh = localStorage.getItem('zhiyin-demo-auth') === 'fresh' } catch { /* session-only */ }
const originalTurns = () => CHAT_TURNS.filter(t => t.from !== 'system').map(t => ({ ...t }))
const academicFixture: AcademicPanelView = {
  school: '河北大学', term: '2026–2027 学年秋季', source: 'json', imported_at: '2026-10-08T02:00:00Z',
  note: '课表与成绩为演示快照。',
  courses: [
    { name: '材料分析方法', weekday: 1, start_period: 1, end_period: 2, weeks: '1–16', place: '综合楼 302', teacher: '示例教师' },
    { name: '材料物理', weekday: 2, start_period: 3, end_period: 4, weeks: '1–16', place: '理科楼 201' },
    { name: '材料实验', weekday: 3, start_period: 5, end_period: 8, weeks: '1–16', place: '实验中心' },
    { name: '工程实践', weekday: 5, start_period: 1, end_period: 2, weeks: '1–16', place: '实训楼' },
  ],
  grades: [
    { name: '材料科学基础', score: '86', credit: '3', point: '3.6', term: '2025–2026 春季', category: '专业课' },
    { name: '实验方法', score: '优秀', credit: '2', point: '', term: '2025–2026 春季', category: '实践课' },
    { name: '大学英语', score: '81', credit: '2', point: '3.1', term: '2025–2026 春季', category: '公共课' },
  ],
}
const sessionsFixture = (): TaskSessionView[] => fresh ? [] : [
  { task_id: 'session-direction', task_name: '看看半导体方向是否适合我', stage: 'diagnose', stage_label: '找到差距', lead_agent_name: '帮你判断方向的人', status: 'active', progress: .4, last_active_at: '2026-10-12T01:30:00Z' },
  { task_id: 'session-first', task_name: '先了解自己的兴趣与能力', stage: 'collect', stage_label: '了解自己', lead_agent_name: '了解你情况的人', status: 'paused', progress: .2, last_active_at: '2026-10-08T02:00:00Z' },
]
const notesFixture = (): NoteView[] => fresh ? [] : [
  { id: 'note-1', kind: 'todo', text: '问学长能否看一眼我的简历', done: false, created_at: '2026-10-09T02:00:00Z' },
  { id: 'note-2', kind: 'goal', text: '先把省内的工艺方向了解清楚', done: false, created_at: '2026-10-08T02:00:00Z' },
]
const state = reactive({
  currentSessionId: fresh ? 'session-new' : 'session-direction',
  sessions: sessionsFixture(),
  histories: { 'session-direction': originalTurns(), 'session-first': originalTurns().slice(0, 4) } as Record<string, ChatTurn[]>,
  notes: notesFixture(),
  academic: fresh ? null : structuredClone(academicFixture) as AcademicPanelView | null,
  materials: [] as ConversationMaterialView[],
  intel: [] as IntelItemView[],
  chsiChecked: false,
  reportAvailable: !fresh,
  directionsAvailable: !fresh,
  planAvailable: !fresh,
  messageRequests: [] as MessageRequest[],
  eventTimes: (fresh ? {} : { answer: '2026-09-12T02:00:00Z', task_done: '2026-09-20T02:00:00Z', review: '2026-09-24T02:00:00Z' }) as Record<string, string>,
})
export const backendDemo = {
  state: readonly(state),
  currentSession: computed(() => state.sessions.find(s => s.task_id === state.currentSessionId)),
  notesDone: computed(() => state.notes.filter(n => n.done).length),
  reset(account: string) {
    fresh = account === 'fresh'
    state.sessions = sessionsFixture()
    state.currentSessionId = fresh ? 'session-new' : 'session-direction'
    state.histories = { 'session-direction': originalTurns(), 'session-first': originalTurns().slice(0, 4) }
    state.notes = notesFixture()
    state.academic = fresh ? null : structuredClone(academicFixture)
    state.materials = []; state.intel = []; state.chsiChecked = false
    state.reportAvailable = !fresh; state.directionsAvailable = !fresh; state.planAvailable = !fresh
    state.messageRequests = []
    state.eventTimes = fresh ? {} : { answer: '2026-09-12T02:00:00Z', task_done: '2026-09-20T02:00:00Z', review: '2026-09-24T02:00:00Z' }
  },
  saveTurns(id: string, turns: readonly ChatTurn[]) {
    state.histories[id] = turns.map(t => ({ ...t }))
    const session = state.sessions.find(s => s.task_id === id)
    if (session) session.last_active_at = now()
    else if (turns.length) state.sessions.push({ task_id: id, task_name: '了解自己的第一段对话', stage: 'collect', stage_label: '了解自己', lead_agent_name: '了解你情况的人', last_active_at: now(), status: 'active' })
  },
  recordMessage(body: MessageRequest) { state.messageRequests.push(body) },
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
    if (state.notes.some(n => n.kind === kind && n.text === cleaned)) return
    state.notes.unshift({ id: 'note-' + crypto.randomUUID(), kind, text: cleaned, done: false, created_at: now() })
  },
  setNoteDone(id: string, done: boolean) { const note = state.notes.find(n => n.id === id); if (note) note.done = done },
  removeNote(id: string) { state.notes = state.notes.filter(n => n.id !== id) },
  loadAcademicSample() { state.academic = { ...structuredClone(academicFixture), imported_at: now() } },
  setAcademic(courses: AcademicCourseView[], grades: AcademicGradeView[], school: string, term: string) {
    state.academic = { courses, grades, school, term, source: 'json', imported_at: now(), note: '当前演示只校验 JSON 数据形状；正式导入由后端解析。' }
  },
  revokeAcademic() { state.academic = null },
  recordMaterial(file: File) {
    if (!file.size) throw new Error('这个文件是空的，请换一份。')
    if (file.size > 2_000_000) throw new Error('材料需小于 2MB，请截取相关的部分。')
    const item: ConversationMaterialView = { material_id: 'material-' + crypto.randomUUID(), name: file.name, size: file.size, chars: 0 }
    state.materials.push(item)
    return item
  },
  loadIntelSample() {
    state.intel = [
      { id: 'intel-major', kind: 'career', kind_label: '职业探索示例', title: '从专业出发，看看相关职业', text: '以材料专业为演示场景。来源入口用于核对职业信息，这里没有实时招聘数据。', source_name: '学职平台', source_url: 'https://xuezhi.chsi.com.cn/', fetched_at: now() },
      { id: 'intel-chsi', kind: 'education', kind_label: '资料核验示例', title: '先核对学历与学籍资料', text: '学校信息用于说明核验流程。提供在线验证码即可，无需提交学信网账号密码。', source_name: '学信网', source_url: 'https://www.chsi.com.cn/', fetched_at: now() },
    ]
  },
  verifySample() { state.chsiChecked = true },
  loadAssessmentSample() { state.reportAvailable = true; state.directionsAvailable = true },
  loadPlanSample() { state.planAvailable = true },
}
