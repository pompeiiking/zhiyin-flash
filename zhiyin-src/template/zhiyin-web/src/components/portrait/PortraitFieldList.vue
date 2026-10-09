<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

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
    /**
     * 更正这一条（issue #26 第三条）。
     *
     * 为什么由外层把动作**当参数传进来**、而不是这一层自己去调接口：
     * 这一层是展示件（见下面补充录入那段说明）—— 它只该知道"用户打算把这一条
     * 改成什么"，写库、乐观更新、失败回滚都是 store 的事（`correctProfileField`）。
     * 返回值是**要给用户看的那句话**：空串 = 存下了，非空 = 为什么没存下。
     */
    correct?: (key: string, value: string) => Promise<string>
  }>(),
  { kind: 'judgment' },
)

const emit = defineEmits<{
  (e: 'select', key: string): void
  /**
   * 挂着「没定」的那一条被点了：上报"要补哪一条"，由外层送他去补。
   *
   * 这一层**只上报、不写数据**：补画像在全站只有一条写路径（把这一条交给主理去问，
   * 见 PortraitOverlay 的 `supplement`）。清单是个展示件，它自己不知道该往库里写什么，
   * 更不该替用户写 —— 画像里每一条都必须是"有出处的事实"。
   */
  (e: 'supplement', key: string): void
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

/**
 * 点一行去哪儿（issue #26 第四条）。
 *
 * 挂着「没定」的那一条，点它 = **去补它**：待验证的条目此前只是一行说明，
 * 用户读完还得自己去找入口；现在点一下就直接落到补充录入的那条路上。
 * 已经定了的条目语义不变，仍然是"看这一条"。
 *
 * 为什么不是"再挂一颗小按钮"：整行本来就是一颗 `<button>`（Tab 能到，
 * 焦点环由 base.css 的 `:focus-visible` 统一给），行内再嵌一颗按钮既不合 HTML，
 * 也会把整行这块大点击区切成两个小块 —— 待验证这一条要的恰恰是"整行都能点"。
 * （行尾那颗「更正」同样是**整行的兄弟节点**、不是嵌在行里的按钮，见 .row__fix。）
 */
function pick(item: PortraitItem) {
  if (item.pending) emit('supplement', item.key)
  else emit('select', item.key)
}

/*
 * ── 就地更正（issue #26 第三条） ────────────────────────────────────
 *
 * 用户的原话是"后续用户想要更正专业信息，无法完成修改"：画像里每一条都只能看。
 * 所以这里补的是**他自己改**的那条路 —— 点「更正」，那一行当场变成输入行，
 * 存下之后界面立刻显示新值（乐观更新在 store 里，失败会整份还原并把原因显示出来）。
 *
 * 【为什么不用弹窗】
 * 改的是一个值，就该在那一行里改：再弹一层界面，用户要重新确认"我在改哪一条"，
 * 而那一行本身就把字段名、现值、来源摆在一起。
 *
 * 【可访问性】
 * 入口、提交、取消都是真 `<button>`（不给 div 挂 click），输入是真 `<input>`：
 * Tab 能依次到达，焦点环由 base.css 的 `:focus-visible` 统一给（见 styles/base.css）；
 * `aria-label` 说清改的是哪一条；`enterkeyhint="done"` 让手机键盘显示"完成"；
 * Enter 提交、Esc 取消（`.stop` 把按键留在这一行里，不然 ↑↓ 会被清单的
 * 上下切换抢走、Esc 会被浮层的"退一层"抢走）。
 */
/**
 * 与后端 `DefaultProfileService.MAX_FIELD_VALUE_CHARS` 对齐（40）。
 *
 * 这里只用来说给用户听（输入框旁边那个计数），**不做静默截断**：
 * 截断会让他以为自己写的后半句被记住了。超长由后端如实拒，
 * 理由照原样显示在输入框下面。
 *
 * **改这个数字必须同时改后端常量**：漂了会让"计数还允许、后端却拒了"（或反过来
 * 提前拦住），而两边都各自看着正常。守卫见 `tests/test_field_length_limit_alignment.py`。
 */
const MAX_CHARS = 40

const editingKey = ref<string | null>(null)
const draft = ref('')
const saving = ref(false)
const error = ref('')
/** 正在改的那一条的输入框（一次只有一个，打开后自动聚焦） */
const editInput = ref<HTMLInputElement | HTMLInputElement[] | null>(null)

const overLimit = computed(() => draft.value.trim().length > MAX_CHARS)

function startEdit(item: PortraitItem) {
  editingKey.value = item.key
  // 现值能读成一句人话就带上（档案那几条都有）；没有就从空开始写。
  // 多值字段（成绩单那种）在行里本来就是"、"连起来的一句话，改它等于用
  // 他自己的话重写这一格 —— 这正是"更正"要做的事。
  draft.value = item.value ?? ''
  error.value = ''
}

function cancelEdit() {
  editingKey.value = null
  error.value = ''
}

async function submitEdit(item: PortraitItem) {
  if (saving.value || !props.correct) return
  saving.value = true
  error.value = ''
  const message = await props.correct(item.key, draft.value)
  saving.value = false
  if (message) {
    // 失败：store 已经把值还原了，输入框留着他改（原因显示在下面）
    error.value = message
    return
  }
  editingKey.value = null
}

/** 打开编辑器就把光标放进去，并全选现值。
 *
 * 全选是有意的：会点「更正」的人多半是要把这一格**整句换掉**
 * （"计算机大类" 换成 "软件工程"），点完直接用键盘重打就行 ——
 * 先按一下退格、或者用鼠标先拖选一遍，是多余的一步。
 * 想改中间几个字的人按一下方向键就取消了选择，不损失什么。
 */
watch(editingKey, async (key) => {
  if (!key) return
  await nextTick()
  const el = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
  el?.focus()
  el?.select()
})
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
        <!-- 更正那一列的列头留空：它会占一列宽（行里的按钮浮在它上面），
             这里不写字，否则这张表会多出一个"更正 / 更正 / 更正…"的标题列 -->
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
          <!--
            正在改的那一条：整行换成输入行（就地改，不弹第二层界面）。
            只有它换成输入行，其余行原样 —— 用户一眼就知道在改哪一条。
          -->
          <div v-if="editingKey === item.key" class="edit" :data-key="item.key">
            <span class="edit__who">更正「{{ item.label }}」</span>
            <input
              ref="editInput"
              v-model="draft"
              class="edit__in"
              type="text"
              autocomplete="off"
              spellcheck="false"
              enterkeyhint="done"
              data-action="profile-field-input"
              :data-key="item.key"
              :aria-label="`更正「${item.label}」的值`"
              aria-describedby="profile-edit-note"
              @keydown.stop
              @keydown.enter.prevent="submitEdit(item)"
              @keydown.esc.prevent="cancelEdit"
            />
            <span class="edit__count" :class="{ 'edit__count--over': overLimit }" aria-hidden="true">
              {{ draft.trim().length }}/{{ MAX_CHARS }}
            </span>
            <button
              class="edit__save"
              type="button"
              data-action="profile-field-save"
              :data-key="item.key"
              :disabled="saving"
              @click="submitEdit(item)"
            >
              {{ saving ? '正在存…' : '存下这条' }}
            </button>
            <button
              class="edit__cancel"
              type="button"
              data-action="profile-field-cancel"
              @click="cancelEdit"
            >
              取消
            </button>
            <p v-if="error" id="profile-edit-note" class="edit__err" role="alert">{{ error }}</p>
            <p v-else id="profile-edit-note" class="edit__why">
              存下之后这一条算你自己填的，不再挂在"还差什么"里 —— 画像按新值重算。
            </p>
          </div>

          <template v-else>
            <button
              class="row"
              :class="{ 'row--rec': !judging, [`row--${tier(item.confidence)}`]: judging, 'row--on': item.key === selectedKey }"
              type="button"
              :aria-current="item.key === selectedKey"
              @click="pick(item)"
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
              <!-- 这一格留给旁边那颗「更正」：它必须浮在整行按钮**上面**，
                   而不是嵌进去（按钮里不能再放按钮）。列宽也对齐，见 .cols -->
              <span class="row__fixslot" aria-hidden="true" />
            </button>

            <button
              v-if="correct"
              class="row__fix"
              type="button"
              data-action="profile-field-correct"
              :data-key="item.key"
              :aria-label="`更正「${item.label}」`"
              @click="startEdit(item)"
            >
              更正
            </button>
          </template>
        </li>
      </ul>
    </template>
  </nav>
</template>

<style scoped>
.list { display: flex; flex-direction: column; gap: var(--s3); min-height: 0;
  /* 行尾「更正」那一列的宽度：列头、行、缺口那一列共用它，三者才对得齐 */
  --fix-w: 62px;
}

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
@media (hover: hover) and (pointer: fine) {
.seg__b:hover { color: var(--pt-ink, var(--ink-1)); }
}
.seg__b--on {
  background: var(--pt-surface, var(--c-paper)); color: var(--pt-ink, var(--ink-1));
  box-shadow: var(--e-1), var(--inner-hi);
}
.seg__b i { font-style: normal; color: var(--pt-faint, var(--ink-3)); font-variant-numeric: tabular-nums; }

/* ── 表 ─────────────────────────────────────────────────────────── */
/*
 * 判断：字段 · 把握值 · 把握条 · 依据与时间 · 箭头 · 更正
 * 档案：字段 · 内容（可变宽）· 来源与时间 · 箭头 · 更正
 * 列头与行共用同一套模板 —— 对不齐的话，它就不是一张表。
 * 最后一列 `--fix-w` 是行尾那颗「更正」的位置（它绝对定位浮在这一列上）。
 */
.cols,
.row {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) 52px minmax(96px, 1fr) 150px 16px var(--fix-w);
  align-items: center; gap: var(--s4);
}
.cols--rec,
.row--rec {
  grid-template-columns: minmax(0, 200px) minmax(0, 1fr) 170px 16px var(--fix-w);
}
.cols {
  padding: 0 14px 6px;
  border-bottom: 1px solid var(--line-1);
}
.cols span { font-size: var(--t-xs); color: var(--ink-3); }
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
.rows li { animation: pt-row-in 420ms var(--ease-expo) both; position: relative; }
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
@media (hover: hover) and (pointer: fine) {
.row:hover { background: var(--pt-surface, var(--c-paper)); transform: translateY(-1px); box-shadow: var(--e-1), var(--inner-hi); }
}
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
  color: var(--pt-warn, var(--warn)); background: color-mix(in srgb, var(--warn) 10%, transparent);
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

