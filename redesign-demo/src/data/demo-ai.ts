import type { AiResult, PortraitAnalysis, DimensionReading, GapClarify, MatchResult, BriefToday, DayAdvice, TimetablePlan, TodoSuggestion, BindResult } from '../api/ai-types'
import { DEMO_AT, DEMO_ACADEMIC } from './demo-fixtures'
import { PROFILE_FIELDS, REPORT_SECTIONS, DIRECTION_PLANS } from './student'
export function demoAi(key:string,params:Record<string,string>={},fresh=false):AiResult<unknown> {
  const points=(rows:string[][])=>rows.map(([label,why])=>({label:label!,why:why!}))
  let data:unknown
  switch(key){
    case 'portraitAnalysis': data={headline:'先把已有实验经历讲清楚，再检验三个方向',reading:'根据当前资料，材料课程与实践兴趣提供了探索起点，但课程成绩不能直接证明岗位胜任。\n\n目前主要缺口是项目表达、企业实践和异地预算。每周六小时来自本人在咨询中的说明，仍需核对实验课与生活安排。',strengths:points([['专业基础','材料科学基础 86、晶体结构 90，已记录在课程资料中。'],['实践兴趣','咨询记录显示倾向动手和成果产出。'],['能够复盘','已有未完成任务的原因记录，能据此缩小下一步。']]),watchouts:points([['实践证据待补充','没有真实产线经历，不把课程实验写成企业实习。'],['城市条件待确认','预算、通勤与家庭支持都需要本人补充。'],['家庭期待需讨论','稳定性与实践兴趣的优先级尚未确定。']]),next:points([['整理一次实验','只写本人负责的过程和可公开结果。'],['核对两份岗位','比较真实职责、学历要求和地点。'],['确认本周时间','先安排一个短任务，再确认周末是否可用。']])} satisfies PortraitAnalysis;break
    case 'dimension': {const id=params.dimension_id??'interest',d=REPORT_SECTIONS.flatMap(s=>s.dimensions).find(d=>d.key===id),field=PROFILE_FIELDS.find(f=>f.key===id);data={id,name:d?.label??field?.label??'已有信息',conclusion:d?.conclusion??'这项信息需要结合原始材料核对。',reading:'依据：'+(d?.evidence.join('；')??field?.value??'尚未提供具体依据。')+'\n\n资料不足的部分仍需继续核对。',score:d?.score,trend:d?.score?[{at:'2026-09-24',v:Math.max(0,d.score-4),why:'第 2 版记录'},{at:'2026-10-13',v:d.score,why:'第 3 版记录；分数变化不直接代表成长'}]:[],next:d?.threshold??'在咨询中补充来源和限制条件。'} satisfies DimensionReading;break}
    case 'gap':data={question:'这项待确认信息，你目前能补充哪一部分？',whyNow:'先确认事实，再调整方向和时间安排。没有把握的部分可以暂时保留。',options:points([['提供具体范围','例如每周可用时间、城市范围或每月预算。'],['补充一次经历','说明本人做了什么、结果是什么、有哪些证据。'],['暂时不确定','保留缺口，不以推测填满画像。']])} satisfies GapClarify;break
    case 'careerMatch':data={cells:DIRECTION_PLANS.flatMap((p,i)=>['专业基础','项目表达','实践证据','地域条件'].map((skill,j)=>({track:p.title,skill,need:[[70,50,60,60],[75,65,70,50],[70,55,50,70]][i]![j]!,have:[88,46,20,50][j]!}))),ranking:DIRECTION_PLANS.map(p=>({track:p.title,fit:Math.round(p.fitScore*100),gap:p.risk,why:p.evidence.join('；')})),recommend:{title:'方向比较：优先验证工艺方向，同时保留两条备选',body:'预设分值仅用于展示要求与现状的比较，不是实时招聘分析，也不替你确认选择。',because:['专业与动手兴趣相互支持。','三条方向都需要可讲清的实践证据。','地域、学历和日常工作方式仍需核对真实来源。']}} satisfies MatchResult;break
    case 'brief':data={headline:'今天先整理一次实验的三条事实',because:[{text:'项目表达是三个候选方向的共同缺口。',from:'第 3 版报告'},{text:'先做小范围任务，降低再次延期的概率。',from:'上周复盘'}],changed:[{text:'增加课程与实验记录，仍未核验真实岗位。',at:'2026-10-13'}],ifYouSkip:'保留任务并记录原因，下一次可以恢复，不把一次延期解释为能力不足。',next:[{id:'project',label:'补充项目证据',why:'写清本人行动和实际结果。'},{id:'budget',label:'确认异地预算',why:'避免只按比较分值比较城市。'}]} satisfies BriefToday;break
    case 'dayAdvice':data={date:params.day??'2026-10-13',headline:'今日安排：先做一个能收尾的小任务',reading:'先核对当天课程和本人安排。空课格不代表空闲；下方是可调整的安排建议。',plan:points([['整理一个实验片段','用 20 分钟写清目标、操作和结果。'],['核对当天限制','实验、通勤或家庭安排冲突时，保留任务并另选时间。']]),watch:'日期来自当前选择；建议时段仍需本人确认，不根据空课格推断空闲。'} satisfies DayAdvice;break
    case 'timetable':data={headline:'把本人说明的六小时拆成可确认的时段',windows:[{day:'周二',slot:'晚间 30 分钟（待确认）',why:'短时间整理项目素材；需核对本人晚间安排。'},{day:'周四',slot:'晚间 30 分钟（待确认）',why:'比较两份真实岗位要求。'},{day:'周末',slot:'两次各 60 分钟（待确认）',why:'避开工作坊、培训与家庭安排；不能仅依据空课格。'}],moves:[{at:'今天',what:'先确认可投入时间',why:'六小时是咨询中的本人说明，需核对本周安排。'},{at:'周末前',what:'再核对课程与生活安排',why:'有冲突时改期，并保留原任务记录。'}]} satisfies TimetablePlan;break
    case 'noteSuggestions':data=[{id:'suggest-project',label:'整理一次材料实验的目标、过程与结果',why:'三个方向都需要可说明的实践证据。',from:'报告中的项目表达缺口',when:'本周',weight:3},{id:'suggest-jobs',label:'核对两份真实工艺岗位说明',why:'投递前核对原始公告与有效期。',from:'方向比较',when:'本周',weight:2},{id:'suggest-budget',label:'写下异地生活预算范围',why:'预算缺口会影响地域选择。',from:'画像待确认项',when:'方便时',weight:1}] satisfies TodoSuggestion[];break
    case 'chsi':data={steps:[{id:'identity',label:'预览：核对学籍基本信息',detail:'逐项查看学校、专业与年级；流程预览不会提交在线验证码或完成个人核验。',got:3,source:'当前资料'},{id:'courses',label:'预览：检查课程与成绩',detail:'展示周末课程、课程冲突和时间待定情况。',got:(DEMO_ACADEMIC.courses?.length??0)+(DEMO_ACADEMIC.grades?.length??0),source:'本地课程快照'}],courses:DEMO_ACADEMIC.courses??[],lifted:[{dim:'major',from:.5,to:.8,because:'核对来源后再更新资料的把握度；预览不会提交个人资料。'}]} satisfies BindResult;break
    default:throw new Error('这个功能需要在线资料，请切换后重试。')
  }
  if(fresh){
    if(key==='portraitAnalysis')data={headline:'先补充一些个人信息',reading:'当前新用户场景还没有个人经历、兴趣与时间依据，暂不形成优势判断。',strengths:[],watchouts:points([['个人资料待补充','已有账号的经历不会写入新用户的资料。']]),next:points([['从一次对话开始','说明专业、当前困惑和希望解决的问题。']])} satisfies PortraitAnalysis
    if(key==='careerMatch')data={cells:[],ranking:[],recommend:{title:'还没有足够资料进行职业匹配',body:'先补充个人经历并核对岗位来源，暂不提供预设排序。',because:['新用户场景保留资料缺口。']}} satisfies MatchResult
    if(key==='brief')data={headline:'先说明你现在最想解决的问题',because:[],changed:[],ifYouSkip:'可以稍后回来，资料缺口会保留。',next:[{id:'interest',label:'开始了解自己',why:'先取得本人说明，再安排任务。'}]} satisfies BriefToday
    if(key==='timetable')data={headline:'先确认每周可投入时间',windows:[],moves:[]} satisfies TimetablePlan
    if(key==='noteSuggestions')data=[] satisfies TodoSuggestion[]
  }
  return {data,citations:[{source:'咨询与课程记录',detail:'从本人说明、课程资料与行动记录整理；评分供方向比较，岗位开放情况另行核对。',at:DEMO_AT}],meta:{by:'已保存的资料解读',at:DEMO_AT,ms:0,cached:true},rationale:'用于体验结论、依据、缺口与后续行动，不作为当前用户的测评或实时岗位判断。'}
}
