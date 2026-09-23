<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * 画像清单 —— 第二层。一份是**判断维度**，一份是**档案事实**。
 *
 * 两种清单长得像，但列不一样，因为要回答的问题不一样：
 *
 *   · 判断（kind='judgment'）：兴趣 / 价值取向 / 经历…… 这些是"你现在怎么看自己"，
 *     每一条都有**真的会变的**把握度和若干条依据 —— 所以列是
 *     名称 · 把握 · 把握条 · 依据与时间，还可以按"把握低 / 还没定"筛。
 *   · 档案（kind='record'）：学校 / 专业 / 学籍 / 学制…… 这些是从学信网抄下来的
 *     行政事实，把握度恒为 1.00。给它们画一根顶满的把握条，只会让九行都一样粗，
 *     读起来像噪声 —— 所以列换成 名称 · 内容 · 来源与时间。
 *     那一根条不是"少了装饰"，是**这一列本来就不该存在**。
 *
 * 一条一份清单，不混在一起：混起来用户分不清哪条是自己说的、哪条是系统抄的，
 * 而"这条从哪来"正是这个产品最要紧的一件事。
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
  /** 取值读成人话之后的样子 —— 档案清单要直接展示它 */
  value?: string
  /** 来源的说法（"权威记录" / "对话"……），档案清单按列显示 */
  sourceLabel?: string
}

const props = withDefaults(
  defineProps<{
    items: PortraitItem[]
    selectedKey: string | null
    /** 缺口数：筛选片"还没定"上带的数 */
    gapCount: number
    /** judgment = 判断维度；record = 档案事实 */
    kind?: 'judgment' | 'record'
  }>(),
  { kind: 'judgment' },
)

const emit = defineEmits<{
  (e: 'select', key: string): void
}>()

const judging = computed(() => props.kind === 'judgment')

const keyword = ref('')
type Filter = 'all' | 'low' | 'pending'
const filter = ref<Filter>('all')
type Sort = 'confidence' | 'updated' | 'name'
/*
 * 默认排序按清单性质分岔：判断维度先看"哪条最薄"（按把握升序），
 * 档案没有把握可排，默认按名称 —— 否则下拉框会停在一个**不存在的选项**上，
 * 界面显示成一片空白（列表里没有"按把握"这一项时，浏览器就选不中任何值）。
 */
const sort = ref<Sort>(props.kind === 'record' ? 'name' : 'confidence')

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
    if (!judging.value) return true
    if (filter.value === 'low') return item.confidence < LOW
    if (filter.value === 'pending') return item.pending
    return true
  })
  list = [...list]
  const byConfidence = judging.value ? sort.value === 'confidence' : false
  if (byConfidence) list.sort((a, b) => a.confidence - b.confidence)
  else if (sort.value === 'updated') list.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
  else if (sort.value === 'name') list.sort((a, b) => a.label.localeCompare(b.label, 'zh'))
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

/** 日期只留月-日：年份对"什么时候记的"没有增量 */
const day = (iso: string) => (iso ? iso.slice(5, 10) : '未记录')
</script>

<template>
  <nav class="list" aria-label="画像清单">
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
          <option v-if="judging" value="confidence">按把握</option>
          <option value="updated">按时间</option>
          <option value="name">按名称</option>
        </select>
      </label>
    </div>

    <!-- 筛选只对判断维度有意义：档案那一堆没有"把握低"这回事 -->
    <div v-if="judging" class="seg" role="group" aria-label="筛选">
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
      {{ items.length ? '这一档里没有字段 —— 换个筛选看看。' : '这里还是空的。' }}
    </p>

    <template v-else>
      <!-- 列头：把"这张表有几列"交代清楚，后面的对齐才读得出来 -->
      <div class="cols" :class="{ 'cols--rec': !judging }" aria-hidden="true">
        <span>字段</span>
        <span v-if="judging" class="cols__num">把握</span>
        <span v-else>内容</span>
        <span v-if="judging" />
        <span>{{ judging ? '依据 / 更新' : '来源 / 更新' }}</span>
        <span />
      </div>

      <ul
        class="rows"
        tabindex="0"
        aria-label="画像字段（上下键可切换）"
        @keydown.down.prevent="move(1)"
        @keydown.up.prevent="move(-1)"
      >
        <li v-for="item in shown" :key="item.key">
          <button
            class="row"
            :class="{ 'row--rec': !judging, [`row--${tier(item.confidence)}`]: judging, 'row--on': item.key === selectedKey }"
            type="button"
            :aria-current="item.key === selectedKey"
            @click="emit('select', item.key)"
          >
            <span class="row__name">
              {{ item.label }}
              <span v-if="item.pending" class="tag" title="这条还没定">没定</span>
            </span>

            <template v-if="judging">
              <span class="row__num">{{ item.confidence.toFixed(2) }}</span>
              <span class="row__track" aria-hidden="true">
                <i :style="{ width: `${Math.max(6, Math.round(item.confidence * 100))}%` }" />
              </span>
              <span class="row__meta">{{ item.evidenceCount }} 条依据 · {{ day(item.updatedAt) }}</span>
            </template>

            <!-- 档案：给的是**内容本身**，不是一根恒等于 1.00 的条 -->
            <template v-else>
              <span class="row__value">{{ item.value || '—' }}</span>
              <span class="row__meta">
                {{ item.sourceLabel || '权威记录' }} · {{ day(item.updatedAt) }}
              </span>
            </template>

            <span class="row__go" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 12 12">
                <path d="M4.4 2.4 8 6l-3.6 3.6" fill="none" stroke="currentColor" stroke-width="1.6"
                      stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </button>
        </li>
      </ul>
    </template>
  </nav>
