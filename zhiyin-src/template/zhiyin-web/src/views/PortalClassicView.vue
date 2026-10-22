<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ref, onMounted, onUnmounted } from 'vue'
import { demo } from '../store'
import { useDisplayName } from '../lib/display-name'
/** 旧门户动态背景恢复自 60d4e4f（2026-10-16 用户确认）。
 * 保留原版光晕与路径节点；按用户反馈移除横向扫光和竖线网格，减少动态效果时保留静态背景。
 * 门户是用户明确要求保留的版本，不套用工作区的装饰动效限制。
 */
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
const reducedMotion = ref(motionPreference.matches)
function syncMotionPreference(event: MediaQueryListEvent) { reducedMotion.value = event.matches }
onMounted(() => motionPreference.addEventListener('change', syncMotionPreference))
onUnmounted(() => motionPreference.removeEventListener('change', syncMotionPreference))

const router = useRouter()
const route = useRoute()
const displayName = useDisplayName()

function start() {
  if (demo.state.authed) router.push('/chat')
  else router.push({ path: '/', query: { ...route.query, signin: '1' } })
}

/** 产品的四条承诺，一左一右 */
const LEFT_WORDS = ['持续陪伴', '专业牵引']
const RIGHT_WORDS = ['行动落地', '心想事成']

/** 恢复旧门户四项产品介绍；采用正式表述，不由通用信任文案替换。 */
const what = [
  {
    title: '循序咨询',
    body: '通过逐步对话梳理个人情况与发展需求，支持按需补充资料、分次开展咨询。',
  },
  {
    title: '结论有据',
    body: '结合个人资料与职业信息开展分析，呈现已有依据，并保留待核对事项。',
  },
  {
    title: '行动落实',
    body: '将发展目标分解为阶段任务，明确行动重点与时间安排，持续记录执行进展。',
  },
  {
    title: '自主选择',
    body: '比较不同方向的条件、差异与风险，为自主决策及后续调整提供参考。',
  },
]
</script>

