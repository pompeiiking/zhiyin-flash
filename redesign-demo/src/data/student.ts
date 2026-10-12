import type {
  CalendarMark,
  ChatTurn,
  CollectItem,
  DirectionPlan,
  Grade,
  Notice,
  ProfileField,
  ReportSection,
  ReviewItem,
  TaskItem,
} from './types'

/**
 * 演示人物：陈亦然（大三 · 材料科学与工程）。
 * 沿用设计文档 8.1 的 U1 与 14.2 十幕主线的人物设定 —— 大三在读、专业谈不上喜欢、秋招前。
 */

export const STUDENT = {
  name: '陈亦然',
  grade: '大三',
  major: '材料科学与工程',
  school: '河北大学',
  /** 顶栏徽章：现在是谁在帮你（身份短语，不是职位名） */
  currentHost: '帮你判断方向的人',
  /** 主体（顶栏那句"谁在替你干活"点开可见） */
  hosts: [
    { key: '了解你情况的人', state: '已交班', note: '聊过 14 轮，把你的情况问清楚了' },
    { key: '帮你判断方向的人', state: '现在是他', note: '正在比对三条方向的契合依据' },
    { key: '帮你排计划的人', state: '待接手', note: '等你选定主攻方向后接手' },
    { key: '陪你推进的人', state: '待接手', note: '计划落地后由他盯进度' },
    { key: '帮你查行情的人', state: '按需出场', note: '需要岗位与行业事实时才出现' },
  ],
}

/**
 * 对你的了解 —— 一条**画像池**，按年级切片。
 *
 * 单一来源原则：池子长度固定，年级决定"已经了解前 N 条"，
 * 第 N 条往后就是缺口。所以「已经了解 12 条」与实际列出的条数永远相等 ——
 * 分成两个数字写（一个写在场景里、一个写在列表里）迟早会对不上。
 *
 * 每条都带来源与把握，点开可盘问。
 */
export const PROFILE_FIELDS: ProfileField[] = [
  {
    key: 'major',
    label: '专业',
    value: '材料科学与工程',
    source: '学信网',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 18 日核验',
  },
  {
    key: 'grade',
    label: '年级',
    value: '大三（2024 级）',
    source: '学信网',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 18 日核验',
  },
  {
    key: 'interest',
    label: '兴趣倾向',
    value: '偏"把事做成"，而不是"研究原理"',
    source: '对话',
    confidence: { level: 'mid', label: '还要再看看', bars: 2 },
    noted: '9 月 12 日，你说的原话',
  },
  {
    key: 'style',
    label: '做事方式',
    value: '独处时更出活，讨厌反复开会',
    source: '对话',
    confidence: { level: 'mid', label: '还要再看看', bars: 2 },
    noted: '9 月 12 日，你说的原话',
  },
  {
    key: 'time',
    label: '每周可投入',
    value: '6 小时（课表空档算出来的）',
    source: '教务系统',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 20 日，按课表算的',
  },
  {
    key: 'rank',
    label: '成绩层级',
    value: '专业前 30%',
    source: '教务系统',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 20 日导入',
  },
  {
    key: 'family',
    label: '家庭期待',
    value: '父母希望考公',
    source: '对话',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 12 日，你主动提的',
  },
  {
    key: 'weakness',
    label: '已知短板',
    value: '简历上没有一个能讲的项目',
    source: '对话',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 15 日，你自己说的',
  },
  {
    key: 'city',
    label: '目标城市',
    value: '倾向留在省内',
    source: '对话',
    confidence: { level: 'low', label: '还不好说', bars: 1 },
    noted: '9 月 12 日，你说"还没想好"',
  },
  {
    key: 'pipeline',
    label: '投递现状',
    value: '投了 4 家，0 个回音',
    source: '行为记录',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '10 月 8 日，你标记的',
  },
  {
    key: 'award',
    label: '在校获奖与处分',
    value: '校级三等奖学金 1 次，无处分',
    source: '学校',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '9 月 22 日，学校系统同步',
  },
  {
    key: 'schedule',
    label: '本周课表空档',
    value: '周三、周五下午各有 2 小时',
    source: '教务系统',
    confidence: { level: 'high', label: '比较确定', bars: 3 },
    noted: '10 月 6 日，按教务课表算的',
  },
  {
    key: 'internship',
    label: '实习经历',
    value: '大二暑期在本地封装厂做过 6 周工艺实习',
    source: '对话',
    confidence: { level: 'low', label: '还不好说', bars: 1 },
    noted: '还没聊到',
  },
  {
    key: 'jobtype',
    label: '目标岗位类型',
    value: '工艺 / 设备岗，暂时不考虑纯研发',
    source: '对话',
    confidence: { level: 'low', label: '还不好说', bars: 1 },
    noted: '还没聊到',
  },
  {
    key: 'salary',
    label: '薪资底线',
    value: '省内 8k 起可以谈，低于 8k 会犹豫',
    source: '对话',
    confidence: { level: 'low', label: '还不好说', bars: 1 },
    noted: '还没聊到',
  },
]

