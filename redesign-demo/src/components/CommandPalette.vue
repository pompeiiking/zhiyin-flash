<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { demo } from '../store'
import { META_LINKS, NAV_SECTIONS } from '../lib/nav'
import { skin } from '../lib/theme'
import { SCENARIOS } from '../data/scenarios'
import type { Grade } from '../data/types'

/**
 * 命令面板（⌘K / Ctrl+K）。
 *
 * 为什么它可以没有动效：键盘发起、一天可能开几十上百次 ——
 * 按"该不该动"的判据，这一档是**明确不动**（Raycast 也没有开合动画，那是对的）。
 * 所以这里是全站唯一一个"瞬间出现"的浮层，这是刻意的，不是漏了。
 *
 * 它承担三件事：跳页面、换皮肤、切年级。入口多了之后，导航条只放 5 步，
 * 其余都收进这里 —— 这就是"不做大侧边栏"的代价与代价的解法。
 */

interface Item {
  id: string
  label: string
  hint: string
  group: string
  run: () => void
}

const open = ref(false)
const query = ref('')
const cursor = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)

const router = useRouter()

const items = computed<Item[]>(() => {
  const nav: Item[] = []
  for (const s of NAV_SECTIONS) {
    nav.push({
      id: `nav-${s.key}`,
      label: s.label,
      hint: s.subs.length ? `含 ${s.subs.map((x) => x.label).join(' / ')}` : '',
      group: '页面',
      run: () => router.push(s.to),
    })
    for (const sub of s.subs) {
      nav.push({
        id: `nav-${s.key}-${sub.to}`,
        label: sub.label,
        hint: `在「${s.label}」这一步里`,
        group: '页面',
        run: () => router.push(sub.to),
      })
    }
  }
  for (const m of META_LINKS) {
    nav.push({ id: `meta-${m.to}`, label: m.label, hint: m.hint, group: '页面', run: () => router.push(m.to) })
  }

  const skinItems: Item[] = [
    { id: 'th-light', label: '主题：浅色', hint: '白底 + 灰底', group: '皮肤', run: () => skin.setTheme('light') },
    { id: 'th-dark', label: '主题：深色', hint: '近黑底，边框更强', group: '皮肤', run: () => skin.setTheme('dark') },
    { id: 'th-sys', label: '主题：跟随系统', hint: '系统换我也换', group: '皮肤', run: () => skin.setTheme('system') },
    { id: 'ac-blue', label: '主色：河大蓝', hint: '蓝做主色，红只作提醒', group: '皮肤', run: () => skin.setAccent('blue') },
    { id: 'ac-red', label: '主色：河大红', hint: '校色红做主色', group: '皮肤', run: () => skin.setAccent('red') },
    { id: 'st-plain', label: '风格：极简', hint: '小圆角、无阴影', group: '皮肤', run: () => skin.setStyle('plain') },
    { id: 'st-soft', label: '风格：柔和', hint: '大圆角、轻影', group: '皮肤', run: () => skin.setStyle('soft') },
    { id: 'st-dense', label: '风格：紧凑', hint: '一屏多看几条', group: '皮肤', run: () => skin.setStyle('dense') },
    /* 「动效」那条轴已删除（完整 / 克制不再可选）—— 减少动效只跟随系统的 prefers-reduced-motion */
  ]

  const grades: Item[] = SCENARIOS.map((g) => ({
    id: `grade-${g.id}`,
    label: `使用场景：${g.grade}`,
    hint: g.focus,
    group: '演示',
    run: () => demo.setGrade(g.id as Grade),
  }))

  const actions: Item[] = [
    ...grades,
    { id: 'reset', label: '复位演示数据', hint: '把勾掉的任务、选的方向都退回初始', group: '演示', run: () => demo.resetDemo() },
  ]

  return [...nav, ...skinItems, ...actions]
})

const results = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(
    (i) =>
      i.label.toLowerCase().includes(q) ||
      i.hint.toLowerCase().includes(q) ||
      i.group.toLowerCase().includes(q),
  )
})

const grouped = computed(() => {
  const map = new Map<string, Item[]>()
  for (const it of results.value) {
    const list = map.get(it.group) ?? []
    list.push(it)
    map.set(it.group, list)
  }
  return [...map.entries()].map(([group, list]) => ({ group, list }))
})

/** 结果被压平后的下标，用来支持 ↑↓ 跨组移动 */
const flat = computed(() => grouped.value.flatMap((g) => g.list))

watch(query, () => {
  cursor.value = 0
})

