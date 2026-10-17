<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import UiIcon from '../components/UiIcon.vue'

const route = useRoute()
const asked = computed(() => (route.fullPath || '/').split('?')[0] || '/')
const recovery = [
  { to: '/chat', icon: 'chat', title: '回到咨询', hint: '继续最近的对话与问题' },
  { to: '/home', icon: 'action', title: '查看今日行动', hint: '回到正在推进的事项' },
  { to: '/profile', icon: 'profile', title: '核对个人画像', hint: '查看已有资料与待补充项' },
  { to: '/directions', icon: 'directions', title: '查看方向方案', hint: '继续比较和确认方向' },
]
</script>

<template>
  <div class="ws-page recovery-page">
    <section class="recovery-hero" aria-labelledby="recovery-title">
      <span class="recovery-hero__code">404</span>
      <div><p>页面没有找到</p><h1 id="recovery-title">这个地址已经失效，或暂时不可用</h1><p class="page__sub">你打开的是 <code>{{ asked }}</code>。已保存的资料不会受到影响，可以从下面继续。</p></div>
    </section>
    <nav class="recovery-grid" aria-label="继续使用职引">
      <RouterLink v-for="item in recovery" :key="item.to" :to="item.to"><UiIcon :name="item.icon" :size="22"/><span><strong>{{ item.title }}</strong><small>{{ item.hint }}</small></span><UiIcon name="arrow" :size="17"/></RouterLink>
    </nav>
    <div class="recovery-footer"><RouterLink class="ws-text-link" to="/">返回职引门户</RouterLink><span>若链接来自他人，请让对方重新发送。</span></div>
  </div>
</template>

<style scoped>
.recovery-page { display:grid; align-content:center; gap:28px; min-height:calc(100dvh - 150px); max-width:880px; }
.recovery-hero { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:start; gap:24px; padding-bottom:26px; border-bottom:1px solid var(--c-border); }
.recovery-hero__code { color:var(--c-primary); font-size:clamp(46px,8vw,82px); font-weight:600; line-height:.95; letter-spacing:-.06em; }
.recovery-hero>div>p:first-child { color:var(--c-primary); font-size:13px; font-weight:600; }
.recovery-hero h1 { max-width:16em; margin-top:7px; font-size:clamp(28px,4vw,42px); line-height:1.24; }
.recovery-hero .page__sub { max-width:52em; margin-top:15px; color:var(--c-text-2); font-size:14px; line-height:1.75; }
.recovery-hero code { padding:2px 6px; border-radius:5px; background:var(--c-surface-2); color:var(--c-text); font-size:12px; }
.recovery-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.recovery-grid a { display:grid; grid-template-columns:28px minmax(0,1fr) 20px; align-items:center; gap:12px; min-height:82px; padding:14px 16px; border:1px solid var(--c-border); border-radius:14px; background:var(--c-surface); color:var(--c-text-2); }
.recovery-grid a:hover { border-color:var(--c-primary-border); background:var(--c-primary-weak); color:var(--c-primary); text-decoration:none; }
.recovery-grid strong,.recovery-grid small { display:block; }
.recovery-grid strong { color:var(--c-text); font-size:15px; }
.recovery-grid small { margin-top:3px; color:var(--c-text-3); font-size:12px; }
.recovery-footer { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; color:var(--c-text-3); font-size:12px; }
@media(max-width:640px){.recovery-page{align-content:start;min-height:0;padding-top:46px}.recovery-hero{grid-template-columns:1fr;gap:14px}.recovery-grid{grid-template-columns:1fr}.recovery-grid a{min-height:72px}.recovery-footer{align-items:flex-start;flex-direction:column}}
</style>