<template>
  <div class="portal">
    <div class="bg" aria-hidden="true">
      <div class="bg__glow bg__glow--a" />
      <div class="bg__glow bg__glow--c" />
      <div class="bg__glow bg__glow--b" />

      <svg class="bg__paths" viewBox="0 0 1200 700" preserveAspectRatio="xMidYMid slice">
        <defs>
              <path id="zp1" d="M-200,520 C 180,470 360,545 640,450 S 1000,345 1320,310" />
          <path id="zp2" d="M-200,600 C 200,575 420,615 740,520 S 1020,435 1320,420" />
        </defs>
        <use class="bg__curve" href="#zp1" />
        <use class="bg__curve bg__curve--dim" href="#zp2" />
        <circle v-if="!reducedMotion" class="bg__node" r="3">
          <animateMotion dur="24s" repeatCount="indefinite" calcMode="linear">
            <mpath href="#zp1" />
          </animateMotion>
        </circle>
        <circle v-if="!reducedMotion" class="bg__node bg__node--dim" r="2.5">
          <animateMotion dur="38s" repeatCount="indefinite" calcMode="linear" begin="-14s">
            <mpath href="#zp1" />
          </animateMotion>
        </circle>
        <circle v-if="!reducedMotion" class="bg__node bg__node--accent" r="2.5">
          <animateMotion dur="31s" repeatCount="indefinite" calcMode="linear" begin="-6s">
            <mpath href="#zp2" />
          </animateMotion>
        </circle>
      </svg>

      <div class="bg__grain" />
    </div>

    <!-- 两侧竖排的四句承诺 -->
    <div class="sides" aria-hidden="true">
      <div class="side side--left">
        <p v-for="w in LEFT_WORDS" :key="w" class="side__word">{{ w }}</p>
      </div>
      <div class="side side--right">
        <p v-for="w in RIGHT_WORDS" :key="w" class="side__word">{{ w }}</p>
      </div>
    </div>

    <header class="top">
      <!-- 品牌回左上角：这是全页最先被扫到的位置，存在感靠位置拿，不靠字号 -->
      <div class="top__brand">
        <span class="top__mark" aria-hidden="true" />
        <span class="top__name">职引</span>
        <span class="top__divider" />
        <span class="top__context">河北大学<span class="top__context-detail"> · 生涯规划与就业指导</span></span>
      </div>
      <div class="pc-controls"><RouterLink v-if="demo.state.authed" class="top__account" to="/chat"><span class="pc-account-name">{{ displayName }} · </span>进入工作空间</RouterLink><button v-else class="top__login" @click="start">登录</button></div>
    </header>

    <main class="main">
      <section class="hero">
        <!--
          横排一行（评审要求）。两行改一行会让顶部重新变成"一道横条"，
          所以字号收到 74px —— 一行 666px 宽，明显窄于容器 1160px，
          读起来仍是"一簇字"而不是"一条线"；底部通栏那道横也继续压着页面最底边，
          不参与中部构图。
        -->
        <h1 class="hero__headline">问出方向，一路陪你</h1>

        <p class="hero__pitch">围绕专业选择、职业方向与行动规划，提供持续支持</p>

        <p class="hero__what">
          <span class="hero__intro">面向大学生的生涯规划与就业指导平台。</span>通过对话梳理个人情况，
          结合已有资料形成分析报告，协助制定并推进阶段行动。
        </p>

        <button class="hero__cta" @click="start">开始生涯咨询</button>

        <p class="hero__cost">
          按需补充资料 · 支持分次咨询 · 可随时结束本次对话
        </p>
      </section>
    </main>

    <!-- 四项服务介绍延续页面底色，以轻分隔收尾，避免形成厚重的灰色底栏。 -->
    <section class="band" aria-label="平台服务特点">
      <div class="band__inner">
        <ul class="band__list">
          <li v-for="w in what" :key="w.title" class="item">
            <p class="item__title">{{ w.title }}</p>
            <p class="item__body">{{ w.body }}</p>
          </li>
        </ul>
      </div>
    </section>

    <!--
      门户**只有一个入口**（评审要求）：这里不再放「设计规范」链接。
      规范页仍在 `#/spec`，评审直接敲 URL 就能打开（README 里也写了），
      但它不该在门户上多出第二个可点的东西 —— 门户只回答"从哪开始"。
    -->
    <footer class="foot">
      <span class="foot__note">明确发展方向，推进具体行动</span>
    </footer>
  </div>
</template>

<style scoped>
.portal {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--portal-bg);
  overflow: hidden;
}

/* ===========================================================================
 * 背景
 * ======================================================================== */
.bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.bg__glow {
  position: absolute;
  background: var(--hero-glow);
  /* 模糊掉边缘：加了模糊之后，它读起来才是"一片光"，而不是"一块浅蓝的斑"。
     模糊半径要比光斑本身小一个量级，否则会糊成一片灰。 */
  filter: blur(60px);
}

.bg__glow--a {
  left: -14%;
  top: -14%;
  width: 1060px;
  height: 700px;
  animation: drift-a 22s var(--ease-in-out) infinite alternate;
}

.bg__glow--b {
  right: -18%;
  bottom: -18%;
  width: 940px;
  height: 640px;
  opacity: 0.85;
  animation: drift-b 30s var(--ease-in-out) infinite alternate;
}

/* 居中那片不漂移：前两片在左上与右下，中间一条会是纯白，视觉上就成了"上下两块空" */
.bg__glow--c {
  left: 50%;
  top: 26%;
  width: 1240px;
  height: 640px;
  transform: translateX(-50%);
}

@keyframes drift-a {
  from {
    transform: translate3d(0, 0, 0);
  }
  to {
    transform: translate3d(16%, 12%, 0);
  }
}

@keyframes drift-b {
  from {
    transform: translate3d(0, 0, 0);
  }
  to {
    transform: translate3d(-18%, -10%, 0);
  }
}