/** 采集动线：还差什么、去哪取（第 5 幕） */
export const COLLECT_ITEMS: CollectItem[] = [
  { label: '学籍与就读状态', from: '学信网', fetchable: true },
  { label: '专业与年级', from: '学信网', fetchable: true },
  { label: '成绩层级', from: '教务系统', fetchable: true },
  { label: '本周课表与空档', from: '教务系统', fetchable: true },
  { label: '在校获奖与处分', from: '学校', fetchable: true },
  { label: '目标岗位类型', from: '对话', fetchable: true },
  { label: '薪资底线', from: '对话', fetchable: true },
  { label: '是否接受外省', from: '对话', fetchable: true },
  {
    label: '实习单位评价',
    from: '行为记录',
    fetchable: false,
    blockedBy: '需要实习单位出具，学校这边取不到 —— 你可以自己传一份',
  },
]

/** 你的报告：三个分区用用户语言，不用维度名（7.4） */
export const REPORT_SECTIONS: ReportSection[] = [
  {
    key: 'self',
    title: '你是什么样的人',
    dimensions: [
      {
        key: 'interest',
        label: '兴趣方向',
        conclusion: '你对"把东西做出来"的兴趣，明显高于"把原理讲清楚"',
        confidence: { level: 'mid', label: '还要再看看', bars: 2 },
        score: 68,
        threshold: '你想投的三条方向里，有两条的日常工作就是做东西 —— 这条对得上，是好事。',
        evidence: ['你 9 月 12 日说的："比起算公式，我更愿意看东西被做出来"', '14 轮对话里，"动手"出现 9 次'],
      },
      {
        key: 'style',
        label: '做事方式',
        conclusion: '你能长时间自己钻一件事，但被反复打断后恢复得慢',
        confidence: { level: 'mid', label: '还要再看看', bars: 2 },
        score: 61,
        threshold: '需要频繁跨部门对齐的岗位会让你消耗很大 —— 选方向时这条要当硬条件看。',
        evidence: ['你说过"一天开三个会就什么都干不了"', '你在晚上的任务完成率是白天的 2.4 倍'],
      },
      {
        key: 'present',
        label: '呈现能力',
        conclusion: '你的经历不缺，但你还没学会把它们讲成别人听得懂的话',
        confidence: { level: 'high', label: '比较确定', bars: 3 },
        score: 46,
        threshold: '你的呈现能力是 46 分，两条主攻方向都要求 50 分以上 —— 差 4 分，是补起来最快的一个。',
        evidence: ['简历第一页目前只有 3 行有效信息', '已投 4 家，0 个回音'],
      },
    ],
  },
  {
    key: 'market',
    title: '外面是什么情况',
    dimensions: [
      {
        key: 'demand',
        label: '岗位供给',
        conclusion: '省内材料类工艺岗今年在招的比去年少，但新能源方向在扩',
        confidence: { level: 'mid', label: '还要再看看', bars: 2 },
        score: 55,
        threshold: '供给在缩的是"传统材料"，在扩的是"新能源与半导体" —— 你只需要换投递的细分。',
        evidence: ['省内 9-10 月发布的材料类岗位 218 条，同比 -12%', '新能源电池方向 +34%'],
      },
      {
        key: 'threshold',
        label: '门槛要求',
        conclusion: '你想去的岗位，一半以上写明要"有项目或实习经历"',
        confidence: { level: 'high', label: '比较确定', bars: 3 },
        score: 62,
        threshold: '这条正好卡在你已知的短板上 —— 所以先补一段经历，比多投 20 家管用。',
        evidence: ['抽查 60 条岗位要求，"项目/实习经历"出现 34 次'],
      },
      {
        key: 'compete',
        label: '竞争者情况',
        conclusion: '和你条件接近的人，普遍比你多一段实习',
        confidence: { level: 'mid', label: '还要再看看', bars: 2 },
        score: 48,
        threshold: '差距不在学校、不在成绩，在一段经历 —— 这是可以补的。',
        evidence: ['同专业上一届 40 人的去向：实习过的 27 人，其中 22 人在秋招前拿到面试'],
      },
    ],
  },
  {
    key: 'tradeoff',
    title: '你要做哪些取舍',
    dimensions: [
      {
        key: 'city',
        label: '城市取舍',
        conclusion: '留在省内，岗位少但竞争也小；出去，机会多但要重新建立关系',
        confidence: { level: 'low', label: '还不好说', bars: 1 },
        score: 50,
        threshold: '这条还缺一个信息：你能不能接受离家 1000 公里。答完这条，取舍就清楚了。',
        evidence: ['你说过"倾向留在省内"，但也说过"还没想好"'],
      },
      {
        key: 'family',
        label: '家里的期待',
        conclusion: '父母希望你考公，你自己没明确反对，但也没准备',
        confidence: { level: 'high', label: '比较确定', bars: 3 },
        score: 72,
        threshold: '这条是"家里要的"和"你要的"没对齐 —— 不对齐不是问题，装作没这回事才是。',
        evidence: ['你 9 月 12 日主动提到"家里希望我考公"', '你从没打开过考公相关的岗位'],
      },
      {
        key: 'time',
        label: '时间取舍',
        conclusion: '你每周只有 6 小时，考公和秋招同时抓不现实',
        confidence: { level: 'high', label: '比较确定', bars: 3 },
        score: 60,
        threshold: '6 小时只够一条主线 —— 两条都抓的结果，通常是两条都做不完。',
        evidence: ['按课表算出的可投入时间为 6 小时/周'],
      },
    ],
  },
]

