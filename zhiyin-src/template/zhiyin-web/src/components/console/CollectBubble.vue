<script setup lang="ts">
/**
 * 采集动线 —— 画布上那块"还缺什么、去哪儿取"。
 *
 * 它取代了原来那块固定写着"核验学籍"的气泡。区别在于：
 *
 *   原来那块是**固定动作**：不管你是谁、已经有什么，它都说同一句话。
 *   现在这块是**当次决策的结果**：缺什么、缺在哪个源头、哪一条没有源头，
 *   全部由采集策略（`policies/collection.py`）按你的画像算出来。
 *
 * 这就是"动态采集"在界面上的样子：同一个位置，不同的人、不同的阶段，
 * 长出来的东西不一样；补完之后它自己就会变（少一条、或者整个消失）。
 */
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const emit = defineEmits<{ (e: 'close'): void; (e: 'resolve'): void }>()

const plan = computed(() => session.collection)

/** 还差的东西里，有多少是现在真能取的 */
const fetchable = computed(() =>
  plan.value ? (plan.value.bySource.chsi ?? 0) + (plan.value.bySource.conversation ?? 0) : 0
)

const SOURCE_LABEL: Record<string, string> = {
  chsi: '学信网',
  conversation: '问你一句',
  academic: '教务系统',
}

/**
 * 第一条要取的，和剩下的。
 *
 * 为什么把"剩下的"也摆出来：这一块拿的是画布上最大的一格（权重 2.4），
 * 而它上一版只写了三行字，下面空出一大块 —— 用户看到的是"一个空荡荡的绿块"。
 * 清单本来就在手边（`plan.items`），把还差的那几条排出来，
 * 这一块才配得上它占的位置，也才真的回答"还缺什么、去哪儿取"。
 *
 * 只列 3 条：再多就把这一块变成一张清单页，那是浮层该干的事。
 */
const firstMissing = computed(
  () => plan.value?.items.find((i) => !i.got && i.available) ?? null,
)
const restMissing = computed(
  () => (plan.value?.items ?? []).filter((i) => !i.got && i !== firstMissing.value).slice(0, 3),
)

function open() {
  session.openOverlay('collect')
}
</script>

<template>
  <Bubble
    size="md"
    tone="accent"
    interactive
    resolvable
    :tilt="0.4"
    label="采集动线"
    @click="open"
    @close="emit('close')"
    @resolve="emit('resolve')"
  >
    <header class="head">
      <span class="label head__k">采集动线</span>
      <span class="label head__meta">{{ plan ? `还差 ${plan.missing} 条` : '待整理' }}</span>
    </header>

    <template v-if="plan">
      <h3 class="title">
        还差 <em>{{ plan.missing }}</em> 条，其中 <em>{{ fetchable }}</em> 条现在就能取。
      </h3>

      <!-- 从哪取：按源头分组。这是"动态"最直接的读法 -->
      <ul class="srcs">
        <li v-for="(count, source) in plan.bySource" :key="source" :class="{ zero: !count }">
          <span class="srcs__n mono">{{ count }}</span>
          <span class="srcs__t">{{ SOURCE_LABEL[source] ?? source }}</span>
        </li>
        <li v-if="plan.blocked.length" class="srcs__blocked">
          <span class="srcs__n mono">—</span>
          <span class="srcs__t">{{ plan.blocked.join(' / ') }} 没有源头</span>
        </li>
      </ul>

      <!-- 第一条：为什么现在要它。用户凭什么再花一次动作，全看这一句 -->
      <p v-if="firstMissing" class="why">
        <span class="label why__k">先取这条</span>
        {{ firstMissing.label }} ——
        {{ firstMissing.why }}
      </p>

      <!-- 其余的：名字 + 从哪取。一句 why 太长，浮层里逐条看 -->
      <ul v-if="restMissing.length" class="more">
        <li v-for="item in restMissing" :key="item.key">
          <span class="more__k">{{ item.label }}</span>
          <span class="label more__s">{{ SOURCE_LABEL[item.source] ?? item.source }}</span>
          <span class="label more__x">{{ item.available ? '能取' : '暂无源头' }}</span>
        </li>
      </ul>
    </template>

    <p v-else class="why why--dim">清单还没算出来。它到之前，这里不猜你缺什么。</p>

    <footer class="foot">
      <span class="label foot__cta">看完整清单 →</span>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__k { color: var(--accent); }
.head__meta { color: var(--ink-3); }
.title { font-size: var(--t-h4); line-height: 1.38; letter-spacing: var(--track-h); }
.title em { font-style: normal; color: var(--accent); font-weight: 600; }

.srcs { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.srcs li {
  display: inline-flex; align-items: baseline; gap: 5px;
  padding: 4px 10px;
  border: 1px solid var(--line-2); border-radius: var(--r-pill);
  background: var(--n-1);
}
.srcs__n { color: var(--accent); }
.srcs__t { font-size: var(--t-xs); color: var(--ink-2); }
.srcs li.zero { opacity: 0.5; }
/* 没有源头的单独一种样式：它不是"待办"，是"这里暂时没有办法" */
.srcs__blocked { border-style: dashed; border-color: var(--line-3); }
.srcs__blocked .srcs__n,
.srcs__blocked .srcs__t { color: var(--ink-3); }

.why {
  font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.why__k { color: var(--ink-3); margin-right: 4px; }
.why--dim { color: var(--ink-faint); }

/*
 * 还差的那几条：一行一条，左边是名字，右边是"从哪取 / 能不能取"。
 * 用一条细线分列，不做成三张卡 —— 这一块里已经有标题、来源胶囊、
 * 说明句了，再加卡片就成"盒子套盒子"。
 */
.more { list-style: none; margin: 0; padding: 0; display: grid; }
.more li {
  display: grid; grid-template-columns: minmax(0, 1fr) auto auto;
  gap: var(--s3); align-items: baseline;
  padding: 7px 0;
  border-top: 1px solid var(--line-1);
}
.more__k { font-size: var(--fs-small); color: var(--ink-1); }
.more__s { color: var(--ink-3); }
.more__x { color: var(--accent); }

/*
 * 矮格位里清单先收：先减行数，再整块收起。
 * "还差几条"和"先取这条"是这一块的主语，任何时候都不能少；
 * 其余那几条是补充，浮层里有完整的一份。
 */
.bubble.is-compact .more li:nth-child(n + 3) { display: none; }
.bubble.is-tiny .more { display: none; }
.bubble.is-tiny .srcs { display: none; }
.bubble.is-compact .title { font-size: var(--t-body); }

.foot { display: flex; align-items: center; gap: var(--s3); margin-top: auto; }
.foot__cta { color: var(--ink-3); }
.bubble:hover .foot__cta { color: var(--accent); }
</style>