</template>

<style scoped>
.list { display: flex; flex-direction: column; gap: var(--s3); min-height: 0; }

/* ── 工具条 ─────────────────────────────────────────────────────── */
.tools { display: grid; grid-template-columns: minmax(0, 280px) auto; gap: var(--s2); }
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

/* 分段控件：一条凹槽 + 一块浮起的选中块（全页只有这一套控件语法） */
.seg {
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
  /* 父级是 flex 容器（纵向），默认会被拉满一整行 —— 三片筛选不该占满 1100px */
  align-self: flex-start;
  width: fit-content; min-width: 240px;
  gap: 2px; padding: 3px;
  border-radius: var(--pt-r-sm, 8px);
  background: var(--pt-well, var(--c-sand-1));
}
.seg__b {
  height: 26px; padding: 0 14px; border-radius: 6px;
  font-size: var(--t-xs); font-weight: 500; color: var(--pt-muted, var(--ink-2));
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  transition: background 160ms var(--ease-out), color 160ms var(--ease-out), box-shadow 160ms var(--ease-out);
}
.seg__b:hover { color: var(--pt-ink, var(--ink-1)); }
.seg__b--on {
  background: var(--pt-surface, var(--c-paper)); color: var(--pt-ink, var(--ink-1));
  box-shadow: var(--e-1), var(--inner-hi);
}
.seg__b i { font-style: normal; color: var(--pt-faint, var(--ink-3)); font-variant-numeric: tabular-nums; }

/* ── 表 ─────────────────────────────────────────────────────────── */
/*
 * 判断：字段 · 把握值 · 把握条 · 依据与时间 · 箭头
 * 档案：字段 · 内容（可变宽）· 来源与时间 · 箭头
 * 列头与行共用同一套模板 —— 对不齐的话，它就不是一张表。
 */
.cols,
.row {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) 52px minmax(96px, 1fr) 150px 16px;
  align-items: center; gap: var(--s4);
}
.cols--rec,
.row--rec {
  grid-template-columns: minmax(0, 200px) minmax(0, 1fr) 170px 16px;
}
.cols {
  padding: 0 14px 6px;
  border-bottom: 1px solid var(--line-1);
}
.cols span { font-size: var(--t-xs); color: var(--ink-4); }
.cols__num { text-align: right; }

.rows {
  list-style: none; margin: 0; padding: 0;
  display: grid; gap: 2px; overflow: auto; min-height: 0;
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
  width: 100%; text-align: left;
  padding: 10px 14px;
  border-radius: var(--pt-r-sm, 8px);
  border: 1px solid transparent;
  transition: background 180ms var(--ease-out), border-color 180ms var(--ease-out),
              box-shadow 180ms var(--ease-out), transform 180ms var(--ease-out);
}
/* 左边那根细线是"看过的是哪一条"的位置标记，所有行都留着它的位置，切换时不跳 */
.row::before {
  content: "";
  position: absolute; left: 4px; top: 9px; bottom: 9px;
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
  font-size: var(--t-body); font-weight: 500; color: var(--pt-ink, var(--ink-1));
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tag {
  flex: 0 0 auto; padding: 1px 5px; border-radius: 5px;
  font-size: 11.5px; font-weight: 500;
  color: var(--pt-warn, var(--warn)); background: rgba(154, 74, 30, 0.10);
}
.row__num {
  font-size: var(--t-sm); color: var(--pt-muted, var(--ink-2));
  font-variant-numeric: tabular-nums; text-align: right;
}

/* 把握条：96px 左右的一根细线，只在这一行里说明"厚不厚" */
.row__track {
  height: 5px; border-radius: var(--r-pill);
  background: var(--pt-track, var(--c-sand-1)); overflow: hidden;
}
.row__track i {
  display: block; height: 100%; border-radius: var(--r-pill);
  background: var(--pt-accent, var(--accent));
  transition: width 620ms var(--ease-expo);
}
/* 三档把握：绿 / 橙 / 粉 —— 平涂，一支色一格 */
.row--mid .row__track i { background: var(--mk-orange); }
.row--low .row__track i { background: var(--mk-pink); }

/* 档案那一列的内容：它是这一行的主角，所以给它正文色而不是说明色 */
.row__value {
  font-size: var(--t-body); color: var(--pt-ink, var(--ink-1));
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.row__meta { font-size: var(--t-xs); color: var(--pt-faint, var(--ink-4)); }
.row__go { color: var(--ink-4); display: grid; place-items: center; }
.row:hover .row__go { color: var(--pt-accent, var(--accent)); }

.empty { font-size: var(--t-sm); color: var(--pt-muted, var(--ink-3)); line-height: 1.7; padding: var(--s2) 0; }

@media (max-width: 900px) {
  .cols { display: none; }
  .row, .row--rec { grid-template-columns: minmax(0, 1fr) auto; gap: 6px var(--s3); }
  .row__track, .row__meta, .row__go { grid-column: 1 / -1; }
  .row__go { display: none; }
}
</style>
