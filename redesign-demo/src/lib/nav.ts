/**
 * 导航模型。
 *
 * 上一版这里叫"旅程导航"：5 个带编号的步骤 + 连接线 + "你在这儿"。
 * 那套语法的问题在评审反馈里被一句话点破：
 *   「这种呈现方式会让用户认为必须一点一点做，按顺序才行」
 * 对 —— 编号 + 连线 + 进度点，就是**向导（wizard）**的视觉语法，
 * 它天然在说"你必须从头走到尾"。而这个产品的价值恰恰相反：
 * 一次只推一件事，用户随时可以从任意一处进来。
 *
 * 所以这一版把**导航**和**进度**分开：
 *   · 导航 = 几个并列的地方，没有编号、没有先后（Tab 的语法是"去哪里"）
 *   · 进度 = 各页自己的事（画像还差几条、报告是第几版、今天要做什么）
 *   · "五步流程"这套模型不当常驻导航用了 —— 它是**解释**，放在「大一到大四」那一页里讲
 *
 * 一屏 5 个入口是上限；多出来的走 ⌘K（大一到大四、设计规范，以及以后新加的）。
 */

export interface NavSection {
  key: string
  label: string
  to: string
  /** 这一步下的其它视图（次级标签）—— 只是"同一处的两层"，不是先后 */
  subs: { label: string; to: string }[]
}

export const NAV_SECTIONS: NavSection[] = [
  /*
   * 「对话」排第一：它是入口页之后的**第一个界面**。
   * 登录进来先落到对话 —— 产品的第一步本来就是"先聊几句了解你"，
   * 而不是先看一张写着"你现在是大三……"的看板。看板是对话把情况问清楚之后才有意义的地方。
   * 顺序即默认：`sectionIndexForPath` 找不到时回落到第 0 项。
   */
  { key: 'chat', label: '对话', to: '/chat', subs: [] },
  {
    key: 'mine',
    label: '任务与计划',
    to: '/home',
    subs: [
      { label: '今日任务', to: '/home' },
      { label: '计划与行动', to: '/plan' },
    ],
  },
  { key: 'profile', label: '学生档案', to: '/profile', subs: [] },
  {
    key: 'report',
    label: '评估报告',
    to: '/report',
    subs: [
      { label: '报告', to: '/report' },
      { label: '方向对比', to: '/report?focus=choose' },
    ],
  },
  { key: 'review', label: '复盘记录', to: '/review', subs: [] },
]

/** 路径 → 属于哪一个地方（用来点亮 tab、决定是否显示次级标签） */
export function sectionIndexForPath(path: string): number {
  return NAV_SECTIONS.findIndex(
    (s) => s.to.split('?')[0] === path || s.subs.some((sub) => sub.to.split('?')[0] === path),
  )
}

/**
 * 顶栏右侧的"更多"：不占导航位，但要在界面里找得到。
 * 「大一到大四」也从侧边栏搬到了这里 —— 它是讲解，不是日常要去的五个地方之一。
 */
export const META_LINKS = [
  { label: '大一到大四 · 五步是怎么走的', to: '/path', hint: '四个年级的场景 + 七步操作路径（含界面截图）' },
  { label: '设计规范', to: '/spec', hint: '三色令牌、皮肤与动效口径' },
  { label: '门户', to: '/', hint: '公开首页：一句主张 + 一个入口' },
]
