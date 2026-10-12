<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import GradeSwitch from './GradeSwitch.vue'
import SkinSwitcher from './SkinSwitcher.vue'
import UiIcon from './UiIcon.vue'
import InfoSheet from './InfoSheet.vue'
const emit = defineEmits<{ openPalette: [] }>()
const router = useRouter()
const accountOpen = ref(false)
const scenario = computed(() => demo.use.scenario.value)
function signOut() {
  accountOpen.value = false
  demo.signOut()
  router.push('/')
}
</script>
<template>
  <header class="ws-topbar">
    <RouterLink class="ws-brand" to="/chat" aria-label="职引，回到对话"><span class="ws-brand__mark" /><strong>职引</strong><span class="ws-brand__context">学生空间</span></RouterLink>
    <div class="ws-topbar__tools">
      <button class="ws-icon-button ws-search" aria-label="搜索与跳转" title="搜索与跳转（Ctrl + K）" @click="emit('openPalette')"><UiIcon name="search" /></button>
      <GradeSwitch />
      <SkinSwitcher />
      <button class="ws-icon-button ws-inbox-trigger" :aria-label="'提醒，' + demo.state.noticeQueue.length + ' 条待处理'" @click="demo.openNotice()"><UiIcon name="bell" :size="18" /><span v-if="demo.state.noticeQueue.length">{{ demo.state.noticeQueue.length }}</span></button>
      <button class="ws-avatar" aria-label="账号与演示设置" @click="accountOpen = true">{{ STUDENT.name.slice(0, 1) }}</button>
    </div>
  </header>
  <InfoSheet :open="accountOpen" title="账号与演示设置" @close="accountOpen = false">
    <p class="ws-person">{{ STUDENT.name }}</p><p class="ws-muted">{{ scenario.grade }} · {{ STUDENT.major }} · {{ STUDENT.school }}</p>
    <p class="ws-demo-note">这是一份示例，用来让你先看清职引能做什么。</p>
    <div class="ws-stack"><button class="btn" @click="demo.resetDemo(); accountOpen = false">复位演示数据</button><button class="btn" @click="demo.resetGuide(); accountOpen = false">恢复操作引导</button><button class="btn" @click="signOut">退出登录</button></div>
  </InfoSheet>
</template>
