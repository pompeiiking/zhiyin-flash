/**
 * 全站唯一的导航模型。
 *
 * 以前有两套：`lib/nav.ts`（旧的五个并列入口）与这里。两套并存导致同一功能多个入口、
 * 面包屑与地址列表各自硬编码、新增路由要改好几处。现在只有这一份。
 *
 * 分组按**用户此刻要做什么**划分，不按产品内部循环划分：
 * 对话 → 了解自己 → 做决定 → 去做 → 回头看。
 */

export interface NavItem {
  /** 稳定标识，用于路由高亮、面包屑与地址列表 */
  key: string
  label: string
  /** 移动底栏等窄空间用的短标签 */
  short?: string
  to: string
  icon: string
  /** 命中这些路径时该项高亮；/home 与 /plan 不再合并成一项 */
  paths: string[]
  hint: string
  /** 该入口只在 query 命中时才算选中（用于同一路由下的两个视图） */
  query?: Record<string, string>
}

export interface NavGroup {
  key: string
  label: string
  icon: string
  items: NavItem[]
}

/** 产品主循环：唯一的主入口，桌面上置顶，移动端第一个 tab。 */
export const WORKSPACE_PRIMARY: NavItem = {
  key: 'chat',
  label: '咨询对话',
  to: '/chat',
  icon: 'chat',
  paths: ['/chat'],
  hint: '和顾问把问题聊清楚',
}

export const WORKSPACE_GROUPS: NavGroup[] = [
  {
    key: 'self',
    label: '了解自己',
    icon: 'profile',
    items: [
      { key: 'profile', label: '个人画像', to: '/profile', icon: 'profile', paths: ['/profile'], hint: '已有的信息、来源与待补充项' },
      { key: 'grades', label: '我的成绩', to: '/grades', icon: 'academic', paths: ['/grades'], hint: '按学期查看与更新成绩' },
      { key: 'report', label: '你的报告', to: '/report', icon: 'report', paths: ['/report'], hint: '结论、依据与历史版本' },
    ],
  },
  {
    key: 'decide',
    label: '做决定',
    icon: 'directions',
    items: [
      { key: 'directions', label: '方向方案', to: '/directions', icon: 'directions', paths: ['/directions'], hint: '主攻、平行与保底的选择' },
      { key: 'intel', label: '职业探索', to: '/intel', icon: 'compass', paths: ['/intel'], hint: '从专业出发了解职业方向与真实去向' },
    ],
  },
  {
    key: 'act',
    label: '行动安排',
    icon: 'action',
    items: [
      { key: 'home', label: '今日行动', to: '/home', icon: 'action', paths: ['/home'], hint: '今天该做的那一件与待执行任务' },
      { key: 'plan', label: '阶段计划', to: '/plan', icon: 'path', paths: ['/plan'], hint: '阶段目标、时间窗与里程碑' },
      { key: 'schedule', label: '日历与课表', to: '/schedule', icon: 'calendar', paths: ['/schedule'], hint: '课程、截止与可投入时间' },
      { key: 'notes', label: '待办与目标', to: '/notes', icon: 'notes', paths: ['/notes'], hint: '自己写下的事与目标' },
    ],
  },
  {
    key: 'review',
    label: '复盘与成长',
    icon: 'review',
    items: [
      { key: 'review', label: '复盘记录', to: '/review', icon: 'review', paths: ['/review'], hint: '做过的事与调整' },
      { key: 'achievements', label: '完成记录', to: '/achievements', icon: 'trophy', paths: ['/achievements'], hint: '已完成、下一步与形成条件' },
    ],
  },
]

const GROUP_ITEMS: NavItem[] = WORKSPACE_GROUPS.flatMap((g) => g.items)

/** 命令面板与地址列表用的扁平全集（含主入口）。 */
export const WORKSPACE_ITEMS: NavItem[] = [WORKSPACE_PRIMARY, ...GROUP_ITEMS]
/** 全部界面目录包含原型登记的非主导航页；主侧栏仍只显示学生任务分组。 */
export const DIRECTORY_PAGES = [
  {label:'账号设置',to:'/settings',hint:'授权、提醒偏好、外观与导出'},
]

/**
 * 不在学生导航里的页面（直链可达，不作为入口）。
 *
 * 这三页都判过"存在理由"，结论是**它们不是学生页**：
 * - `/spec` 设计规范：内部文档，教的是本工程自己的排版与配色；
 * - `/path` 大一到大四：页面文案写着「设计要点」「截图来自改造后的实际浏览器预览」，
 *   是给评审看的施工说明书（且内嵌截图已过期）；
 * - `/tools` 应用工具：后端无数据时全文 327 字，**整页恰好一屏的空页**。
 *
 * 只在这里留标题，给直链打开时的面包屑一个说法 —— **不导出成任何列表**，
 * 所以侧栏页脚、移动「更多」、⌘K 与 404 的"有效地址"都不会再出现它们。
 * 这一份同时兑现文件头的老决定（"内部文档，不进学生导航"）与 `PLAN §2.4`。
 */
const INTERNAL_PAGE_TITLES: Record<string, string> = {
  '/reminders': '提醒',
  '/spec': '设计规范',
  '/path': '大一到大四',
  '/tools': '应用工具',
}

/**
 * 公开门户：已登录的人不该被导航带出应用，所以它不占导航位，只留在账号菜单里。
 * 不是数组 —— 404 页的"现在有效的地址"读的是导航模型，门户不该混进学生的地址列表。
 */
export const PORTAL_LINK = { label: '返回门户', to: '/', hint: '职引如何帮助你' }

/** 移动端底栏：完整呈现主循环的六个高频节点，其余能力进入「更多」。 */
export const MOBILE_TABS: NavItem[] = [
  { ...WORKSPACE_PRIMARY, short: '对话' },
  { ...findItem('profile'), short: '画像' },
  { ...findItem('report'), short: '报告' },
  { ...findItem('directions'), short: '方向' },
  { ...findItem('home'), short: '今日' },
  { ...findItem('plan'), short: '计划' },
]

function findItem(key: string): NavItem {
  return WORKSPACE_ITEMS.find((i) => i.key === key)!
}

interface RouteLike {
  path: string
  query: Record<string, unknown>
}

function queryMatches(item: NavItem, route: RouteLike): boolean {
  if (!item.query) return true
  return Object.entries(item.query).every(([k, v]) => route.query[k] === v)
}

/**
 * 同一路径下有 query 变体时（如 /review 与 /review?view=achievements），
 * 无 query 的那一项不能把变体的地址也点亮。
 */
export function isNavActive(item: NavItem, route: RouteLike): boolean {
  if (!item.paths.includes(route.path)) return false
  if (item.query) return queryMatches(item, route)
  const variant = WORKSPACE_ITEMS.find((i) => i.query && i.paths.includes(route.path))
  return variant ? !queryMatches(variant, route) : true
}

/** 当前路由所属分组，用于侧栏展开与顶栏面包屑。 */
export function activeGroup(route: RouteLike): NavGroup | undefined {
  return WORKSPACE_GROUPS.find((g) => g.items.some((i) => isNavActive(i, route)))
}

/** 当前路由对应的导航项。 */
export function activeItem(route: RouteLike): NavItem | undefined {
  return WORKSPACE_ITEMS.find((i) => isNavActive(i, route))
}

/** 面包屑与兜底页共用的「地址 → 名称」查询，避免各处再写一份硬编码映射。 */
export function labelForPath(path: string, query: Record<string, unknown> = {}): string | undefined {
  return activeItem({ path, query })?.label ?? INTERNAL_PAGE_TITLES[path]
}
