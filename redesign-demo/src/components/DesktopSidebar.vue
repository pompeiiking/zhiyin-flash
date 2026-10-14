<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AccordionContent, AccordionHeader, AccordionItem, AccordionRoot, AccordionTrigger } from 'reka-ui'
import { WORKSPACE_GROUPS, WORKSPACE_PRIMARY, PORTAL_LINK, isNavActive, activeGroup } from '../lib/workspace-nav'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import UiIcon from './UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
const route = useRoute()
const router = useRouter()
defineEmits<{ newChat: []; account: []; collapse: [] }>()
const collapseButton = ref<HTMLButtonElement | null>(null)
defineExpose({ focusCollapse() { collapseButton.value?.focus() } })
/**
 * 默认**全部展开**。
 *
 * 之前只展开当前组、其余收起 —— 用户要先点一下才知道里面有什么，导航变成猜谜。
 * 分组是稳定入口，不是渐进展开的内容；收起只作为用户主动收窄列表的选择。
 */
const openGroups = ref<string[]>(WORKSPACE_GROUPS.map((g) => g.key))
watch(() => route.path, () => {
  const key = activeGroup({ path: route.path, query: route.query })?.key
  // 路由变化只**补开**当前组，不收起用户已经打开的其它组。
  if (key && !openGroups.value.includes(key)) openGroups.value = [...openGroups.value, key]
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
    <div class="desk-scroll">
    <nav class="desk-nav" aria-label="学生空间导航">
      <RouterLink :to="WORKSPACE_PRIMARY.to" class="desk-link desk-link--conversation" :aria-current="isNavActive(WORKSPACE_PRIMARY, route) ? 'page' : undefined"><UiIcon :name="WORKSPACE_PRIMARY.icon" :size="20" /><span>{{ WORKSPACE_PRIMARY.label }}</span><span class="desk-link__dot" v-if="isNavActive(WORKSPACE_PRIMARY, route)" /></RouterLink>
      <AccordionRoot v-model="openGroups" type="multiple" class="desk-menu">
        <AccordionItem v-for="group in WORKSPACE_GROUPS" :key="group.key" :value="group.key" class="desk-menu__group">
          <AccordionHeader><AccordionTrigger class="desk-menu__trigger" :class="{ 'desk-menu__trigger--active': group.items.some(i => isNavActive(i, route)) }"><UiIcon :name="group.icon" :size="19" /><span>{{ group.label }}</span><UiIcon class="desk-menu__chevron" name="chevron" :size="15" /></AccordionTrigger></AccordionHeader>
          <AccordionContent class="desk-menu__content"><div class="desk-menu__children"><RouterLink v-for="item in group.items" :key="item.key" :to="item.to" class="desk-link desk-link--child" :aria-current="isNavActive(item, route) ? 'page' : undefined"><span>{{ item.label }}</span><span v-if="isNavActive(item, route)" class="desk-link__dot" /></RouterLink></div></AccordionContent>
        </AccordionItem>
      </AccordionRoot>
    </nav>
    <section class="desk-history" aria-label="历史会话"><div class="desk-history__head"><h2>历史会话</h2><span>{{ backendDemo.state.sessions.length }}</span></div><button v-for="session in sessions" :key="session.task_id" class="desk-session" :title="session.task_name" :aria-pressed="route.path === '/chat' && session.task_id === demo.state.currentSessionId" :disabled="demo.state.chatBusy" @click="resumeSession(session.task_id)"><span>{{ session.task_name || '未命名咨询' }}</span><small>{{ sessionDate(session.last_active_at) }}</small></button><p v-if="!sessions.length" class="desk-history__empty">创建咨询后，会话将显示在这里。</p></section>
    </div>
    <!--
      页脚只留两样：账号（与顶栏、移动端指向**同一个「账号」抽屉**）、返回门户。
      原来这里并排四颗内部页链接（使用指南 / 应用工具 / 设计规范 / 返回门户），
      每颗 35×41 —— 既不到 44px，又让内部文档从导航裂缝漏回学生入口。
    -->
    <div class="desk-footer">
      <button class="desk-person" aria-label="账号" @click="$emit('account')"><span class="desk-person__avatar">{{ userName.slice(0, 1) }}</span><span><strong>{{ userName }}</strong><small>{{ demo.state.account === 'fresh' ? '演示账号 · 待完善资料' : demo.use.scenario.value.grade + ' · ' + STUDENT.school }}</small></span><UiIcon name="chevron" :size="16" /></button>
      <div class="desk-footer__links"><RouterLink :to="PORTAL_LINK.to">{{ PORTAL_LINK.label }}</RouterLink></div>
    </div>
  </aside>
</template>