function firstIndex(id: string | undefined) {
  if (!id) return 0
  const i = flat.value.findIndex((x) => x.id === id)
  return i >= 0 ? i : 0
}

function show() {
  open.value = true
  query.value = ''
  cursor.value = 0
  void nextTick(() => inputEl.value?.focus())
}

function hide() {
  open.value = false
}

function move(delta: number) {
  if (!flat.value.length) return
  cursor.value = (cursor.value + delta + flat.value.length) % flat.value.length
}

function runCurrent() {
  const it = flat.value[cursor.value]
  if (!it) return
  hide()
  it.run()
}

function onKeydown(e: KeyboardEvent) {
  // ⌘K / Ctrl+K：全站唯一的热键
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value ? hide() : show()
    return
  }
  if (!open.value) return
  if (e.key === 'Escape') {
    e.preventDefault()
    hide()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(-1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    runCurrent()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

defineExpose({ show })
</script>

<template>
  <div v-if="open" class="palette" role="dialog" aria-modal="true" aria-label="命令面板">
    <div class="palette__mask" @click="hide" />
    <div class="palette__panel">
      <div class="palette__input-row">
        <span class="palette__icon" aria-hidden="true">⌘K</span>
        <input
          ref="inputEl"
          v-model="query"
          class="palette__input"
          placeholder="跳页面、换皮肤、切年级 —— 输入关键词"
          aria-label="搜索命令"
        />
        <button class="palette__esc" @click="hide">Esc</button>
      </div>

      <div class="palette__results">
        <template v-for="g in grouped" :key="g.group">
          <p class="palette__group">{{ g.group }}</p>
          <button
            v-for="it in g.list"
            :key="it.id"
            class="palette__item"
            :class="{ 'palette__item--on': flat[cursor]?.id === it.id }"
            @mouseenter="cursor = firstIndex(it.id)"
            @click="runCurrent()"
          >
            <span class="palette__label">{{ it.label }}</span>
            <span class="palette__hint">{{ it.hint }}</span>
          </button>
        </template>

        <p v-if="!flat.length" class="palette__empty">没有匹配的命令。</p>
      </div>

      <footer class="palette__foot">
        <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
        <span><kbd>Enter</kbd> 执行</span>
        <span><kbd>Esc</kbd> 关闭</span>
        <span class="palette__foot-note">这个面板刻意没有开合动画：键盘发起、高频使用</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.palette {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  justify-content: center;
  padding-top: 12vh;
}

.palette__mask {
  position: absolute;
  inset: 0;
  background: var(--overlay-mask);
}

/* 没有 enter/leave 过渡 —— 见组件顶部注释 */
.palette__panel {
  position: relative;
  width: min(620px, calc(100vw - 32px));
  max-height: 68vh;
  display: flex;
  flex-direction: column;
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--e-3);
  overflow: hidden;
}

.palette__input-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.palette__icon {
  flex: none;
  padding: 2px var(--sp-2);
  border-radius: var(--r-sm);
  background: var(--c-surface-3);
  font-family: var(--font-mono);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.palette__input {
  flex: 1;
  min-width: 0;
  height: 30px;
  border: none;
  background: transparent;
  font-size: var(--fs-14);
  outline: none;
}

.palette__esc {
  flex: none;
  padding: 2px var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.palette__esc:hover {
  border-color: var(--c-border-strong);
  color: var(--c-text);
}

.palette__results {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2);
}

.palette__group {
  padding: var(--sp-3) var(--sp-2) var(--sp-1);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.palette__item {
  width: 100%;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-sm);
  text-align: left;
}

.palette__item--on {
  background: var(--c-primary-weak);
}

.palette__label {
  font-size: var(--fs-14);
  color: var(--c-text);
}

.palette__item--on .palette__label {
  color: var(--c-primary);
  font-weight: var(--fw-medium);
}

.palette__hint {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  text-align: right;
}

.palette__empty {
  padding: var(--sp-6);
  text-align: center;
  font-size: var(--fs-14);
  color: var(--c-text-3);
}

.palette__foot {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-2) var(--sp-4);
  border-top: var(--bw-1) solid var(--c-border);
  background: var(--c-surface-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.palette__foot kbd {
  display: inline-block;
  min-width: 16px;
  margin-right: 2px;
  padding: 0 4px;
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: 3px;
  background: var(--c-surface);
  font-family: var(--font-mono);
  font-size: var(--fs-12);
  text-align: center;
}

.palette__foot-note {
  margin-left: auto;
  color: var(--c-text-3);
}

@media (max-width: 640px) {
  .palette__foot-note {
    display: none;
  }
}
</style>
