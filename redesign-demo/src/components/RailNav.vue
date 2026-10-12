<script setup lang="ts">
/**
 * 索引栏的目录（索引式档案页 · 方案 B）。
 *
 * 它做的是"这一页有什么"：**条目文字全部取自页面里已经有的东西** ——
 * 分区名、来源层的名字、日期、条数。不新造任何信息，也不重复主栏的正文。
 *
 * 两条版面纪律由它承担：
 *   1. 同一分组内**不画分隔线**，只靠 12px 的靠近说"它们是一伙的"（Proximity）；
 *   2. 分组之间才用间距与分组名把它推开。
 *
 * 样式在 base.css 的 `.rail-index*` 里 —— 版面口径全工程只有一份，
 * 五个页面共用，所以它是个零件，不是每页各写一遍。
 */

export interface RailEntry {
  /** 条目文字。必须是页面上已有的名字 —— 不在这里发明新词 */
  label: string
  /** 右侧的计数 / 日期（可选） */
  meta?: string
}

export interface RailGroup {
  /** 分组名（可选）。有它才画分组，没有就是一条平铺的目录 */
  title?: string
  entries: RailEntry[]
}

defineProps<{
  /** 这一页目录的总标题 */
  title: string
  groups: RailGroup[]
  /**
   * 被选中的条目下标（`组下标:条目下标`）；null = 没有选中（这一屏全都在）。
   * 五个内页都做"点一条定位到那一块"，所以它是必填的 —— 不做"看着能点、点了没反应"。
   */
  active: string | null
  /** 目录底下的一句注解（语气档一：说人话） */
  note?: string
}>()

const emit = defineEmits<{ (e: 'pick', id: string): void }>()

function key(gi: number, ei: number) {
  return `${gi}:${ei}`
}
</script>

<template>
  <nav class="rail-index" aria-label="这一页的分区索引">
    <h2 class="rail-index__title">{{ title }}</h2>

    <div class="rail-index__list">
      <template v-for="(g, gi) in groups" :key="gi">
        <p v-if="g.title" class="rail-index__group">{{ g.title }}</p>
        <button
          v-for="(e, ei) in g.entries"
          :key="key(gi, ei)"
          class="rail-index__item"
          :class="{ 'rail-index__item--on': active === key(gi, ei) }"
          :type="'button'"
          :aria-current="active === key(gi, ei) ? 'true' : undefined"
          @click="emit('pick', key(gi, ei))"
        >
          <span class="rail-index__label">{{ e.label }}</span>
          <span v-if="e.meta" class="rail-index__meta t-num">{{ e.meta }}</span>
        </button>
      </template>
    </div>

    <p v-if="note" class="rail-index__note">{{ note }}</p>
  </nav>
</template>