.row__meta { font-size: var(--t-xs); color: var(--pt-faint, var(--ink-3)); }
.row__go { color: var(--ink-4); display: grid; place-items: center; }
@media (hover: hover) and (pointer: fine) {
.row:hover .row__go { color: var(--pt-accent, var(--accent)); }
}

.empty { font-size: var(--t-sm); color: var(--pt-muted, var(--ink-3)); line-height: 1.7; padding: var(--s2) 0; }

/* ── 就地更正 ───────────────────────────────────────────────────── */

/*
 * 行尾那颗「更正」。
 *
 * 它**不能**嵌在整行按钮里（按钮里放按钮不是合法 HTML，Tab 也会乱），
 * 所以它是整行的兄弟节点，绝对定位浮在行的最后一列上：
 * 位置由 `--fix-w` 与行的右内边距决定，视觉上就在那一格里。
 * 平时低调（它就是一行字），hover / 聚焦时才亮起来 —— 一屏十几行，
 * 每行都挂一颗实心按钮会把"这一行在说什么"淹掉。
 */
.row__fix {
  position: absolute; right: 14px; top: 50%;
  transform: translateY(-50%);
  width: var(--fix-w);
  height: 26px; border-radius: var(--r-pill);
  border: 1px solid transparent;
  font-size: var(--t-xs); font-weight: 500;
  color: var(--pt-faint, var(--ink-3));
  transition: color 160ms var(--ease-out), border-color 160ms var(--ease-out),
              background 160ms var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
.row__fix:hover {
  color: var(--pt-accent, var(--accent));
  border-color: var(--pt-line, var(--line-2));
  background: var(--pt-surface, var(--c-paper));
}
}
.row__fix:focus-visible {
  color: var(--pt-accent, var(--accent));
  border-color: var(--pt-line, var(--line-2));
  background: var(--pt-surface, var(--c-paper));
}

