<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import UiIcon from './UiIcon.vue'
import { navigation } from '../lib/layout'
import { activeGroup, labelForPath } from '../lib/workspace-nav'
import BrandMark from './BrandMark.vue'
import SkinPopover from './SkinPopover.vue'

/**
 * 工作区顶栏。
 *
 * **按频次分层**（PLAN §2.4 / §3.5）：
 * - 高频留在顶栏：搜索、提醒（带未读徽标）；
 * - 低频收进账号菜单：完整外观选项（主题 / 主色 / 风格）、账号身份、退出；
 * - 演示开关不再混进账号菜单 —— 拆出独立的「工作空间设置」，由演示标识进入。
 *
 * 原来这里还有一颗 `皮肤` 按钮和一条"演示数据 / 数据设置"带：
 * 390px 上顶栏一次挤着 品牌 + 搜索 40×40 + 皮肤 38×40 + 提醒 40×40 + 账号 34×34，
 * 带子上再挂一颗 56×40 的按钮，**没有一个到 44px**。现在顶栏剩下的每个控件都 ≥44px。
 */
const emit = defineEmits<{ openPalette: []; expandSidebar: []; openMobileMenu: [] }>()
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
const expandButton = ref<HTMLButtonElement | null>(null)
defineExpose({
  focusExpand() { expandButton.value?.focus() },
})
</script>
<template>
  <header class="ws-topbar">
    <div v-if="desktop" class="desk-location">
      <button v-if="navigation.sidebarCollapsed.value" ref="expandButton" class="ws-icon-button" aria-label="展开侧栏" title="展开侧栏" aria-controls="student-desktop-sidebar" aria-expanded="false" @click="emit('expandSidebar')"><UiIcon name="sidebar" /></button>
      <span>学生空间</span><span aria-hidden="true">/</span><strong>{{ groupLabel }}</strong>
    </div>
    <button v-else class="mobile-brand-button" aria-label="职引，打开导航" @click="emit('openMobileMenu')"><BrandMark /></button>
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
      <SkinPopover />
      <!-- 搜索不再另留一颗 44×44 图标按钮：顶栏只留**一个**搜索入口（左边那个盒子），
           两颗并存就是"同一个功能两个入口"，正是这个壳层一直在收敛的东西。 -->
    </div>
  </header>

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
  .ws-brand-switch i { display:none; }
  .ws-brand-switch span { display:inline; }
}
.mobile-brand-button { display:inline-flex; align-items:center; min-height:44px; padding:4px 6px 4px 2px; border-radius:10px; }
.mobile-brand-button:hover { background:var(--c-surface-2); }
.account-card { display:flex; align-items:center; gap:14px; padding:4px 0 18px; border-bottom:1px solid var(--c-border); }
.account-card__avatar { display:grid; place-items:center; width:48px; height:48px; border-radius:15px; background:var(--c-primary-weak); color:var(--c-primary); font-size:18px; font-weight:600; }
.account-card div { display:grid; gap:3px; }
.account-card strong { font-size:16px; }
.account-card small { color:var(--c-text-3); font-size:12px; }
.account-signout { width:100%; min-height:44px; margin-top:12px; border-radius:10px; background:var(--c-surface-2); color:var(--c-text-2); font-size:13px; }
.account-signout:hover { background:var(--c-surface-3); color:var(--c-attention-strong); }
</style>
