import {studentApi,type Notice} from '../api/student-capabilities'
import { mapMessage, withGuide } from './conversation-turns'
export { mapMessage } from './conversation-turns'
import type {ConversationTurnView} from '../api/backend-types'
import { reactive } from 'vue'
import { backendClient } from '../api/backend-client'
import { auth } from './auth'
import { featureEnabled } from './features'
import { backendDemo } from './backend-demo'
import { demo } from '../store'
import type { TrackEventView, AchievementListView } from '../api/backend-types'

export const systemData = reactive({ snapshot: null as ConversationTurnView|null, busy: false, shellReady: false, error: '', events: [] as TrackEventView[], achievements: null as AchievementListView | null })
export function clearSystemData(){selecting++;systemData.snapshot=null;systemData.events=[];systemData.achievements=null;systemData.error='';systemData.busy=false;systemData.shellReady=false}
let selecting = 0
if (typeof window !== 'undefined') window.addEventListener('zhiyin:session-cleared', clearSystemData)
export async function openSession(id: string) {
  if (demo.state.chatBusy) return
  const serial = ++selecting
  systemData.busy = true; systemData.error = ''
  try {
    const [messages,snapshot] = await Promise.all([backendClient.turns(id),studentApi.sessionSnapshot(id)])
    if (serial !== selecting) return
    systemData.snapshot=snapshot
    // 最后一条是用户提问、没有回复（生成中刷新/中断）时，snapshot 里的 guide
    // 属于上一轮：不能再挂一条空的主理回复到这句提问下面（实测会显示上一轮残片）。
    const lastRole = messages.length ? messages[messages.length - 1]?.role : ''
    const guideSnapshot = lastRole === 'user' ? null : snapshot
    const turns = withGuide(messages.map((m, i) => mapMessage(m, `${id}-${i}`)), guideSnapshot, `${id}-guide`)
    backendDemo.selectSession(id); backendDemo.saveTurns(id, turns); demo.setChatTurns(turns, id)
  } catch(e) { if (serial === selecting) systemData.error = (e as Error).message; throw e }
  finally { if (serial === selecting) systemData.busy = false }
}
export async function newSession(taskCode?: string, fresh = false) {
  if (systemData.busy || demo.state.chatBusy) throw new Error('正在读取会话，请稍候再试。')
  systemData.busy = true; systemData.error = ''
  try {
    const code = taskCode || auth.state.bootstrap?.task_entries?.[0]?.code
    if (!code) throw new Error('当前没有可用的咨询入口，请刷新或联系管理员。')
    // fresh=true 表示"新建一条会话"：后端会把同入口的进行中旧会话标记完成，
    // 再建一条新的；旧会话仍留在历史里（不是续接同一条）。
    const session = await backendClient.enter(code, fresh)
    systemData.snapshot=await studentApi.sessionSnapshot(session.task_id)
    backendDemo.setCurrentSession(session)
    const turns = withGuide((await backendClient.turns(session.task_id)).map((m,i) => mapMessage(m, `${session.task_id}-${i}`)), systemData.snapshot, `${session.task_id}-guide`)
    demo.setChatTurns(turns, session.task_id)
  } catch(e) { systemData.error = (e as Error).message; throw e }
  finally { systemData.busy = false }
}
export async function refreshNotifications(current?: Notice[]) {
  const notices = current ?? await studentApi.notifications()
  demo.setNotices(notices.filter(n => n.status === 'pending').map(n => ({ id:n.id, title:n.title, body:n.body ?? '', kind:'提醒', action:'标为已读', secondary:'关闭', queued:0 })))
}
export async function loadShell() {
  systemData.shellReady = false
  systemData.error = ''
  const results = await Promise.allSettled([
    backendClient.sessions().then(async s => {
      backendDemo.setSessions(s.sessions ?? [], demo.state.currentSessionId || s.current_task_id || '')
      // 恢复顺序：本标签页正在看的那条（sessionStorage）→ 后端最近会话 → 列表第一条。
      // 只认仍在列表里的 id，避免恢复到已被清理/空会话。
      let tabSession = ''
      try { tabSession = sessionStorage.getItem('zhiyin-current-session') || '' } catch { /* 不可用就退回账号级 */ }
      const known = (s.sessions ?? []).some(item => item.task_id === tabSession)
      const restoreId = (known ? tabSession : '') || s.current_task_id || s.sessions?.[0]?.task_id
      if (!demo.state.currentSessionId && restoreId) await openSession(restoreId)
    }),
    backendClient.action().then(backendDemo.setAction),
    backendClient.notes().then(backendDemo.setNotes),
    backendClient.workspace().then(backendDemo.setWorkspace),
    refreshNotifications(),
  ])
  const failure = results.find(r => r.status === 'rejected')
  if (failure?.status === 'rejected') systemData.error = failure.reason instanceof Error ? failure.reason.message : '部分资料加载失败'
  systemData.shellReady = true
}
export async function loadAchievements() {
  if (!featureEnabled('achievements')) { systemData.achievements = null; return null }
  const achievements = await backendClient.achievements()
  systemData.achievements = achievements
  return achievements
}
export async function loadRecords() {
  const [events, achievements] = await Promise.allSettled([backendClient.events(), loadAchievements()])
  if(events.status === 'fulfilled') systemData.events = events.value
  if(events.status === 'rejected') throw events.reason
  if(achievements.status === 'rejected') throw achievements.reason
}
