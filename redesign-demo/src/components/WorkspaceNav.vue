<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
const route = useRoute()
const more = ref(false)
const spaces = [
  { label: '对话', to: '/chat', icon: 'chat', paths: ['/chat'] },
  { label: '任务与计划', to: '/home', icon: 'action', paths: ['/home', '/plan'] },
  { label: '学生档案', to: '/profile', icon: 'profile', paths: ['/profile'] },
  { label: '评估报告', to: '/report', icon: 'report', paths: ['/report'] },
  { label: '复盘记录', to: '/review', icon: 'review', paths: ['/review'] },
]
</script>
<template>
  <nav class="ws-bookmarks" aria-label="学生空间导航">
    <RouterLink v-for="s in spaces" :key="s.to" :to="s.to" class="ws-bookmark" :class="{ 'ws-bookmark--active': s.paths.includes(route.path) }" :aria-current="s.paths.includes(route.path) ? 'page' : undefined">
      <UiIcon :name="s.icon" :size="20" /><span>{{ s.label }}</span>
    </RouterLink>
    <button class="ws-bookmark ws-bookmark--more" aria-label="更多功能" @click="more = true"><UiIcon name="more" /><span>更多</span></button>
  </nav>
  <InfoSheet :open="more" title="更多功能" @close="more = false">
    <div class="ws-directory">
      <RouterLink to="/path" @click="more = false"><strong>大一到大四</strong><span>看看每个年级该关注什么，以及完整使用路径</span><UiIcon name="arrow" /></RouterLink>
      <RouterLink to="/spec" @click="more = false"><strong>设计规范</strong><span>配色、排版与组件的说明</span><UiIcon name="arrow" /></RouterLink>
      <RouterLink to="/" @click="more = false"><strong>回到门户</strong><span>职引如何帮助你</span><UiIcon name="arrow" /></RouterLink>
    </div>
  </InfoSheet>
</template>
