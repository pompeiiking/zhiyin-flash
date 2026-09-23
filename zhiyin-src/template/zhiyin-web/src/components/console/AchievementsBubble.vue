<script setup lang="ts">
/**
 * 完成记录 —— 画布上那一块。
 *
 * 它回答的是"我到目前为止**做到过**什么"，判据只有一条：**行为日志里真实发生过**。
 * 勾掉一件任务、选中一套方案、复盘一次，都会在日志里留下一条 —— 这块牌子读的就是它。
 * 所以这里没有"发奖"、也没有"领奖"：事情发生的那一刻它就已经成立了。
 *
 * 三件刻意的取舍：
 *
 *   · **不画进度条**。解锁条件是"做过一次某件事"，拆成百分比就是编出来的刻度
 *     （"认领差距 60%"没有含义）—— 宁可不给这一格。
 *   · **没拿到的也写出来**（"还差哪几件"），否则这一屏只剩一行数字。
 *     但**不写内部事件名**：那是我们的话，不是他的。
 *   · 名字与"怎么拿到"按 `badge.<key>.label` / `.how` 从文案包取 ——
 *     文案在 `data/registry/copies.json` 里改，不发版。
 */
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const emit = defineEmits<{ (e: 'close'): void }>()

/** 文案：包里没有就退回一句兜底，不留空白 */
const labelOf = (key: string) => session.copyBundle[`badge.${key}.label`] || '完成了一件事'

const list = computed(() => session.achievements?.items ?? [])
const unlockedCount = computed(() => session.achievements?.unlocked ?? 0)
const total = computed(() => session.achievements?.total ?? 0)

/** 已解锁的按时间倒序取最近一枚 —— 这块只说得下一枚 */
const latest = computed(() => {
  const done = list.value.filter((item) => item.unlocked && item.unlocked_at)
  if (!done.length) return null
  return [...done].sort(
    (a, b) =>
      new Date(b.unlocked_at as string).getTime() - new Date(a.unlocked_at as string).getTime(),
  )[0]
})

const remaining = computed(() => Math.max(0, total.value - unlockedCount.value))
</script>

<template>
  <Bubble
    size="sm"
    tone="plain"
    interactive
    :tilt="0.6"
    label="完成记录"
    @click="session.openOverlay('achievements')"
    @close="emit('close')"
  >
    <header class="head">
      <span class="label">完成记录</span>
      <span class="label head__meta">{{ unlockedCount }}/{{ total || '—' }}</span>
    </header>

    <template v-if="latest">
      <p class="now">{{ labelOf(latest.key) }}</p>
      <p class="label hint">最近拿到的一枚 · 这些是你真做过的</p>
    </template>
    <template v-else-if="total">
      <p class="now">还一件都没记上。</p>
      <p class="label hint">答上一句、勾掉一件任务，这里就会多一条。</p>
    </template>
    <template v-else>
      <p class="now">这份记录还没读出来。</p>
      <p class="label hint">它不是我们写给你的评语 —— 是你自己做过的事。</p>
    </template>

    <footer class="foot">
      <span v-if="remaining > 0" class="label foot__rest">还有 {{ remaining }} 枚没拿到</span>
      <span v-else class="label foot__rest">这一批都拿到了</span>
      <span class="label foot__go">看全部 →</span>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__meta { color: var(--ink-3); font-variant-numeric: tabular-nums; }
.now { font-size: var(--fs-body); color: var(--ink-1); line-height: 1.5; }
.hint { color: var(--ink-3); }
.foot { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.foot__rest { color: var(--ink-3); }
.foot__go { color: var(--accent); }
</style>
