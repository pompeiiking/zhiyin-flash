<script setup lang="ts">
import { computed, ref } from 'vue'
import { routeEnabled } from '../lib/features'
import { useRoute, useRouter } from 'vue-router'
import { backendDemo } from '../lib/backend-demo'
import { openSession, systemData } from '../lib/system-data'
import { demo, toast } from '../store'
import { useDisplayName } from '../lib/display-name'
import AnchoredCard from './AnchoredCard.vue'
import UiIcon from './UiIcon.vue'
import { WORKSPACE_GROUPS, MOBILE_TABS, isNavActive, isMobileTabActive, isMobileMoreActive } from '../lib/workspace-nav'
import { navigation } from '../lib/layout'

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
const sessions = computed(() => [...backendDemo.state.sessions].sort((a,b) => ((b.last_message_at || b.last_active_at) || '').localeCompare((a.last_message_at || a.last_active_at) || '')))
async function resume(id: string) { try { await openSession(id); more.value = false; await router.push('/chat') } catch(e) { toast((e as Error).message) } }
const more = ref(false)
const moreActive = computed(() => isMobileMoreActive(route))
const displayName = useDisplayName()
defineExpose({ show() { more.value = true } })
</script>

<template>
  <nav class="ws-bookmarks" aria-label="学生空间导航">
    <RouterLink
      v-for="tab in MOBILE_TABS.filter(tab => routeEnabled(tab.to))"
      :key="tab.key"
      :to="tab.to"
      class="ws-bookmark"
      :class="{ 'ws-bookmark--active': isMobileTabActive(tab, route) }"
      :aria-current="isMobileTabActive(tab, route) ? 'page' : undefined"
    >
      <UiIcon :name="tab.icon" :size="20" /><span>{{ tab.short ?? tab.label }}</span>
    </RouterLink>
    <AnchoredCard v-model="more" class="ws-bookmark ws-bookmark--more" :class="{ 'ws-bookmark--active': moreActive }" :aria-current="moreActive ? 'page' : undefined" title="全部功能" label="更多功能" side="top" align="end" size="wide">
      <template #trigger><UiIcon name="more" :size="20" /><span>更多</span></template>
    <RouterLink class="mobile-account-entry" to="/settings" @click="more=false">
      <span class="mobile-account-entry__avatar" aria-hidden="true">{{ displayName.slice(0,1) }}</span>
      <span><strong>{{ displayName }}</strong><small>账号、资料授权与导出</small></span>
      <UiIcon name="arrow" :size="16" />
    </RouterLink>
    <div class="mobile-function-map">
      <section v-for="(group, index) in WORKSPACE_GROUPS" :key="group.key" class="mobile-function-group">
        <header><span>{{ String(index + 1).padStart(2, '0') }}</span><UiIcon :name="group.icon" :size="18" /><h2>{{ group.label }}</h2></header>
        <div class="mobile-function-group__items">
          <RouterLink v-for="item in group.items.filter(item => routeEnabled(item.to))" :key="item.key" :to="item.to" :class="{ 'is-active': isNavActive(item, route) }" :aria-current="isNavActive(item, route) ? 'page' : undefined" @click="more=false">
            <UiIcon :name="item.icon" :size="19" /><span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span><UiIcon name="arrow" :size="15" />
          </RouterLink>
        </div>
      </section>
    </div>
    <div v-if="!navigation.compact.value" class="mobile-layout-return">
      <div><UiIcon name="sidebar" :size="18"/><span><strong>桌面侧栏</strong><small>恢复大分类、小分类与历史会话</small></span></div>
      <button type="button" class="btn" @click="navigation.set('desktop');more=false">切换</button>
    </div>
    <details class="mobile-session-history" aria-label="历史会话"><summary><span>历史会话</span><small>{{ sessions.length }} 个</small><UiIcon name="chevron" :size="16"/></summary><div><button v-for="session in sessions" :key="session.task_id" :disabled="demo.state.chatBusy || systemData.busy" :aria-pressed="session.task_id === demo.state.currentSessionId" @click="resume(session.task_id)"><strong>{{ session.task_name }}</strong><small>{{ session.last_message || '还没有消息' }}</small></button><p v-if="!sessions.length">还没有历史会话。开始咨询后会自动保存在这里。</p></div></details>
    </AnchoredCard>
  </nav>
