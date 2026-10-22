<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from '../lib/auth'
import { navigation } from '../lib/layout'
import { PORTAL_LINK } from '../lib/workspace-nav'
import { demo, toast } from '../store'
import { useDisplayName } from '../lib/display-name'
import AnchoredCard from './AnchoredCard.vue'
import UiIcon from './UiIcon.vue'

defineOptions({ inheritAttrs:false })
withDefaults(defineProps<{ side?: 'top' | 'bottom' | 'left' | 'right'; align?: 'start' | 'center' | 'end' }>(), { side:'right', align:'end' })
const route = useRoute()
const router = useRouter()
const displayName = useDisplayName()
const open = ref(false)
watch(() => route.fullPath, () => { open.value = false })
async function signOut() {
  try { await auth.logout(); open.value = false; await router.push('/') }
  catch (error) { toast((error as Error).message) }
}
</script>

<template>
  <AnchoredCard v-model="open" title="账号" label="账号与工作空间" :side="side" :align="align" v-bind="$attrs">
    <template #trigger><slot name="trigger" /></template>
    <div class="account-popover__identity">
      <span aria-hidden="true">{{ displayName.slice(0, 1) }}</span>
      <strong>{{ displayName }}</strong>
    </div>
    <nav class="account-popover__links" aria-label="账号功能">
      <RouterLink to="/settings"><UiIcon name="settings" :size="18" /><span>账号与资料设置</span><UiIcon name="arrow" :size="15" /></RouterLink>
      <RouterLink :to="PORTAL_LINK.to"><UiIcon name="home" :size="18" /><span>{{ PORTAL_LINK.label }}</span><UiIcon name="arrow" :size="15" /></RouterLink>
    </nav>
    <div class="account-popover__workspace">
      <label>导航布局
        <select aria-label="导航布局" :value="navigation.mode.value" @change="navigation.set(($event.target as HTMLSelectElement).value as 'desktop' | 'mobile')">
          <option value="desktop" :disabled="navigation.compact.value">桌面侧栏</option>
          <option value="mobile">移动导航</option>
        </select>
      </label>
      <button type="button" @click="demo.resetGuide();open=false">恢复操作引导</button>
    </div>
    <button class="account-popover__signout" type="button" @click="signOut">退出登录</button>
  </AnchoredCard>
</template>

<style scoped>
.account-popover__identity { display:flex; align-items:center; gap:11px; padding:0 0 14px; border-bottom:1px solid var(--c-border); }
.account-popover__identity span { display:grid; place-items:center; width:38px; height:38px; border-radius:12px; background:var(--c-primary-weak); color:var(--c-primary); font-weight:600; }
.account-popover__identity strong { min-width:0; overflow:hidden; font-size:14px; text-overflow:ellipsis; white-space:nowrap; }
.account-popover__links { display:grid; padding:8px 0; border-bottom:1px solid var(--c-border); }
.account-popover__links a { display:grid; grid-template-columns:22px minmax(0,1fr) 16px; align-items:center; gap:9px; min-height:44px; padding:4px 8px; border-radius:10px; color:var(--c-text-2); font-size:13px; }
.account-popover__links a:hover { background:var(--c-surface-2); color:var(--c-primary); text-decoration:none; }
.account-popover__workspace { display:grid; gap:8px; padding:12px 0; border-bottom:1px solid var(--c-border); }
.account-popover__workspace label { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; color:var(--c-text-2); font-size:12px; }
.account-popover__workspace select { min-width:112px; height:38px; padding:0 9px; border:1px solid var(--c-border); border-radius:9px; background:var(--c-surface); color:var(--c-text); }
.account-popover__workspace button,.account-popover__signout { min-height:42px; border:0; border-radius:10px; background:var(--c-surface-2); color:var(--c-text-2); font-size:13px; cursor:pointer; }
.account-popover__workspace button:hover { color:var(--c-primary); }
.account-popover__signout { width:100%; margin-top:12px; }
.account-popover__signout:hover { color:var(--c-attention-strong); }
</style>
