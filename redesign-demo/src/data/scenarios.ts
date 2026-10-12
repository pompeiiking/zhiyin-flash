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
    focus: '先看清自己，别急着定方向',
    taskCards: [
      '不了解我的专业能做什么',
      '想试试不同的方向',
      '想认识几个学长学姐',
      '想先摸清自己的兴趣',
      '直接开聊',
    ],
    known: 4,
    nextStep: '先聊三五个问题，把"我大概是个什么样的人"立起来',
    reportFocus: '你是什么样的人',
    milestones: [
      {
        id: 'm-f1',
        title: '弄清 3 个可能的方向',
        window: '大一下学期开学前',
        progress: 0.35,
        note: '先求广，不求准 —— 这个阶段排除掉不合适的，就算进展',
      },
      {
        id: 'm-f2',
        title: '把每周固定投入的时间定下来',
        window: '本学期内',
        progress: 0.6,
        note: '时间投入是后面所有计划的地基',
      },
    ],
    reviewFocus: '这周有没有真的动手 —— 不是"想了没有"',
    probe: '你更怕选错，还是更怕一直不定？',
  },
  {
    id: 'sophomore',
    grade: '大二',
    situation: '有一个大概想试的方向，但手上没有任何能拿出手的东西',
    focus: '攒证据：把兴趣变成能讲的项目和经历',
    taskCards: [
      '想验证一个方向到底适不适合我',
      '想找一个能做的项目或竞赛',
      '想练一项真正用得上的硬技能',
      '实习什么时候开始准备',
      '直接开聊',
    ],
    known: 7,
    nextStep: '先定一件这学期能做完、能写进简历的事',
    reportFocus: '你是什么样的人',
    milestones: [
      {
        id: 'm-s1',
        title: '有 1 个能讲清楚的项目',
        window: '大二结束前',
        progress: 0.2,
        note: '能讲清楚 = 说得出你做了什么、遇到了什么、怎么解决的',
      },
      {
        id: 'm-s2',
        title: '有 1 段真实经历（实习 / 竞赛 / 实验室）',
        window: '大二结束前',
        progress: 0.1,
        note: '哪怕只有两周，也算 —— 但必须是你真的干了活的',
      },
    ],
    reviewFocus: '投入的时间有没有变成"能展示的产出"',
    probe: '这件事做完，你能用三句话把它讲清楚吗？',
  },
  {
    id: 'junior',
    grade: '大三',
    situation: '秋招就在眼前，专业谈不上喜欢，几个方向拿不准',
    focus: '定方向、上手投，别再收集信息了',
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
    nextStep: '把方向收敛成主攻一条，今天先动第一件',
    reportFocus: '你要做哪些取舍',
    milestones: [
      {
        id: 'm-j1',
        title: '简历能投出去（第一页改完）',
        window: '9 月 20 日前',
        progress: 0.5,
        note: '先能投，再谈好不好 —— 卡在这一步的人最多',
      },
      {
        id: 'm-j2',
        title: '投满 15 家，主攻方向占一半',
        window: '10 月 31 日前',
        progress: 0.27,
        note: '投递量是这一步唯一能靠努力改变的事',
      },
      {
        id: 'm-j3',
        title: '拿到 2 次面试',
        window: '11 月 30 日前',
        progress: 0,
        note: '面试反馈是唯一真实的方向校准信号',
      },
    ],
    reviewFocus: '投了没回音，到底差在哪 —— 任务、方法还是方向',
    probe: '你更怕选错，还是更怕一直不定？',
  },
  {
    id: 'senior',
    grade: '大四',
    situation: '秋招收尾、春招在即，手上有选择但不敢定，时间最紧',
    focus: '把手上有的，换成一份能签的工作',
    taskCards: [
      '手上两个 offer 怎么选',
      '面试总卡在二面',
      '签三方要注意什么',
      '考研没上岸想直接工作',
      '想补一个保底方向',
      '直接开聊',
    ],
    known: 14,
    nextStep: '把 offer 的取舍条件摆到明面上，再决定',
    reportFocus: '你要做哪些取舍',
    milestones: [
      {
        id: 'm-e1',
        title: '保住一个可签的保底',
        window: '春招启动前',
        progress: 0.7,
        note: '有保底，才谈得上从容地挑',
      },
      {
        id: 'm-e2',
        title: '二面通过率提上来',
        window: '春招结束前',
        progress: 0.25,
        note: '把二面被问倒的三类问题逐条补上',
      },
    ],
    reviewFocus: '这一轮的结果，是运气还是能改的地方',
    probe: '这两个 offer，你真正怕失去的是哪一个？',
  },
]

export const GRADE_ORDER: Grade[] = ['freshman', 'sophomore', 'junior', 'senior']

export function scenarioOf(id: Grade): Scenario {
  return SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[2]
}
