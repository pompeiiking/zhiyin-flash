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
 * - 演示开关不再混进账号菜单 —— 拆出独立的「演示设置」，由演示标识进入。
 *
 * 原来这里还有一颗 `皮肤` 按钮和一条"演示数据 / 数据设置"带：
 * 390px 上顶栏一次挤着 品牌 + 搜索 40×40 + 皮肤 38×40 + 提醒 40×40 + 账号 34×34，
 * 带子上再挂一颗 56×40 的按钮，**没有一个到 44px**。现在顶栏剩下的每个控件都 ≥44px。
 */
const emit = defineEmits<{ openPalette: []; expandSidebar: []; openAccount: [] }>()
const router = useRouter()
const route = useRoute()
/**
 * 桌面形态与 `lib/layout.ts` 的 compact（<1000px）不是同一个阈值：
 * 契约只允许 768 / 1120 两档（PLAN §2.7），所以这里按 1120 判断。
 */
const desktop = computed(() => navigation.mode.value === 'desktop' && window.innerWidth >= 1120)
const groupLabel = computed(() => activeGroup({ path: route.path, query: route.query })?.label ?? labelForPath(route.path, route.query) ?? '学生空间')
const accountOpen = ref(false)
const demoOpen = ref(false)
const expandButton = ref<HTMLButtonElement | null>(null)
/** 打开「账号」抽屉：顶栏账号按钮、桌面侧栏人名行、折叠态顶栏**三处都走这一个入口**。 */
function openAccount() { demoOpen.value = false; accountOpen.value = true }
/** 打开「演示设置」：账号抽屉里的那一行与顶栏的演示标识都走这里。 */
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
  { id: 'blue', label: '河大蓝', hint: '蓝做主色，红只作提醒' },
  { id: 'red', label: '河大红', hint: '校色红做主色，蓝退为信息色' },
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
 * 错误态演示：对话页读 `?demo-error=1`，本轮必然失败并可重试。
 * 原来那颗调试按钮长在对话页头（和"咨询成果""个人画像"并排），
 * 现在挪进这里 —— 调试开关属于演示设置，不属于学生页面的首要行动位。
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
    <RouterLink v-else class="ws-brand" to="/chat" aria-label="职引，回到对话"><span class="ws-brand__mark" /><strong>职引</strong></RouterLink>
    <div class="ws-topbar__tools">
      <button class="ws-icon-button" aria-label="搜索与跳转" title="搜索与跳转（Ctrl + K）" @click="emit('openPalette')"><UiIcon name="search" /></button>
      <button class="ws-icon-button ws-inbox-trigger" :aria-label="'提醒，' + demo.state.noticeQueue.length + ' 条待处理'" @click="demo.openNotice()"><UiIcon name="bell" :size="18" /><span v-if="demo.state.noticeQueue.length">{{ demo.state.noticeQueue.length }}</span></button>
      <!-- 演示标识：壳层的一行小字，点击进「演示设置」。它不占行、不与主行动竞争 -->
      <button class="ws-demo-badge" :class="{ 'ws-demo-badge--service': dataMode === 'service' }" :title="dataMode === 'demo' ? '演示数据 · 虚构人物与本地预设结果' : '服务数据 · 读取结果需后端支持'" :aria-label="'演示设置，当前' + (dataMode === 'demo' ? '演示数据' : '服务数据')" @click="demoOpen = true">
        <span aria-hidden="true" />{{ dataMode === 'demo' ? '演示数据' : '服务数据' }}
      </button>
      <button class="ws-account" aria-label="账号菜单" @click="openAccount">
        <span class="ws-account__avatar" aria-hidden="true">{{ demo.state.account === 'fresh' ? '新' : STUDENT.name.slice(0, 1) }}</span>
        <span class="ws-account__label">账号</span>
        <UiIcon class="ws-account__chevron" name="chevron" :size="15" />
      </button>
    </div>
  </header>

  <!-- 账号抽屉：只管账号。身份、演示标识说明、退出。 -->
  <InfoSheet :open="accountOpen" title="账号" @close="accountOpen = false">
    <p class="ws-person">{{ demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</p>
    <p class="ws-muted">{{ demo.state.account === 'fresh' ? '个人资料待完善' : scenario.grade + ' · ' + STUDENT.major + ' · ' + STUDENT.school }}</p>
    <p class="ws-demo-note">这是一份示例，用来让你先看清职引能做什么。</p>
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
    <div class="ws-account-list">
      <button class="ws-account-row" @click="openDemo()">
        <span><strong>演示设置</strong><small>数据来源、演示场景、导航布局、复位</small></span>
        <UiIcon name="chevron" :size="16" />
      </button>
      <RouterLink class="ws-account-row" :to="PORTAL_LINK.to" @click="accountOpen = false">
        <span><strong>{{ PORTAL_LINK.label }}</strong><small>{{ PORTAL_LINK.hint }}</small></span>
        <UiIcon name="arrow" :size="16" />
      </RouterLink>
    </div>
    <div class="ws-stack"><button class="btn" @click="signOut">退出登录</button></div>
  </InfoSheet>

  <!-- 演示设置：独立入口，收纳所有演示开关。账号抽屉里不再有这些。 -->
  <InfoSheet :open="demoOpen" title="演示设置" @close="demoOpen = false">
    <p class="ws-demo-note">下面这些开关只影响这台的演示数据与导航形态，不改变学生看到的功能。</p>
    <label class="ws-field">数据来源
      <select aria-label="数据来源" :value="dataMode" @change="setDataSource">
        <option value="demo">本地演示数据</option>
        <option value="service">服务数据（需后端）</option>
      </select>
    </label>
    <p class="ws-demo-note">本地演示使用虚构人物、岗位和预设分析，操作仅保存在当前浏览器会话。切换来源后请重新读取页面结果。</p>
    <div class="desk-account-grade"><p class="ws-muted">演示使用场景</p><GradeSwitch /></div>
    <label class="ws-field">导航布局
      <select aria-label="导航布局" :value="desktop ? 'desktop' : 'mobile'" @change="navigation.set(($event.target as HTMLSelectElement).value as 'desktop' | 'mobile')">
        <option value="desktop" :disabled="navigation.compact.value">桌面侧栏</option>
        <option value="mobile">移动导航</option>
      </select>
    </label>
    <div class="ws-stack">
      <button class="btn" @click="openErrorDemo">错误态演示 · 去对话页触发一次失败</button>
      <button class="btn" :disabled="route.query['demo-error'] === undefined" @click="clearErrorDemo">关掉错误态演示</button>
      <button class="btn" @click="demo.resetDemo(); demoOpen = false">复位演示数据</button>
      <button class="btn" @click="demo.resetGuide(); demoOpen = false">恢复操作引导</button>
    </div>
    <p class="ws-demo-note">「错误态演示」打开后，对话页下一次回答会走真实失败路径（可重试、内容不丢）；关掉它才会恢复正常的预设回答。</p>
    <p class="ws-demo-note">外观（主题 / 主色 / 风格）在账号菜单 → 外观里；这里只管演示状态。</p>
  </InfoSheet>
</template>
