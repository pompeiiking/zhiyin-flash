<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { backendDemo } from '../lib/backend-demo'
import { STUDENT } from '../data/student'
import GradeSwitch from './GradeSwitch.vue'
import { skin, type Accent, type StyleId, type ThemeMode } from '../lib/theme'
import UiIcon from './UiIcon.vue'
import InfoSheet from './InfoSheet.vue'
import { navigation } from '../lib/layout'
import { activeGroup, labelForPath, PORTAL_LINK } from '../lib/workspace-nav'

/**
 * 工作区顶栏。
 *
 * **按频次分层**（PLAN §2.4 / §3.5）：
 * - 高频留在顶栏：搜索、提醒（带未读徽标）；
 * - 低频收进账号菜单：外观（主题 / 主色 / 风格）、账号身份、退出；
 * - 演示开关不再混进账号菜单 —— 拆出独立的「工作空间设置」，由演示标识进入。
 *
 * 原来这里还有一颗 `皮肤` 按钮和一条"演示数据 / 数据设置"带：
 * 390px 上顶栏一次挤着 品牌 + 搜索 40×40 + 皮肤 38×40 + 提醒 40×40 + 账号 34×34，
 * 带子上再挂一颗 56×40 的按钮，**没有一个到 44px**。现在顶栏剩下的每个控件都 ≥44px。
 */
const emit = defineEmits<{ openPalette: []; expandSidebar: []; openAccount: []; openMobileMenu: [] }>()
const router = useRouter()
const route = useRoute()
/**
 * 与 App/WorkspaceNav 共用一个响应式布局来源，切换宽度时同步更新。
 */
const desktop = computed(() => navigation.mode.value === 'desktop' && !navigation.compact.value)
const groupLabel = computed(() => activeGroup({ path: route.path, query: route.query })?.label ?? labelForPath(route.path, route.query) ?? '学生空间')
/**
 * 搜索键帽按平台给，不是照着样张抄一个按不出来的键。
 *
 * c2 靶子的顶栏写的是 `⌘K`（样张是 Mac 截图）。本工程是 Windows 优先的演示件，
 * 而 `CommandMenu.vue:30` 同时绑了 `metaKey` 与 `ctrlKey` —— 所以键帽写 `Ctrl K`
 * 才对得上这台机器上真正能按出来的那一个键。Mac 上仍然是 `⌘K`。
 */
const modKey = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent) ? '⌘K' : 'Ctrl K'
const accountOpen = ref(false)
const demoOpen = ref(false)
const expandButton = ref<HTMLButtonElement | null>(null)
/** 打开「账号」抽屉：顶栏账号按钮、桌面侧栏人名行、折叠态顶栏**三处都走这一个入口**。 */
function openAccount() { demoOpen.value = false; accountOpen.value = true }
/** 打开「工作空间设置」：账号抽屉里的那一行与顶栏的演示标识都走这里。 */
function openDemo() { accountOpen.value = false; demoOpen.value = true }
defineExpose({
  showAccount: openAccount,
  showDemo: openDemo,
  focusExpand() { expandButton.value?.focus() },
})
const scenario = computed(() => demo.use.scenario.value)
const dataMode = computed(() => backendDemo.state.dataMode)
/**
 * 外观（PLAN §3.5：唯一入口 = 账号菜单 → 外观）。
 *
 * 三轴 18 种组合与 `lib/theme.ts` 的 `skin` 是同一个来源，只是**不再用浮层**：
 * 触发器原来在顶栏，浮层挂在 body 上；现在它在 `<dialog>` 里，
 * 而 dialog 在 top layer，浮层会被弹窗的遮罩压住、往下弹还会被外沿裁掉。
 * 所以外观直接在抽屉里展开（原生 `details`，键盘与读屏免费拿到）。
 * `SkinSwitcher.vue` 保留原样（它仍是三轴皮肤浮层的实现），只是不再有顶栏触发点。
 */
const themeOptions: { id: ThemeMode; label: string }[] = [
  { id: 'light', label: '浅色' },
  { id: 'dark', label: '深色' },
  { id: 'system', label: '跟随系统' },
]
const accentOptions: { id: Accent; label: string; hint: string }[] = [
  { id: 'blue', label: '校徽蓝', hint: '蓝做主色，红只作提醒' },
  { id: 'red', label: '官网红', hint: '校色红做主色，蓝退为信息色' },
]
const styleOptions: { id: StyleId; label: string; hint: string }[] = [
  { id: 'plain', label: '极简', hint: '小圆角、无阴影、1px 描边' },
  { id: 'soft', label: '柔和', hint: '大圆角、轻影、更松的内距' },
  { id: 'dense', label: '紧凑', hint: '更小圆角与内距，一屏多看几条' },
]
const appearanceSummary = computed(() => {
  const t = skin.state.theme === 'system' ? '跟随系统' : skin.state.theme === 'dark' ? '深色' : '浅色'
  return `${t} · ${skin.state.accent === 'red' ? '河大红' : '河大蓝'} · ${styleOptions.find((o) => o.id === skin.state.style)?.label ?? '极简'}`
})

