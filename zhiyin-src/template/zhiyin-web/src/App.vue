<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppTopBar from './components/WorkspaceHeader.vue'
import WorkspaceNav from './components/WorkspaceNav.vue'
import CommandPalette from './components/CommandMenu.vue'
import AuthLayer from './components/AuthLayer.vue'
import FloatingReminders from './components/FloatingReminders.vue'
import InterventionModal from './components/CareSheet.vue'
import { demo } from './store'
import { skin } from './lib/theme'
import { INTERVENTION } from './data/student'
import DesktopSidebar from './components/DesktopSidebar.vue'
import { useNavigationLayout } from './lib/layout'
import { loadShell, systemData, refreshNotifications } from './lib/system-data'
import { auth } from './lib/auth'
import { toast } from './store'
import { routeLoadError, retryRoute, routeLoading } from './router'
import { sessionCacheAvailable } from './lib/session-cache'

/**
 * 应用壳。
 *
 * 结构：品牌与工具 → 当前工作空间 → 底部浮动书签。
 * 门户是独立的公开布局；内页保留五个可发现的功能入口。
 *
 * 演示状态**不再是每页一行**：那句话原来是一条 `demo-data-label` 带子
 * （"演示数据 · 虚构人物与本地预设结果 / 数据设置"），渲染在每个页面的首屏，
 * 白占一行还挂一颗按钮。现在它是顶栏上的一枚小标识（`.ws-demo-badge`），
 * 点开进「演示设置」—— 壳层的事留在壳层，页面首屏交还给内容。
 */
const route = useRoute()
const router = useRouter()
const palette = ref<InstanceType<typeof CommandPalette> | null>(null)
const workspaceHeader = ref<InstanceType<typeof AppTopBar> | null>(null)
const sidebar = ref<InstanceType<typeof DesktopSidebar> | null>(null)
const mobileNav = ref<InstanceType<typeof WorkspaceNav> | null>(null)

const bare = computed(() => route.meta.public === true)

/* 页面自己已经给出错误横幅时，壳层不再重复一条同样的提示（同一句话出现两遍）。 */
const contentRef = ref<HTMLElement | null>(null)
const pageErrorShown = ref(false)
let pageErrorObserver: MutationObserver | undefined
function refreshPageError() {
  pageErrorShown.value = !!contentRef.value?.querySelector('.ws-page [role="alert"], .ws-page .ws-field-error')
}
const layout = useNavigationLayout()
/**
 * C2 外壳与导航共用 layout 的响应式宽度：768 以下底栏，
 * 768–1023 图标轨，1024 起完整侧栏。用户仍可主动选择移动布局。
 */
const desktop = computed(() => layout.mode.value === 'desktop' && !layout.compact.value)
async function collapseSidebar() {
  layout.setSidebarCollapsed(true)
  await nextTick()
  workspaceHeader.value?.focusExpand()
}
async function expandSidebar() {
  layout.setSidebarCollapsed(false)
  await nextTick()
  sidebar.value?.focusCollapse()
}
async function newChat() {
 try { await router.push({ path:'/chat', query:{ new:String(Date.now()) } }) } catch(e) { toast((e as Error).message) }
}

/**
 * 顶部进度条的宽度：**跟内容列对齐**，不是一个全页固定值。
 * 原来写死 920px 居中，而对话页中栏只有 760px（且当时左右栏 232/272 不对称，
 * 中栏还偏右 28px），于是进度条两边凸出来、左右还不一样多。
 */
const progressMax = computed(() => (route.name === 'chat' ? '760px' : '920px'))
const authOpen = computed(() => route.query.signin === '1' && !demo.state.authed)

function closeAuth() {
  if(demo.state.authed){void router.replace(typeof route.query.redirect==='string' && route.query.redirect.startsWith('/') && !route.query.redirect.startsWith('//') ? route.query.redirect : '/chat');return}
  if (route.query.signin) {
    const q = { ...route.query }
    delete q.signin
    router.replace({ path: route.path, query: q })
  }
}

