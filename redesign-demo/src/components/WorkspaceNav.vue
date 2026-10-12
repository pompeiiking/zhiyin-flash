<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
import { WORKSPACE_GROUPS, WORKSPACE_TOOLS } from '../lib/workspace-nav'
import { AccordionRoot, AccordionItem, AccordionHeader, AccordionTrigger, AccordionContent } from 'reka-ui'
const route = useRoute()
const more = ref(false)
const openGroup = ref('')
watch(() => [route.path, more.value], () => {
  openGroup.value = WORKSPACE_GROUPS.find(g => g.items.some(i => i.paths.includes(route.path)))?.label ?? ''
}, { immediate: true })
const spaces = [
  { label: '对话', to: '/chat', icon: 'chat', paths: ['/chat'] },
  { label: '行动', to: '/home', icon: 'action', paths: ['/home', '/plan', '/schedule', '/notes'] },
  { label: '画像', to: '/profile', icon: 'profile', paths: ['/profile', '/academic', '/report'] },
  { label: '方向', to: '/directions', icon: 'directions', paths: ['/directions', '/intel'] },
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
    <AccordionRoot v-model="openGroup" type="single" collapsible class="desk-menu"><AccordionItem v-for="group in WORKSPACE_GROUPS" :key="group.label" :value="group.label"><AccordionHeader><AccordionTrigger class="desk-menu__trigger"><UiIcon :name="group.icon" /><span>{{ group.label }}</span><UiIcon class="desk-menu__chevron" name="chevron" :size="16" /></AccordionTrigger></AccordionHeader><AccordionContent class="desk-menu__content"><div class="desk-menu__children"><RouterLink v-for="item in group.items" :key="item.to" :to="item.to" class="desk-link desk-link--child" :aria-current="item.paths.includes(route.path) ? 'page' : undefined" @click="more = false">{{ item.label }}</RouterLink></div></AccordionContent></AccordionItem></AccordionRoot>
    <div class="ws-directory">
      <RouterLink v-for="item in WORKSPACE_TOOLS" :key="item.to" :to="item.to" @click="more = false"><strong>{{ item.label }}</strong><span>{{ item.hint }}</span><UiIcon name="arrow" /></RouterLink>
    </div>
  </InfoSheet>
</template>
