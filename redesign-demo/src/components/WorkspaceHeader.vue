<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import GradeSwitch from './GradeSwitch.vue'
import SkinSwitcher from './SkinSwitcher.vue'
import UiIcon from './UiIcon.vue'
import InfoSheet from './InfoSheet.vue'
import { navigation } from '../lib/layout'
import { WORKSPACE_GROUPS } from '../lib/workspace-nav'
const emit = defineEmits<{ openPalette: [] }>()
const router = useRouter()
const route = useRoute()
const desktop = computed(() => navigation.mode.value === 'desktop' && !navigation.compact.value)
const groupLabel = computed(() => WORKSPACE_GROUPS.find(g => g.items.some(i => i.paths.includes(route.path)))?.label ?? '咨询空间')
const accountOpen = ref(false)
defineExpose({ showAccount() { accountOpen.value = true } })
const scenario = computed(() => demo.use.scenario.value)
function signOut() {
  accountOpen.value = false
  demo.signOut()
  router.push('/')
}
</script>
<template>
  <header class="ws-topbar">
    <div v-if="desktop" class="desk-location"><span>学生空间 · 演示</span><span aria-hidden="true">/</span><strong>{{ groupLabel }}</strong></div>
    <RouterLink v-else class="ws-brand" to="/chat" aria-label="职引，回到对话"><span class="ws-brand__mark" /><strong>职引</strong></RouterLink>
    <div class="ws-topbar__tools">
      <button class="ws-icon-button ws-search" aria-label="搜索与跳转" title="搜索与跳转（Ctrl + K）" @click="emit('openPalette')"><UiIcon name="search" /></button>
      <label class="desk-layout-select"><span>导航</span><select aria-label="导航布局" :value="desktop ? 'desktop' : 'mobile'" @change="navigation.set(($event.target as HTMLSelectElement).value as 'desktop' | 'mobile')"><option value="desktop" :disabled="navigation.compact.value">桌面侧栏</option><option value="mobile">移动导航</option></select></label>
      <SkinSwitcher />
      <button class="ws-icon-button ws-inbox-trigger" :aria-label="'提醒，' + demo.state.noticeQueue.length + ' 条待处理'" @click="demo.openNotice()"><UiIcon name="bell" :size="18" /><span v-if="demo.state.noticeQueue.length">{{ demo.state.noticeQueue.length }}</span></button>
      <button v-if="!desktop" class="ws-avatar" aria-label="账号与演示设置" @click="accountOpen = true">{{ demo.state.account === 'fresh' ? '新' : STUDENT.name.slice(0, 1) }}</button>
    </div>
  </header>
  <InfoSheet :open="accountOpen" title="账号与演示设置" @close="accountOpen = false">
    <p class="ws-person">{{ demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</p><p class="ws-muted">{{ demo.state.account === 'fresh' ? '个人资料待完善' : scenario.grade + ' · ' + STUDENT.major + ' · ' + STUDENT.school }}</p>
    <p class="ws-demo-note">这是一份示例，用来让你先看清职引能做什么。</p>
    <div class="desk-account-grade"><p class="ws-muted">演示使用场景</p><GradeSwitch /></div>
    <div class="ws-stack"><button class="btn" @click="demo.resetDemo(); accountOpen = false">复位演示数据</button><button class="btn" @click="demo.resetGuide(); accountOpen = false">恢复操作引导</button><button class="btn" @click="signOut">退出登录</button></div>
  </InfoSheet>
</template>
