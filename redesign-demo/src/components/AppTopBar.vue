<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { STUDENT } from '../data/student'
import { NAV_SECTIONS, sectionIndexForPath } from '../lib/nav'
import GradeSwitch from './GradeSwitch.vue'
import SkinSwitcher from './SkinSwitcher.vue'

/**
 * 顶栏：滚动时从"整条栏"丝滑变成"悬浮胶囊"。
 *
 * 参考（都是这次现查的）：
 *   · 21st.dev《Floating Navbars: The Pill and Its Three Problems》—— 悬浮胶囊的三个坑
 *       https://21st.dev/blog/react-floating-navbar-components
 *   · gitcode《Hallmark N10 Floating-on-scroll morph》—— 滚动时把导航栏变成悬浮胶囊
 *
 * 三个坑的对应处理：
 *   1. 「它浮在内容之上 → backdrop-filter 在滚动页面上每帧重绘，很贵」
 *      → 模糊只给 10px，底色接近不透明。可读性由底色保证，不由模糊保证；
 *        模糊只是让边缘软一点，所以它慢一点也不会"看不清"。
 *   2. 「它挡住内容 → 锚点会落在导航底下」
 *      → base.css 里给 :target 加了 scroll-margin-top（原话说"大多数站都漏了这条"）。
 *   3. 「它没有宽度 → 居中胶囊大约只放得下 4 个入口」
 *      → 我们 5 个地方全是 2–4 字短标签，宽度够；其余入口（大一到大四、设计规范）
 *        本来就不在导航里，在 ⌘K。
 *
 * 另外两条也照着做了：
 *   · 「它必须仍是 <nav> 加真实链接」→ 全部 RouterLink，不是调路由的按钮
 *   · 「最常见 bug 是菜单开在触发它的那条栏底下」→ 浮层层级 40 > 导航 20
 *
 * 滚动状态用 IntersectionObserver 盯一颗 1px 哨兵，不用 scroll 事件 ——
 * 原话是"scroll 监听跑在性能最敏感的那一帧上"。
 */

const route = useRoute()
const router = useRouter()
const emit = defineEmits<{ openPalette: [] }>()

const menuOpen = ref(false)
const floating = ref(false)
/** ?float=1 强制悬浮态：只给截图与评审用。设了它就不再让 observer 接管 ——
    否则 observer 的首次回调会立刻把值覆盖回 false（页面顶部确实不该悬浮），
    表现就是"参数传了没反应"。 */
const forcedFloat = ref(false)
const sentinel = ref<HTMLElement | null>(null)
let io: IntersectionObserver | null = null

const activeIndex = computed(() => {
  const i = sectionIndexForPath(route.path)
  return i >= 0 ? i : 0
})

const progress = computed(() => demo.use.profileProgress.value)
const progressRatio = computed(() =>
  progress.value.total ? progress.value.known / progress.value.total : 0,
)

onMounted(() => {
  // ?float=1：演示与截图用，直接进悬浮态（真实产品里没有这个口子）
  if (new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('float') === '1') {
    forcedFloat.value = true
    floating.value = true
    return
  }

  if (typeof IntersectionObserver === 'undefined' || !sentinel.value) return
  io = new IntersectionObserver(
    ([entry]) => {
      floating.value = !entry.isIntersecting
    },
    { threshold: 0 },
  )
  io.observe(sentinel.value)
})

onUnmounted(() => io?.disconnect())

function goSignIn() {
  router.push({ path: '/', query: { signin: '1' } })
}

function signOut() {
  menuOpen.value = false
  demo.signOut()
  router.push('/')
}
</script>

