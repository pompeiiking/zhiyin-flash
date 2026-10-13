import type { AiResult, PortraitAnalysis, DimensionReading, GapClarify, MatchResult, BriefToday, DayAdvice, TimetablePlan, TodoSuggestion, BindResult } from '../api/ai-types'
import { DEMO_AT, DEMO_ACADEMIC } from './demo-fixtures'
import { PROFILE_FIELDS, REPORT_SECTIONS, DIRECTION_PLANS } from './student'
export function demoAi(key:string,params:Record<string,string>={},fresh=false):AiResult<unknown> {
  const points=(rows:string[][])=>rows.map(([label,why])=>({label:label!,why:why!}))
  let data:unknown
  switch(key){
    case 'portraitAnalysis': data={headline:'先把已有实验经历讲清楚，再检验三个方向',reading:'这是陈亦然的**虚构演示分析**。材料课程与实践兴趣提供了探索起点，但课程成绩不能直接证明岗位胜任。\n\n目前主要缺口是项目表达、企业实践和异地预算。每周六小时来自本人在示例对话中的说明，仍需核对实验课与生活安排。',strengths:points([['专业基础','材料科学基础 86、晶体结构 90，是演示成绩。'],['实践兴趣','示例对话倾向动手和成果产出。'],['能够复盘','已有未完成任务的原因记录，能据此缩小下一步。']]),watchouts:points([['实践证据待补充','没有真实产线经历，不把课程实验写成企业实习。'],['城市条件待确认','预算、通勤与家庭支持都需要本人补充。'],['家庭期待需讨论','稳定性与实践兴趣的优先级尚未确定。']]),next:points([['整理一次实验','只写本人负责的过程和可公开结果。'],['核对两份岗位','比较真实职责、学历要求和地点。'],['确认本周时间','先安排一个短任务，再确认周末是否可用。']])} satisfies PortraitAnalysis;break
    case 'dimension': {const id=params.dimension_id??'interest',d=REPORT_SECTIONS.flatMap(s=>s.dimensions).find(d=>d.key===id),field=PROFILE_FIELDS.find(f=>f.key===id);data={id,name:d?.label??field?.label??'已有信息',conclusion:d?.conclusion??'这项信息需要结合原始材料核对。',reading:'演示说明：'+(d?.evidence.join('；')??field?.value??'尚未提供具体依据。')+'\n\n以上为预设样例，不代表对当前用户的测评。',score:d?.score,trend:d?.score?[{at:'2026-09-24',v:Math.max(0,d.score-4),why:'第 2 版虚构演示数值'},{at:'2026-10-13',v:d.score,why:'第 3 版虚构演示数值；不推断真实成长'}]:[],next:d?.threshold??'在咨询中补充来源和限制条件。'} satisfies DimensionReading;break}
    case 'gap':data={question:'这项待确认信息，你目前能补充哪一部分？',whyNow:'先确认事实，再调整方向和时间安排。没有把握的部分可以暂时保留。',options:points([['提供具体范围','例如每周可用时间、城市范围或每月预算。'],['补充一次经历','说明本人做了什么、结果是什么、有哪些证据。'],['暂时不确定','保留缺口，不以推测填满画像。']])} satisfies GapClarify;break
    case 'careerMatch':data={cells:DIRECTION_PLANS.flatMap((p,i)=>['专业基础','项目表达','实践证据','地域条件'].map((skill,j)=>({track:p.title,skill,need:[[70,50,60,60],[75,65,70,50],[70,55,50,70]][i]![j]!,have:[88,46,20,50][j]!}))),ranking:DIRECTION_PLANS.map(p=>({track:p.title,fit:Math.round(p.fitScore*100),gap:p.risk,why:p.evidence.join('；')})),recommend:{title:'演示比较：优先验证工艺方向，同时保留两条备选',body:'预设分值仅用于展示要求与现状的比较，不是实时招聘分析，也不替你确认选择。',because:['专业与动手兴趣相互支持。','三条方向都需要可讲清的实践证据。','地域、学历和日常工作方式仍需核对真实来源。']}} satisfies MatchResult;break
    case 'brief':data={headline:'今天先整理一次实验的三条事实',because:[{text:'项目表达是三个演示方向的共同缺口。',from:'第 3 版演示报告'},{text:'先做小范围任务，降低再次延期的概率。',from:'上周演示复盘'}],changed:[{text:'增加课程与实验记录，仍未核验真实岗位。',at:'2026-10-13'}],ifYouSkip:'保留任务并记录原因，下一次可以恢复，不把一次延期解释为能力不足。',next:[{id:'project',label:'补充项目证据',why:'写清本人行动和实际结果。'},{id:'budget',label:'确认异地预算',why:'避免只按演示分值比较城市。'}]} satisfies BriefToday;break
    case 'dayAdvice':data={date:params.day??'2026-10-13',headline:'演示安排：先做一个能收尾的小任务',reading:'先核对当天课程和本人安排。空课格不代表空闲；下方是可修改的演示建议。',plan:points([['整理一个实验片段','用 20 分钟写清目标、操作和结果。'],['核对当天限制','实验、通勤或家庭安排冲突时，保留任务并另选时间。']]),watch:'日期来自当前选择；建议内容为本地预设，不是当天真实空闲时间推断。'} satisfies DayAdvice;break
    case 'timetable':data={headline:'把本人说明的六小时拆成可确认的时段',windows:[{day:'周二',slot:'晚间 30 分钟（待确认）',why:'短时间整理项目素材；需核对本人晚间安排。'},{day:'周四',slot:'晚间 30 分钟（待确认）',why:'比较两份真实岗位要求。'},{day:'周末',slot:'两次各 60 分钟（待确认）',why:'避开示例工作坊、培训与家庭安排；不能仅依据空课格。'}],moves:[{at:'今天',what:'先确认可投入时间',why:'六小时是示例对话中的本人说明。'},{at:'周末前',what:'再核对课程与生活安排',why:'有冲突时改期，并保留原任务记录。'}]} satisfies TimetablePlan;break
    case 'noteSuggestions':data=[{id:'suggest-project',label:'整理一次材料实验的目标、过程与结果',why:'三个方向都需要可说明的实践证据。',from:'演示报告的项目表达缺口',when:'本周',weight:3},{id:'suggest-jobs',label:'核对两份真实工艺岗位说明',why:'演示岗位不用于实际投递。',from:'演示方向比较',when:'本周',weight:2},{id:'suggest-budget',label:'写下异地生活预算范围',why:'预算缺口会影响地域选择。',from:'画像待确认项',when:'方便时',weight:1}] satisfies TodoSuggestion[];break
    case 'chsi':data={steps:[{id:'identity',label:'演示：核对学籍基本信息',detail:'河北大学、材料科学与工程、大三。此处为虚构样例，不代表通过学信网核验。',got:3,source:'本地演示资料'},{id:'courses',label:'演示：检查课程与成绩',detail:'展示周末课程、课程冲突和时间待定情况。',got:24,source:'本地课程快照'}],courses:DEMO_ACADEMIC.courses??[],lifted:[{dim:'major',from:.5,to:.8,because:'演示可信度变化，仅用于展示核验反馈。'}]} satisfies BindResult;break
    default:throw new Error('这个功能尚无演示结果，请切换服务数据。')
  }
  if(fresh){
    if(key==='portraitAnalysis')data={headline:'先补充一些个人信息',reading:'当前新用户场景还没有个人经历、兴趣与时间依据，暂不形成优势判断。',strengths:[],watchouts:points([['个人资料待补充','陈亦然的演示经历不会作为新用户的资料。']]),next:points([['从一次对话开始','说明专业、当前困惑和希望解决的问题。']])} satisfies PortraitAnalysis
    if(key==='careerMatch')data={cells:[],ranking:[],recommend:{title:'还没有足够资料进行职业匹配',body:'先补充个人经历并核对岗位来源，暂不提供预设排序。',because:['新用户场景保留资料缺口。']}} satisfies MatchResult
    if(key==='brief')data={headline:'先说明你现在最想解决的问题',because:[],changed:[],ifYouSkip:'可以稍后回来，资料缺口会保留。',next:[{id:'interest',label:'开始了解自己',why:'先取得本人说明，再安排任务。'}]} satisfies BriefToday
    if(key==='timetable')data={headline:'先确认每周可投入时间',windows:[],moves:[]} satisfies TimetablePlan
    if(key==='noteSuggestions')data=[] satisfies TodoSuggestion[]
  }
  return {data,citations:[{source:'本地虚构演示资料',detail:'陈亦然、课程成绩、岗位与分值均为界面演示样例；未请求模型或真实核验服务。',at:DEMO_AT}],meta:{by:'本地演示 · 预设结果',at:DEMO_AT,ms:0,cached:true},rationale:'用于体验结论、依据、缺口与后续行动，不作为当前用户的测评或实时岗位判断。'}
}
