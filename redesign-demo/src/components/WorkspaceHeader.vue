<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { backendDemo } from '../lib/backend-demo'
import { STUDENT } from '../data/student'
import GradeSwitch from './GradeSwitch.vue'
import SkinSwitcher from './SkinSwitcher.vue'
import UiIcon from './UiIcon.vue'
import InfoSheet from './InfoSheet.vue'
import { navigation } from '../lib/layout'
import { WORKSPACE_GROUPS } from '../lib/workspace-nav'
const emit = defineEmits<{ openPalette: []; expandSidebar: [] }>()
const router = useRouter()
const route = useRoute()
const desktop = computed(() => navigation.mode.value === 'desktop' && !navigation.compact.value)
const groupLabel = computed(() => WORKSPACE_GROUPS.find(g => g.items.some(i => i.paths.includes(route.path)))?.label ?? ({ '/chat': '咨询空间', '/tools': '应用工具', '/path': '使用指南', '/spec': '设计规范' }[route.path] ?? '学生空间'))
const accountOpen = ref(false)
const expandButton = ref<HTMLButtonElement | null>(null)
defineExpose({ showAccount() { accountOpen.value = true }, focusExpand() { expandButton.value?.focus() } })
const scenario = computed(() => demo.use.scenario.value)
function setDataSource(event:Event){const mode=(event.target as HTMLSelectElement).value as 'demo'|'service';backendDemo.setDataMode(mode);void router.replace({path:route.path,query:{...route.query,data:mode}})}
function signOut() {
  accountOpen.value = false
  demo.signOut()
  router.push('/')
}
</script>
<template>
  <header class="ws-topbar">
    <div v-if="desktop" class="desk-location"><button v-if="navigation.sidebarCollapsed.value" ref="expandButton" class="ws-icon-button" aria-label="展开侧栏" title="展开侧栏" aria-controls="student-desktop-sidebar" aria-expanded="false" @click="emit('expandSidebar')"><UiIcon name="sidebar" /></button><span>学生空间 · {{ backendDemo.state.dataMode==='demo'?'演示数据':'服务数据' }}</span><span aria-hidden="true">/</span><strong>{{ groupLabel }}</strong></div>
    <RouterLink v-else class="ws-brand" to="/chat" aria-label="职引，回到对话"><span class="ws-brand__mark" /><strong>职引</strong></RouterLink>
    <div class="ws-topbar__tools">
      <button class="ws-icon-button ws-search" aria-label="搜索与跳转" title="搜索与跳转（Ctrl + K）" @click="emit('openPalette')"><UiIcon name="search" /></button>
      <SkinSwitcher />
      <button class="ws-icon-button ws-inbox-trigger" :aria-label="'提醒，' + demo.state.noticeQueue.length + ' 条待处理'" @click="demo.openNotice()"><UiIcon name="bell" :size="18" /><span v-if="demo.state.noticeQueue.length">{{ demo.state.noticeQueue.length }}</span></button>
      <button v-if="!desktop || navigation.sidebarCollapsed.value" class="ws-avatar" aria-label="账号与演示设置" @click="accountOpen = true">{{ demo.state.account === 'fresh' ? '新' : STUDENT.name.slice(0, 1) }}</button>
    </div>
  </header>
  <InfoSheet :open="accountOpen" title="账号与演示设置" @close="accountOpen = false">
    <p class="ws-person">{{ demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</p><p class="ws-muted">{{ demo.state.account === 'fresh' ? '个人资料待完善' : scenario.grade + ' · ' + STUDENT.major + ' · ' + STUDENT.school }}</p>
    <p class="ws-demo-note">这是一份示例，用来让你先看清职引能做什么。</p>
    <label class="ws-field">数据来源<select aria-label="数据来源" :value="backendDemo.state.dataMode" @change="setDataSource"><option value="demo">本地演示数据</option><option value="service">服务数据（需后端）</option></select></label><p class="ws-demo-note">本地演示使用虚构人物、岗位和预设分析，操作仅保存在当前浏览器会话。切换来源后请重新读取页面结果。</p><div class="desk-account-grade"><p class="ws-muted">演示使用场景</p><GradeSwitch /></div>
    <label class="ws-field">导航布局<select aria-label="导航布局" :value="desktop ? 'desktop' : 'mobile'" @change="navigation.set(($event.target as HTMLSelectElement).value as 'desktop' | 'mobile')"><option value="desktop" :disabled="navigation.compact.value">桌面侧栏</option><option value="mobile">移动导航</option></select></label>
    <div class="ws-stack"><button class="btn" @click="demo.resetDemo(); accountOpen = false">复位演示数据</button><button class="btn" @click="demo.resetGuide(); accountOpen = false">恢复操作引导</button><button class="btn" @click="signOut">退出登录</button></div>
  </InfoSheet>
</template>
