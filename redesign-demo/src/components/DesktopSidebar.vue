<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AccordionContent, AccordionHeader, AccordionItem, AccordionRoot, AccordionTrigger } from 'reka-ui'
import { WORKSPACE_GROUPS } from '../lib/workspace-nav'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import UiIcon from './UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
const route = useRoute()
const router = useRouter()
defineEmits<{ search: []; newChat: []; account: []; collapse: [] }>()
const collapseButton = ref<HTMLButtonElement | null>(null)
defineExpose({ focusCollapse() { collapseButton.value?.focus() } })
const openGroups = ref<string[]>([])
watch(() => route.path, () => {
  const group = WORKSPACE_GROUPS.find(g => g.items.some(i => i.paths.includes(route.path)))?.label
  if (group && !openGroups.value.includes(group)) openGroups.value = [...openGroups.value, group]
}, { immediate: true })
const sessions = computed(() => [...backendDemo.state.sessions].sort((a, b) => (b.last_active_at ?? '').localeCompare(a.last_active_at ?? '')))
function resumeSession(id: string) {
  if (demo.state.chatBusy) return
  if (id !== demo.state.currentSessionId) demo.startChatSession(backendDemo.selectSession(id), id)
  router.push('/chat')
}
const userName = computed(() => demo.state.account === 'fresh' ? '新用户' : STUDENT.name)
function sessionDate(date?: string | null) { return date ? new Date(date).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : '' }
</script>
<template>
  <aside id="student-desktop-sidebar" class="desk-sidebar" aria-label="桌面导航">
    <div class="desk-brand-row"><RouterLink class="desk-brand" to="/chat" aria-label="职引，回到对话"><span class="desk-brand__symbol" aria-hidden="true"><span /><span /><span /></span><div><strong>职引</strong><span>生涯规划与就业指导</span></div></RouterLink><button ref="collapseButton" class="ws-icon-button desk-collapse" aria-label="收起侧栏" title="收起侧栏" aria-controls="student-desktop-sidebar" aria-expanded="true" @click="$emit('collapse')"><UiIcon name="sidebar" :size="19" /></button></div>
    <button class="desk-new-chat" :disabled="demo.state.chatBusy" @click="$emit('newChat')"><UiIcon name="plus" :size="18" /><span>新建咨询</span></button>
    <button class="desk-search" @click="$emit('search')"><UiIcon name="search" :size="16" /><span>搜索功能</span><kbd>Ctrl K</kbd></button>
    <div class="desk-scroll">
    <nav class="desk-nav" aria-label="学生空间导航">
      <RouterLink to="/chat" class="desk-link desk-link--conversation" :aria-current="route.path === '/chat' ? 'page' : undefined"><UiIcon name="chat" :size="20" /><span>咨询对话</span><span class="desk-link__dot" v-if="route.path === '/chat'" /></RouterLink>
      <AccordionRoot v-model="openGroups" type="multiple" class="desk-menu">
        <AccordionItem v-for="group in WORKSPACE_GROUPS" :key="group.label" :value="group.label" class="desk-menu__group">
          <AccordionHeader><AccordionTrigger class="desk-menu__trigger" :class="{ 'desk-menu__trigger--active': group.items.some(i => i.paths.includes(route.path)) }"><UiIcon :name="group.icon" :size="19" /><span>{{ group.label }}</span><UiIcon class="desk-menu__chevron" name="chevron" :size="15" /></AccordionTrigger></AccordionHeader>
          <AccordionContent class="desk-menu__content"><div class="desk-menu__children"><RouterLink v-for="item in group.items" :key="item.to" :to="item.to" class="desk-link desk-link--child" :aria-current="item.paths.includes(route.path) ? 'page' : undefined"><span>{{ item.label }}</span><span v-if="item.paths.includes(route.path)" class="desk-link__dot" /></RouterLink></div></AccordionContent>
        </AccordionItem>
      </AccordionRoot>
    </nav>
    <section class="desk-history" aria-label="历史会话"><div class="desk-history__head"><h2>历史会话</h2><span>{{ backendDemo.state.sessions.length }}</span></div><button v-for="session in sessions" :key="session.task_id" class="desk-session" :title="session.task_name" :aria-pressed="route.path === '/chat' && session.task_id === demo.state.currentSessionId" :disabled="demo.state.chatBusy" @click="resumeSession(session.task_id)"><span>{{ session.task_name || '未命名咨询' }}</span><small>{{ sessionDate(session.last_active_at) }}</small></button><p v-if="!sessions.length" class="desk-history__empty">创建咨询后，会话将显示在这里。</p></section>
    </div>
    <div class="desk-footer">
      <button class="desk-person" aria-label="账号与演示设置" @click="$emit('account')"><span class="desk-person__avatar">{{ userName.slice(0, 1) }}</span><span><strong>{{ userName }}</strong><small>{{ demo.state.account === 'fresh' ? '演示账号 · 待完善资料' : demo.use.scenario.value.grade + ' · ' + STUDENT.school }}</small></span><UiIcon name="chevron" :size="16" /></button>
      <div class="desk-footer__links"><RouterLink to="/tools">应用工具</RouterLink><RouterLink to="/path">使用指南</RouterLink><RouterLink to="/">门户</RouterLink></div>
    </div>
  </aside>
</template>
