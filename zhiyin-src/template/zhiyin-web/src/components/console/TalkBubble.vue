<script setup lang="ts">
/**
 * 对话气泡 —— 画布上那块"跟主理把话说清楚"。
 *
 * 为什么它该是一块气泡，而不是角落里的聊天窗：
 *
 *   · 这一屏的规矩是"每块气泡都是一件能动手的事"。跟主理说清楚，
 *     本来就是其中最该被看见的一件 —— 它没有理由被降级成一个边角入口；
 *   · 一块气泡能**同时说清三件事**：现在是谁在跟你说话、
 *     他刚说了什么、下一步他等你做什么。角落那个小窗只能塞一行标题。
 *
 * 它是入口，不是对话本身：点开才是完整的那一层（TalkOverlay）。
 * 这样"需要的时候再对话"才是真的 —— 平时它安静的待在这儿，
 * 有话说的时候，上面那行字会变。
 */
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const emit = defineEmits<{ (e: 'close'): void; (e: 'resolve'): void }>()

/** 最近一句主理说的话 —— 气泡上要能看见"它在跟你说什么"，而不是一个空的入口 */
const lastAi = computed(() => [...session.chatTurns].reverse().find((t) => t.role === 'ai'))
const lead = computed(() => session.rail?.leadName ?? '')
const started = computed(() => !!session.rail)

function open() {
  session.openOverlay('talk')
}
</script>

<template>
  <Bubble
    size="md"
    tone="plain"
    interactive
    resolvable
    :tilt="0.25"
    label="和主理聊聊"
    @click="open"
    @close="emit('close')"
    @resolve="emit('resolve')"
  >
    <header class="head">
      <span class="label head__k">和主理聊聊</span>
      <span class="label head__who">{{ started ? lead : '还没开始' }}</span>
    </header>

    <template v-if="started">
      <p class="said">{{ lastAi?.text }}</p>
    </template>
    <template v-else>
      <h3 class="title">有一件事说不清楚？</h3>
      <p class="said said--dim">
        不用先想好怎么问。说一句，系统判环节、派主理接手 ——
        谁接的、为什么换人，都会写在里面。
      </p>
    </template>

    <footer class="foot">
      <!-- AI 在等什么，就摆在这一块上：点它直接进对话，且已经站在问题上 -->
      <NextAsk v-if="session.nextAsk" compact />
      <span v-else class="label foot__cta">进去说一句 →</span>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__k { color: var(--mk-purple); }
.head__who { color: var(--ink-3); }
.title { font-size: var(--t-h4); line-height: 1.4; }
.said {
  font-size: var(--fs-small); color: var(--ink-2); line-height: 1.72;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.said--dim { color: var(--ink-3); }
.foot { display: flex; align-items: center; justify-content: flex-start; gap: var(--s3); margin-top: auto; }
.foot__cta { color: var(--ink-3); }
.bubble:hover .foot__cta { color: var(--accent); }
</style>