watch(
  () => demo.state.authed,
  (v) => {
    if (!v && !route.meta.public) router.replace({ path: '/', query: { signin: '1' } })
    /*
     * 登录成功、人还在门户上 —— 直接进第一个界面（对话）。
     * 只认"门户 + 带 signin"这一种情况：点「稍后再说」不会把 authed 置真，不会被卷进来，
     * 而门户本身要留着可访问（它是宣传入口，用户可能只是想回来再看一眼）。
     */
    if(v) { void loadShell(); if(route.path === '/' && route.query.signin) router.replace(typeof route.query.redirect==='string' && route.query.redirect.startsWith('/') && !route.query.redirect.startsWith('//') ? route.query.redirect : '/chat') }
  },
)

onMounted(() => {
  document.documentElement.lang = 'zh-CN'
  skin.init()
  void auth.restore().then(ok => {if(ok)void loadShell()})
  void nextTick(() => {
    refreshPageError()
    if (!contentRef.value) return
    pageErrorObserver = new MutationObserver(() => refreshPageError())
    pageErrorObserver.observe(contentRef.value, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'role'] })
  })
})
watch(() => route.path, async () => {
  await nextTick()
  document.querySelector('.app__main')?.scrollTo(0, 0)
  refreshPageError()
  // SPA 路由切换不换文档：把焦点交给主内容，键盘与读屏用户不用从侧栏重新 Tab 一遍。
  if (!bare.value && !authOpen.value && !routeLoadError.value) document.getElementById('main-content')?.focus({ preventScroll: true })
})
const notificationTimer=setInterval(()=>{if(demo.state.authed && document.visibilityState==='visible')void refreshNotifications().catch(()=>{})},60000)
onUnmounted(()=>{clearInterval(notificationTimer);pageErrorObserver?.disconnect()})
</script>