/**
 * 自我画像六维（雷达图用）。
 * 只有"结论一句 + 有多大把握"是 L1，分值是 L2 —— 点开才出现。
 */
export const SELF_RADAR = [
  { label: '兴趣', value: 68 },
  { label: '做事方式', value: 61 },
  { label: '呈现', value: 46 },
  { label: '抗压', value: 72 },
  { label: '学习速度', value: 64 },
  { label: '协作', value: 52 },
]

/**
 * 门槛对照：主攻方向给你定的三条硬要求。
 * 报告的"门槛解释"就落在这张表上 —— 差几分、差在哪，一眼看完。
 */
export const THRESHOLD_COMPARE = [
  { label: '呈现能力', mine: 46, requirement: 50, note: '两条主攻方向都要求 50 分以上' },
  { label: '项目经历', mine: 20, requirement: 60, note: '岗位要求里写得最多的就是这一条' },
  { label: '专业对口', mine: 88, requirement: 70, note: '这条你已经过了，不用再花时间' },
]

/** 结论段：每次打开读的是那一版资产，不重复生成（第 6 幕） */
export const REPORT_SUMMARY =
  '你现在的处境不是"没有方向"，而是"三个方向都够得着一部分，缺的那一部分不一样"。' +
  '往外看：省内材料类岗位整体在缩，但新能源与半导体两条细分在扩，你想投的传统材料正好是缩的那一支。' +
  '往回看你自己的手上：专业、兴趣、抗压都对得上，唯一被反复卡住的是"呈现"—— 46 分，离两条主攻方向的门槛差 4 分。' +
  '所以这一版的建议很具体：先把呈现补到 50，再谈投多少家。'

/** 报告版本（演示版本下拉与差异） */
export const REPORT_VERSIONS = [
  { id: 'v3', label: '第 3 版（当前）', at: '10 月 8 日', change: '补上"呈现能力"与岗位门槛的差距', fit: 82 },
  { id: 'v2', label: '第 2 版', at: '9 月 24 日', change: '学籍核验后，成绩层级参与折算', fit: 71 },
  { id: 'v1', label: '第 1 版', at: '9 月 12 日', change: '首次生成：只有对话来源', fit: 61 },
]

