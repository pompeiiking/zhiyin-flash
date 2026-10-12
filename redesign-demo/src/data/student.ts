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
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 18 日核验',
  },
  {
    key: 'grade',
    label: '年级',
    value: '大三（2024 级）',
    source: '学信网',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 18 日核验',
  },
  {
    key: 'interest',
    label: '兴趣倾向',
    value: '偏"把事做成"，而不是"研究原理"',
    source: '对话',
    confidence: { level: 'mid', label: '待验证', bars: 2 },
    noted: '9 月 12 日，你说的原话',
  },
  {
    key: 'style',
    label: '做事方式',
    value: '独处时更出活，讨厌反复开会',
    source: '对话',
    confidence: { level: 'mid', label: '待验证', bars: 2 },
    noted: '9 月 12 日，你说的原话',
  },
  {
    key: 'time',
    label: '每周可投入',
    value: '6 小时（课表空档算出来的）',
    source: '教务系统',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 20 日，按课表算的',
  },
  {
    key: 'rank',
    label: '成绩层级',
    value: '专业前 30%',
    source: '教务系统',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 20 日导入',
  },
  {
    key: 'family',
    label: '家庭期待',
    value: '父母希望考公',
    source: '对话',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 12 日，你主动提的',
  },
  {
    key: 'weakness',
    label: '已知短板',
    value: '简历上没有一个能讲的项目',
    source: '对话',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 15 日，你自己说的',
  },
  {
    key: 'city',
    label: '目标城市',
    value: '倾向留在省内',
    source: '对话',
    confidence: { level: 'low', label: '信息不足', bars: 1 },
    noted: '9 月 12 日，你说"还没想好"',
  },
  {
    key: 'pipeline',
    label: '投递现状',
    value: '投了 4 家，0 个回音',
    source: '行为记录',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '10 月 8 日，你标记的',
  },
  {
    key: 'award',
    label: '在校获奖与处分',
    value: '校级三等奖学金 1 次，无处分',
    source: '学校',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '9 月 22 日，学校系统同步',
  },
  {
    key: 'schedule',
    label: '本周课表空档',
    value: '周三、周五下午各有 2 小时',
    source: '教务系统',
    confidence: { level: 'high', label: '依据充分', bars: 3 },
    noted: '10 月 6 日，按教务课表算的',
  },
  {
    key: 'internship',
    label: '实习经历',
    value: '大二暑期在本地封装厂做过 6 周工艺实习',
    source: '对话',
    confidence: { level: 'low', label: '信息不足', bars: 1 },
    noted: '还没聊到',
  },
  {
    key: 'jobtype',
    label: '目标岗位类型',
    value: '工艺 / 设备岗，暂时不考虑纯研发',
    source: '对话',
    confidence: { level: 'low', label: '信息不足', bars: 1 },
    noted: '还没聊到',
  },
  {
    key: 'salary',
    label: '薪资底线',
    value: '省内 8k 起可以谈，低于 8k 会犹豫',
    source: '对话',
    confidence: { level: 'low', label: '信息不足', bars: 1 },
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
    title: '个人特征与能力',
    dimensions: [
      {
        key: 'interest',
        label: '兴趣方向',
        conclusion: '倾向于实践与成果产出，理论研究兴趣相对较低',
        confidence: { level: 'mid', label: '待验证', bars: 2 },
        score: 68,
        threshold: '示例方向中有两条偏向实践产出，与当前兴趣倾向基本匹配。',
        evidence: ['你 9 月 12 日说的："比起算公式，我更愿意看东西被做出来"', '14 轮对话里，"动手"出现 9 次'],
      },
      {
        key: 'style',
        label: '做事方式',
        conclusion: '具备持续专注能力，频繁切换任务时恢复效率较低',
        confidence: { level: 'mid', label: '待验证', bars: 2 },
        score: 61,
        threshold: '选择岗位时，应考虑跨部门协作频率及任务切换要求。',
        evidence: ['你说过"一天开三个会就什么都干不了"', '你在晚上的任务完成率是白天的 2.4 倍'],
      },
      {
        key: 'present',
        label: '呈现能力',
        conclusion: '已有实践经历，但经历表达与简历组织能力仍需提升',
        confidence: { level: 'high', label: '依据充分', bars: 3 },
        score: 46,
        threshold: '示例呈现能力为 46 分，目标要求为 50 分，差距为 4 分。',
        evidence: ['简历第一页目前只有 3 行有效信息', '已投 4 家，0 个回音'],
      },
    ],
  },
  {
    key: 'market',
    title: '职业环境分析',
    dimensions: [
      {
        key: 'demand',
        label: '岗位供给',
        conclusion: '示例岗位快照提示不同细分方向的供给差异，实际趋势需核对最新来源',
        confidence: { level: 'mid', label: '待验证', bars: 2 },
        score: 55,
        threshold: '可进一步比较传统材料、新能源与半导体方向，选择前需核验实时岗位数据。',
        evidence: ['演示统计：材料类岗位 218 条，同比 -12%（非真实实时数据）', '演示统计：新能源方向 +34%（非真实实时数据）'],
      },
      {
        key: 'threshold',
        label: '门槛要求',
        conclusion: '示例岗位要求较重视项目或实习经历',
        confidence: { level: 'high', label: '依据充分', bars: 3 },
        score: 62,
        threshold: '建议补充相关实践经历，并在简历中清晰展示项目成果。',
        evidence: ['抽查 60 条岗位要求，"项目/实习经历"出现 34 次'],
      },
      {
        key: 'compete',
        label: '竞争者情况',
        conclusion: '示例对比显示，相关实习经历是当前主要差距之一',
        confidence: { level: 'mid', label: '待验证', bars: 2 },
        score: 48,
        threshold: '建议通过实习、项目或实验室实践补充岗位相关经历。',
        evidence: ['同专业上一届 40 人的去向：实习过的 27 人，其中 22 人在秋招前拿到面试'],
      },
    ],
  },
  {
    key: 'tradeoff',
    title: '决策条件与约束',
    dimensions: [
      {
        key: 'city',
        label: '城市取舍',
        conclusion: '需综合比较地域偏好、岗位机会与异地生活成本',
        confidence: { level: 'low', label: '信息不足', bars: 1 },
        score: 50,
        threshold: '需进一步确认异地就业接受程度及生活成本约束。',
        evidence: ['你说过"倾向留在省内"，但也说过"还没想好"'],
      },
      {
        key: 'family',
        label: '家里的期待',
        conclusion: '家庭期待与个人职业意愿尚需进一步确认',
        confidence: { level: 'high', label: '依据充分', bars: 3 },
        score: 72,
        threshold: '建议明确家庭期待与个人意愿的差异，再确定职业选择。',
        evidence: ['你 9 月 12 日主动提到"家里希望我考公"', '你从没打开过考公相关的岗位'],
      },
      {
        key: 'time',
        label: '时间取舍',
        conclusion: '每周可投入时间约 6 小时，建议明确主要目标并安排优先级',
        confidence: { level: 'high', label: '依据充分', bars: 3 },
        score: 60,
        threshold: '建议先确定主要目标，避免有限时间分散到多个执行方案。',
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
  { label: '项目经历', mine: 20, requirement: 60, note: '示例岗位的主要能力要求' },
  { label: '专业对口', mine: 88, requirement: 70, note: '已满足示例岗位的专业要求' },
]

/** 结论段：每次打开读的是那一版资产，不重复生成（第 6 幕） */
export const REPORT_SUMMARY =
  '示例诊断包含三个备选方向，各方向的匹配条件与能力差距不同。' +
  '当前建议优先提升经历表达能力：示例分值为 46 分，目标要求为 50 分。' +
  '可结合项目或实习经历修订简历，并核验最新岗位信息后制定投递计划。'

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
    fit: { level: 'high', label: '匹配度较高', bars: 3 },
    fitScore: 0.82,
    evidence: ['专业对口：材料科学与工程', '兴趣倾向：实践与成果产出', '示例供给：省内 3 家企业的模拟岗位快照'],
    risk: '需补充洁净室或产线相关实践经历',
    ripple: 4,
    ripplePoints: ['简历第一页的主线表述', '本周任务的排序', '报告里"门槛要求"那条的结论', '投递清单的前 5 家'],
  },
  {
    id: 'd2',
    role: '平行',
    title: '新能源电池研发助理',
    fit: { level: 'mid', label: '待验证', bars: 2 },
    fitScore: 0.64,
    evidence: ['示例供给：新能源相关岗位快照', '示例成绩：相关实验课程表现良好'],
    risk: '研发岗普遍要求研究生学历，本科要投需要挑中小企业',
    ripple: 3,
    ripplePoints: ['投递清单', '是否需要考研的判断', '简历里的课程项目排序'],
  },
  {
    id: 'd3',
    role: '保底',
    title: '省内国企材料检测岗',
    fit: { level: 'mid', label: '待验证', bars: 2 },
    fitScore: 0.58,
    evidence: ['示例岗位：材料检测类岗位要求', '就业地域与当前偏好基本一致'],
    risk: '岗位日常与实践产出兴趣存在差异，需评估长期适应性',
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
      why: '明确可投入时间，有助于制定可执行计划。',
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
      why: '根据当前咨询目标安排优先事项。',
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
      why: '建议根据目标岗位调整简历重点，提高经历与岗位要求的关联性。',
      bucket: 'now',
      origin: '计划拆下来的',
    },
    {
      id: 't2',
      title: '投 3 家新能源方向的工艺岗',
      minutes: 25,
      why: '根据示例投递计划安排本轮岗位申请，实际岗位开放情况需核验。',
      bucket: 'now',
      origin: '计划拆下来的',
      due: '今天',
    },
    {
      id: 't3',
      title: '找出 2 段能写进简历的课程项目',
      minutes: 20,
      why: '整理已有课程项目，明确个人职责、实施过程及成果。',
      bucket: 'now',
      origin: '建议的',
    },
    {
      id: 't4',
      title: '联系学长，了解半导体岗位日常',
      minutes: 5,
      why: '通过职业访谈补充岗位认知，再确定是否申请。',
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
      why: '明确可投入时间，有助于制定可执行计划。',
      bucket: 'done',
      origin: '计划拆下来的',
      doneAt: '9 月 20 日',
    },
    {
      id: 't8',
      title: '看清三条方向的差别',
      minutes: 30,
      why: '根据当前咨询目标安排优先事项。',
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
  { day: 15, label: '完成简历修订', kind: 'deadline' },
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
    text: '可以先明确当前关注的重点：你更关注方向选择的风险，还是迟迟未开始行动？',
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
    text: '已记录。后续建议将优先关注可执行的行动步骤，并根据反馈继续完善方向判断。',
    citations: ['来自你 10 月 8 日的回答', '记入"学生档案"第 12 条'],
  },
  {
    id: 'c5',
    from: 'host',
    speaker: '帮你判断方向的人',
    text: '当前咨询进入方向分析，将结合三个备选方向的岗位要求开展比较。',
    handoff: {
      to: '帮你判断方向的人',
      why: '当前问题已转向方向比较与选择',
      basedOn: '三条方向的门槛要求 + 你已有的 12 条了解',
    },
  },
  {
    id: 'c6',
    from: 'host',
    speaker: '帮你判断方向的人',
    text: '示例分析显示，半导体工艺方向与专业及兴趣基本匹配，主要差距为产线或洁净室实践经历。岗位供给信息仍需通过最新来源核验。',
    citations: ['岗位要求：抽查 60 条中 34 条写明"项目/实习经历"', '省内半导体材料线今年扩招 3 家'],
  },
  {
    id: 'c7',
    from: 'host',
    speaker: '帮你判断方向的人',
    text: '建议先通过简短的职业访谈了解岗位日常，再结合反馈确定方向。',
    task: { title: '联系学长，了解半导体岗位日常', minutes: 5 },
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
