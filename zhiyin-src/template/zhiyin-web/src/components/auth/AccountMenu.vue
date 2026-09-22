<script setup lang="ts">
/**
 * 左上角那一个按钮 —— 品牌与身份合并成同一个入口。
 *
 * 上一版把"你是谁"和"钥匙"分在两处：顶栏写着一个名字，退出登录是旁边一颗孤零零的按钮。
 * 现在合成一颗：点它就打开账号面板（身份 / 设置 / 退出），这也是用户熟悉的那种位置。
 *
 * 面板贴着按钮落下，用的是全站那张玻璃薄片（.sheet）；点外面、按 ESC 都能收回。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { useEscLayerManual } from '@/composables/useEscLayer'
import { initialOf, roleLabel } from '@/lib/identity'
import { authToken } from '@/api/client'

const session = useSessionStore()
const router = useRouter()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

/*
 * 顶栏那一颗按钮要如实回答"现在是谁"。
 *
 * 两个真问题都在这里：
 *   · 兜底文案原本写的是 `'已登录'` —— 于是**没登录时它也说自己已登录**，
 *     用户看到的就是"怎么还有个已登录的名字"；
 *   · 令牌被清掉（过期 / 换库）之后若还用内存里那份 identity，
 *     顶栏会挂着一个已经失效的旧名字。
 * 判断依据是**令牌 + 身份同时在**，缺一个就当没登录。
 */
const signedIn = computed(() => !!authToken() && !!session.identity)
const name = computed(() => (signedIn.value ? session.identity?.nickname || '' : ''))
const role = computed(() => (signedIn.value ? roleLabel(session.identity?.role) : '未登录'))
const face = computed(() => (signedIn.value ? initialOf(name.value) : '·'))

const esc = useEscLayerManual(() => (open.value = false))

watch(open, (on) => (on ? esc.activate() : esc.deactivate()))

function toggle() {
  // 没登录就别展开"账号面板" —— 那里面全是"当前账号 / 退出登录"，
  // 对一个还没登录的人没有一处用得上。直接掀登录层。
  if (!signedIn.value) {
    session.openAuth()
    return
  }
  open.value = !open.value
}

/** 点面板以外的地方就收回 —— 这是下拉面板，不该要用户去找关闭键 */
function onPointerDown(e: PointerEvent) {
  if (!open.value) return
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('pointerdown', onPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onPointerDown))

function signOut() {
  open.value = false
  session.signOut()
  router.push('/portal')
}

function backToPortal() {
  open.value = false
  router.push('/portal')
}
</script>

<template>
  <div ref="root" class="account">
    <button class="trigger" type="button" :aria-expanded="open" aria-haspopup="dialog" @click="toggle">
      <span class="brand">
        <span class="brand__mark" aria-hidden="true" />
        <span class="brand__name">职引</span>
      </span>

      <span class="rule trigger__rule" aria-hidden="true" />

      <span class="face" aria-hidden="true">{{ face }}</span>
      <span class="who">
        <span class="who__name">{{ signedIn ? name : '去登录' }}</span>
        <span class="label who__meta">{{ role }}</span>
      </span>

      <svg class="caret" width="10" height="10" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M2.6 4.4 6 7.8l3.4-3.4" fill="none" stroke="currentColor" stroke-width="1.6"
              stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <transition name="drop">
      <div v-if="open" class="panel sheet" role="dialog" aria-label="账号">
        <!-- 谁在用：头像 + 名字 + 角色，下面一行是数据归属 -->
        <header class="head">
          <span class="face face--lg" aria-hidden="true">{{ face }}</span>
          <div class="head__who">
            <span class="head__name">{{ name }}</span>
            <span class="label head__role">{{ role }}</span>
          </div>
          <span class="mono head__id">当前账号</span>
        </header>

        <p class="note label">画像、方案与对话按这个账号隔离；退出只清掉这台设备上的登录状态。</p>

        <div class="group">
          <span class="label group__k">这一台机器上</span>
          <ul class="rows">
            <li>
              <button class="row row--go" type="button" @click="backToPortal">
                <span>回门户看看</span>
                <span class="mono row__tag row__tag--go">→</span>
              </button>
            </li>
          </ul>
        </div>

        <button class="quit" type="button" @click="signOut">退出登录</button>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.account { position: relative; }