/** 方向方案：系统永不替用户选（产出契约里没有"选择"字段） */
export const DIRECTION_PLANS: DirectionPlan[] = [
  {
    id: 'd1',
    role: '主攻',
    title: '半导体材料工艺工程师',
    fit: { level: 'high', label: '很大把握', bars: 3 },
    fitScore: 0.82,
    evidence: ['专业对口：材料科学与工程', '兴趣对得上：偏"把东西做出来"', '省内 3 家企业今年在扩这条线'],
    risk: '需要一段洁净室或产线相关的经历，你现在没有',
    ripple: 4,
    ripplePoints: ['简历第一页的主线表述', '本周任务的排序', '报告里"门槛要求"那条的结论', '投递清单的前 5 家'],
  },
  {
    id: 'd2',
    role: '平行',
    title: '新能源电池研发助理',
    fit: { level: 'mid', label: '还要再看看', bars: 2 },
    fitScore: 0.64,
    evidence: ['新能源方向在扩招', '你的实验课成绩不错'],
    risk: '研发岗普遍要求研究生学历，本科要投需要挑中小企业',
    ripple: 3,
    ripplePoints: ['投递清单', '是否需要考研的判断', '简历里的课程项目排序'],
  },
  {
    id: 'd3',
    role: '保底',
    title: '省内国企材料检测岗',
    fit: { level: 'mid', label: '还要再看看', bars: 2 },
    fitScore: 0.58,
    evidence: ['招人稳定，门槛不高', '留在省内，符合你目前的倾向'],
    risk: '与你"想做东西"的兴趣方向相反，几年后可能想转',
    ripple: 2,
    ripplePoints: ['是否需要考公的判断', '时间分配'],
  },
]

/**
 * 计划与行动：**每个年级一套**。
 *
 * 这是"场景化设计"里最容易被做假的一处：只换标题不换事，大一和大三的任务清单一样，
 * 界面上一眼就能看出来。所以四套任务的"事、时长、为什么是现在"全部按该年级的真实处境写。
 * 每条仍然三样齐全（7.4）。
 */