/* 路径与节点：极淡，只做"这条路一直在走"的暗示，不抢文字 */
.bg__paths {
  -webkit-mask-image: linear-gradient(to bottom, #000 65%, transparent 84%);
  mask-image: linear-gradient(to bottom, #000 65%, transparent 84%);
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.bg__curve {
  fill: none;
  stroke: var(--c-border-strong);
  stroke-width: 1;
  opacity: 0.75;
}

.bg__curve--dim {
  opacity: 0.45;
}

.bg__node {
  fill: var(--c-primary-brand);
  opacity: 0.55;
}

.bg__node--dim {
  opacity: 0.3;
}

.bg__node--accent {
  fill: var(--brand-stripe);
  opacity: 0.35;
}

/* 颗粒（思路取自 Fffuel 的 nnnoise）。**刻意不动** —— 它压在文字底下，动起来字会发飘 */
.bg__grain {
  position: absolute;
  inset: 0;
  opacity: 0.5;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.045'/%3E%3C/svg%3E");
}

/* ===========================================================================
 * 两侧竖排的四句承诺
 * ======================================================================== */
.sides {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.side {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}

.side--left {
  left: clamp(20px, 3vw, 56px);
}

.side--right {
  right: clamp(20px, 3vw, 56px);
  align-items: flex-end;
}

/* 竖排：中文原有的排法。放在一个高校的产品上不突兀，
   而且正好用掉左右两条空白带 —— 它是氛围里的承诺，不抢正文，但也不该轻到看不见。
   不加上下边框：加了每条都像一根被封口的短竖条，反而更像版面上的笔画。 */
.side__word {
  writing-mode: vertical-rl;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  letter-spacing: 0.45em;
  /* 用 --c-text-3 而不是 --c-text-4：后者在令牌注释里写着"仅图标/分隔符，不当文字用"，
     拿它排 14px 的中文是越界（虽然肉眼能看见，但白底对比度只有 2.5:1）。
     text-3 对纸面 5.36:1，过 AA。 */
  color: var(--c-text-3);
}

/* 横向空间不够时收起 —— 竖排挤内容比留白更糟。断点见文件末尾（统一为 1120px）。 */

/* ===========================================================================
 * 顶栏
 * ======================================================================== */
.top {
  position: relative;
  /* 3 而不是 2：`.main` 与 `.band` 都是 `z-index: 2`，DOM 里排在 `.top` 之后，
     于是同层里后来的赢 —— 顶栏里 slot 的「工作空间设置」下拉（PortalView 给的 z-index:10，
     但它在 `.top` 这个层叠上下文里）会被 `.main` 盖住，按钮点不动。抬一层即可。 */
  z-index: 3;
  height: var(--w-topbar);
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: 0 var(--sp-6);
}

.top__brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.pc-controls { display: flex; align-items: center; gap: 24px; flex: none; }

.top__mark {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--brand-stripe);
}

.top__name {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.22em;
}

.top__divider {
  width: 1px;
  height: 12px;
  margin: 0 var(--sp-2);
  background: var(--c-border-strong);
}

.top__context {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.top__account,
.top__login {
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.top__login {
  padding: 0 var(--sp-3);
  height: var(--btn-h-sm);
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: var(--btn-radius);
  transition:
    border-color var(--dur-1) ease,
    color var(--dur-1) ease;
}

@media (hover: hover) and (pointer: fine) {
  .top__login:hover {
    border-color: var(--c-primary);
    color: var(--c-primary);
  }
}

/* ===========================================================================
 * 主区
 * ======================================================================== */
.main {
  position: relative;
  z-index: 2;
  flex: 1;
  width: 100%;
  max-width: 1160px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: var(--sp-4) var(--sp-6) var(--sp-5);
}

.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.hero__headline {
  /* 一行排下"问出方向，一路陪你"（9 个字符位）：4.6vw 在 1600 屏上约 74px，
     净宽 666px，容器 1160px —— 留得住两边的余量，不会顶到边。 */
  font-size: clamp(28px, 4.6vw, 74px);
  font-weight: var(--fw-semibold);
  line-height: 1.15;
  letter-spacing: -0.02em;
}

/* 宣传词：解决"这件事对我意味着什么" */
.hero__pitch {
  margin-top: var(--sp-4);
  font-size: clamp(16px, 1.5vw, 21px);
  font-weight: var(--fw-medium);
  color: var(--c-text);
  letter-spacing: 0.01em;
}

/* 定位：解决"这是什么、给谁用" */
.hero__what {
  margin-top: var(--sp-5);
  max-width: 34em;
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: 1.85;
}

.hero__cta {
  margin-top: var(--sp-6);
  height: 52px;
  padding: 0 var(--sp-9);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  box-shadow: var(--e-2);
  transition:
    background-color var(--dur-1) ease,
    transform var(--dur-1) var(--ease-out),
    box-shadow var(--dur-1) ease;
}

.hero__cta:active {
  transform: scale(var(--btn-press));
}

@media (hover: hover) and (pointer: fine) {
  .hero__cta:hover {
    background: var(--c-primary-hover);
    box-shadow: var(--e-3);
  }
}

.hero__cost {
  margin-top: var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* 服务介绍与主视觉共用底色，用渐隐分隔线保留清楚的阅读边界。 */
.band {
  position: relative;
  z-index: 2;
  flex: none;
  background: transparent;
}
.band::before {
  content: '';
  display: block;
  height: 1px;
  width: min(1112px, calc(100% - 48px));
  margin: 0 auto;
  background: linear-gradient(90deg, transparent, var(--c-border) 16%, var(--c-border) 84%, transparent);
}
.band__inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: 28px var(--sp-6);
}

.band__list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-5);
}

.item__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text);
  line-height: 1.5;
}

.item__body {
  margin-top: var(--sp-1);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: 1.75;
}

/* ===========================================================================
 * 页脚
 * ======================================================================== */
.foot {
  position: relative;
  z-index: 2;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-4);
  padding: 0 var(--sp-6) var(--sp-6);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.foot__note {
  color: var(--c-text-3);
}

/* 减少动态效果：保留背景与正文，停止 CSS 动画并移除移动节点。 */
@media (prefers-reduced-motion: reduce) {
  .bg__glow { animation: none; }

  .top__login,
  .hero__cta {
    transition: none;
  }

  .hero__cta:active {
    transform: none;
  }
}

/* 平板保持两列介绍；手机调整阅读顺序和触控尺寸。 */
@media (max-width: 1120px) {
  .sides {
    display: none;
  }

  .band__list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--sp-5) var(--sp-4);
  }
}