<template>
  <div class="app" :data-route="route.path" :data-nav="layout.mode.value" :class="{ 'app--workspace': !bare, 'app--desktop': !bare && desktop, 'app--sidebar-collapsed': !bare && desktop && layout.sidebarCollapsed.value, 'app--chat': route.name === 'chat' }" :style="{ '--progress-max': progressMax }">
    <a v-if="!bare" class="skip-link" href="#main-content">跳到主要内容</a>
    <template v-if="bare && !routeLoadError">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" :key="route.path" />
        </Transition>
      </RouterView>
    </template>

    <template v-else>
      <DesktopSidebar v-if="desktop" v-show="!layout.sidebarCollapsed.value" ref="sidebar" @new-chat="newChat" @collapse="collapseSidebar" />
      <AppTopBar ref="workspaceHeader" @open-palette="palette?.show()" @expand-sidebar="expandSidebar" @open-mobile-menu="mobileNav?.show()" />
      <main id="main-content" class="app__main" tabindex="-1" :aria-busy="routeLoading">
        <p class="sr-only" role="status" aria-live="polite">{{ routeLoading ? '正在加载页面…' : '' }}</p>
        <!-- 氛围层：与门户同一套语言（一片很淡的品牌色光 + 颗粒），但强度低得多 -->
        <div class="app__atmos" aria-hidden="true" />

        <div class="app__content" ref="contentRef"><div v-if="systemData.error && !pageErrorShown" class="ws-field-error" role="alert">{{systemData.error}} <button class="ws-text-button" @click="loadShell">重试</button></div>
          <section v-if="routeLoadError" class="ws-page ws-route-error" role="alert"><h1>页面暂时没有加载成功</h1><p>{{ sessionCacheAvailable ? '本次演示记录和已保存的咨询草稿会在重新加载后恢复。' : '浏览器未能保存当前工作空间上下文，请先保留重要内容。' }}可以重新加载，或先查看其他页面。</p><div class="ws-inline-actions"><button class="btn btn--primary" @click="retryRoute">重新加载</button><RouterLink class="btn" to="/chat">去咨询对话</RouterLink></div></section>
          <RouterView v-else v-slot="{ Component }">
            <component :is="Component" :key="route.path" />
          </RouterView>
        </div>
      </main>
      <WorkspaceNav v-if="!desktop" ref="mobileNav" />
    </template>

    <CommandPalette ref="palette" />
    <AuthLayer v-if="authOpen" @close="closeAuth" />
    <!-- 提醒是登录后的产品功能，不出现在公开门户上 -->
    <FloatingReminders v-if="demo.state.authed && !bare" />
    <InterventionModal
      v-if="demo.state.interventionOpen"
      :host="INTERVENTION.host"
      :title="INTERVENTION.title"
      :body="INTERVENTION.body"
      :action="INTERVENTION.action"
      :secondary="INTERVENTION.secondary"
      :rules="INTERVENTION.rules"
      @close="demo.closeIntervention"
      @action="demo.planChatTask('先投 1 家半导体方向的工艺岗', 5); demo.closeIntervention()"
    />

    <!--
      toast 在**公共层**：以前它渲染在 `app--workspace` 分支里，
      于是 `bare`（门户）布局下整条反馈路径不存在 —— 门户上"登录成功"永远没有任何回应。
      审计 D6 把它记成硬缺陷。现在两种布局共用同一个节点，同一次操作在哪都看得见。
    -->
    <Transition name="toast">
      <div v-if="demo.state.toast" class="toast" role="status">
        {{ demo.state.toast }}
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.app {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.skip-link {
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: calc(var(--z-toast) + 1);
  padding: 10px 14px;
  border-radius: var(--r-md);
  background: var(--c-text);
  color: var(--c-surface);
  box-shadow: var(--e-2);
  transform: translateY(calc(-100% - 20px));
  transition: transform var(--dur-1) var(--ease-out);
}

.skip-link:focus-visible {
  color: var(--c-surface);
  outline: 2px solid var(--c-primary);
  outline-offset: 2px;
  transform: translateY(0);
}

.app__main {
  position: relative;
  flex: 1;
  min-width: 0;
  background: var(--c-bg);
}

/* 氛围层：一片很淡的光 + 一层颗粒。depth 到"底色有温度"为止 ——
   内页是干活的地方，氛围再重就会干扰读表和读列表。 */
.app__atmos {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: var(--app-glow),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
  background-position: center -180px, 0 0;
  background-repeat: no-repeat, repeat;
  background-size: 1200px 620px, 160px 160px;
}

/* 内容必须在氛围层之上：.app__atmos 是绝对定位元素，会盖住未定位的块级内容 */
.app__content {
  position: relative;
  z-index: 1;
}

.toast {
  position: fixed;
  left: 50%;
  bottom: var(--sp-6);
  transform: translateX(-50%);
  z-index: var(--z-toast);
  max-width: min(560px, calc(100vw - 48px));
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-md);
  background: var(--c-text);
  color: var(--c-surface);
  font-size: var(--fs-14);
  box-shadow: var(--e-3);
}

/* 路由入场：160ms ease-out，位移 6px（远小于一屏，属于"接得上"而不是"飞进来"）*/
.workspace-page-enter-active {
  transition: opacity 160ms var(--ease-out), transform 160ms var(--ease-out);
}
.workspace-page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-enter-active {
  transition:
    opacity 160ms var(--ease-out),
    transform 160ms var(--ease-out);
}

.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-leave-active {
  transition: opacity 80ms ease;
}

.page-leave-to {
  opacity: 0;
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--dur-2) var(--ease-out),
    transform var(--dur-2) var(--ease-out);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 8px);
}

/*
 * 换肤的过渡：**先禁过渡、再整页淡入** —— 不是给所有元素挂一条全局 transition。
 * 挂全局 transition 会让每个元素按自己的时长各自跑，像打翻的调色盘；
 * 而且会把之后每一次 hover 都拖成同样的慢速动画。
 * 具体禁用与淡入的规则写在 base.css（不受 scoped 影响，也不怕 keyframes 被改名）。
 */

/* 减少动效：保留淡入，去掉位移 */
@media (prefers-reduced-motion: reduce) {
  .skip-link { transition: none; }
  .workspace-page-enter-active { transition: none; }
  .workspace-page-enter-from { transform: none; }
  .page-enter-from {
    transform: none;
  }

  .toast-enter-from,
  .toast-leave-to {
    transform: translateX(-50%);
  }
}
</style>
