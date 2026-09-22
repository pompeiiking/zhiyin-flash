<script setup lang="ts">
import { watch } from 'vue'
import { useEscLayerManual } from '@/composables/useEscLayer'
import { useSessionStore } from '@/stores/session'

// 第 3 层：依据 / 时间轴。
//
// 它的职责是"不打断当前动作地把依据拿出来"，所以它不能是一堵从天花板到地板的墙 ——
// 上一版整条右栏铺满、颜色接近纯黑，读起来就是在页面上又开了一个黑框。
//
// 这一版：一张浮在右下角的玻璃片（最大 72vh，四周都留出页面的边），
// 从未固定角展开、关闭时收回同一个角；条目之间用发丝线分开，不再一条一个盒子。
//
// 它在层级上比覆盖层更深，所以 z 值单独抬高，不用 --z-drawer（那个是浮窗层用的）。
const session = useSessionStore()

// 这个组件是常驻的，只有里面的面板是 v-if ——
// 所以 Esc 归属权要跟着"面板开着没有"来开关，而不是跟着组件的挂载。
const esc = useEscLayerManual(() => {
  if (session.drawer) session.closeDrawer()
})

watch(
  () => session.drawer,
  (open) => (open ? esc.activate() : esc.deactivate()),
  { immediate: true },
)

type AnyItem = Record<string, unknown>

const isTimeline = (item: AnyItem) => 'actor' in item && 'what' in item
</script>

<template>
  <Transition name="rise">
    <aside
      v-if="session.drawer"
      class="drawer sheet"
      role="dialog"
      aria-modal="false"
      aria-label="依据"
    >
      <span class="drawer__spine" aria-hidden="true" />

      <header class="drawer__head">
        <div class="drawer__titles">
          <span class="label">依据</span>
          <h2 class="drawer__title">{{ session.drawer.title }}</h2>
          <p class="mono drawer__sub">{{ session.drawer.subtitle }}</p>
        </div>
        <button class="btn ghost" type="button" @click="session.closeDrawer()">关闭</button>
      </header>

      <ol class="list">
        <li v-for="(item, i) in (session.drawer.items as AnyItem[])" :key="i">
          <template v-if="isTimeline(item)">
            <div class="tl">
              <span class="mono tl__time">{{ item.time }}</span>
              <span class="tl__actor">{{ item.actor }}</span>
              <span class="tl__what">{{ item.what }}</span>
              <span class="mono tl__basis">{{ item.basis }}</span>
              <p v-if="item.handoff" class="tl__handoff">
                <span class="label">显式交接</span>{{ item.handoff }}
              </p>
            </div>
          </template>
          <template v-else>
            <div class="ev">
              <div class="ev__top">
                <span class="ev__source">{{ item.source }}</span>
                <span class="label ev__conf">把握 {{ Number(item.confidence ?? 0).toFixed(2) }}</span>
              </div>
              <p class="ev__detail">{{ item.detail }}</p>
              <span v-if="item.at" class="mono ev__at">{{ item.at }}</span>
            </div>
          </template>
        </li>
      </ol>

      <footer class="drawer__foot">
        <span class="label">结论会随新信息变化；变化时会告诉你哪一条变了</span>
      </footer>
    </aside>
  </Transition>
</template>

<style scoped>
.drawer {
  position: fixed;
  right: var(--s5);
  bottom: var(--s5);
  width: min(430px, 92vw);
  max-height: min(72vh, 620px);
  /* 比覆盖层更深一层：它是"在你现在看的东西旁边，再摊开一张" */
  z-index: calc(var(--z-overlay) + 6);
  display: flex; flex-direction: column;
  /* 从右下角那个固定的角展开，关闭也收回同一个角 —— 有来有回 */
  transform-origin: 100% 100%;
  box-shadow: var(--e-4), var(--inner-hi);
}

/* 一条"书脊"：暗示这是一叠可以继续往下翻的东西 */
.drawer__spine {
  position: absolute; left: 0; top: var(--s6); bottom: var(--s6); width: 2px;
  border-radius: 2px;
  background: linear-gradient(180deg, var(--accent), transparent 82%);
  opacity: 0.55;
}

.drawer__head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s4);
  padding: var(--s5) var(--s5) var(--s4);
  border-bottom: 1px solid var(--line-1);
}
.drawer__titles { min-width: 0; display: grid; gap: 3px; }
.drawer__title { font-size: var(--t-h3); letter-spacing: var(--track-h); margin-top: 4px; }
.drawer__sub { color: var(--ink-3); text-transform: none; letter-spacing: 0.04em; }

.list {
  list-style: none; margin: 0;
  padding: var(--s2) var(--s5) var(--s4);
  overflow: auto; flex: 1;
}
/* 发丝分隔，而不是一条一个盒子 */
.list li { border-bottom: 1px solid var(--line-1); }
.list li:last-child { border-bottom: 0; }

.ev {
  display: grid; gap: 6px;
  padding: var(--s4) var(--s2);
  margin: 0 calc(var(--s2) * -1);
  border-radius: var(--r-sm);
  transition: background var(--dur-fast) var(--ease-out);
}
.ev:hover { background: var(--fill-subtle); }
.ev__top { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.ev__source { font-size: var(--fs-small); color: var(--accent); }
.ev__conf { color: var(--ink-faint); }
.ev__detail { font-size: var(--fs-small); color: var(--ink); }
.ev__at { color: var(--ink-faint); }

.tl {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 2px var(--s3);
  padding: var(--s4) var(--s2);
  margin: 0 calc(var(--s2) * -1);
  border-radius: var(--r-sm);
  transition: background var(--dur-fast) var(--ease-out);
}
.tl:hover { background: var(--fill-subtle); }
.tl__time { grid-row: span 3; color: var(--ink-faint); }
.tl__actor { font-size: var(--fs-small); color: var(--accent); }
.tl__what { font-size: var(--fs-small); color: var(--ink); }
.tl__basis { color: var(--ink-faint); }
.tl__handoff {
  grid-column: 1 / -1;
  margin-top: var(--s2); padding-top: var(--s2);
  border-top: 1px dashed var(--line-2);
  font-size: var(--fs-small); color: var(--ink-dim);
}
.tl__handoff .mono { display: block; margin-bottom: 2px; color: var(--fact); }

.drawer__foot {
  padding: var(--s3) var(--s5) var(--s4);
  border-top: 1px solid var(--line-1);
  color: var(--ink-3);
}

/* 从右下角长出来 / 收回右下角（退出比进入快，约 60%） */
.rise-enter-active { transition: transform 420ms var(--ease-expo), opacity 260ms var(--ease-out); }
.rise-leave-active { transition: transform 240ms var(--ease-in), opacity 180ms var(--ease-out); }
.rise-enter-from, .rise-leave-to {
  opacity: 0;
  transform: translate(26px, 20px) scale(0.965);
}
</style>
