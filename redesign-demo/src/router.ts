import { createRouter, createWebHashHistory } from 'vue-router'
import { demo } from './store'
import { backendDemo } from './lib/backend-demo'
import type { Grade } from './data/types'
import { ref } from 'vue'
import { sessionCacheAvailable } from './lib/session-cache'
export const routeLoadError = ref(false)
export function retryRoute() { try { sessionStorage.removeItem('zhiyin-demo-chunk-reload') } catch { /* Explicit retry still works when storage is unavailable. */ } window.location.reload() }

/**
 * 路由承担"层级"，不承担"动线"。
 *
 * 用 hash 模式：演示工程要能双击 index.html 或丢到任意静态托管上就跑，
 * 不能要求服务器配 rewrite。
 *
 * 鉴权口径与产品一致：门户永远公开；其余页面要登录，未登录时把人送回门户
 * 并把登录浮层掀起来 —— 不把人丢到一个没有上下文的"登录页"上。
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      alias: '/portal',
      name: 'portal',
      component: () => import('./views/PortalView.vue'),
      meta: { public: true, title: '门户' },
    },
    {
      path: '/home',
      name: 'home',
      component: () => import('./views/TodayView.vue'),
      meta: { title: '行动计划', step: 'today' },
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('./views/ConversationView.vue'),
      meta: { title: '对话', step: 'know' },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('./views/StudentView.vue'),
      meta: { title: '个人画像', step: 'know' },
    },
    {
      path: '/report',
      name: 'report',
      component: () => import('./views/AssessmentView.vue'),
      meta: { title: '诊断报告', step: 'report' },
    },
    {
      path: '/plan',
      name: 'plan',
      component: () => import('./views/RoadmapView.vue'),
      meta: { title: '行动计划', step: 'today' },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('./views/ReflectionView.vue'),
      meta: { title: '复盘与记录', step: 'review' },
    },
    { path: '/directions', name: 'directions', component: () => import('./views/AssessmentView.vue'), meta: { title: '方向方案' } },
    { path: '/academic', name: 'academic', component: () => import('./views/AcademicView.vue'), meta: { title: '学籍与资料' } },
    { path: '/schedule', name: 'schedule', component: () => import('./views/ScheduleView.vue'), meta: { title: '日历与课表' } },
    { path: '/notes', name: 'notes', component: () => import('./views/NotesView.vue'), meta: { title: '待办与目标' } },
    { path: '/intel', name: 'intel', component: () => import('./views/IntelView.vue'), meta: { title: '岗位资讯' } },
    { path: '/tools', name: 'tools', component: () => import('./views/ToolsView.vue'), meta: { title: '应用工具' } },
    ...['settings','reminders','guide','gallery','login','achievements'].map(name => ({path:'/' + name,name,component:() => import('./views/SystemView.vue'),meta:{title:({settings:'账号设置',reminders:'提醒',guide:'使用指南',gallery:'通用组件与状态',login:'登录',achievements:'成长记录'} as Record<string,string>)[name]}})),
    { path: '/notfound', name: 'notfound', component: () => import('./views/NotFoundView.vue'), meta: { title: '异常页' } },
    {
      path: '/path',
      name: 'path',
      component: () => import('./views/PathView.vue'),
      meta: { title: '大一到大四', step: 'choose' },
    },
    {
      path: '/spec',
      name: 'spec',
      component: () => import('./views/SpecView.vue'),
      meta: { title: '设计规范' },
    },
    /*
     * 兜底：**必须放最后**。没有它时，匹配不到的地址会让 <RouterView> 什么都不渲染 ——
     * 外壳在、中间全空、控制台也不报错，用户看到的就是"页面坏了"。
     *
     * 【2026-10-14 · wave5】**故意不标 `public`**（原来标了）。
     * `meta.public` 在 App.vue 里就是 `bare`，标上它等于把 404 分到门户/规范那条
     * **裸布局**分支 —— 全站 16 条路由里只有它没有侧栏与顶栏，也正是 vs1 报告 G-06。
     * 去掉之后 404 走 `.app__content` 那一支，与另外 15 条路由是同一段壳层代码。
     * 本站非公开路由对未登录访问本来就会静默落到演示账号（见下面 beforeEach 的注释），
     * 所以"坏地址也能直接打开"这条能力一点没少。
     */
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./views/NotFoundView.vue'),
      meta: { title: '地址不存在' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.path === '/report' && to.query.focus === 'choose') {
    const query = { ...to.query }
    delete query.focus
    return { path: '/directions', query, replace: true }
  }
  /*
   * 演示直达：地址里带 ?as=<账号> 就直接落到已登录状态。
   * 用途有两个：给评审发一条"打开就是这一屏"的链接；给截图脚本用（不用先点登录）。
   * 真实产品里没有这个口子 —— 这是演示工程。
   */
  const as = to.query.as
  if (typeof as === 'string' && as && !demo.state.authed) {
    demo.signIn(as, true)
  }

  if(to.query.data==='service'||to.query.data==='demo') backendDemo.setDataMode(to.query.data)

  // 直达链接：?grade=freshman 直接落到某个年级的使用场景
  const grade = to.query.grade
  if (
    typeof grade === 'string' &&
    ['freshman', 'sophomore', 'junior', 'senior'].includes(grade)
  ) {
    demo.setGrade(grade as Grade, true)
  }

  // 直达链接：?dir=d1 预置"已选主攻方向"的状态
  const dir = to.query.dir
  if (typeof dir === 'string' && dir && !demo.state.selectedDirectionId) {
    demo.preselectDirection(dir)
  }

  if (to.meta.public) return true
  if (!demo.state.authed) {
    /*
     * 未登录直接打开内页（刷新、新标签页、粘贴 URL）时**静默落到演示账号**，
     * 不再弹回门户：演示里链接就是主要入口，一个"请先登录"的白墙等于链接坏了。
     * 门户上的登录 / 退出流程照旧保留 —— 想演示换账号，点「退出登录」即可。
     */
    demo.signIn('mid', true)
  }
  return true
})

/**
 * 懒加载的路由组件拉取失败 → 自动整页重载一次。
 *
 * 症状很典型：页面先闪一下正常界面，然后变白 —— 壳mount上了，但某个
 * `() => import('./views/XxxView.vue')` 拉不到（dev 下文件正在被写时 Vite 会返回 500），
 * vue-router 拿不到组件，`<RouterView>` 就渲染成空的。
 *
 * 重载一次通常就好了（文件写完就正常）。用 sessionStorage 记一次，
 * 避免"一直坏、一直重载"的死循环；下一次导航成功就把这个标记清掉，
 * 这样以后再遇到偶发失败仍然能自愈。
 */
const RELOAD_KEY = 'zhiyin-demo-chunk-reload'

router.onError((_error, _to) => {
  if (!sessionCacheAvailable.value) { routeLoadError.value = true; return }
  try {
    if (sessionStorage.getItem(RELOAD_KEY)) { routeLoadError.value = true; return }
    sessionStorage.setItem(RELOAD_KEY, '1')
  } catch {
    // 存储不可用时不敢贸然重载，直接返回，交给 main.ts 那块提示兜底
    routeLoadError.value = true
    return
  }
  window.location.reload()
})

router.afterEach(() => {
  routeLoadError.value = false
  try {
    sessionStorage.removeItem(RELOAD_KEY)
  } catch {
    /* 同上 */
  }
})
