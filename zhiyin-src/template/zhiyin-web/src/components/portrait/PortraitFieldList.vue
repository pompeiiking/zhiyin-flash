<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * 字段清单 —— 左边这一列。
 *
 * 职责只有一个：**让人快速找到那一条**。所以给三样东西 —— 搜索、筛选、排序，
 * 加上键盘上下切换。缺一样，字段一多就只能在列表里上下瞎找。
 *
 * 每一行三段：名字与把握、一根把握条、依据与时间。把握条按三档上色
 * （薄 = 红、中 = 琥珀、稳 = 绿），但**数值永远写在行上** —— 颜色只是辅助。
 */
export interface PortraitItem {
  key: string
  label: string
  confidence: number
  source: string
  updatedAt: string
  evidenceCount: number
  /** 这一条是不是也出现在"待补"里（画像与缺口的交集） */
  pending: boolean
}

const props = defineProps<{
  items: PortraitItem[]
  selectedKey: string | null
  /** 缺口数：筛选片"还没定"上带的数 */
  gapCount: number
}>()

const emit = defineEmits<{
  (e: 'select', key: string): void
}>()

const keyword = ref('')
type Filter = 'all' | 'low' | 'pending'
const filter = ref<Filter>('all')
type Sort = 'confidence' | 'updated' | 'name'
const sort = ref<Sort>('confidence')

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'low', label: '把握低' },
  { key: 'pending', label: '还没定' },
]

/** 低于这个把握算"薄"：0.6 是采集口径里的缺口语义线（见 policies/collection_gate） */
const LOW = 0.6

const shown = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  let list = props.items.filter((item) => {
    if (kw && !(item.label.toLowerCase().includes(kw) || item.key.toLowerCase().includes(kw))) return false
    if (filter.value === 'low') return item.confidence < LOW
    if (filter.value === 'pending') return item.pending
    return true
  })
  list = [...list]
  if (sort.value === 'confidence') list.sort((a, b) => a.confidence - b.confidence)
  else if (sort.value === 'updated') list.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
  else list.sort((a, b) => a.label.localeCompare(b.label, 'zh'))
  return list
})

const tier = (v: number) => (v < LOW ? 'low' : v < 0.85 ? 'mid' : 'high')
const pendingCount = () => props.items.filter((item) => item.pending).length

/** 键盘上下切换：列表长的时候，鼠标一个个点是负担 */
function move(step: number) {
  if (!shown.value.length) return
  const index = shown.value.findIndex((item) => item.key === props.selectedKey)
  const next = shown.value[Math.min(shown.value.length - 1, Math.max(0, index + step))]
  if (next) emit('select', next.key)
}
</script>

<template>
  <nav class="list" aria-label="画像字段">
    <div class="tools">
      <label class="search">
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.6" />
          <path d="M10.6 10.6 14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
        <input v-model="keyword" type="search" placeholder="找一条…" aria-label="搜索画像字段">
      </label>
      <label class="sort">
        <span class="sr">排序</span>
        <select v-model="sort" aria-label="排序方式">
          <option value="confidence">按把握</option>
          <option value="updated">按时间</option>
          <option value="name">按名称</option>
        </select>
      </label>
    </div>

    <div class="seg" role="group" aria-label="筛选">
      <button
        v-for="f in FILTERS"
        :key="f.key"
        type="button"
        class="seg__b"
        :class="{ 'seg__b--on': filter === f.key }"
        :aria-pressed="filter === f.key"
        @click="filter = f.key"
      >
        {{ f.label }}<i v-if="f.key === 'pending' && pendingCount()">{{ pendingCount() }}</i>
      </button>
    </div>

    <p v-if="!shown.length" class="empty">
      {{ items.length ? '这一档里没有字段 —— 换个筛选看看。' : '画像还是空的，去聊两句。' }}
    </p>

    <ul
      v-else
      class="rows"
      tabindex="0"
      aria-label="画像字段（上下键可切换）"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
    >
      <li v-for="item in shown" :key="item.key">
        <button
          class="row"
          type="button"
          :class="[{ 'row--on': item.key === selectedKey }, `row--${tier(item.confidence)}`]"
          :aria-current="item.key === selectedKey"
          @click="emit('select', item.key)"
        >
          <span class="row__name">
            {{ item.label }}
            <span v-if="item.pending" class="tag" title="这条还没定">没定</span>
          </span>
          <span class="row__num">{{ item.confidence.toFixed(2) }}</span>
          <span class="row__track" aria-hidden="true"><i :style="{ width: `${Math.max(4, Math.round(item.confidence * 100))}%` }" /></span>
          <span class="row__meta">
            {{ item.evidenceCount }} 条依据 · {{ item.updatedAt ? item.updatedAt.slice(5, 10) : '未记录' }}
          </span>
        </button>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.list { display: flex; flex-direction: column; gap: var(--s3); min-height: 0; }