/* 输入行：一整行（含列头行的高度），让人一眼看出"改的是这一条" */
.edit {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto auto;
  align-items: center; gap: var(--s2) var(--s3);
  padding: 9px 14px;
  border: 1px solid var(--pt-accent, var(--accent));
  border-radius: var(--pt-r-sm, 8px);
  background: var(--pt-surface, var(--c-paper));
  box-shadow: var(--e-1), var(--inner-hi);
}
.edit__who {
  font-size: var(--t-sm); font-weight: 600;
  color: var(--pt-ink, var(--ink-1)); white-space: nowrap;
}
.edit__in {
  height: 30px; min-width: 0; padding: 0 10px;
  border: 1px solid var(--pt-line, var(--line-2));
  border-radius: 6px;
  background: var(--pt-well, var(--c-sand-1));
  font-size: var(--t-sm); color: var(--pt-ink, var(--ink-1));
}
.edit__in:focus-within,
.edit__in:focus { background: var(--pt-surface, var(--c-paper)); }
.edit__count {
  font-size: var(--t-xs); color: var(--pt-faint, var(--ink-3));
  font-variant-numeric: tabular-nums;
}
/* 超长只是**说给他听**（后端会如实拒并说明上限），不静默截断 */
.edit__count--over { color: var(--pt-warn, var(--warn)); }