</template>
<style scoped>
.mobile-account-entry { display:flex; align-items:center; gap:12px; width:100%; min-height:64px; padding:10px 12px; border:1px solid var(--c-border); border-radius:14px; background:var(--c-surface-2); color:var(--c-text); text-align:left; }
.mobile-account-entry>span:nth-child(2) { flex:1; min-width:0; }
.mobile-account-entry strong { display:block; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mobile-account-entry small { display:block; margin-top:2px; color:var(--c-text-3); font-size:12px; }
.mobile-account-entry__avatar { display:grid; place-items:center; width:34px; height:34px; border-radius:10px; background:var(--c-surface-3); color:var(--c-text-2); }
.mobile-function-map { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin-top:18px; }
.mobile-function-group { min-width:0; padding:14px; border:1px solid var(--c-border); border-radius:16px; background:var(--c-surface); }
.mobile-function-group header { display:flex; align-items:center; gap:8px; padding-bottom:10px; border-bottom:1px solid var(--c-border); }
.mobile-function-group header>span { color:var(--c-primary); font-size:11px; font-variant-numeric:tabular-nums; }
.mobile-function-group header h2 { font-size:14px; font-weight:600; }
.mobile-function-group__items { display:grid; gap:2px; padding-top:6px; }
.mobile-function-group__items a { display:grid; grid-template-columns:22px minmax(0,1fr) 16px; align-items:center; gap:9px; min-height:58px; padding:7px 5px; border-radius:10px; color:var(--c-text-2); }
.mobile-function-group__items a:hover,.mobile-function-group__items a.is-active { background:var(--c-primary-weak); color:var(--c-primary); text-decoration:none; }
.mobile-function-group__items span { min-width:0; }
.mobile-function-group__items strong { display:block; color:var(--c-text); font-size:13px; }
.mobile-function-group__items small { display:block; overflow:hidden; margin-top:2px; color:var(--c-text-3); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.mobile-layout-return { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:16px; padding:10px 12px; border:1px solid var(--c-primary-border); border-radius:13px; background:var(--c-primary-weak); }
.mobile-layout-return>div { display:flex; align-items:center; gap:10px; min-width:0; color:var(--c-primary); }.mobile-layout-return>div>span { min-width:0; }.mobile-layout-return strong,.mobile-layout-return small { display:block; }.mobile-layout-return strong { color:var(--c-text); font-size:13px; }.mobile-layout-return small { margin-top:2px; color:var(--c-text-2); font-size:12px; }
.mobile-session-history { margin-top:16px; border-top:1px solid var(--c-border); }
.mobile-session-history summary { display:grid; grid-template-columns:minmax(0,1fr) auto 18px; align-items:center; gap:8px; min-height:52px; cursor:pointer; list-style:none; color:var(--c-text-2); font-size:13px; }
.mobile-session-history summary::-webkit-details-marker { display:none; }
.mobile-session-history summary small { color:var(--c-text-3); }
.mobile-session-history[open] summary svg { transform:rotate(180deg); }
.mobile-session-history button {display:block;width:100%;min-height:44px;border:0;background:none;text-align:left;color:var(--c-text-2);font-size:14px;}
.mobile-session-history button strong {display:block;font-weight:var(--fw-regular);}
.mobile-session-history button small {display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--c-text-3);font-size:12px;line-height:1.5;}
.mobile-session-history button[aria-pressed=true] {color:var(--c-primary);}
@media(max-width:620px){.mobile-function-map{grid-template-columns:1fr}.mobile-function-group__items{grid-template-columns:repeat(2,minmax(0,1fr))}.mobile-function-group__items a{grid-template-columns:20px minmax(0,1fr)}.mobile-function-group__items a>svg:last-child{display:none}}
</style>
