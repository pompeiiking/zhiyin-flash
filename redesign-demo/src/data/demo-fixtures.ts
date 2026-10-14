/** Fictional, local-only fixtures. These are not verified academic or recruiting records. */
import type { AcademicPanelView, IntelItemView, NoteView, TaskSessionView, ReportFullTextView, DirectionPlanListView, WorkspacePageView, ProfileSource } from '../api/backend-types'
import type { ChatTurn } from './types'
import { PROFILE_FIELDS, REPORT_SECTIONS, REPORT_SUMMARY, DIRECTION_PLANS } from './student'
export const DEMO_AT = '2026-10-13T02:00:00Z'
export const DEMO_ACADEMIC: AcademicPanelView = {
  school:'河北大学',term:'2026–2027 学年秋季',source:'本人保存的课程资料',imported_at:DEMO_AT,note:'按课程表整理；时间冲突与日期缺失分别保留，仍需对照教务原始记录。',
  courses:[
    {name:'材料分析方法',weekday:1,start_period:1,end_period:2,weeks:'1–16',place:'综合楼 302',teacher:'课程教师',credit:'3'},
    {name:'工程数学',weekday:1,start_period:5,end_period:6,weeks:'1–16',place:'理科楼 103'},
    {name:'材料物理',weekday:2,start_period:3,end_period:4,weeks:'1–16',place:'理科楼 201'},
    {name:'专业英语',weekday:2,start_period:7,end_period:8,weeks:'1–12',place:'外语楼 205'},
    {name:'材料实验',weekday:3,start_period:5,end_period:8,weeks:'1–16',place:'实验中心',teacher:'实验指导教师'},
    {name:'创新项目讨论',weekday:3,start_period:7,end_period:8,weeks:'3–10',place:'创新中心'},
    {name:'半导体工艺概论',weekday:4,start_period:1,end_period:2,weeks:'1–16',place:'综合楼 406'},
    {name:'材料性能测试',weekday:4,start_period:5,end_period:6,weeks:'1–16',place:'实验中心'},
    {name:'工程实践',weekday:5,start_period:1,end_period:2,weeks:'1–16',place:'实训楼'},
    {name:'职业发展工作坊',weekday:6,start_period:3,end_period:4,weeks:'5、9、13',place:'就业指导中心'},
    {name:'实验室安全培训',weekday:7,start_period:1,end_period:2,weeks:'第 7 周',place:'实验中心'},
    {name:'企业参访（时间待定）',weeks:'待通知',place:'参访单位待确认'},
    {name:'材料表面与界面',weekday:2,start_period:1,end_period:2,weeks:'1–16',place:'综合楼 305'},
    {name:'数据分析与可视化',weekday:5,start_period:5,end_period:6,weeks:'1–12',place:'计算中心'},
    {name:'学术写作',weekday:4,start_period:7,end_period:8,weeks:'2–12',place:'理科楼 203'},
    {name:'项目组周会',weekday:5,start_period:7,end_period:8,weeks:'3–14',place:'创新中心'}
  ],
  grades:[['材料科学基础','86','3','专业课'],['实验方法','优秀','2','实践课'],['大学英语','81','2','公共课'],['高等数学','78','4','基础课'],['大学物理','84','3','基础课'],['无机化学','88','3','基础课'],['材料热力学','82','3','专业课'],['晶体结构','90','2','专业课'],['金属学','85','3','专业课'],['工程制图','良好','2','实践课'],['程序设计基础','79','2','公共课'],['创新实践','通过','1','实践课'],['材料力学','83','3','专业课'],['电化学基础','87','2','专业课'],['科技论文阅读','良好','1','公共课'],['材料加工原理','85','3','专业课'],['实验数据处理','91','2','实践课'],['工程伦理','通过','1','公共课']].map(([name,score,credit,category])=>({name:name!,score:score!,credit:credit!,category:category!,term:'2025–2026 春季'}))
}
export const DEMO_NOTES: NoteView[] = [
  ['todo','问学长能否看一眼我的简历',false],['goal','先把省内的工艺方向了解清楚',false],['todo','整理材料实验的过程照片和原始数据',false],['todo','比较三个岗位的学历与实践要求',false],['todo','确认下周六是否有家庭安排',false],['todo','给项目老师列三个具体问题',false],['goal','本月形成一页能讲清楚的项目说明',false],['goal','每周保留六小时用于职业探索',false],['todo','完成学籍资料整理',true],['todo','写下最近一次任务没完成的原因',true],['goal','列出三个候选方向',true],['todo','把第一版简历保存成 PDF',true],['todo','为实验报告选出两张能说明结果的图',false],['todo','请同组同学核对我写的个人分工',false],['todo','给职业访谈准备五个开放问题',false],['goal','建立一份自己的岗位要求对照表',false],['todo','记录石家庄与保定的通勤条件',false],['todo','核对两个目标方向的专业门槛',false],['goal','月底能用两分钟讲清一次实验',false],['todo','整理实验记录的文件名与日期',true],['todo','把岗位要求分成必须与加分两栏',true],['goal','完成第一轮职业访谈准备',true],['todo','确定复盘固定在周日晚间',true],['todo','列出异地生活成本需要查的三项',false]
].map(([kind,text,done],i)=>({id:'note-'+(i+1),kind:kind as 'todo'|'goal',text:text as string,done:done as boolean,created_at:`2026-10-${String(12-i%7).padStart(2,'0')}T02:00:00Z`}))
export const DEMO_SESSIONS: TaskSessionView[] = [
  ['direction','材料方向怎么选：三个方向的依据与差距','diagnose','找到差距'],['first','先了解自己的兴趣与能力','collect','了解自己'],['resume','把材料实验经历写进简历','act','开始行动'],['city','省内就业与异地机会怎么比较','decide','比较方向'],['review','上周计划没完成，重新安排一下','review','回看行动'],['family','和家里讨论就业与考研的取舍','collect','了解自己'],['project','材料实验如何形成一页项目说明','act','开始行动'],['interview','职业访谈要问什么才有收获','collect','了解自己'],['budget','城市选择：先列生活成本与支持条件','decide','比较方向'],['week','下周六小时怎么安排得更稳','review','回看行动']
].map(([id,name,stage,label],i)=>({task_id:'session-'+id,task_name:name!,stage:stage as TaskSessionView['stage'],stage_label:label!,lead_agent_name:'职业分析顾问',status:i===0?'active':'paused',last_active_at:`2026-10-${String(12-i).padStart(2,'0')}T02:00:00Z`}))
const historyQuestions=["我做过材料实验，但简历上不知道怎么写。", "我倾向留在省内，也想了解异地工作的代价。", "上周写简历的任务没有完成，实验课占用了时间。", "家里希望我考公，我自己更想先试试工程岗位。", "材料性能测试做了两周，我该怎么讲清这段经历？", "准备和学长聊半导体工艺岗，我应该问什么？", "去外地工作之前，有哪些生活成本要算清楚？", "下周实验课多，还想留六小时准备求职，怎么排？"]
const historyAnswers=["选一次你实际参与的实验，按目标、本人行动、结果、证据写成四栏。", "先列出通勤、租房预算、岗位要求和家庭支持，尚未确认的条件保持待补充。", "保留没有完成的记录。今天只整理三条事实，其余内容拆到周末。", "分别写出你和家里最看重的条件，再用具体岗位和考试路径核对。", "从一次异常排查讲起：初始现象、变量、你做的调整，以及记录下来的结果。", "围绕典型工作日、入职前要会什么、最常见的困难和新人练习四方面提问。", "把住房、通勤、餐饮和返乡分别列出来，再确认预算上限与可获得的支持。", "先固定课程占用，把六小时拆成两次九十分钟和三个一小时，不把课间当成可用时间。"]
const historyFollowups=["我有原始实验照片和一份数据表。", "预算还没和家里确认，先留空。", "我今天能先做十五分钟。", "我想先访谈，再和家里讨论。", "异常排查是我负责的，同学主要做样品制备。", "我想知道是否经常倒班，也担心自己没有产线经历。", "先按石家庄和保定比较，其他城市以后再看。", "周五下午和周日晚间比较稳定。"]
const historyClosings=["先整理资料日期和本人贡献，再选一张最能支持结果的图。", "可以先比较职责和工作方式，等预算补齐后再更新城市判断。", "把第一步缩到找出一份原始资料。做完后记下实际用时。", "访谈后记下支持和不支持你的证据，不急着选定。", "把分工写明，再请同组同学核对。这能帮助区分个人贡献与团队成果。", "直接问真实的排班频率和新人培养安排，不根据岗位名称推断。", "先记录同一组生活成本项目，避免两个城市使用不同口径。", "先在日历留出这两个窗口，剩余时间保持机动。"]
export const DEMO_HISTORIES: Record<string,ChatTurn[]> = Object.fromEntries(DEMO_SESSIONS.slice(2).map((session,i)=>[session.task_id,[
 {id:session.task_id+'-question',from:'me',text:historyQuestions[i]!},
 {id:session.task_id+'-answer',from:'host',text:historyAnswers[i]!,citations:['本次咨询记录','本人参与的课程与行动资料']},
 {id:session.task_id+'-followup',from:'me',text:historyFollowups[i]!},
 {id:session.task_id+'-closing',from:'host',text:historyClosings[i]!,options:['把这一步加入计划','再核对一条依据']}
]]))
DEMO_HISTORIES['session-first']=[{id:'first-question',from:'me',text:'我对专业谈不上喜欢，但做实验时会更投入。怎么判断兴趣？'},{id:'first-answer',from:'host',text:'先看具体发生过的事：哪类任务你愿意继续做，哪类让你容易拖延。兴趣、擅长和工作偏好分开记录。'},{id:'first-followup',from:'me',text:'比起推公式，我更想看到东西做出来。'},{id:'first-closing',from:'host',text:'这是一条实践兴趣线索。先用一个小项目和一次职业访谈确认，再回来判断。'}]
const intelRows = [
  [
    "career",
    "半导体工艺工程师：先了解这五类日常",
    "工作通常围绕工艺记录、参数核对、样品分析和异常追踪展开。准备一份实验记录，说明变量怎样控制、异常怎样定位。具体倒班、洁净室要求与学历条件需要逐项核对企业公告。"
  ],
  [
    "career",
    "新能源材料研发助理：本科与研发岗分别看",
    "实验配合、测试数据整理与项目文档是可探索的起点。岗位标题相近不代表学历门槛相同；把本科助理与研究生研发的职责、指导方式分别列出，再核对本人经历。"
  ],
  [
    "career",
    "材料检测岗：规范与可追溯性为什么重要",
    "材料检测的准备重点包括样品编号、测试条件、原始数据与报告表达。用课程实验检验自己是否喜欢规范化流程；不能用一次课程成绩代替岗位胜任判断。"
  ],
  [
    "career",
    "半导体工艺面试：把一次异常讲清楚",
    "准备一个真实例子，按现象、初步判断、变量控制、排查过程和结果表达。没有产线经验就说明课程实验的边界，避免把课堂练习写成生产优化。"
  ],
  [
    "career",
    "新能源材料方向：哪些资料可以成为技能证据",
    "把电化学作业、实验曲线和操作记录放在一起，标明日期、本人分工和可公开范围。解释数据支持什么结论，也保留没有验证的推测。"
  ],
  [
    "career",
    "质量工程与检测岗位：工作方式怎么比较",
    "关注问题追踪、质量流程、跨部门沟通和报告频率。把自己对开会、独处与规范化工作的偏好写出来，再通过访谈核对岗位日常。"
  ],
  [
    "career",
    "工艺与设备方向：相邻岗位也要逐项看",
    "岗位名称可能同时包含工艺和设备，但工作对象不同。比较现场操作、分析工具、值班要求与培训安排，不按标题直接归类。"
  ],
  [
    "career",
    "实验室助理：先核对安全与指导安排",
    "了解样品处理、设备使用权限、安全培训和带教方式。申请前准备可说明本人责任的实验材料，不把没有操作过的仪器列为熟练技能。"
  ],
  [
    "industry",
    "材料检测与工艺：从工作对象看区别",
    "检测侧重测量规范与报告可追溯性，工艺侧重参数、流程与异常改善。以同一组条件比较职责与工作方式；具体范围仍由岗位说明和访谈核对。"
  ],
  [
    "industry",
    "新能源材料探索：先做一个可完成的小项目",
    "选可公开的课程数据，形成一页项目说明。记录目标、过程、结果、证据和局限，再检查它能支持哪些岗位要求。"
  ],
  [
    "industry",
    "半导体岗位中的洁净室：访谈前先列问题",
    "把工作环境、防护要求、排班、入职培训和新人常见困难列进问题单。工作条件需要从实际岗位与从业者获得，不能由行业印象代替。"
  ],
  [
    "industry",
    "怎样读岗位要求里的“优先”和“必须”",
    "将学历、专业、安全资质等硬条件与工具经验、项目经验等加分项分开。暂未满足的要求写成具体差距，而不是笼统评价能力不足。"
  ],
  [
    "education",
    "核对学校资料：更新时间和本人信息一起看",
    "逐项核对学校、专业、年级、更新时间与原始记录。资料核验需要本人授权；自己整理的成绩表仍保留为本人资料。"
  ],
  [
    "education",
    "成绩与项目：怎样共同支持方向判断",
    "课程成绩说明学习基础，项目材料说明具体行动。两者相互补充，成绩高不能直接代替实践经验；缺少导师评价时也保留缺口。"
  ],
  [
    "education",
    "准备成绩表导入：保留表头与原始版本",
    "整理课程名称、成绩、学分与学期。粘贴前保留原表；导入时先核对识别结果，重复项或缺失字段逐条处理。"
  ],
  [
    "education",
    "学籍核验前：只使用本人的在线验证码",
    "先核对有效期与授权范围，不提交学校账号密码。服务无法取得资料时保留原记录，验证码过期则重新申请。"
  ],
  [
    "campus",
    "职业发展工作坊：带着具体问题参加",
    "准备一页简历和两个想解决的问题。交流后分别记录被指出的事实、建议与待确认项，是否开展及报名时间以学校通知为准。"
  ],
  [
    "campus",
    "实验室开放交流：先问能参与哪类任务",
    "了解安全培训、带教安排、可参与的操作与资料公开边界。把可做的第一步写进待办，活动时间与名额需要核对校内通知。"
  ],
  [
    "campus",
    "导师交流前：一页项目材料比泛泛提问更有用",
    "把现象、数据图、个人分工与困惑整理在一页，给导师提出三个具体问题。会后记录得到的反馈，不把建议自动当成已确认结论。"
  ],
  [
    "campus",
    "校友职业访谈：二十分钟怎么用",
    "提前发出简短邀请，说明想了解岗位日常。优先问工作对象、入职培训、困难与选择原因；结束后征得许可再保存访谈摘要。"
  ],
  [
    "guide",
    "项目经历写作：目标、行动、结果、证据",
    "区分个人贡献与团队成果。说明负责的步骤、采用的方法、得到的结果以及可以核对的材料，缺失的数据保留待补充。"
  ],
  [
    "guide",
    "收到岗位信息后，先核对这五项",
    "来源、发布日期、学历门槛、职责和地点都要核对。只有原始公告确认仍开放时再申请，探索笔记本身不能作为投递入口。"
  ],
  [
    "guide",
    "准备职业访谈：用开放问题获得具体信息",
    "把“这工作好吗”换成“一个典型工作日怎样安排”。请对方举例说明新人困难、培训和评价方式，记录事实与个人感受的区别。"
  ],
  [
    "guide",
    "每周复盘：任务没完成，先看哪里卡住",
    "记录实际花费时间、卡住的步骤与可调整条件。任务太大就拆小，方法不对就换步骤，方向问题则补证据；归因不变成对人的评价。"
  ]
]
export const DEMO_INTEL: IntelItemView[] = intelRows.map(([kind,title,text],i)=>({id:'demo-intel-'+(i+1),kind,kind_label:({career:'岗位要求',industry:'行业观察',education:'学校资料',campus:'校园机会',guide:'求职方法'} as Record<string,string>)[kind!],title,text,source_name:({career:'职业探索 · 岗位要求笔记',industry:'职业探索 · 行业阅读',education:'资料整理指南',campus:'校园探索计划',guide:'求职准备手册'} as Record<string,string>)[kind!],fetched_at:`2026-10-${String(14-Math.floor(i/4)).padStart(2,'0')}T02:00:00Z`}))
const extras = [
 ['学习能力','已具备专业课程基础，可通过小项目检验知识迁移。','课程记录：晶体结构 90，材料科学基础 86；尚无真实项目迁移记录。'],
 ['协作能力','能完成实验分工，但跨团队协作经验仍需补充。','咨询记录描述参与实验小组；没有导师评价。'],
 ['压力与恢复','任务受实验课影响，应缩小起步范围并保留恢复入口。','复盘记录中有一次未完成任务，不足以判断长期抗压能力。'],
 ['实践证据','课程实验可以成为起点，尚不能替代产线经历。','已有课程实验记录；企业实践资料待补充。'],
 ['经济条件','异地成本承受范围未明确，暂不按薪资排序。','预算与家庭支持均未填写，保留待确认。'],
 ['职业价值观','偏好实际成果，稳定性与成长空间的排序仍需讨论。','演示对话中同时出现实践兴趣与家庭稳定期待。']
]
export function demoReport(version=3): ReportFullTextView {
  let index=0
  const sections=REPORT_SECTIONS.map(s=>({id:s.key,title:s.title,method:'兴趣、经历与岗位要求的定性对照；评分用于方向比较',items:s.dimensions.map(d=>({index:++index,name:d.label,tag:d.confidence.label,conclusion:d.conclusion,evidence:'依据：'+d.evidence.join('；')}))}))
  sections.push({id:'supplement',title:'实践条件与待确认项',method:'区分已有材料、假设和资料缺口',items:extras.map(([name,conclusion,evidence])=>({index:++index,name:name!,tag:'待核对',conclusion:conclusion!,evidence:'依据：'+evidence}))})
  if(version===1)for(const section of sections)for(const item of section.items){const known=['兴趣方向','做事方式','城市取舍','家里的期待'].includes(item.name);item.conclusion=known?'首次咨询线索：'+item.conclusion:'本版资料不足，尚未形成这项结论。';item.evidence=known?'第 1 版：只依据首次对话，仍待验证。':'第 1 版尚未取得后续课程、项目与行动记录。';item.tag='待核对'}
  if(version===2){const item=sections[0]!.items[2]!;item.conclusion='已整理课程经历，仍需形成完整项目表述。';item.evidence='第 2 版：增加课程信息，不包含第 3 版的简历核对。';for(const item of sections[3]!.items){item.conclusion='当时尚未完成补充分析，保留资料缺口。';item.evidence='第 2 版记录：需要后续补充实践、预算与复盘资料。'}}
  return {report_id:'demo-report',version,generated_at:version===3?DEMO_AT:version===2?'2026-09-24T02:00:00Z':'2026-09-12T02:00:00Z',verdict:{summary:version===3?REPORT_SUMMARY:'历史报告：当时资料不足，结论用于对比版本，不代表当前建议。'},sections,toc:sections.map(s=>({id:s.id,title:s.title})),swot:{strengths:'专业基础与动手兴趣相互支持。',weaknesses:'项目表达、产线经历和城市预算待补充。',opportunities:'先用小项目和职业交流检验三个方向。',threats:'学历门槛、时间限制与地域偏好可能缩小选择范围。'},methodologies:['兴趣与经历交叉核对','岗位要求与现状逐项比较','资料不足时不推断结论'],sources:['咨询记录','本人课程与成绩资料','职业探索笔记；投递前核对原始公告']}
}
export function demoDirections(selected: string|null=null): DirectionPlanListView {return {selected_id:selected,match_score_method:'同一刻度比较匹配条件；评分供比较参考',plans:DIRECTION_PLANS.map((p,i)=>({id:p.id,name:p.title,role:(['main','parallel','fallback'] as const)[i]!,match_score:p.fitScore,target_desc:['参与材料与半导体工艺流程、记录并排查实验问题。','协助电池材料实验与数据整理，需核对岗位学历门槛。','参与材料样品检测、质量记录与规范执行。'][i],fit_reason:p.evidence.join('；'),main_risk:p.risk,selected:p.id===selected,revocable:true,gaps:[{requirement:'能清楚说明本人项目贡献',current_state:'现有课程经历尚未整理成项目说明',suggestion:'写出一次实验的目标、本人行动、结果与证据'},{requirement:i===1?'核对本科助理岗与研究生研发岗的区别':'了解岗位实际工作环境',current_state:'已整理方向要求，尚未核对当前开放岗位',suggestion:'核对两份真实岗位说明并记录差异'}]}))}}
const sourceMap: Record<string,ProfileSource>={'对话':'conversation','行为记录':'record','本人填写':'user_edit','简历材料':'resume','导师记录':'mentor'}
export function demoWorkspace(academic:AcademicPanelView|null):WorkspacePageView {return {academic_panel:academic,profile_panel:{updated_at:DEMO_AT,fields:PROFILE_FIELDS.map(f=>({key:f.key,label:f.label,value:f.value,source:sourceMap[f.source]??'assessment',confidence:f.confidence.bars/3,updated_at:DEMO_AT,evidence:[''+f.noted]})),gaps:[{key:'budget',label:'异地生活预算',reason:'尚未填写，不推断经济条件',suggested_next_action:'确认每月预算和家庭支持'},{key:'project',label:'实践证据',reason:'缺少可公开的项目资料',suggested_next_action:'补充本人参与的实验记录'}]}}}