export const TASKS_BY_GRADE: Record<Grade, TaskItem[]> = {
  freshman: [
    {
      id: 'f1',
      title: '把"我的专业以后能干什么"整理成 3 条路',
      minutes: 20,
      why: '你现在连可选的路有哪些都还不清楚 —— 先求广，不求准',
      bucket: 'now',
      origin: '计划拆下来的',
    },
    {
      id: 'f2',
      title: '找 1 位同专业的学长聊 15 分钟',
      minutes: 15,
      why: '同专业的人踩过的坑，比网上的经验贴准得多',
      bucket: 'now',
      origin: '建议的',
    },
    {
      id: 'f3',
      title: '把兴趣那三个问题答完',
      minutes: 10,
      why: '画像还差 11 条，答完这几条方向才给得出来',
      bucket: 'now',
      origin: '计划拆下来的',
      due: '今天',
    },
    {
      id: 'f4',
      title: '等学校开放转专业申请的日程',
      minutes: 0,
      why: '日程没出，你决定不了要不要准备 —— 到时候会自动提醒',
      bucket: 'waiting',
      origin: '关键节点',
    },
    {
      id: 'f5',
      title: '等学长回消息',
      minutes: 0,
      why: '发出去了，等回复就行，不用反复看',
      bucket: 'waiting',
      origin: '自己写的',
    },
    {
      id: 'f6',
      title: '完成学籍在线验证',
      minutes: 10,
      why: '验证完，专业与年级就不用再问你一遍了',
      bucket: 'done',
      origin: '关键节点',
      doneAt: '9 月 18 日',
    },
    {
      id: 'f7',
      title: '把每周可投入时间确认成 4 小时',
      minutes: 5,
      why: '时间不清，后面的计划都是空排',
      bucket: 'done',
      origin: '计划拆下来的',
      doneAt: '9 月 20 日',
    },
  ],

  sophomore: [
    {
      id: 's1',
      title: '选一个 3 周内能做完的小项目，今晚定题',
      minutes: 20,
      why: '你要的是"能讲出来的东西"，不是"更多想法" —— 定不下来就永远开不了工',
      bucket: 'now',
      origin: '计划拆下来的',
      due: '今天',
    },
    {
      id: 's2',
      title: '给实验室老师发一封问询邮件',
      minutes: 10,
      why: '大二结束前要有 1 段真实经历，而这件事越早开口越好',
      bucket: 'now',
      origin: '建议的',
    },
    {
      id: 's3',
      title: '把成绩单里分最高的两门课找出来',
      minutes: 10,
      why: '项目选题从你已经会的东西开始，最快',
      bucket: 'now',
      origin: '计划拆下来的',
    },
    {
      id: 's4',
      title: '等竞赛报名结果',
      minutes: 0,
      why: '报完了，结果出来前不用动',
      bucket: 'waiting',
      origin: '自己写的',
      due: '本周内',
    },
    {
      id: 's5',
      title: '完成学籍在线验证',
      minutes: 10,
      why: '验证完，成绩层级才能参与折算',
      bucket: 'done',
      origin: '关键节点',
      doneAt: '9 月 18 日',
    },
    {
      id: 's6',
      title: '列出 3 个想试的方向',
      minutes: 30,
      why: '这是你自己提出的问题，也是这个阶段最该花时间的地方',
      bucket: 'done',
      origin: '自己写的',
      doneAt: '10 月 2 日',
    },
  ],

  junior: [
    {
      id: 't1',
      title: '把简历第一页的封面表述改成"工艺方向"',
      minutes: 15,
      why: '你要投的前 5 家都会先看这一页 —— 现在这一页还是通用的',
      bucket: 'now',
      origin: '计划拆下来的',
    },
    {
      id: 't2',
      title: '投 3 家新能源方向的工艺岗',
      minutes: 25,
      why: '这个细分方向在扩招，而你已经两天没投了',
      bucket: 'now',
      origin: '计划拆下来的',
      due: '今天',
    },
    {
      id: 't3',
      title: '找出 2 段能写进简历的课程项目',
      minutes: 20,
      why: '门槛要求那条卡的就是"项目经历" —— 先把你已经有的翻出来',
      bucket: 'now',
      origin: '建议的',
    },
    {
      id: 't4',
      title: '给上一届学长发一条消息，问一句半导体岗日常',
      minutes: 5,
      why: '你收藏了 3 个半导体岗位但一次没投 —— 先问清楚再决定',
      bucket: 'waiting',
      origin: '建议的',
    },
    {
      id: 't5',
      title: '等中建某院结构岗的笔试结果',
      minutes: 0,
      why: '截止已过，结果预计本周出来，出来前不用动',
      bucket: 'waiting',
      origin: '自己写的',
      due: '本周内',
    },
    {
      id: 't6',
      title: '完成学籍在线验证',
      minutes: 10,
      why: '核验完，成绩层级才能参与折算，报告才有第 2 版',
      bucket: 'done',
      origin: '关键节点',
      doneAt: '9 月 18 日',
    },
    {
      id: 't7',
      title: '把每周可投入时间确认成 6 小时',
      minutes: 5,
      why: '时间不清，后面的计划都是空排',
      bucket: 'done',
      origin: '计划拆下来的',
      doneAt: '9 月 20 日',
    },
    {
      id: 't8',
      title: '看清三条方向的差别',
      minutes: 30,
      why: '这是你自己提出的问题，也是这个阶段最该花时间的地方',
      bucket: 'done',
      origin: '自己写的',
      doneAt: '10 月 2 日',
    },
  ],

  senior: [
    {
      id: 'e1',
      title: '把两个 offer 的取舍条件写成一张表',
      minutes: 20,
      why: '你说"不敢定" —— 其实是条件没摆到明面上，摆出来就定得下来',
      bucket: 'now',
      origin: '计划拆下来的',
      due: '今天',
    },
    {
      id: 'e2',
      title: '给二面被问倒的三类问题各写一版回答',
      minutes: 30,
      why: '二面卡住的不是能力，是那三类问题你没准备过',
      bucket: 'now',
      origin: '计划拆下来的',
    },
    {
      id: 'e3',
      title: '确认保底那家的三方截止日',
      minutes: 10,
      why: '有保底，才谈得上从容地挑 —— 先把日期握在手里',
      bucket: 'now',
      origin: '建议的',
    },
    {
      id: 'e4',
      title: '等 HR 回复薪资范围',
      minutes: 0,
      why: '问过了，等回复；没有数字之前不用比',
      bucket: 'waiting',
      origin: '自己写的',
    },
    {
      id: 'e5',
      title: '等春招岗位放出',
      minutes: 0,
      why: '春招一般 2 月启动，现在准备材料就够',
      bucket: 'waiting',
      origin: '关键节点',
    },
    {
      id: 'e6',
      title: '完成学籍在线验证',
      minutes: 10,
      why: '签三方前必须核验，别等签约当天才做',
      bucket: 'done',
      origin: '关键节点',
      doneAt: '9 月 18 日',
    },
    {
      id: 'e7',
      title: '修订简历第一页',
      minutes: 15,
      why: '这一版投出去才有的回音',
      bucket: 'done',
      origin: '计划拆下来的',
      doneAt: '10 月 5 日',
    },
  ],
}

/** 日历：关键节点（由规划师写入，不是前端写死） */
export const CALENDAR_MARKS: CalendarMark[] = [
  { day: 8, label: '投递 3 家', kind: 'action' },
  { day: 15, label: '简历改完', kind: 'deadline' },
  { day: 23, label: '本周复盘', kind: 'review' },
  { day: 28, label: '中建笔试结果', kind: 'deadline' },
]

