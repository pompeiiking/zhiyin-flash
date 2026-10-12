<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
import { WORKSPACE_ITEMS, WORKSPACE_TOOLS } from '../lib/workspace-nav'
const route = useRoute()
const more = ref(false)
const spaces = [
  { label: '对话', to: '/chat', icon: 'chat', paths: ['/chat'] },
  { label: '行动', to: '/home', icon: 'action', paths: ['/home', '/plan', '/schedule', '/notes'] },
  { label: '画像', to: '/profile', icon: 'profile', paths: ['/profile', '/academic'] },
  { label: '报告', to: '/report', icon: 'report', paths: ['/report', '/directions'] },
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
      <RouterLink v-for="item in [...WORKSPACE_ITEMS, ...WORKSPACE_TOOLS]" :key="item.to" :to="item.to" @click="more = false"><strong>{{ item.label }}</strong><span>{{ item.hint }}</span><UiIcon name="arrow" /></RouterLink>
    </div>
  </InfoSheet>
</template>
