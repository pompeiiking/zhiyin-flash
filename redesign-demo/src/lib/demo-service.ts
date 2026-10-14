/** Explicit local mode. No failed service response is replaced with a fixture. */
import { backendDemo } from './backend-demo'
import { demoReport, demoDirections, demoWorkspace, DEMO_AT } from '../data/demo-fixtures'
import { TASKS_BY_GRADE } from '../data/student'
import { DEMO_PHASE_TASK_IDS } from '../data/phase-tasks'
import type { ActionPlanView, NoteView, AcademicCourseView, AcademicGradeView } from '../api/backend-types'
type Options={params?:Record<string,string>;query?:Record<string,string|number>;body?:unknown}
type Mutable<T> = T extends readonly (infer U)[] ? Mutable<U>[] : T extends object ? {-readonly [K in keyof T]:Mutable<T[K]>} : T
const copy=<T>(value:T):Mutable<T>=>JSON.parse(JSON.stringify(value))
async function action():Promise<ActionPlanView>{
  if(backendDemo.state.liveAction)return copy(backendDemo.state.liveAction)
  if(!backendDemo.state.planAvailable)return {has_plan:false,phases:[]}
  const {demo}=await import('../store'),grade=demo.state.grade,source=demo.state.tasks
  const all=source.length?source:TASKS_BY_GRADE[grade]
  const phases=Object.entries(DEMO_PHASE_TASK_IDS).filter(([id])=>id.startsWith('m-'+({freshman:'f',sophomore:'s',junior:'j',senior:'e'}[grade]))).map(([,ids],i)=>({name:['整理已有材料','验证方向与补齐差距','投递与复盘'][i]!,tag:i===0?'当前阶段':'后续阶段',date_range:['10 月 13–19 日','10 月 20–26 日','10 月 27 日–11 月 2 日'][i],tasks:all.filter(t=>ids.includes(t.id)).map(t=>({task_id:t.id,text:t.title,done:t.bucket==='done',phase:['整理已有材料','验证方向与补齐差距','投递与复盘'][i],due_date:null}))}))
  return {has_plan:true,plan_id:'demo-plan-'+grade,phases,next_task:phases.flatMap(p=>p.tasks).find(t=>!t.done)??null}
}
export async function demoRequest(key:string,options:Options={}):Promise<unknown>{
  const state=backendDemo.state,body=(options.body??{}) as Record<string,unknown>,params=options.params??{}
  switch(key){
    case 'workspace':return state.liveWorkspace?copy(state.liveWorkspace):backendDemo.isFresh.value?{academic_panel:copy(state.academic),profile_panel:{fields:[],gaps:[{key:'interest',label:'兴趣与经历',reason:'当前还没有本人资料',suggested_next_action:'先说明当前问题'}]}}:demoWorkspace(copy(state.academic))
    case 'correctProfile':{const workspace=state.liveWorkspace?copy(state.liveWorkspace):demoWorkspace(copy(state.academic));const field=workspace.profile_panel?.fields?.find(f=>f.key===params.key);if(!field)throw new Error('没有找到这项信息');field.value=String(body.value??'');field.source='user_edit';field.updated_at=new Date().toISOString();backendDemo.setWorkspace(workspace);return field}
    case 'report':if(!state.reportAvailable)throw new Error('请先加载报告示例');return demoReport(Number(options.query?.version??3))
    case 'versions':return state.reportAvailable?[3,2,1].map(version=>({asset_id:'demo-report',asset_type:params.asset_type,version,created_at:demoReport(version).generated_at,depends_on_profile_keys:version===1?['interest','city']:['interest','city','time','weakness'],needs_recompute:version===3&&state.assetChanges.profileKeys.length>0,diff_from_previous:['首次报告：仅有对话线索','增加课程信息，保留城市与预算缺口','补充经历表达与实践证据分析'][version-1]})):[]
    case 'directions':return state.liveDirections?copy(state.liveDirections):state.directionsAvailable?demoDirections():{plans:[]}
    case 'selectDirection':{const plans=state.liveDirections?copy(state.liveDirections):demoDirections();if(!plans.plans?.some(p=>p.id===params.option_id))throw new Error('无效的示例方向');plans.selected_id=params.option_id;plans.plans.forEach(p=>{p.selected=p.id===params.option_id});backendDemo.setLiveDirections(plans);return plans}
    case 'action':return action()
    case 'actionDone':{const plan=await action(),task=plan.phases?.flatMap(p=>p.tasks??[]).find(t=>t.task_id===body.task_id);if(!task)throw new Error('没有找到这项任务');task.done=body.done!==false;task.done_at=task.done?new Date().toISOString():null;plan.next_task=plan.phases?.flatMap(p=>p.tasks??[]).find(t=>!t.done)??null;backendDemo.setAction(plan);return plan}
    case 'calendar':return backendDemo.isFresh.value?[]:[{node_id:'demo-project',title:'整理项目说明初稿',due_at:'2026-10-15T12:00:00+08:00',source:'manual',related_task_text:'只写本人实际参与的实验'},{node_id:'demo-workshop',title:'职业发展工作坊',due_at:'2026-10-17T10:00:00+08:00',source:'manual'},{node_id:'demo-review',title:'周复盘：确认任务与时间',due_at:'2026-10-18T19:00:00+08:00',source:'manual'},{node_id:'demo-compare',title:'核对两份真实岗位要求',due_at:'2026-10-21T19:00:00+08:00',source:'planner'},{node_id:'demo-deadline',title:'项目说明定稿（个人计划）',due_at:'2026-10-25T20:00:00+08:00',source:'manual'},{node_id:'demo-pending',title:'企业参访：时间待通知',due_at:null,source:'manual'}]
    case 'notes':return copy(state.notes)
    case 'addNote':{const kind=body.kind==='goal'?'goal':'todo';backendDemo.addNote(String(body.text??''),kind);return copy(state.notes.find(n=>n.text===body.text&&n.kind===kind) as NoteView)}
    case 'noteDone':backendDemo.setNoteDone(params.note_id!,body.done===true);return copy(state.notes.find(n=>n.id===params.note_id))
    case 'removeNote':backendDemo.removeNote(params.note_id!);return {removed:params.note_id}
    case 'intel':case 'intelRefresh':{const q=String(options.query?.q??'').trim();return {fetched_at:DEMO_AT,items:copy(state.intel.filter(i=>((i.title??'')+' '+(i.text??'')).includes(q)))}}
    case 'academicImport':{const courses=JSON.parse(String(body.courses??'[]')) as AcademicCourseView[],grades=JSON.parse(String(body.grades??'[]')) as AcademicGradeView[];backendDemo.setAcademic(courses,grades,String(body.school??''),String(body.term??''));if(state.liveWorkspace){const workspace=copy(state.liveWorkspace);workspace.academic_panel=copy(state.academic);backendDemo.setWorkspace(workspace)}return {courses_count:courses.length,grades_count:grades.length,imported_at:new Date().toISOString()}}
    case 'academicRevoke':backendDemo.revokeAcademic();return {revoked:true}
    case 'modules':return [{manifest:{id:'demo-plan',name:'阶段任务工具',version:'demo-1',description:'管理当前阶段的任务，保留完成与恢复记录。',kind:'app',actions:['plan.task.set_done']},policy:{enabled:true,actions:['plan.task.set_done']}}]
    case 'moduleAction':{const payload=(body.payload??{}) as Record<string,unknown>;await demoRequest('actionDone',{body:payload});return demoRequest('moduleData')}
    case 'moduleData':{const plan=await action();return {data:{tasks:plan.phases?.flatMap(p=>(p.tasks??[]).map(t=>({...t,phase:p.name})))??[]},sources:['当前阶段计划'],module_version:'demo-1',empty:!plan.has_plan}}
    default:throw new Error('这个功能需要在线服务，请切换在线资料后使用。')
  }
}
