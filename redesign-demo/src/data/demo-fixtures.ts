/** Fictional, local-only fixtures. These are not verified academic or recruiting records. */
import type { AcademicPanelView, IntelItemView, NoteView, TaskSessionView, ReportFullTextView, DirectionPlanListView, WorkspacePageView, ProfileSource } from '../api/backend-types'
import type { ChatTurn } from './types'
import { PROFILE_FIELDS, REPORT_SECTIONS, REPORT_SUMMARY, DIRECTION_PLANS } from './student'
export const DEMO_AT = '2026-10-13T02:00:00Z'
export const DEMO_ACADEMIC: AcademicPanelView = {
  school:'河北大学',term:'2026–2027 学年秋季',source:'演示数据',imported_at:DEMO_AT,note:'虚构的课程与成绩，用于体验导入、冲突、周末和缺少时间的情况。',
  courses:[
    {name:'材料分析方法',weekday:1,start_period:1,end_period:2,weeks:'1–16',place:'综合楼 302',teacher:'示例教师甲',credit:'3'},
    {name:'工程数学',weekday:1,start_period:5,end_period:6,weeks:'1–16',place:'理科楼 103'},
    {name:'材料物理',weekday:2,start_period:3,end_period:4,weeks:'1–16',place:'理科楼 201'},
    {name:'专业英语',weekday:2,start_period:7,end_period:8,weeks:'1–12',place:'外语楼 205'},
    {name:'材料实验',weekday:3,start_period:5,end_period:8,weeks:'1–16',place:'实验中心',teacher:'示例教师乙'},
    {name:'创新项目讨论（时间冲突示例）',weekday:3,start_period:7,end_period:8,weeks:'3–10',place:'创新中心'},
    {name:'半导体工艺概论',weekday:4,start_period:1,end_period:2,weeks:'1–16',place:'综合楼 406'},
    {name:'材料性能测试',weekday:4,start_period:5,end_period:6,weeks:'1–16',place:'实验中心'},
    {name:'工程实践',weekday:5,start_period:1,end_period:2,weeks:'1–16',place:'实训楼'},
    {name:'职业发展工作坊',weekday:6,start_period:3,end_period:4,weeks:'5、9、13',place:'就业指导中心'},
    {name:'实验室安全培训',weekday:7,start_period:1,end_period:2,weeks:'第 7 周',place:'实验中心'},
    {name:'企业参访（时间待定）',weeks:'待通知',place:'示例企业'}
  ],
  grades:[['材料科学基础','86','3','专业课'],['实验方法','优秀','2','实践课'],['大学英语','81','2','公共课'],['高等数学','78','4','基础课'],['大学物理','84','3','基础课'],['无机化学','88','3','基础课'],['材料热力学','82','3','专业课'],['晶体结构','90','2','专业课'],['金属学','85','3','专业课'],['工程制图','良好','2','实践课'],['程序设计基础','79','2','公共课'],['创新实践','通过','1','实践课']].map(([name,score,credit,category])=>({name:name!,score:score!,credit:credit!,category:category!,term:'2025–2026 春季'}))
}
export const DEMO_NOTES: NoteView[] = [
  ['todo','问学长能否看一眼我的简历',false],['goal','先把省内的工艺方向了解清楚',false],['todo','整理材料实验的过程照片和原始数据',false],['todo','比较三个示例岗位的学历与实践要求',false],['todo','确认下周六是否有家庭安排',false],['todo','给项目老师列三个具体问题',false],['goal','本月形成一页能讲清楚的项目说明',false],['goal','每周保留六小时用于职业探索',false],['todo','完成学籍资料整理',true],['todo','写下最近一次任务没完成的原因',true],['goal','列出三个候选方向',true],['todo','把第一版简历保存成 PDF',true]
].map(([kind,text,done],i)=>({id:'note-'+(i+1),kind:kind as 'todo'|'goal',text:text as string,done:done as boolean,created_at:`2026-10-${String(12-i%7).padStart(2,'0')}T02:00:00Z`}))
export const DEMO_SESSIONS: TaskSessionView[] = [
  ['direction','材料方向怎么选：三个方向的依据与差距','diagnose','找到差距'],['first','先了解自己的兴趣与能力','collect','了解自己'],['resume','把材料实验经历写进简历','act','开始行动'],['city','省内就业与异地机会怎么比较','decide','比较方向'],['review','上周计划没完成，重新安排一下','review','回看行动'],['family','和家里讨论就业与考研的取舍','collect','了解自己']
].map(([id,name,stage,label],i)=>({task_id:'session-'+id,task_name:name!,stage:stage as TaskSessionView['stage'],stage_label:label!,lead_agent_name:'演示咨询顾问',status:i===0?'active':'paused',last_active_at:`2026-10-${String(12-i).padStart(2,'0')}T02:00:00Z`}))
export const DEMO_HISTORIES: Record<string,ChatTurn[]> = Object.fromEntries(DEMO_SESSIONS.slice(2).map((s,i)=>[s.task_id,[{id:s.task_id+'-question',from:'me',text:['我做过材料实验，但简历上不知道怎么写。','我倾向留在省内，也想了解异地工作的代价。','上周写简历的任务没有完成，实验课占用了时间。','家里希望我考公，我自己更想先试试工程岗位。'][i]!},{id:s.task_id+'-answer',from:'host',text:['先选一次你实际参与的实验。记录目标、你负责的步骤、得到的结果，再标出能公开的证据。没有做过的部分保留为空。','可以分别列出通勤、租房预算、岗位要求和家庭支持。城市偏好还没确认，先比较条件，不替你做选择。','先保留没完成的记录。今天只整理一个项目的三条事实，剩余工作移到周末；周末是否可用仍需你确认。','分别写出你与家里最看重的条件，再用两个真实岗位和一个考试路径核对。演示中的岗位不能直接用于实际选择。'][i]!}]]))
const intelRows = [
 ['career','半导体材料工艺工程师｜应届岗位示例','工艺记录、基础材料分析和实验安全是重点。演示要求：本科材料相关专业；提供一项实验或项目说明。地点、待遇和招聘期限均待真实来源确认。'],
 ['career','新能源电池研发助理｜岗位比较示例','演示要求：理解电化学基础，能整理实验数据。本科助理岗与研究生研发岗需分别核对，不把两类门槛混在一起。'],
 ['career','省内国企材料检测岗｜职责示例','演示职责：样品制备、检测记录、质量流程。可用来比较工作方式与地域偏好，不代表任何企业正在招聘。'],
 ['career','半导体材料工艺工程师｜面试准备示例','围绕实验目的、变量控制、异常排查和结果表达准备问题。未参与产线实践时，应如实说明经历边界。'],
 ['career','新能源电池研发助理｜技能证据示例','把电化学课程作业、测试数据和实验记录放在一起，确认哪些内容能证明技能；成绩好不直接等于岗位胜任。'],
 ['industry','材料检测与工艺岗位有哪些区别','演示比较：检测侧重规范与可追溯性，工艺侧重流程参数和问题排查。实际职责需核对具体岗位说明。'],
 ['industry','新能源材料方向如何做小规模探索','先用公开课程和可公开实验材料完成一页项目说明，再与真实岗位逐项核对。演示不提供行业增长预测。'],
 ['education','学籍资料核验前应准备什么','核对学校、专业、年级与更新时间。真实核验需使用本人授权的在线验证码，演示数据不代表学籍验证通过。'],
 ['campus','职业发展工作坊｜校园活动示例','示例活动：简历交流、经历表达练习和模拟问答。时间为课表演示配置；真实校内活动请以学校通知为准。'],
 ['campus','实验室开放日｜实践探索示例','先问清安全培训、可参与任务和指导安排。示例用来体验待办与日历衔接，没有实际报名入口。'],
 ['guide','项目经历如何写得可信','按目标、本人行动、结果、证据组织内容。区分个人贡献与团队成果，缺失的数据保留待补充。'],
 ['guide','拿到岗位信息后先核对这五项','来源、发布日期、学历门槛、职责、地点。没有真实招聘链接的演示条目不应用来投递。']
]
export const DEMO_INTEL: IntelItemView[] = intelRows.map(([kind,title,text],i)=>({id:'demo-intel-'+(i+1),kind,kind_label:({career:'岗位示例',industry:'行业比较示例',education:'资料核验示例',campus:'校园活动示例',guide:'求职方法示例'} as Record<string,string>)[kind!],title,text,source_name:'本地虚构演示资料 · 非招聘公告',fetched_at:DEMO_AT}))
const extras = [
 ['学习能力','已具备专业课程基础，可通过小项目检验知识迁移。','演示成绩：晶体结构 90，材料科学基础 86；尚无真实项目迁移记录。'],
 ['协作能力','能完成实验分工，但跨团队协作经验仍需补充。','虚构咨询记录描述参与实验小组；没有导师评价。'],
 ['压力与恢复','任务受实验课影响，应缩小起步范围并保留恢复入口。','演示复盘中有一次未完成任务，不足以判断长期抗压能力。'],
 ['实践证据','课程实验可以成为起点，尚不能替代产线经历。','已有课程实验记录；企业实践资料待补充。'],
 ['经济条件','异地成本承受范围未明确，暂不按薪资排序。','预算与家庭支持均未填写，保留待确认。'],
 ['职业价值观','偏好实际成果，稳定性与成长空间的排序仍需讨论。','演示对话中同时出现实践兴趣与家庭稳定期待。']
]
export function demoReport(version=3): ReportFullTextView {
  let index=0
  const sections=REPORT_SECTIONS.map(s=>({id:s.key,title:s.title,method:'虚构资料的定性对照；示例评分仅用于界面展示',items:s.dimensions.map(d=>({index:++index,name:d.label,tag:d.confidence.label,conclusion:d.conclusion,evidence:'演示依据：'+d.evidence.join('；')}))}))
  sections.push({id:'supplement',title:'实践条件与待确认项',method:'区分已有材料、假设和资料缺口',items:extras.map(([name,conclusion,evidence])=>({index:++index,name:name!,tag:'待核对',conclusion:conclusion!,evidence:'演示依据：'+evidence}))})
  if(version===1)for(const section of sections)for(const item of section.items){const known=['兴趣方向','做事方式','城市取舍','家里的期待'].includes(item.name);item.conclusion=known?'首次演示对话提示：'+item.conclusion:'本版资料不足，尚未形成这项结论。';item.evidence=known?'第 1 版演示：只依据首次对话，仍待验证。':'第 1 版尚未取得后续课程、项目与行动记录。';item.tag='待核对'}
  if(version===2){const item=sections[0]!.items[2]!;item.conclusion='已整理课程经历，仍需形成完整项目表述。';item.evidence='第 2 版演示：增加课程信息，不包含第 3 版的简历核对。';for(const item of sections[3]!.items){item.conclusion='当时尚未完成补充分析，保留资料缺口。';item.evidence='第 2 版记录：需要后续补充实践、预算与复盘资料。'}}
  return {report_id:'demo-report',version,generated_at:version===3?DEMO_AT:version===2?'2026-09-24T02:00:00Z':'2026-09-12T02:00:00Z',verdict:{summary:version===3?REPORT_SUMMARY:'历史演示报告：当时资料不足，结论用于对比版本，不代表当前建议。'},sections,toc:sections.map(s=>({id:s.id,title:s.title})),swot:{strengths:'专业基础与动手兴趣相互支持。',weaknesses:'项目表达、产线经历和城市预算待补充。',opportunities:'先用小项目和职业交流检验三个方向。',threats:'学历门槛、时间限制与地域偏好可能缩小选择范围。'},methodologies:['演示：兴趣与经历交叉核对','演示：岗位要求与现状逐项比较','资料不足时不推断结论'],sources:['本地虚构人物对话','本地课程与成绩演示快照','本地岗位要求示例；未核验实时招聘信息']}
}
export function demoDirections(selected: string|null=null): DirectionPlanListView {return {selected_id:selected,match_score_method:'演示预设比例，用于展示比较关系；非模型测算',plans:DIRECTION_PLANS.map((p,i)=>({id:p.id,name:p.title,role:(['main','parallel','fallback'] as const)[i]!,match_score:p.fitScore,target_desc:['参与材料与半导体工艺流程、记录并排查实验问题。','协助电池材料实验与数据整理，需核对岗位学历门槛。','参与材料样品检测、质量记录与规范执行。'][i],fit_reason:p.evidence.join('；'),main_risk:p.risk,selected:p.id===selected,revocable:true,gaps:[{requirement:'能清楚说明本人项目贡献',current_state:'现有课程经历尚未整理成项目说明',suggestion:'写出一次实验的目标、本人行动、结果与证据'},{requirement:i===1?'核对本科助理岗与研究生研发岗的区别':'了解岗位实际工作环境',current_state:'仅看过演示要求，尚未核对真实岗位',suggestion:'核对两份真实岗位说明并记录差异'}]}))}}
const sourceMap: Record<string,ProfileSource>={'对话':'conversation','行为记录':'record','本人填写':'user_edit','简历材料':'resume','导师记录':'mentor'}
export function demoWorkspace(academic:AcademicPanelView|null):WorkspacePageView {return {academic_panel:academic,profile_panel:{updated_at:DEMO_AT,fields:PROFILE_FIELDS.map(f=>({key:f.key,label:f.label,value:f.value,source:sourceMap[f.source]??'assessment',confidence:f.confidence.bars/3,updated_at:DEMO_AT,evidence:['演示资料：'+f.noted]})),gaps:[{key:'budget',label:'异地生活预算',reason:'尚未填写，不推断经济条件',suggested_next_action:'确认每月预算和家庭支持'},{key:'project',label:'实践证据',reason:'缺少可公开的项目资料',suggested_next_action:'补充本人参与的实验记录'}]}}}