/** 对话：含交接卡、可点选项、带时长的任务（第 4 幕） */
export const CHAT_TURNS: ChatTurn[] = [
  {
    id: 'c1',
    from: 'me',
    text: '我不知道自己适合什么。专业是调剂的，说不上喜欢。',
  },
  {
    id: 'c2',
    from: 'host',
    speaker: '了解你情况的人',
    text: '先不急着定方向。我问你一个问题就够了 —— 你更怕选错，还是更怕一直不定？',
    question: '你更怕选错，还是更怕一直不定？',
    options: ['更怕选错', '更怕一直不定', '两个都怕'],
  },
  {
    id: 'c3',
    from: 'me',
    text: '更怕一直不定。看着别人都动起来了。',
  },
  {
    id: 'c4',
    from: 'host',
    speaker: '了解你情况的人',
    text: '那这一条我记下了：你要的是"先动起来"，不是"想清楚再动"。这样后面我给的每一件事，都会是能今天就做完的。',
    citations: ['来自你 10 月 8 日的回答', '记入"学生档案"第 12 条'],
  },
  {
    id: 'c5',
    from: 'host',
    speaker: '帮你判断方向的人',
    text: '接下来由我接手。因为你已经聊到"要哪条路"这一步了，我不再问情况，只帮你比方向。我依据的是三条方向各自的门槛要求。',
    handoff: {
      to: '帮你判断方向的人',
      why: '你已经开始问"选哪个"，不再是"我是谁"',
      basedOn: '三条方向的门槛要求 + 你已有的 12 条了解',
    },
  },
  {
    id: 'c6',
    from: 'host',
    speaker: '帮你判断方向的人',
    text: '我比完了：半导体工艺这条，你的专业、兴趣、省内岗位供给三个都对得上，是最大把握的一条。但它卡在一个地方 —— 需要一段产线或洁净室经历，你没有。',
    citations: ['岗位要求：抽查 60 条中 34 条写明"项目/实习经历"', '省内半导体材料线今年扩招 3 家'],
  },
  {
    id: 'c7',
    from: 'host',
    speaker: '帮你判断方向的人',
    text: '不用现在决定。你先做一件 5 分钟的事，做完你对这条路的判断会清楚很多。',
    task: { title: '给上一届学长发一条消息，问一句半导体岗日常', minutes: 5 },
  },
  {
    id: 'c8',
    from: 'system',
    text: '本次未能生成内容。请再发一句，我会重新生成。',
  },
]

/** 提醒与干预：一条消息只做一件事，必须自带动作（7.4） */
export const NOTICES: Notice[] = [
  {
    id: 'n1',
    kind: '提醒',
    title: '中建某院的结构岗后天 18:00 截止',
    body: '你收藏了但还没投',
    action: '排进今天',
    secondary: '不适合，撤掉',
    deadline: '后天 18:00',
    queued: 2,
  },
]

/** 复盘：时间线 + 归因三选一（不归到人） */
export const REVIEW_ITEMS: ReviewItem[] = [
  {
    id: 'r1',
    when: '10 月 7 日',
    what: '把每周可投入时间写进计划',
    result: 'done',
  },
  {
    id: 'r2',
    when: '10 月 6 日',
    what: '投 3 家半导体方向',
    result: 'missed',
    attribution: '任务太大',
  },
  {
    id: 'r3',
    when: '10 月 5 日',
    what: '改简历第一页',
    result: 'partial',
    attribution: '方法不对',
  },
  {
    id: 'r4',
    when: '10 月 3 日',
    what: '和学长聊 15 分钟',
    result: 'done',
  },
]

export const REVIEW_CONCLUSION =
  '这一周你有 3 天动了手。没完成的那一件不是"你不自律" —— 是"投 3 家"这个任务本身太大，一次要 40 分钟以上。下一轮我把它拆成"先投 1 家"。'

/** 主动干预：全产品只有"陪你推进的人"能主动开口（第 9 幕） */
export const INTERVENTION = {
  host: '陪你推进的人',
  title: '看你好几天没动，来问一句',
  body: '不是催你 —— 上次那条"投 3 家"确实太大了。要不先投 1 家，5 分钟？',
  action: '先投 1 家（5 分钟）',
  secondary: '这周先缓一缓',
  rules: ['停滞 3 天触发', '同一条冷却 48 小时', '7 天最多 2 次'],
}