<template>
  <!-- 哨兵：1px，贴在页面最顶端。它离开视口 = 页面开始滚动 -->
  <div ref="sentinel" class="sentinel" aria-hidden="true" />

  <header class="nav" :class="{ 'nav--floating': floating, 'nav--forced': forcedFloat }">
    <div class="nav__inner">
      <!-- 表面与影各占一层：几何恒定，只有影的 opacity 与整体的 transform 在动 -->
      <span class="nav__surface" aria-hidden="true" />
      <span class="nav__ring" aria-hidden="true" />

      <RouterLink class="brand" to="/chat" aria-label="回到对话">
        <span class="brand__mark" aria-hidden="true" />
        <span class="brand__name">职引</span>
      </RouterLink>

      <!-- 五个地方，全是真链接 -->
      <nav class="links" aria-label="主导航">
        <RouterLink
          v-for="(s, i) in NAV_SECTIONS"
          :key="s.key"
          class="link"
          :class="{ 'link--on': i === activeIndex }"
          :to="s.to"
          :aria-current="i === activeIndex ? 'page' : undefined"
        >
          {{ s.label }}
        </RouterLink>
      </nav>

      <div class="utils">
        <button class="util" title="搜索与跳转" @click="emit('openPalette')">
          <span class="util__key">⌘K</span>
        </button>

        <GradeSwitch />
        <SkinSwitcher />

        <div
          class="account"
          @mouseenter="menuOpen = true"
          @mouseleave="menuOpen = false"
          @focusin="menuOpen = true"
          @focusout="menuOpen = false"
        >
          <button class="account__btn" :aria-expanded="menuOpen">
            <span v-if="demo.state.authed">{{ STUDENT.name.slice(0, 1) }}</span>
            <span v-else>未登录</span>
          </button>

          <div v-if="menuOpen" class="account__pop">
            <template v-if="demo.state.authed">
              <p class="account__name">
                {{ STUDENT.name }} · {{ demo.use.scenario.value.grade }} · {{ STUDENT.major }}
              </p>
              <p class="t-note">{{ STUDENT.school }}</p>
              <hr class="divider" style="margin: 12px 0" />
              <button class="btn btn--sm btn--block" @click="demo.resetDemo()">复位演示数据</button>
              <button class="btn btn--sm btn--block" style="margin-top: 8px" @click="signOut">
                退出登录
              </button>
            </template>
            <template v-else>
              <p class="account__name">还没登录</p>
              <button class="btn btn--sm btn--primary btn--block" style="margin-top: 12px" @click="goSignIn">
                登录
              </button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 画像完备度：嵌在容器底边，不额外占一行。表示"事实"，不是"你必须走到第几步" -->
    <RouterLink
      class="progress"
      to="/profile"
      :title="`学生档案：${progress.known} / ${progress.total} 条 —— 点开看还差哪几条`"
    >
      <span class="progress__fill" :style="{ '--v': progressRatio }" />
    </RouterLink>
  </header>
</template>

<style scoped>
/* 哨兵：正常流里的第一个元素。
   一开始写成 position:absolute，结果**在页面顶部就进了悬浮态** ——
   IntersectionObserver 的首次回调跑在布局稳定之前，绝对定位元素被报成"不可见"。
   放进正常流并用 margin-bottom 抵消那 1px，判定就准了，也不会改变页面高度。 */
.sentinel {
  width: 100%;
  height: 1px;
  margin-bottom: -1px;
  pointer-events: none;
}

.nav {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  flex: none;
  /* 到顶时是整条栏，不占额外高度：只有内层在变，所以不会引起布局跳动 */
  padding: 0 var(--sp-4);
}

/* 内层的**几何是恒定的**：始终一颗 920px 的胶囊，宽高、外距、内距、圆角都不动。
   形态差异（抬没抬起来、边和影有没有出现）全部用 transform 与 opacity 表达。

   上一版这里是 max-width / height / margin / padding / border-radius 一起过渡 ——
   按 review-animations 的标准那是**布局动画**：每次状态切换都要重算布局，滚动时最明显。
   现在这些值全部退出过渡，只留 transform 与 opacity 两个属性。 */
.nav__inner {
  position: relative;
  max-width: 920px;
  margin: 10px auto 0;
  height: 48px;
  display: flex;
  align-items: center;
  gap: var(--sp-5);
  padding: 0 var(--sp-3);
  transform: translateY(-10px);
  transition: transform var(--dur-3) var(--ease-out);
}

/* 表面：底、边、模糊、圆角。**
   刻意不参与过渡** —— 它一直就在，只是到顶时"还没浮起来"。
   模糊只负责边缘柔和，可读性由 92% 的底色承担。 */
.nav__surface {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: var(--r-pill);
  border: var(--bw-1) solid var(--c-border);
  background: color-mix(in srgb, var(--c-surface) 92%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  pointer-events: none;
}

/* 影单独一层：只用 opacity 淡入 —— 这样"浮起来"这件事也是纯 GPU 的 */
.nav__ring {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: var(--r-pill);
  box-shadow: var(--e-2);
  opacity: 0;
  transition: opacity var(--dur-2) ease;
  pointer-events: none;
}

.nav--floating .nav__inner {
  transform: translateY(0);
}

.nav--floating .nav__ring {
  opacity: 1;
}

/* 内容必须压在表面与影之上：它们是绝对定位元素，会盖住未定位的兄弟节点 */
.brand,
.links,
.utils {
  position: relative;
  z-index: 1;
}

/* ---- 品牌 ---- */
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: none;
  text-decoration: none;
}

