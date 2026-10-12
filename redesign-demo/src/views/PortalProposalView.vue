<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import UiIcon from '../components/UiIcon.vue'
import PortalExample from '../components/PortalExample.vue'

const route = useRoute()
const router = useRouter()
function start() {
  if (demo.state.authed) router.push('/chat')
  else router.push({ path: '/', query: { ...route.query, signin: '1' } })
}
const promises = [
  { title: '持续陪伴', body: '从认识自己，到行动后的复盘。' },
  { title: '专业牵引', body: '方向带依据，风险说清楚。' },
  { title: '行动落地', body: '把选择变成今天能做的一件事。' },
  { title: '心想事成', body: '你决定走哪条路，我们陪你推进。' },
]
</script>

<template>
  <div class="pf-portal">
    <header class="pf-header">
      <div class="pf-brand"><span class="pf-brand__mark" aria-hidden="true" /><strong>职引</strong><span class="pf-brand__school">{{ STUDENT.school }} · 生涯规划与就业指导</span></div>
      <div class="pf-header__controls"><slot name="portal-switch" /><RouterLink v-if="demo.state.authed" class="pf-account" to="/chat"><span class="pf-account__name">{{ STUDENT.name }} ·</span>进入<UiIcon name="arrow" :size="16" /></RouterLink><button v-else class="pf-login" @click="start">登录</button></div>
    </header>
    <main class="pf-main">
      <section class="pf-hero" aria-label="职引，给大学生的生涯规划与就业指导">
        <div class="pf-intro">
          <h1>问出方向，<br /><span>一路陪你。</span></h1>
          <p class="pf-description">给正在寻找方向的大学生。<br />通过对话看清自己，把职业选择变成具体行动。</p>
          <button class="pf-start" @click="start">开始第一个问题<UiIcon name="arrow" :size="22" /></button>
          <p class="pf-cost">首次约 5 分钟 · 无需填表 · 可随时中止</p>
        </div>
        <div class="pf-example"><PortalExample /></div>
      </section>
      <section class="pf-promises" aria-label="我们的四个承诺">
        <article v-for="p in promises" :key="p.title"><h2>{{ p.title }}</h2><p>{{ p.body }}</p></article>
      </section>
    </main>
    <footer class="pf-footer">
      <p>回答仅用于生成你自己的报告</p>
      <span>演示环境 · 数据为预置内容，页面交互真实可用</span>
    </footer>
  </div>
</template>

<style scoped>
/* 原生 Vue/CSS 的门户试稿，沿用项目配色、字体与圆角系统。 */
.pf-portal { min-height: 100dvh; background: var(--portal-bg); display: flex; flex-direction: column; isolation: isolate; }
.pf-header { width: 100%; max-width: 1320px; margin: 0 auto; height: 80px; padding: 0 40px; display: flex; justify-content: space-between; align-items: center; gap: 24px; flex: none; }
.pf-brand { display: flex; align-items: center; gap: 12px; }
.pf-brand__mark { width: 9px; height: 9px; border-radius: 2px; background: var(--brand-stripe); }
.pf-brand strong { font-size: var(--fs-20); font-weight: 600; letter-spacing: .12em; }
.pf-brand__school { border-left: 1px solid var(--c-border-strong); margin-left: 10px; padding-left: 22px; font-size: var(--fs-12); color: var(--c-text-3); }
.pf-header__controls { display: flex; align-items: center; gap: 24px; flex: none; }
.pf-account { display: inline-flex; align-items: center; gap: 12px; min-height: 42px; font-size: var(--fs-14); color: var(--c-text-2); white-space: nowrap; }
.pf-login { min-height: 42px; padding: 8px 20px; border: 1px solid var(--c-border-strong); border-radius: var(--r-md); font-size: var(--fs-14); }
.pf-login:hover, .pf-account:hover { color: var(--c-primary); }
.pf-main { width: 100%; max-width: 1240px; margin: auto; padding: 0 40px; }
.pf-hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, .95fr); gap: 86px; align-items: center; min-height: calc(100dvh - 278px); padding: 44px 0 56px; }
.pf-intro h1 { font-size: clamp(38px, 4.9vw, 68px); line-height: 1.22; letter-spacing: -.035em; font-weight: 600; }
.pf-intro h1 span { color: var(--c-primary); }
.pf-description { color: var(--c-text-2); font-size: var(--fs-16); line-height: 1.85; margin-top: 26px; max-width: 29em; }
.pf-start { display: inline-flex; align-items: center; justify-content: space-between; gap: 36px; margin-top: 36px; min-height: 56px; padding: 14px 24px; border-radius: var(--r-md); background: var(--c-primary); color: var(--c-on-primary); font-size: var(--fs-16); font-weight: 500; white-space: nowrap; transition: background-color 150ms var(--ease-out), transform 150ms var(--ease-out); }
.pf-start:hover { background: var(--c-primary-hover); }
.pf-start:active { transform: translateY(1px); }
.pf-cost { color: var(--c-text-3); font-size: var(--fs-12); margin-top: 18px; }
.pf-example { position: relative; z-index: 0; padding: 12px 0 0 12px; }
.pf-promises { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 30px; padding: 30px 0 32px; border-top: 1px solid var(--c-border-strong); }
.pf-promises h2 { font-size: var(--fs-14); font-weight: 600; line-height: 1.5; }
.pf-promises p { font-size: var(--fs-14); line-height: 1.8; color: var(--c-text-3); margin-top: 8px; }
.pf-footer { max-width: 1240px; width: 100%; margin: 0 auto; padding: 0 40px 26px; display: flex; justify-content: space-between; align-items: center; gap: 16px; font-size: var(--fs-12); color: var(--c-text-3); }
@media (min-width: 761px) and (prefers-reduced-motion: no-preference) {
  .pf-intro, .pf-example { animation: pf-arrive 420ms var(--ease-out) both; }
  .pf-example { animation-delay: 80ms; }
}
@keyframes pf-arrive { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
@media (max-width: 1100px) {
  .pf-header, .pf-main, .pf-footer { padding-left: 32px; padding-right: 32px; }
  .pf-hero { gap: 44px; }
}
@media (max-width: 760px) {
  .pf-header { height: 64px; padding: 0 24px; gap: 16px; }
  .pf-brand__school { display: none; }
  .pf-header__controls { gap: 10px; }
  .pf-account__name { display: none; }
  .pf-login { padding: 8px 12px; }
  .pf-account { gap: 8px; }
  .pf-main { padding: 0 24px; margin-top: 0; }
  .pf-hero { grid-template-columns: minmax(0, 1fr); min-height: 0; gap: 44px; padding: 36px 0 42px; }
  .pf-intro h1 { font-size: clamp(38px, 8.5vw, 56px); line-height: 1.2; letter-spacing: -.025em; }
  .pf-description { margin-top: 22px; font-size: var(--fs-16); max-width: 24em; }
  .pf-start { margin-top: 26px; min-height: 52px; gap: 30px; }
  .pf-cost { margin-top: 14px; }
  .pf-example { padding-left: 8px; }
  .pf-promises { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 26px 24px; padding: 28px 0; }
  .pf-promises p { font-size: var(--fs-14); }
  .pf-footer { align-items: flex-start; flex-direction: column; gap: 8px; padding: 0 24px 24px; }
}
@media (max-width: 360px) {
  .pf-header { padding: 0 20px; }
  .pf-main { padding: 0 20px; }
  .pf-footer { padding-left: 20px; padding-right: 20px; }
  .pf-description br { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .pf-start { transition: none; }
  .pf-start:active { transform: none; }
}
</style>