/* ── 触发按钮：品牌 + 身份，一整块可点 ────────────────────────── */
.trigger {
  display: flex; align-items: center; gap: 10px;
  /* 与顶栏同一条基线：34px 是"有头像但不过分占高"的那一档 */
  height: 34px; padding: 0 10px 0 9px;
  border: var(--bw) solid transparent;
  border-radius: var(--r-pill);
  transition: border-color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out);
}
.trigger:hover { border-color: var(--line-2); background: var(--fill-hover); }
.trigger[aria-expanded="true"] { border-color: var(--line-3); background: var(--fill-hover); }

.brand { display: flex; align-items: center; gap: 9px; }
.brand__mark {
  width: 12px; height: 12px; border-radius: 3px; background: var(--accent);
  /* 品牌方块：一小块平涂的墨，不要光晕 */
  transform: rotate(-4deg);
}
.brand__name { font-weight: 600; letter-spacing: 0.06em; }
.trigger__rule { width: 1px; height: 18px; }

/* 头像：一块浅绿底 + 深绿字，和强调色同源，不做第二种颜色 */
.face {
  width: 26px; height: 26px; flex: 0 0 auto;
  display: grid; place-items: center;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12.5px; font-weight: 600;
}
.face--lg { width: 38px; height: 38px; font-size: 16px; }

.who { display: flex; align-items: baseline; gap: var(--s2); min-width: 0; }
.who__name { font-size: var(--t-sm); }
.who__meta { color: var(--ink-3); }
.caret { color: var(--ink-3); transition: transform var(--dur-exit) var(--ease-out); }
.trigger[aria-expanded="true"] .caret { transform: rotate(180deg); }

/* ── 面板 ──────────────────────────────────────────────────────── */
.panel {
  position: absolute; left: 0; top: calc(100% + 10px);
  z-index: var(--z-float);
  width: 300px;
  padding: var(--s4);
  display: flex; flex-direction: column; gap: var(--s3);
  border-radius: var(--r-md);
  animation: sheet-in 300ms var(--ease-expo) both;
}

.head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: var(--s3); }
.head__who { display: grid; gap: 1px; min-width: 0; }
.head__name { font-size: var(--t-body); font-weight: 600; letter-spacing: -0.01em; }
.head__id { color: var(--ink-faint); }

.note {
  color: var(--ink-3); line-height: 1.6;
  padding-bottom: var(--s3);
  border-bottom: 1px solid var(--line-1);
}

.group { display: grid; gap: 4px; }
.group__k { color: var(--ink-faint); }
.rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 1px; }
.row {
  width: 100%;
  display: flex; align-items: center; justify-content: space-between; gap: var(--s3);
  padding: 8px 10px;
  border-radius: var(--r-sm);
  font-size: var(--fs-small); color: var(--ink-dim);
  text-align: left;
  transition: background var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out);
}
.row--go:hover { background: var(--fill-hover); color: var(--ink); }
.row__tag { color: var(--ink-faint); }
.row__tag--go { color: var(--ink-3); }
.row--go:hover .row__tag--go { color: var(--accent); }

.quit {
  height: 36px; margin-top: var(--s1);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-pill);
  font-size: var(--fs-small); font-weight: 500; color: var(--ink-2);
  transition: border-color var(--dur-micro) var(--ease-out),
              color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out);
}
.quit:hover { border-color: var(--warn); color: var(--warn); background: rgba(183, 77, 26, 0.05); }

.drop-enter-active { transition: opacity 180ms var(--ease-out), transform 240ms var(--ease-expo); }
.drop-leave-active { transition: opacity 130ms var(--ease-in), transform 130ms var(--ease-in); }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-8px) scale(0.985); }

@media (max-width: 720px) {
  .who { display: none; }
}
</style>
