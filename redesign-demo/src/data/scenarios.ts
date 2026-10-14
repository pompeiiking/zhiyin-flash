import type { Scenario, Grade } from './types'

/**
 * 场景化设计：一年级到四年级，四套不同的使用场景。
 *
 * 评审要求原文：「按一年级到四年级的不同使用场景设计内容，每个操作步骤配对应
 * 界面截图，直观展示产品使用路径」。所以 demo 顶栏放了一个年级切换器，
 * 切一次，首页的任务卡、画像进度、里程碑、报告重点、复盘关注点整套跟着换。
 *
 * 内容口径遵守 7.4：全部是用户语言 —— 界面不出现环节名、维度名、内部词。
 */
export const SCENARIOS: Scenario[] = [
  {
    id: 'freshman',
    grade: '大一',
    situation: '专业是调剂的，谈不上喜欢，也不知道以后能干什么',
    focus: '探索兴趣与职业方向',
    taskCards: [
      '不了解我的专业能做什么',
      '想试试不同的方向',
      '想认识几个学长学姐',
      '想先摸清自己的兴趣',
      '直接开聊',
    ],
    known: 4,
    nextStep: '通过咨询补充兴趣、能力与个人条件',
    reportFocus: '个人特征与能力',
    milestones: [
      {
        id: 'm-f1',
        title: '了解 3 个备选职业方向',
        window: '大一下学期开学前',
        progress: 0.35,
        note: '优先扩大职业认知范围，逐步排除不匹配方向。',
      },
      {
        id: 'm-f2',
        title: '确定每周可投入时间',
        window: '本学期内',
        progress: 0.6,
        note: '根据可投入时间安排后续实践计划。',
      },
    ],
    reviewFocus: '本阶段行动执行情况',
    probe: '你更怕选错，还是更怕一直不定？',
  },
  {
    id: 'sophomore',
    grade: '大二',
    situation: '有一个大概想试的方向，但手上没有任何能拿出手的东西',
    focus: '积累项目与实践经历',
    taskCards: [
      '想验证一个方向到底适不适合我',
      '想找一个能做的项目或竞赛',
      '想练一项真正用得上的硬技能',
      '实习什么时候开始准备',
      '直接开聊',
    ],
    known: 7,
    nextStep: '确定本学期可完成的实践项目',
    reportFocus: '个人特征与能力',
    milestones: [
      {
        id: 'm-s1',
        title: '完成 1 个可展示的实践项目',
        window: '大二结束前',
        progress: 0.2,
        note: '明确项目职责、实施过程与成果。',
      },
      {
        id: 'm-s2',
        title: '有 1 段真实经历（实习 / 竞赛 / 实验室）',
        window: '大二结束前',
        progress: 0.1,
        note: '经历应包含真实职责与可验证的实践成果。',
      },
    ],
    reviewFocus: '实践投入与项目成果',
    probe: '这件事做完，你能用三句话把它讲清楚吗？',
  },
  {
    id: 'junior',
    grade: '大三',
    situation: '秋招就在眼前，专业谈不上喜欢，几个方向拿不准',
    focus: '明确目标方向并推进岗位申请',
    taskCards: [
      '考研还是就业',
      '投了几家没回音',
      '想转方向',
      '家里希望我考公',
      '几个方向拿不准',
      '定了方向不知道怎么动',
      '执行卡住',
      '该复盘了',
      '直接开聊',
    ],
    known: 12,
    nextStep: '确定主攻方向，并执行当前优先任务',
    reportFocus: '决策条件与约束',
    milestones: [
      {
        id: 'm-j1',
        dueAt: '2026-09-20',
        dependsOn: [],
        handoff: '简历修订完成后，下一步投出去的才是更新后的材料。',
        title: '完成简历修订并满足申请要求',
        window: '9 月 20 日前',
        progress: 0.5,
        note: '优先完成目标岗位所需的简历材料。',
      },
      {
        id: 'm-j2',
        dueAt: '2026-10-31',
        dependsOn: ['m-j1'],
        handoff: '投递的岗位与回应会成为下一步面试准备的依据。',
        title: '申请 15 个岗位，主攻方向不少于一半',
        window: '10 月 31 日前',
        progress: 0.27,
        note: '结合岗位开放情况与匹配程度执行投递计划。',
      },
      {
        id: 'm-j3',
        dueAt: '2026-11-30',
        dependsOn: ['m-j2'],
        handoff: '面试反馈回到复盘，继续核对方向与材料。',
        title: '获得 2 次面试机会',
        window: '11 月 30 日前',
        progress: 0,
        note: '结合面试反馈进一步修订方向与求职材料。',
      },
    ],
    reviewFocus: '分析岗位申请结果与执行障碍',
    probe: '你更怕选错，还是更怕一直不定？',
  },
  {
    id: 'senior',
    grade: '大四',
    situation: '秋招收尾、春招在即，手上有选择但不敢定，时间最紧',
    focus: '评估就业选择并完成求职准备',
    taskCards: [
      '手上两个 offer 怎么选',
      '面试总卡在二面',
      '签三方要注意什么',
      '考研没上岸想直接工作',
      '想补一个保底方向',
      '直接开聊',
    ],
    known: 14,
    nextStep: '比较录用条件与个人约束后进行选择',
    reportFocus: '决策条件与约束',
    milestones: [
      {
        id: 'm-e1',
        title: '确认 1 项可接受的备选录用',
        window: '春招启动前',
        progress: 0.7,
        note: '保留可接受的备选方案，评估其他录用条件。',
      },
      {
        id: 'm-e2',
        title: '提升复试准备质量',
        window: '春招结束前',
        progress: 0.25,
        note: '针对复试中的主要问题补充案例与回答。',
      },
    ],
    reviewFocus: '分析求职结果与可调整因素',
    probe: '这两个 offer，你真正怕失去的是哪一个？',
  },
]

export const GRADE_ORDER: Grade[] = ['freshman', 'sophomore', 'junior', 'senior']

export function scenarioOf(id: Grade): Scenario {
  return SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[2]
}
