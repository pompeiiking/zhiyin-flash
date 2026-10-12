import { createRouter, createWebHashHistory } from 'vue-router'
import { demo } from './store'
import type { Grade } from './data/types'

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
      meta: { public: true, title: '设计规范' },
    },
    /*
     * 兜底：**必须放最后**。没有它时，匹配不到的地址会让 <RouterView> 什么都不渲染 ——
     * 外壳在、中间全空、控制台也不报错，用户看到的就是"页面坏了"。
     * 标 public：一个坏地址不该再触发登录流程。
     */
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./views/NotFoundView.vue'),
      meta: { public: true, title: '地址不存在' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  /*
   * 演示直达：地址里带 ?as=<账号> 就直接落到已登录状态。
   * 用途有两个：给评审发一条"打开就是这一屏"的链接；给截图脚本用（不用先点登录）。
   * 真实产品里没有这个口子 —— 这是演示工程。
   */
  const as = to.query.as
  if (typeof as === 'string' && as && !demo.state.authed) {
    demo.signIn(as, true)
  }

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
  try {
    if (sessionStorage.getItem(RELOAD_KEY)) return
    sessionStorage.setItem(RELOAD_KEY, '1')
  } catch {
    // 存储不可用时不敢贸然重载，直接返回，交给 main.ts 那块提示兜底
    return
  }
  window.location.reload()
})

router.afterEach(() => {
  try {
    sessionStorage.removeItem(RELOAD_KEY)
  } catch {
    /* 同上 */
  }
})