function setDataSource(event: Event) {
  const mode = (event.target as HTMLSelectElement).value as 'demo' | 'service'
  backendDemo.setDataMode(mode)
  void router.replace({ path: route.path, query: { ...route.query, data: mode } })
}
function signOut() {
  accountOpen.value = false
  demo.signOut()
  router.push('/')
}
/**
 * 错误状态预览：对话页读 `?demo-error=1`，本轮必然失败并可重试。
 * 原来那颗调试按钮长在对话页头（和"咨询成果""个人画像"并排），
 * 现在挪进这里 —— 调试开关属于工作空间设置，不属于学生页面的首要行动位。
 * 这里只负责写 query 并跳到对话页，不再往别的文件里塞状态。
 */
function openErrorDemo() {
  demoOpen.value = false
  const query = { ...route.query, 'demo-error': '1' }
  void router.push({ path: '/chat', query })
}
function clearErrorDemo() {
  if (route.query['demo-error'] === undefined) return
  const query = { ...route.query }
  delete query['demo-error']
  void router.replace({ path: route.path, query })
}
</script>
<template>
  <header class="ws-topbar">
    <div v-if="desktop" class="desk-location">
      <button v-if="navigation.sidebarCollapsed.value" ref="expandButton" class="ws-icon-button" aria-label="展开侧栏" title="展开侧栏" aria-controls="student-desktop-sidebar" aria-expanded="false" @click="emit('expandSidebar')"><UiIcon name="sidebar" /></button>
      <span>学生空间</span><span aria-hidden="true">/</span><strong>{{ groupLabel }}</strong>
    </div>
    <button v-else class="ws-icon-button c2-mobile-menu" aria-label="打开导航" @click="emit('openMobileMenu')"><UiIcon name="menu" :size="20" /></button>
    <!--
      搜索：c2 靶子的顶栏第一件东西就是这个输入框（左放大镜 + 占位文案 + 键帽）。
      它做成 **button** 而不是 input —— 因为它不自己收字：点一下打开的是**已有的命令面板**
      （`CommandMenu.vue`，与任何位置按 ⌘K / Ctrl+K 走的是同一个 `show()`），
      这里只复用顶栏本来就有的 `openPalette` 出口，不新开第二条搜索通路。
      做成装饰 input 是这工程反复犯过的病（点上去没反应），所以宁可把它写成"能按的盒子"。
      占位文案没有照抄靶子的「搜索对话、画像与资讯」：面板搜的是**页面与功能**，不搜对话正文，
      写一句做不到的承诺就是同一个病的另一种形态。要改回靶子文案只需改这一行的文字。
    -->
    <button type="button" class="hf-search" :aria-label="'搜索与跳转（' + modKey + '）'" :title="'搜索与跳转（' + modKey + '）'" aria-keyshortcuts="Control+K Meta+K" @click="emit('openPalette')">
      <UiIcon name="search" :size="16" />
      <span class="hf-search__ph">搜索页面与功能</span>
      <kbd class="hf-search__kbd">{{ modKey }}</kbd>
    </button>
    <div class="ws-topbar__tools">
      <!-- 搜索不再另留一颗 44×44 图标按钮：顶栏只留**一个**搜索入口（左边那个盒子），
           两颗并存就是"同一个功能两个入口"，正是这个壳层一直在收敛的东西。 -->
      <button class="ws-icon-button ws-inbox-trigger" :aria-label="'提醒，' + demo.state.noticeQueue.length + ' 条待处理'" @click="router.push('/reminders')"><UiIcon name="bell" :size="18" /><span v-if="demo.state.noticeQueue.length">{{ demo.state.noticeQueue.length }}</span></button>
      <!-- 演示标识：壳层的一行小字，点击进「工作空间设置」。它不占行、不与主行动竞争 -->
      <button class="ws-account" aria-label="账号菜单" @click="openAccount">
        <span class="ws-account__avatar" aria-hidden="true">{{ demo.state.account === 'fresh' ? '新' : STUDENT.name.slice(0, 1) }}</span>
        <span class="ws-account__label hf-account__label">{{ demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</span>
        <UiIcon class="ws-account__chevron" name="chevron" :size="15" />
      </button>
    </div>
  </header>

  <nav class="c2-appearance-bar" aria-label="工作空间外观">
    <button class="c2-directory-button" @click="emit('openPalette')"><UiIcon name="apps" :size="14" />全部页面</button>
    <div class="c2-appearance-axis"><span>主色</span><button v-for="o in accentOptions" :key="o.id" :aria-pressed="skin.state.accent === o.id" @click="skin.setAccent(o.id)">{{ o.label }}</button></div>
    <div class="c2-appearance-axis"><span>主题</span><button v-for="o in themeOptions" :key="o.id" :aria-pressed="skin.state.theme === o.id" @click="skin.setTheme(o.id)">{{ o.label }}</button></div>
    <div class="c2-appearance-axis"><span>密度</span><button :aria-pressed="skin.state.style !== 'dense'" @click="skin.setStyle('plain')">常规</button><button :aria-pressed="skin.state.style === 'dense'" @click="skin.setStyle('dense')">紧凑</button></div>
  <span class="c2-appearance-reading">{{ skin.state.accent === 'blue' ? '校徽蓝' : '官网红' }} · {{ themeOptions.find(o=>o.id===skin.state.theme)?.label }} · {{ skin.state.style === 'dense' ? '紧凑' : '常规' }}</span></nav>

  <!-- 账号抽屉：只管账号。身份、演示标识说明、退出。 -->
  <InfoSheet shape="sheet" :open="accountOpen" title="账号" @close="accountOpen = false">
    <p class="ws-person">{{ demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</p>
    <p class="ws-muted">{{ demo.state.account === 'fresh' ? '个人资料待完善' : scenario.grade + ' · ' + STUDENT.major + ' · ' + STUDENT.school }}</p>

    <!-- PLAN §3.5：外观的唯一入口 = 账号菜单 → 外观（顶栏那颗「皮肤」按钮已移除）。
         展开后是三轴 18 组合，与 `lib/theme.ts` 同一套令牌；重置也在里面。 -->
    <details class="ws-appearance">
      <summary class="ws-appearance__summary"><span>外观<small>主题 · 主色 · 风格</small></span><span class="ws-appearance__now">{{ appearanceSummary }}<UiIcon name="chevron" :size="16" /></span></summary>
      <div class="ws-appearance__body">
        <p class="ws-appearance__title">主题</p>
        <div class="ws-appearance__seg">
          <button v-for="o in themeOptions" :key="o.id" :class="{ 'is-on': skin.state.theme === o.id }" :aria-pressed="skin.state.theme === o.id" @click="skin.setTheme(o.id)">{{ o.label }}</button>
        </div>
        <p class="ws-appearance__title">主色</p>
        <div class="ws-appearance__seg">
          <button v-for="o in accentOptions" :key="o.id" :class="{ 'is-on': skin.state.accent === o.id }" :aria-pressed="skin.state.accent === o.id" @click="skin.setAccent(o.id)">{{ o.label }}</button>
        </div>
        <p class="ws-appearance__hint">{{ accentOptions.find((o) => o.id === skin.state.accent)?.hint }}</p>
        <p class="ws-appearance__title">风格</p>
        <div class="ws-appearance__seg">
          <button v-for="o in styleOptions" :key="o.id" :class="{ 'is-on': skin.state.style === o.id }" :aria-pressed="skin.state.style === o.id" @click="skin.setStyle(o.id)">{{ o.label }}</button>
        </div>
        <p class="ws-appearance__hint">{{ styleOptions.find((o) => o.id === skin.state.style)?.hint }}</p>
        <button class="btn btn--sm btn--block" @click="skin.reset()">恢复默认外观</button>
        <p class="ws-demo-note">选择记在本地，下次打开还是这套；改的只是令牌，页面结构不动。</p>
      </div>
    </details>
    <div class="ws-account-list"><RouterLink class="ws-account-row" to="/settings" @click="accountOpen=false"><span><strong>账号设置</strong><small>资料授权、提醒、外观与导出</small></span><UiIcon name="arrow" :size="16"/></RouterLink>
      <button class="ws-account-row" @click="openDemo()">
        <span><strong>工作空间设置</strong><small>资料来源、年级、导航布局、重置</small></span>
        <UiIcon name="chevron" :size="16" />
      </button>
      <RouterLink class="ws-account-row" :to="PORTAL_LINK.to" @click="accountOpen = false">
        <span><strong>{{ PORTAL_LINK.label }}</strong><small>{{ PORTAL_LINK.hint }}</small></span>
        <UiIcon name="arrow" :size="16" />
      </RouterLink>
    </div>
    <div class="ws-stack"><button class="btn" @click="signOut">退出登录</button></div>
  </InfoSheet>

  <!-- 工作空间设置：独立入口，收纳所有演示开关。账号抽屉里不再有这些。 -->
  <InfoSheet shape="sheet" :open="demoOpen" title="工作空间设置" @close="demoOpen = false">
    <p class="ws-demo-note">设置当前资料来源、年级与导航布局。修改后会保留已有操作记录。</p>
    <label class="ws-field">数据来源
      <select aria-label="数据来源" :value="dataMode" @change="setDataSource">
        <option value="demo">本地资料</option>
        <option value="service">在线资料（需后端）</option>
      </select>
    </label>
    <p class="ws-demo-note">本地资料保存在当前浏览器会话；在线资料按服务返回结果展示。切换来源后请重新读取结果。</p>
    <div class="desk-account-grade"><p class="ws-muted">当前年级</p><GradeSwitch /></div>
    <label class="ws-field">导航布局
      <select aria-label="导航布局" :value="desktop ? 'desktop' : 'mobile'" @change="navigation.set(($event.target as HTMLSelectElement).value as 'desktop' | 'mobile')">
        <option value="desktop" :disabled="navigation.compact.value">桌面侧栏</option>
        <option value="mobile">移动导航</option>
      </select>
    </label>
    <div class="ws-stack">
      <button class="btn" @click="openErrorDemo">错误状态预览 · 去对话页触发一次失败</button>
      <button class="btn" :disabled="route.query['demo-error'] === undefined" @click="clearErrorDemo">关掉错误状态预览</button>
      <button class="btn" @click="demo.resetDemo(); demoOpen = false">重置工作空间</button>
      <button class="btn" @click="demo.resetGuide(); demoOpen = false">恢复操作引导</button>
    </div>
    <p class="ws-demo-note">「错误状态预览」打开后，对话页下一次回答会走真实失败路径（可重试、内容不丢）；关掉它才会恢复正常的预设回答。</p>
    <p class="ws-demo-note">外观（主题 / 主色 / 风格）在账号菜单 → 外观里；这里管理工作空间。</p>
  </InfoSheet>
</template>

<style scoped>
/*
  顶栏搜索：把 c2 靶子 `.search` 的**长相**搬过来，行为接的是本工程已有的命令面板。
  为什么这些规则必须写在这里（scoped）而不是 workspace.css：
    · 顶栏的尺寸令牌（`.ws-topbar` 的高度、内距）是全局的，本组件只在它里面放东西；
    · 类名刻意用 `hf-` 前缀：`scripts/check-classes.mjs` 抓的是"同名类同时出现在全局与
      scoped"——`.search` / `.iconbtn` / `.topbar__*` 这些靶子的类名一个都不能用，
      否则全局那条的版面属性会从 scoped 的缝里漏进来（这个工程栽过两次）。
  与靶子的两处**有意差异**（都在回报里点名）：
    1. 高度 44px 而不是靶子的 34px —— 触控目标 ≥44×44 是本项目的硬约束（CRAFT-BRIEF / WCAG 2.5.8），
       顶栏搜索是主要动作，不按样张的 34px 走。
    2. ≤767px 收到 44×44 的图标药丸（占位文案与键帽隐藏）：390px 上壳层要同时放
       品牌(58) + 演示标识(44) + 提醒(44) + 账号(69/105)，留给文本框的只有 27px，
       与其塞一个截成"搜"字的输入框，不如让它退回图标药丸（出口、命中区都不变）。
*/
.hf-search {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 400px;
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 44px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  color: var(--c-text-3);
  font-size: var(--fs-14);
  text-align: left;
  transition: background-color var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out);
}
.hf-search:hover { background: var(--c-surface-2); border-color: var(--c-border-strong); }
/* 只把边压成主色：焦点环的形状（2px + 2px 偏移）是全站唯一一种，写在 base.css 的
   `:focus-visible` 里，组件不许改它的形状（改一处就是两套焦点语言）。 */
.hf-search:focus-visible { border-color: var(--c-primary); }
.hf-search__ph {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.hf-search__kbd {
  flex: none;
  padding: 2px 6px;
  border-radius: var(--r-sm);
  background: var(--c-surface-3);
  border: var(--bw-1) solid var(--c-border);
  color: var(--c-text-3);
  font-family: var(--font-sans);
  font-size: var(--fs-12);
  letter-spacing: 0.02em;
}
@media (max-width: 767px) {
  /* 窄屏：只留放大镜。命中的还是同一个面板（同一个 @click），只是不再装作能收字 */
  .hf-search { flex: none; width: 44px; max-width: none; padding: 0; justify-content: center; }
  .hf-search__ph, .hf-search__kbd { display: none; }
  /* 账号标签让位给搜索入口：头像 + chevron 仍然说明"这是我"，aria-label 不变 */
  .hf-account__label { display: none; }
}
</style>
