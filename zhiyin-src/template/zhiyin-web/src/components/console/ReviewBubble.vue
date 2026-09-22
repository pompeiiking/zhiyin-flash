<script setup lang="ts">
import Bubble from '@/components/console/Bubble.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import { computed, onMounted } from 'vue'
import { track } from '@/api/client'
import { useSessionStore } from '@/stores/session'

/**
 * 上周复盘。
 *
 * 五步里的最后一步。它不生成报告，只回答一句："你上周做的那件事，有没有用。"
 * 有用就说清楚涨在哪 —— 这才是用户下周还愿意动的原因。
 *
 * 复盘结论来自后端 review_panel.evaluation；没有就直说没有，
 * 不在前端编一段"把握度 +0.06"。
 */
const emit = defineEmits<{ (e: 'close'): void; (e: 'resolve'): void }>()
const session = useSessionStore()
const liveReview = computed(() => session.wsPanels?.review || '')

/*
 * 复盘块出现在画布上 = "提醒你回头看"这件事被展示了（注册表里的 review_warning_show）。
 *
 * 放在挂载时而不是某个点击上：这块本身就是一条提醒 —— 它的存在即展示。
 * 这块点开就是 ⑤ 复盘的完整界面（ReviewOverlay：结论 + 跟踪时间线）。
 */
onMounted(() => track('review_warning_show', { has_review: !!liveReview.value }))
</script>

<template>
  <Bubble
    size="sm"
    tone="accent"
    interactive
    resolvable
    :tilt="0.45"
    label="上周复盘"
    @click="session.openOverlay('review')"
    @close="emit('close')"
    @resolve="emit('resolve')"
  >
    <header class="head">
      <span class="label head__k">上周复盘</span>
      <span class="label head__t">{{ liveReview ? '本周结论' : '待生成' }}</span>
    </header>

    <h3 v-if="liveReview" class="title">这一周的复盘：</h3>
    <h3 v-else class="title">还没有复盘结论。</h3>
    <p v-if="liveReview" class="why">{{ liveReview }}</p>
    <p v-else class="why">先完成一次行动，把结果记回来，这里就会有可看的东西。</p>

    <div class="acts">
      <NextAsk compact />
        <button class="act act--go" type="button" @click.stop="session.openOverlay('review')">看时间线</button>
      <button class="act" type="button" @click="emit('resolve')">记下</button>
    </div>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s2); }
.head__k { color: var(--mk-green); }
.head__t { color: var(--ink-3); }
.title { font-size: var(--t-body); font-weight: 600; line-height: 1.4; }
.up { color: var(--mk-green); font-weight: 600; }
.why { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.act {
  flex: 1; height: 30px; border-radius: var(--r-pill);
  border: 1px solid var(--line-2); font-size: var(--fs-small); color: var(--ink-2);
  background: var(--n-1);
  transition: border-color var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.act:hover { border-color: var(--ink-1); color: var(--ink-1); }
.act--go { border-color: var(--mk-green); color: var(--mk-green); }
.act:disabled { opacity: 0.45; cursor: not-allowed; }

/* 紧凑形态：同上 —— 矮格位里先舍元信息与次要动作，不裁字 */
.bubble.is-compact { gap: var(--s2); }
.bubble.is-compact .head__t { display: none; }
.bubble.is-compact .title { font-size: var(--t-sm); }
.bubble.is-compact .why { -webkit-line-clamp: 1; }
.bubble.is-compact .act:not(.act--go) { display: none; }

/* 再小一档（<200px）：说明句整句收掉，只留结论 + 一个动作 */
.bubble.is-tiny .why { display: none; }
.bubble.is-tiny .head { display: none; }
.bubble.is-tiny .act { height: 26px; }
.bubble.is-tiny .acts { gap: 4px; }
.bubble.is-tiny .title { line-height: 1.25; }
</style>