/* ── 工具条 ─────────────────────────────────────────────────────── */
.tools { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--s2); }
.search {
  display: flex; align-items: center; gap: 7px;
  height: 34px; padding: 0 11px;
  border: 1px solid var(--pt-line, var(--line-2));
  border-radius: var(--pt-r-sm, 8px);
  background: var(--pt-well, var(--c-sand-1));
  color: var(--pt-faint, var(--ink-3));
  transition: border-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out), background 160ms var(--ease-out);
}
.search:focus-within {
  background: var(--pt-surface, var(--c-paper));
  border-color: var(--pt-accent, var(--accent));
}
.search input {
  flex: 1; min-width: 0; border: 0; outline: none; background: none;
  font-size: var(--t-sm); color: var(--pt-ink, var(--ink-1));
}
.search input::-webkit-search-cancel-button { display: none; }

.sort { position: relative; display: flex; align-items: center; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.sort select {
  height: 34px; padding: 0 8px;
  border: 1px solid var(--pt-line, var(--line-2));
  border-radius: var(--pt-r-sm, 8px);
  background: var(--pt-surface, var(--c-paper)); color: var(--pt-muted, var(--ink-2));
  font-size: var(--t-xs); cursor: pointer;
}

/* 分段控件：一条凹槽 + 一块浮起的选中块 */
.seg {
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
  gap: 2px; padding: 3px;
  border-radius: var(--pt-r-sm, 8px);
  background: var(--pt-well, var(--c-sand-1));
}
.seg__b {
  height: 26px; border-radius: 6px;
  font-size: var(--t-xs); font-weight: 500; color: var(--pt-muted, var(--ink-2));
  display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  transition: background 160ms var(--ease-out), color 160ms var(--ease-out), box-shadow 160ms var(--ease-out);
}
.seg__b:hover { color: var(--pt-ink, var(--ink-1)); }
.seg__b--on {
  background: var(--pt-surface, var(--c-paper)); color: var(--pt-ink, var(--ink-1));
  box-shadow: var(--e-1, 0 1px 1px rgba(23, 22, 20, 0.05)), var(--inner-hi, none);
}
.seg__b i { font-style: normal; color: var(--pt-faint, var(--ink-3)); font-variant-numeric: tabular-nums; }

/* ── 行 ─────────────────────────────────────────────────────────── */
.rows {
  list-style: none; margin: 0; padding: 0;
  display: grid; gap: 4px; overflow: auto; min-height: 0;
}
.rows:focus-visible { outline: none; }

/*
 * 入场：一行一行落下来，错开 40ms。
 * 列表是这一页里唯一"成组出现"的东西，给它一次编排就够了 —— 别处都是静态的。
 * 降低动效时 base.css 里那条全局规则会把时长压到 0.001ms，直接给终态。
 */
@keyframes pt-row-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}
.rows li { animation: pt-row-in 420ms var(--ease-expo) both; }
.rows li:nth-child(2) { animation-delay: 40ms; }
.rows li:nth-child(3) { animation-delay: 80ms; }
.rows li:nth-child(4) { animation-delay: 120ms; }
.rows li:nth-child(n + 5) { animation-delay: 160ms; }

.row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 10px;
  width: 100%; text-align: left;
  padding: 10px 12px 10px 14px;
  border-radius: var(--pt-r-sm, 8px);
  border: 1px solid transparent;
  transition: background 180ms var(--ease-out), border-color 180ms var(--ease-out),
              box-shadow 180ms var(--ease-out), transform 180ms var(--ease-out);
}
/* 左边那根细线是"选中"的位置标记，所有行都留着它的位置，切换时不跳 */
.row::before {
  content: "";
  position: absolute; left: 5px; top: 10px; bottom: 10px;
  width: 3px; border-radius: 3px;
  background: transparent;
  transition: background 180ms var(--ease-out);
}
.row:hover { background: var(--pt-surface, var(--c-paper)); transform: translateY(-1px); box-shadow: var(--e-1), var(--inner-hi); }
.row--on {
  background: var(--pt-surface, var(--c-paper));
  border-color: var(--pt-line, var(--line-2));
  box-shadow: var(--e-2), var(--inner-hi);
}
.row--on::before { background: var(--pt-accent, var(--accent)); }

.row__name {
  display: inline-flex; align-items: center; gap: 6px; min-width: 0;
  font-size: var(--t-sm); font-weight: 500; color: var(--pt-ink, var(--ink-1));
}
.tag {
  flex: 0 0 auto; padding: 1px 5px; border-radius: 5px;
  font-size: 11.5px; font-weight: 500;
  color: var(--pt-warn, var(--warn)); background: rgba(154, 74, 30, 0.10);
}
.row__num { font-size: var(--t-xs); color: var(--pt-muted, var(--ink-2)); font-variant-numeric: tabular-nums; }

.row__track {
  grid-column: 1 / -1; height: 4px; border-radius: var(--r-pill);
  background: var(--pt-track, var(--c-sand-1)); overflow: hidden;
}
.row__track i {
  display: block; height: 100%; border-radius: var(--r-pill);
  background: var(--pt-accent, var(--accent));
  transition: width 620ms var(--ease-expo);
}
/* 三档把握：蓝 / 橙 / 粉 —— 平涂，一支色一格 */
.row--mid .row__track i { background: var(--mk-orange); }
.row--low .row__track i { background: var(--mk-pink); }

.row__meta { grid-column: 1 / -1; font-size: var(--t-xs); color: var(--pt-faint, var(--ink-4)); }

.empty { font-size: var(--t-xs); color: var(--pt-muted, var(--ink-3)); line-height: 1.7; padding: var(--s2) 0; }
</style>
