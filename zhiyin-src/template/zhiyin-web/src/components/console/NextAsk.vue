<script setup lang="ts">
/**
 * "下一步"的那颗按钮 —— AI 指哪，这里就是哪儿。
 *
 * 两种形态，同一个动作：
 *   · 完整形态放在顶栏和对话窗口里：谁在等、等什么、点一下做什么；
 *   · 紧凑形态放进各个气泡：只留一个动词，让"这里能点"这件事不用找。
 *
 * 两种形态读的是**同一个** `session.nextAsk`，所以同一时刻全站只有一句"下一步"。
 * 这也是"AI 在编排"和"每个组件自己写文案"的分界：前者用户知道该听谁的，后者不知道。
 */
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import type { Ask } from '@/lib/asks'

const props = withDefaults(
  defineProps<{
    /** 不传就用全局那一个 —— 绝大多数情况都该不传 */
    ask?: Ask | null
    compact?: boolean
  }>(),
  { ask: null, compact: false }
)

const session = useSessionStore()
const current = computed(() => props.ask ?? session.nextAsk)

function run() {
  const ask = current.value
  if (!ask) return
  const target = ask.target
  if (target.to === 'chat') {
    session.askChat(target.prompt, target.options.map((o) => (typeof o === 'string' ? o : o.label)))
  } else if (target.to === 'tasks') {
    session.openOverlay('tasks')
  } else {
    session.openDrawer(target.title, `${ask.who} 推给你的下一步`, [
      { source: ask.who, detail: target.body, confidence: 1, at: '现在' },
    ])
  }
}
</script>

<template>
  <button
    v-if="current"
    class="ask"
    :class="{ 'ask--compact': props.compact }"
    type="button"
    :title="current.why"
    @click.stop="run"
  >
    <span class="ask__dot" aria-hidden="true" />

    <template v-if="!props.compact">
      <span class="ask__who label">{{ current.who }} 在等</span>
      <span class="ask__what">{{ current.label }}</span>
      <span class="ask__cta">{{ current.cta }}</span>
    </template>

    <!-- 紧凑：只留动词。气泡里空间小，但"这能点"必须一眼看见 -->
    <template v-else>
      <span class="ask__cta">{{ current.cta }}</span>
      <svg class="ask__arrow" width="10" height="10" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M4 2.4 7.6 6 4 9.6" fill="none" stroke="currentColor" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </template>
  </button>
</template>

<style scoped>
/*
 * 它得比周围"响"一点点 —— 这是全站唯一一个"AI 在跟你说话"的入口，
 * 混在按钮堆里就白做了。所以用强调色底 + 描边 + 一颗呼吸的点，
 * 而不是又一个灰色小 chip。
 */
.ask {
  display: inline-flex; align-items: center; gap: var(--s2);
  max-width: 100%;
  padding: 7px 13px 7px 11px;
  border: var(--bw) solid var(--accent);
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent);
  text-align: left;
  transition: background var(--dur-micro) var(--ease-out),
              transform var(--dur-micro) var(--ease-out),
              box-shadow var(--dur-micro) var(--ease-out);
}
.ask:hover {
  background: var(--accent);
  color: var(--accent-ink);
  transform: translateY(-1px);
  box-shadow: var(--e-2);
}
.ask:active { transform: translateY(1px); }

.ask__dot {
  width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%;
  background: currentColor;
  animation: mo-breathe 2.2s var(--ease-out) infinite;
}

.ask__who { color: inherit; opacity: 0.75; white-space: nowrap; }
.ask__what {
  font-size: var(--fs-small); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 34ch;
}
/* 动词：手绘下划线，让人下意识想点 —— 全站"能点"的手势语言就是这个 */
.ask__cta {
  position: relative; flex: 0 0 auto;
  font-size: var(--fs-small); font-weight: 600; white-space: nowrap;
}
.ask__cta::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: -3px; height: 2px;
  background: currentColor; opacity: 0.5;
  border-radius: 2px;
  transform: rotate(-0.6deg);
  transition: opacity var(--dur-micro) var(--ease-out);
}
.ask:hover .ask__cta::after { opacity: 0.9; }

.ask--compact { padding: 5px 11px 5px 9px; }
.ask__arrow { flex: 0 0 auto; }

@media (prefers-reduced-motion: reduce) {
  .ask__dot { animation: none; }
}
</style>
