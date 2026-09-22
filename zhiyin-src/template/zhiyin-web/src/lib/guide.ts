/*
 * 导览 —— 系统的声音。
 *
 * 它和五个业务智能体是**两种东西**，这条边界必须先划清楚：
 *
 *   五个智能体（建档分析师 / 职业顾问 / …）谈的是**你的事**：
 *   你的专业、你的方向、你的缺口。它们有名字、有分工、会交接。
 *
 *   导览谈的是**这个软件**：这里是哪、能去哪、这块为什么长这样、
 *   你卡住的时候可以从哪儿绕。它不分析你，也不替你判断。
 *
 * 所以它没有名字（有名字就成了第六个智能体），它的形态是**一张便签**而不是对话框，
 * 它的句子永远在回答三件事：你在哪 / 你能去哪 / 现在最好先做什么。
 *
 * 这个分界在实现上也是硬的：导览只说它**确实知道**的状态（画像几条、缺口几条、
 * 学籍核没核验），不编造关于用户的判断 —— 那是业务层的事，越界就会变成
 * "用一个助手壳装两个脑子"，用户分不清谁在说话。
 */

export type GuideTipKind = 'route' | 'overlay'

export interface GuideTip {
  id: string
  label: string
  note: string
  kind: GuideTipKind
  /** kind=route 时是路由；kind=overlay 时是浮层名 */
  to: string
}

export interface GuideView {
  /** 一句话：现在处在什么状态。会随用户的状态变，这是"灵动"的来源 */
  line: string
  /** 这一屏是什么 —— 教程性质的那一句 */
  where: string
  /** 索引：能去哪 */
  tips: GuideTip[]
}

export interface GuideInput {
  route: string
  hasProfile: boolean
  fieldCount: number
  gapCount: number
  chsiBound: boolean
  /** 编排器当前推的那一步；null 表示它现在没有特别要你做的 */
  askLabel: string | null
}

const INDEX: GuideTip[] = [
  { id: 'console', label: '今天', note: '一屏之内，全是你能动的事', kind: 'route', to: '/' },
  // 摆进索引里，"任意地方都能把对话叫出来"就不需要第二个全局按钮：
  // 导览本来就在每一页上，它指向哪儿，用户就能去哪儿。
  { id: 'talk', label: '跟主理聊聊', note: '说不清楚的时候，一句话就够', kind: 'overlay', to: 'talk' },
  { id: 'portrait', label: '我的画像', note: '系统现在怎么看你、还差哪几条', kind: 'overlay', to: 'portrait' },
  { id: 'tasks', label: '全部任务', note: '待办与已经办完的', kind: 'overlay', to: 'tasks' },
  { id: 'report', label: '完整报告', note: '每条结论的依据与把握程度', kind: 'route', to: '/report' },
  { id: 'chsi', label: '核验学籍', note: '用学信网在线验证码，不用账号密码', kind: 'overlay', to: 'bind' },
]

/** 每一屏是什么 —— 教程的那一半。进去第一眼不需要猜 */
const WHERE: Record<string, string> = {
  '/': '这里是今天：每块气泡都是一件能动手的事，点开就是细节，右边角上是这一屏的导览。',
  '/report': '这里是完整报告：结论、决策线、依据，都能点开溯源。',
  '/portal': '这里是门户：只出现一次，回答"这是个什么东西"。',
}

export function buildGuide(input: GuideInput): GuideView {
  const tips = input.chsiBound ? INDEX.filter((t) => t.id !== 'chsi') : INDEX

  return {
    line: line(input),
    where: WHERE[input.route] ?? '点下面的索引，哪儿都能去。',
    tips: tips.filter((t) => !(t.kind === 'route' && t.to === input.route)),
  }
}

/**
 * 那句会变的话。
 *
 * 语气刻意保持"我在旁边看着你操作"而不是"我来分析你"：
 * 前者是导览，后者是顾问 —— 越界就串味了。
 */
function line(input: GuideInput): string {
  if (input.route === '/report') {
    return '报告是结果，不是起点。看不懂哪一条，回今天接着做也行。'
  }

  if (!input.hasProfile) {
    return '你还没建档 —— 所以这屏大部分是空的，这不是坏了。先聊两句，后面每一步才有得算。'
  }

  /*
   * 顺序就是"它先说哪一句"，这一版按**变化最快的先说**排。
   *
   * 改之前把"学籍没核验"排在缺口前面：只要用户一直没去核验学籍，
   * 这句话就永远是同一句 —— 导览看上去是死的（用户直接这么反馈的）。
   * 现在先说**当前那一步**（每轮都在变），再说缺口，最后才是学籍这类"长期状态"。
   */
  if (input.askLabel) {
    return `现在这一步：${input.askLabel}`
  }

  if (input.gapCount > 0) {
    return `画像里还差 ${input.gapCount} 条。不用你找 —— AI 会一次问一条，答完它自己往下走。`
  }

  if (!input.chsiBound) {
    return `画像里有 ${input.fieldCount} 条了。学籍还没核验：核验完，学校、专业、层次会直接补进画像。`
  }

  return '这一轮该补的都补上了。想往下推，就从任意一块点进去。'
}

/** 导览自己的一句话身份，给组件做标题用 */
export const GUIDE_TITLE = '导览'
export const GUIDE_NOTE = '它只说这个软件怎么用，不替你做判断 —— 判断是五个主理的事。'
