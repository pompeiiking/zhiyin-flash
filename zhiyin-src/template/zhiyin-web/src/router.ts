import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from './stores/session'

/**
 * 路由只承担"层级"：控制台是家，其余是按需打开的更深一层页面。
 * 注意 /portal 是独立入口，正常使用不会经过它。
 */
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'console', component: () => import('@/views/ConsoleView.vue') },
    { path: '/portal', name: 'portal', component: () => import('@/views/PortalView.vue') },
    // 登录不再是独立页面，而是任意页面上能掀起来的那一层浮窗；
    // 留着这条路径只为老链接还能用 —— 落到门户，浮层会自己打开。
    { path: '/login', redirect: { path: '/portal', query: { signin: '1' } } },
    { path: '/report', name: 'report', component: () => import('@/views/ReportView.vue') },
  ],
  scrollBehavior: () => ({ top: 0 }),
})


/*
 * 鉴权守卫：控制台与报告需要登录；门户公开。
 *
 * 没登录时不把人丢到一个"登录页"上，而是送回门户、顺手把登录浮层掀起来 ——
 * 门户本来就回答了"这是什么东西、凭什么信"，用户在那里登录是有上下文的。
 */
router.beforeEach((to) => {
  const hasToken = !!localStorage.getItem('zhiyin_token')
  const publicPaths = ['/portal']
  if (!hasToken && !publicPaths.includes(to.path)) {
    useSessionStore().openAuth()
    return { path: '/portal' }
  }
})
