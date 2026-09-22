<script setup lang="ts">
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import { STAGES } from '@/data/content'
import { useSessionStore } from '@/stores/session'

/**
 * 待办气泡 —— 现在该做的那一件事。
 *
 * "这一件事"由工作台算出来（action_panel.evaluation）。
 * 之前在本地写死了五套阶段文案 —— 算不出来时界面上照样有一条很像样的待办，
 * 那恰好把"这里其实没有依据"盖住了。现在没数据就直说没数据。
 */
const session = useSessionStore()
const stage = computed(() => STAGES.find((s) => s.id === session.stage) ?? null)
const liveAction = computed(() => session.wsPanels?.action || '')

const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <Bubble size="lg" tone="plain" :tilt="-0.4" label="待办" @close="emit('close')">
    <header class="head">
      <span class="label">待办</span>
      <span class="label head__meta">{{ session.customTodos.length }} 件自建待办</span>
    </header>

    <div v-if="liveAction" class="now">
      <span class="now__label label">现在</span>
      <p class="now__title">{{ liveAction }}</p>
    </div>

    <div v-else class="now">
      <span class="now__label label">现在</span>
      <p class="now__title">今天这一件还没定下来。</p>
      <p class="now__meta">先开一次对话；有了画像与窗口期，这里才会有内容。</p>
    </div>

    <footer class="foot">
      <!-- 待办不是让用户自己想的 —— AI 指哪件就做哪件，指不动就先把话说清楚 -->
      <NextAsk v-if="!liveAction" compact />
      <button v-if="stage" class="label foot__why" type="button" @click="session.openDrawer('为什么是这一件', stage.question, [])">
        为什么这一件
      </button>
      <span v-else class="label foot__why is-off">为什么这一件</span>
      <button class="label foot__cta" type="button" @click="session.openOverlay('tasks')">
        全部任务 →
      </button>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__meta { color: var(--ink-faint); }
.now { display: flex; flex-direction: column; gap: 4px; }
.now__label { color: var(--accent); }
.now__title {
  font-size: clamp(18px, 1.7vw, var(--t-h2));
  line-height: 1.35;
  letter-spacing: -0.015em;
  max-width: 24ch;
}
.now__meta { color: var(--ink-dim); font-size: var(--fs-small); }
.options { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.opt {
  padding: 7px 14px; border-radius: var(--r-pill);
  border: var(--bw) solid var(--line-2); background: var(--n-1);
  font-size: var(--fs-small); color: var(--ink-dim);
  transition: color var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out),
              background var(--dur-fast) var(--ease-out),
              transform var(--dur-fast) var(--ease-out);
}
.opt:hover { color: var(--ink); border-color: var(--ink-dim); transform: translateY(-1px); }
.opt.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
/*
 * 页脚钉在气泡底部（margin-top: auto）。
 * 气泡高度是平铺引擎给的固定值，正文短的时候页脚会紧贴上一段文字 ——
 * "开始对话"整个贴在字下面，既不像底部动作，也失去了它的位置含义。
 */
.foot { display: flex; align-items: center; justify-content: space-between; gap: var(--s3); margin-top: auto; }
.foot__why { color: var(--ink-faint); }
.foot__why:hover { color: var(--ink); }
.foot__why.is-off { opacity: 0.45; }
.foot__cta { color: var(--ink-dim); }
.bubble:hover .foot__cta { color: var(--accent); }

/*
 * 紧凑形态 —— 平铺引擎给到矮格位（实测 380×146）时的那一套排版。
 *
 * 为什么必须写这一条：这一块的内容是"标题 + 现在这一件 + 一行说明 + 页脚"，
 * 完整形态要 246px 高。格位只有 146px 时浏览器只能按 overflow: hidden 裁掉，
 * 用户看到的就是"字被切掉了半句"（历史 bug 的其中一处）。
 *
 * 判据由外层给（shouldCompact 按**像素**算，不看格子数），这里只负责
 * "矮下来之后先舍掉哪一层"：先舍元信息，再舍次要动作，
 * 但"现在这一件"和主入口一个字都不能少 —— 那是这块存在的理由。
 */
.bubble.is-compact { gap: 6px; }
.bubble.is-compact .head__meta { display: none; }
.bubble.is-compact .now__meta { display: none; }
.bubble.is-compact .now__title {
  font-size: var(--t-h3);
  line-height: 1.3;
  max-width: none;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.bubble.is-compact .foot__why { display: none; }
.bubble.is-compact .foot { gap: var(--s2); }
</style>
