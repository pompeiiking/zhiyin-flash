import { createRouter, createWebHashHistory } from 'vue-router'
import { demo, toast } from './store'
import { routeEnabled } from './lib/features'
import { auth } from './lib/auth'
import {backendRequest} from './api/backend-client'
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
    { path:'/login',redirect:'/?signin=1' },
    { path:'/developer',component:()=>import('./views/DeveloperView.vue'),meta:{title:'开发者管理'} },
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
      meta: { title: '今日行动', step: 'today' },
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
      meta: { title: '你的报告', step: 'report' },
    },
    {
      path: '/plan',
      name: 'plan',
      component: () => import('./views/RoadmapView.vue'),
      meta: { title: '阶段计划', step: 'today' },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('./views/ReflectionView.vue'),
      meta: { title: '复盘与记录', step: 'review' },
    },
    { path: '/directions', name: 'directions', component: () => import('./views/DirectionsView.vue'), meta: { title: '方向方案' } },
    { path: '/academic', redirect: '/grades' },
    { path: '/grades', name: 'grades', component: () => import('./views/GradesView.vue'), meta: { title: '我的成绩', step: 'know' } },
    { path: '/schedule', name: 'schedule', component: () => import('./views/ScheduleView.vue'), meta: { title: '日历与课表' } },
    { path: '/notes', name: 'notes', component: () => import('./views/NotesView.vue'), meta: { title: '待办与目标' } },
    { path: '/intel', name: 'intel', component: () => import('./views/IntelView.vue'), meta: { title: '职业探索' } },
    { path: '/tools', name: 'tools', component: () => import('./views/ToolsView.vue'), meta: { title: '应用工具' } },
    ...['settings','reminders','guide','achievements'].map(name => ({path:'/' + name,name,component:() => import('./views/SystemView.vue'),meta:{title:({settings:'账号设置',reminders:'提醒',guide:'使用指南',gallery:'通用组件与状态',login:'登录',achievements:'完成记录'} as Record<string,string>)[name]}})),
    { path: '/notfound', name: 'notfound', component: () => import('./views/NotFoundView.vue'), meta: { title: '异常页' } },
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

router.beforeEach(async (to) => {
  if (to.path === '/review' && to.query.view === 'achievements') return '/achievements'
  if (to.path === '/report' && to.query.focus === 'choose') return '/directions'
  if (to.meta.public) return true
  if (!demo.state.authed && !await auth.restore()) return {path:'/',query:{signin:'1',redirect:to.fullPath}}
  if (!routeEnabled(to.path)) { toast('此功能当前未开放。'); return '/chat' }
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

router.afterEach((to) => {
  const event:Record<string,string>={'/report':'diagnosis_view','/directions':'decision_compare','/profile':'collect_gap_show'}
  if(demo.state.authed && event[to.path])void backendRequest('track',{body:{event:event[to.path],payload:{path:to.path},client_event_id:crypto.randomUUID()}}).catch(()=>{})

  routeLoadError.value = false
  try {
    sessionStorage.removeItem(RELOAD_KEY)
  } catch {
    /* 同上 */
  }
})
