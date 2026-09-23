<script setup lang="ts">
/**
 * 完成记录 —— 完整的一屏（内部叫"成就"，界面上叫「完成记录」）。
 *
 * 这一屏要说清两件事，顺序不能反：
 *
 *   1. **拿到的那几枚是什么时候的事**（"9 月 23 日 · 做完第一件"）——
 *      时间来自行为日志里那条行为的真实发生时间，不是"你打开这一屏的时间"；
 *   2. **还没拿到的那几枚差什么**（一句话，写的是他能做的动作，不是内部事件名）。
 *
 * 两句话都按规则 code 从文案包取（`badge.<key>.label` / `.how`）：
 * 规则在 `badge_rules.json`、名字在 `copies.json`，两边各自可改，都不用发版。
 */
import { computed } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

const items = computed(() => session.achievements?.items ?? [])
const unlockedCount = computed(() => session.achievements?.unlocked ?? 0)
const total = computed(() => session.achievements?.total ?? 0)

const labelOf = (key: string) => session.copyBundle[`badge.${key}.label`] || '完成了一件事'
const howOf = (key: string) => session.copyBundle[`badge.${key}.how`] || ''

/** 拿到的那几枚在前，且按时间倒序；没拿到的按规则顺序跟在后面 */
const rows = computed(() => {
  const done = items.value
    .filter((item) => item.unlocked)
    .sort(
      (a, b) =>
        new Date(b.unlocked_at ?? 0).getTime() - new Date(a.unlocked_at ?? 0).getTime(),
    )
  const todo = items.value.filter((item) => !item.unlocked)
  return [...done, ...todo]
})

/** 时间戳 → `9 月 23 日`；读不出来就不写日期，不猜 */
function dayOf(iso: string | null | undefined): string {
  if (!iso) return ''
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ''
  return `${at.getMonth() + 1} 月 ${at.getDate()} 日`
}
</script>

<template>
  <Overlay
    title="完成记录"
    :subtitle="total ? `拿到 ${unlockedCount} 枚 · 全部是你做过的事` : '做到过的那几件事'"
    from="achievements"
    @close="session.closeOverlay()"
  >
    <p class="lead sheet">
      这份记录不评价你，只记事实：答过一句、认领过一件事、拿定过一个方向、做完过一件、
      回头看过一次 —— 做到的那一刻它就已经记上了。
    </p>

    <p v-if="!total" class="warn">这份记录还没读出来（可能是刚才没连上）。过一会儿再打开看看。</p>

    <ul v-else class="rows">
      <li v-for="item in rows" :key="item.key" :class="{ done: item.unlocked }">
        <span class="mark" aria-hidden="true">
          <svg v-if="item.unlocked" viewBox="0 0 14 14">
            <path
              d="M2.6 7.4 5.6 10.4 11.4 3.8" fill="none" stroke="currentColor"
              stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            />
          </svg>
        </span>
        <span class="body">
          <span class="name">{{ labelOf(item.key) }}</span>
          <span class="label how">{{ item.unlocked ? howOf(item.key) : `还差这一件：${howOf(item.key)}` }}</span>
        </span>
        <span class="label when">
          {{ item.unlocked ? dayOf(item.unlocked_at) || '已记上' : '还没' }}
        </span>
      </li>
    </ul>

    <p v-if="total" class="label foot sheet">
      名字与说明来自文案包（`data/registry/copies.json` 里 `badge.*`），
      解锁条件来自规则表（`badge_rules.json`）—— 两处都可以随时改，不用发版。
    </p>
  </Overlay>
</template>

<style scoped>
.lead { padding: var(--s5); font-size: var(--fs-small); color: var(--ink-2); line-height: 1.8; }
.warn { padding: var(--s5); color: var(--warn); font-size: var(--fs-small); }
.rows { list-style: none; margin: var(--s4) 0 0; padding: 0; display: grid; }
.rows li {
  display: grid; grid-template-columns: 22px minmax(0, 1fr) 72px;
  gap: var(--s3); align-items: center;
  padding: var(--s3) var(--s5); border-top: 1px solid var(--line-1);
}
.rows li:first-child { border-top: 0; }
.mark {
  width: 18px; height: 18px; border-radius: 50%;
  border: var(--bw) solid var(--line-3); color: transparent;
  display: grid; place-items: center;
}
.mark svg { width: 11px; height: 11px; }
.rows li.done .mark { border-color: var(--mk-green); color: var(--mk-green); background: var(--accent-soft); }
.body { display: grid; gap: 2px; }
.name { font-size: var(--fs-small); color: var(--ink-1); }
.rows li:not(.done) .name { color: var(--ink-3); }
.how { color: var(--ink-3); }
.when { color: var(--ink-3); text-align: right; }
.foot { padding: var(--s3) var(--s5) 0; color: var(--ink-3); line-height: 1.7; }
</style>