.brand__mark {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--brand-stripe);
}

.brand__name {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.22em;
  color: var(--c-text);
}

/* 品牌全名常驻。
   上一版它在悬浮时用 max-width 收掉 —— 那也是布局动画。
   为了"只动 transform/opacity"，这个折叠直接不要了：少一个形变，也少一次重算。 */
.brand__title {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  white-space: nowrap;
}

/* ---- 五个地方 ---- */
.links {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  flex: 1;
  min-width: 0;
  justify-content: center;
}

.link {
  position: relative;
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 var(--sp-3);
  border-radius: var(--r-pill);
  font-size: var(--fs-14);
  color: var(--c-text-3);
  text-decoration: none;
  white-space: nowrap;
  transition:
    color var(--dur-1) ease,
    background-color var(--dur-2) var(--ease-out);
}

.link:hover {
  color: var(--c-text);
  text-decoration: none;
  background: var(--c-surface-3);
}

/* 选中态是一颗实心胶囊，不是下划线 ——
   胶囊里再画一条下划线会显得脏；这一条也和"这是浮动胶囊"这个形态一致。 */
.link--on {
  color: var(--c-on-primary);
  background: var(--c-primary);
  font-weight: var(--fw-medium);
}

.link--on:hover {
  color: var(--c-on-primary);
  background: var(--c-primary-hover);
}

/* ---- 工具区 ---- */
.utils {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: none;
}

.util {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--btn-h-md);
  min-width: 38px;
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  transition:
    border-color var(--dur-1) ease,
    color var(--dur-1) ease;
}

.util:hover {
  border-color: var(--c-border-strong);
  color: var(--c-text);
}

.util__key {
  font-family: var(--font-mono);
  font-size: var(--fs-12);
}

.account {
  position: relative;
  padding-bottom: 6px;
  margin-bottom: -6px;
}

.account__btn {
  min-width: 32px;
  height: 32px;
  padding: 0 var(--sp-2);
  border-radius: var(--r-pill);
  background: var(--c-surface-3);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  transition: background-color var(--dur-1) ease;
}

.account__btn:hover {
  background: var(--c-border);
}

.account__pop {
  position: absolute;
  top: calc(100% + 2px);
  right: 0;
  width: 250px;
  padding: var(--sp-4);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--e-3);
  /* 浮层必须高于导航：最常见 bug 是菜单开在触发它的那条栏底下 */
  z-index: calc(var(--z-sticky) + 30);
  transform-origin: top right;
  animation: pop-in var(--dur-2) var(--ease-out) both;
}

@keyframes pop-in {
  from {
    opacity: 0;
    transform: scale(0.97);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* 强制悬浮态时不做形变过渡：截图要一次到位，不要拍到中间帧 */
.nav--forced .nav__inner,
.nav--forced .brand__title,
.nav--forced .progress {
  transition: none;
}

.account__name {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

/* ---- 进度线 ---- */
/* 恒定 920px，不再随悬浮态变宽窄（那也是一次布局动画）。
   填充用 transform: scaleX 表达 —— 这是纯 GPU 的。 */
.progress {
  display: block;
  /* 宽度跟**内容列**对齐，不是一个全页固定值：对话页中栏 760px，
     其它页是"主栏 + 侧栏"的整幅。由 App.vue 按路由给值（--progress-max）。 */
  max-width: var(--progress-max, 920px);
  margin: 0 auto;
  height: 2px;
  background: var(--c-border);
}

.progress__fill {
  display: block;
  height: 100%;
  background: var(--c-primary);
  transform-origin: left center;
  transform: scaleX(var(--v, 0));
  transition: transform var(--dur-4) var(--ease-out);
}

@media (max-width: 1080px) {
  .brand__title {
    display: none;
  }
}

@media (max-width: 760px) {
  .links {
    gap: 0;
  }

  .link {
    padding: 0 var(--sp-2);
    font-size: var(--fs-14);
  }
}

/* 减少动效：形态变化直接切，不做过渡 */
@media (prefers-reduced-motion: reduce) {
  .nav__inner,
  .brand__title,
  .progress {
    transition: none;
  }
}
</style>
