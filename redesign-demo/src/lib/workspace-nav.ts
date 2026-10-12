export const WORKSPACE_GROUPS = [
  { label: '了解与选择', items: [
    { label: '个人画像', to: '/profile', icon: 'profile', paths: ['/profile', '/academic'], hint: '来源、缺口与学籍资料' },
    { label: '诊断报告', to: '/report', icon: 'report', paths: ['/report'], hint: '结论、依据与历史版本' },
    { label: '方向方案', to: '/directions', icon: 'directions', paths: ['/directions'], hint: '主攻、平行与保底选择' },
  ] },
  { label: '安排与推进', items: [
    { label: '行动计划', to: '/home', icon: 'action', paths: ['/home', '/plan'], hint: '今天这一件与阶段计划' },
    { label: '日历与课表', to: '/schedule', icon: 'calendar', paths: ['/schedule'], hint: '关键日期、课程与可用时间' },
    { label: '待办与目标', to: '/notes', icon: 'notes', paths: ['/notes'], hint: '自己写下的事与目标' },
  ] },
  { label: '资料与记录', items: [
    { label: '岗位资讯', to: '/intel', icon: 'compass', paths: ['/intel'], hint: '带来源的外部事实与职业匹配' },
    { label: '复盘与记录', to: '/review', icon: 'review', paths: ['/review'], hint: '发生过的事与完成记录' },
  ] },
]
export const WORKSPACE_ITEMS = [
  { label: '咨询对话', to: '/chat', icon: 'chat', paths: ['/chat'], hint: '从问题开始，接着上次聊' },
  ...WORKSPACE_GROUPS.flatMap(g => g.items),
]
export const WORKSPACE_TOOLS = [
  { label: '应用工具', to: '/tools', hint: '已发布的应用入口' },
  { label: '大一到大四', to: '/path', hint: '演示不同年级的场景' },
  { label: '设计规范', to: '/spec', hint: '配色、组件与排版' },
  { label: '产品门户', to: '/', hint: '职引如何帮助你' },
]
