<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { backendDemo } from '../lib/backend-demo'
import { openSession, systemData } from '../lib/system-data'
import { demo, toast } from '../store'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
import { WORKSPACE_GROUPS, WORKSPACE_PRIMARY, MOBILE_TABS, isNavActive, activeGroup } from '../lib/workspace-nav'
import { AccordionRoot, AccordionItem, AccordionHeader, AccordionTrigger, AccordionContent } from 'reka-ui'
import BrandMark from './BrandMark.vue'

/**
 * 移动端导航。
 *
 * 底栏四个常用去处 + 「更多」。四个 tab 各自覆盖**整组**路由，所以同一组内的
 * 二级页面切换时 tab 保持高亮，不会掉。其余入口都在「更多」里，与桌面侧栏
 * 读的是同一份 `workspace-nav` 模型。
 *
 * 「更多」里原来是"分组目录 + 主入口 + 一排内部页链接（使用指南 / 应用工具 /
 * 设计规范 / 返回门户）"。内部页已按审计结论移出学生入口，返回门户在账号抽屉里；
 * 这里只剩学生真正要去的地方。
 */
const route = useRoute()
const router = useRouter()
const sessions = computed(() => [...backendDemo.state.sessions].sort((a,b) => (b.last_active_at || '').localeCompare(a.last_active_at || '')))
async function resume(id: string) { try { await openSession(id); more.value = false; await router.push('/chat') } catch(e) { toast((e as Error).message) } }
const more = ref(false)
const emit = defineEmits<{ account: [] }>()
defineExpose({ show() { more.value = true } })
/** 与桌面侧栏一致：分组默认全部展开，收起只是用户主动收窄列表。 */
const openGroup = ref<string[]>(WORKSPACE_GROUPS.map((g) => g.key))

watch(
  () => [route.path, more.value],
  () => {
    const key = activeGroup({ path: route.path, query: route.query })?.key
    if (key && !openGroup.value.includes(key)) openGroup.value = [...openGroup.value, key]
  },
  { immediate: true },
)
</script>

<template>
  <nav class="ws-bookmarks" aria-label="学生空间导航">
    <RouterLink
      v-for="tab in MOBILE_TABS"
      :key="tab.key"
      :to="tab.to"
      class="ws-bookmark"
      :class="{ 'ws-bookmark--active': isNavActive(tab, route) }"
      :aria-current="isNavActive(tab, route) ? 'page' : undefined"
    >
      <UiIcon :name="tab.icon" :size="20" /><span>{{ tab.short ?? tab.label }}</span>
    </RouterLink>
    <button class="ws-bookmark ws-bookmark--more" type="button" aria-label="更多功能" @click="more = true">
      <UiIcon name="more" :size="20" /><span>更多</span>
    </button>
  </nav>

  <InfoSheet shape="sheet" :open="more" title="更多功能" @close="more = false">
    <div class="mobile-menu-brand"><BrandMark /></div>
    <button class="mobile-account-entry" type="button" @click="more=false;emit('account')">
      <span class="mobile-account-entry__avatar" aria-hidden="true">{{ demo.state.account.slice(0,1) }}</span>
      <span><strong>{{ demo.state.account }}</strong><small>账号与外观设置</small></span>
      <UiIcon name="arrow" :size="16" />
    </button>
    <RouterLink class="ws-directory__primary" :to="WORKSPACE_PRIMARY.to" @click="more = false">
      <UiIcon :name="WORKSPACE_PRIMARY.icon" /><span><strong>{{ WORKSPACE_PRIMARY.label }}</strong><small>{{ WORKSPACE_PRIMARY.hint }}</small></span>
      <UiIcon name="arrow" :size="16" />
    </RouterLink>
    <AccordionRoot v-model="openGroup" type="multiple" class="desk-menu">
      <AccordionItem v-for="group in WORKSPACE_GROUPS" :key="group.key" :value="group.key">
        <AccordionHeader>
          <AccordionTrigger class="desk-menu__trigger">
            <UiIcon :name="group.icon" /><span>{{ group.label }}</span><UiIcon class="desk-menu__chevron" name="chevron" :size="16" />
          </AccordionTrigger>
        </AccordionHeader>
        <AccordionContent class="desk-menu__content">
          <div class="desk-menu__children">
            <RouterLink
              v-for="item in group.items"
              :key="item.key"
              :to="item.to"
              class="desk-link desk-link--child"
              :aria-current="isNavActive(item, route) ? 'page' : undefined"
              @click="more = false"
            >{{ item.label }}</RouterLink>
          </div>
        </AccordionContent>
      </AccordionItem>
    </AccordionRoot>
    <section class="mobile-session-history" aria-label="历史会话"><h2>历史会话</h2><button v-for="session in sessions" :key="session.task_id" :disabled="demo.state.chatBusy || systemData.busy" :aria-pressed="session.task_id === demo.state.currentSessionId" @click="resume(session.task_id)">{{ session.task_name }}</button><p v-if="!sessions.length">还没有历史会话。</p></section>
  </InfoSheet>
</template>
<style scoped>
.mobile-menu-brand { display:flex; align-items:center; padding:0 0 14px; border-bottom:1px solid var(--c-border); }
.mobile-account-entry { display:flex; align-items:center; gap:12px; width:100%; min-height:58px; padding:8px 0; border-bottom:1px solid var(--c-border); color:var(--c-text); text-align:left; }
.mobile-account-entry>span:nth-child(2) { flex:1; min-width:0; }
.mobile-account-entry strong { display:block; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mobile-account-entry small { display:block; margin-top:2px; color:var(--c-text-3); font-size:12px; }
.mobile-account-entry__avatar { display:grid; place-items:center; width:34px; height:34px; border-radius:10px; background:var(--c-surface-3); color:var(--c-text-2); }
.mobile-session-history {border-top:1px solid var(--c-border);margin-top:16px;padding-top:16px;}
.mobile-session-history h2 {font-size:12px;font-weight:500;color:var(--c-text-3);}
.mobile-session-history button {display:block;width:100%;min-height:44px;border:0;background:none;text-align:left;color:var(--c-text-2);font-size:14px;}
.mobile-session-history button[aria-pressed=true] {color:var(--c-primary);}
</style>
