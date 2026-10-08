/**
 * 画布上有哪些块、各叫什么。
 *
 * 从 `ConsoleView.vue` 里搬出来的：这份名单现在有**两个读者** —— 画布本身，
 * 以及「全部组件」面板（收起 / 放回 / 排序）。两边各写一份的下场很具体：
 * 面板里少一块（用户看不到、也就收不起来），或者同一个块在两处叫不同名字。
 *
 * `BLOCK_ORDER` 只是**初始顺序**：真正的顺序由后端的 `layout_panel` 给，
 * 用户自己排过则以他那份为准（见 store 的 `blocksOrder`）。
 */

/**
 * 核心区块数：**用户还没自己管过**的时候，一屏只铺这么多。
 *
 * 八块是这套"手绘草稿台"在 1440×900 上还能一眼读清的上限（再多就滑向
 * "九宫格同构卡片"那种杂乱 —— 评审与 issue #22/#25 说的都是这件事）。
 * 用户一旦自己收过或排过（`blocksHidden` / `blocksOrder` 非空），就完全听他的。
 *
 * 它放在这里而不是画布里，是因为**画布与「全部组件」面板都要用它**：
 * 两边各写一个数字，就会出现"面板说在画布上、画布上却没有"。
 */
export const CORE_COUNT = 8

/** 画布上可能出现的块（顺序即默认先后） */
export const BLOCK_ORDER: string[] = [
  'talk',
  'portrait',
  'todo',
  'collect',
  'plans',
  'action',
  'calendar',
  'timetable',
  'match',
  'market',
  'greet',
  'people',
  'review',
  'achievements',
]

/**
 * 块的显示名（界面上的人话名，不是 id）。
 *
 * 键必须覆盖 `BLOCK_ORDER` 里的每一个 —— 守卫 `test_every_block_has_a_label`
 * 会比对：漏掉一个，那块在「全部组件」里就会显示成英文 id，而画布上照常有它。
 */
export const BLOCK_LABELS: Record<string, string> = {
  talk: '和主理聊聊',
  portrait: '你的画像',
  todo: '待办',
  collect: '采集动线',
  plans: '方向方案',
  action: '行动计划',
  calendar: '日历',
  timetable: '本周课表',
  match: '匹配与推荐',
  market: '外部情报',
  greet: '今日简报',
  people: '交接',
  review: '上周复盘',
  achievements: '完成记录',
}
