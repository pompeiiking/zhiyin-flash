<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { WORKSPACE_GROUPS } from '../lib/workspace-nav'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import UiIcon from './UiIcon.vue'
const route = useRoute()
defineEmits<{ search: []; newChat: [] }>()
const progress = computed(() => demo.use.profileProgress.value)
</script>
<template>
  <aside class="desk-sidebar" aria-label="桌面导航">
    <RouterLink class="desk-brand" to="/chat" aria-label="职引，回到对话"><span class="desk-brand__symbol" aria-hidden="true"><span /><span /><span /></span><div><strong>职引</strong><span>把选择，走成下一步</span></div></RouterLink>
    <button class="desk-new-chat" :disabled="demo.state.chatBusy" @click="$emit('newChat')"><UiIcon name="plus" :size="18" /><span>开启一段对话</span></button>
    <button class="desk-search" @click="$emit('search')"><UiIcon name="search" :size="16" /><span>搜索功能</span><kbd>Ctrl K</kbd></button>
    <nav class="desk-nav" aria-label="学生空间导航">
      <RouterLink to="/chat" class="desk-link desk-link--conversation" :aria-current="route.path === '/chat' ? 'page' : undefined"><UiIcon name="chat" :size="20" /><span>咨询对话</span><span class="desk-link__dot" v-if="route.path === '/chat'" /></RouterLink>
      <section v-for="group in WORKSPACE_GROUPS" :key="group.label" class="desk-group">
        <h2>{{ group.label }}</h2>
        <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" class="desk-link" :aria-current="item.paths.includes(route.path) ? 'page' : undefined"><UiIcon :name="item.icon" :size="19" /><span>{{ item.label }}</span><UiIcon v-if="item.paths.includes(route.path)" name="arrow" :size="14" /></RouterLink>
      </section>
    </nav>
    <div class="desk-footer">
      <RouterLink class="desk-person" to="/profile"><span class="desk-person__avatar">{{ STUDENT.name.slice(0, 1) }}</span><span><strong>{{ STUDENT.name }}</strong><small>{{ demo.use.scenario.value.grade }} · {{ STUDENT.school }}</small></span><UiIcon name="chevron" :size="16" /></RouterLink>
      <div class="desk-footer__links"><RouterLink to="/tools">应用工具</RouterLink><RouterLink to="/path">使用指南</RouterLink><RouterLink to="/">门户</RouterLink></div>
      <p class="desk-demo">演示空间 · 已了解 {{ progress.known }} 条信息</p>
    </div>
  </aside>
</template>