@media (max-width: 768px) {
  .portal { min-height: 100svh; }
  .top { height: 64px; padding: 0 20px; gap: 12px; }
  .top__brand { gap: 6px; }
  .top__divider { margin: 0 6px; }
  .top__context { white-space: nowrap; }
  .pc-controls { gap: 0; }
  .pc-account-name, .top__context-detail { display: none; }
  .top__account, .top__login { display: inline-flex; align-items: center; min-height: 44px; font-size: 13px; }
  .main { flex: none; padding: 28px 22px 30px; }
  .hero__headline { font-size: clamp(28px, 7.7vw, 36px); line-height: 1.25; }
  .hero__pitch { max-width: 24em; margin-top: 16px; font-size: 15px; line-height: 1.75; text-wrap: balance; }
  .hero__what { max-width: 25em; margin-top: 18px; line-height: 1.8; text-wrap: pretty; }
  .hero__intro { display: none; }
  .hero__cta { width: 100%; max-width: 344px; min-height: 52px; margin-top: 24px; font-size: 18px; }
  .hero__cost { max-width: 30em; margin-top: 14px; line-height: 1.8; text-wrap: balance; }
  .band__inner { padding: 24px 22px 26px; }
  .band::before { width: calc(100% - 44px); }
  .band__list { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px 22px; }
  .item__title { font-size: 14px; }
  .item__body { margin-top: 8px; font-size: 13px; line-height: 1.75; }
  .foot { margin-top: auto; padding: 12px 22px calc(20px + env(safe-area-inset-bottom)); }
  /* 路径在主视觉内淡出，避免穿过窄屏服务介绍的正文。 */
  .bg__paths { height: 440px; max-height: 58%; }
}
@media (max-width: 359px) {
  .top { padding: 0 16px; }
  .top__brand { gap: 4px; }
  .top__divider { margin: 0 4px; }
  .top__name { font-size: 18px; }
  .main { padding: 24px 18px 26px; }
  .band__inner { padding: 22px 18px; }
  .band__list { grid-template-columns: minmax(0, 1fr); gap: 20px; }
  .item { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 14px; }
  .item__body { margin-top: 0; }
}
</style>