.edit__save {
  height: 28px; padding: 0 14px; border-radius: var(--r-pill);
  background: var(--pt-accent, var(--accent)); color: var(--accent-ink);
  font-size: var(--t-xs); font-weight: 600;
  transition: background 160ms var(--ease-out), transform 160ms var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
.edit__save:hover:not(:disabled) { background: var(--pt-accent-deep, var(--accent-deep)); transform: translateY(-1px); }
}
.edit__save:disabled { opacity: 0.6; cursor: default; }
.edit__cancel {
  height: 28px; padding: 0 10px; border-radius: var(--r-pill);
  font-size: var(--t-xs); font-weight: 500; color: var(--pt-muted, var(--ink-2));
  border: 1px solid var(--pt-line, var(--line-2));
}
@media (hover: hover) and (pointer: fine) {
.edit__cancel:hover { color: var(--pt-ink, var(--ink-1)); border-color: var(--pt-line-strong, var(--line-3)); }
}

.edit__why,
.edit__err {
  grid-column: 1 / -1;
  font-size: var(--t-xs); line-height: 1.65;
}
.edit__why { color: var(--pt-faint, var(--ink-3)); }
/* 没改成的那句话：说清**为什么**（空值 / 超长 / 画像里没这一格），他照着改就行 */
.edit__err { color: var(--pt-warn, var(--warn)); }

@media (max-width: 900px) {
  .cols { display: none; }
  .row, .row--rec { grid-template-columns: minmax(0, 1fr) auto; gap: 6px var(--s3); }
  .row__track, .row__meta, .row__go, .row__fixslot { grid-column: 1 / -1; }
  .row__go { display: none; }
  /* 窄屏：更正浮在行的右上角（列头已隐藏，不必再对齐某一列） */
  .row__fix { top: 6px; transform: none; }
  .edit { grid-template-columns: minmax(0, 1fr) auto auto; }
  .edit__who { grid-column: 1 / -1; }
  .edit__count { display: none; }
}
</style>
