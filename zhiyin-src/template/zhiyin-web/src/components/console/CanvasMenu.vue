<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

/**
 * 控制台的鼠标右键功能栏。
 *
 * 空白处右键 = "把东西叫出来"：可以唤回被你解决掉的块、叫出新的功能块、整体重排。
 * 在某个块上右键 = "对这块做什么"：解决它、先挪开、看它的依据。
 *
 * 之所以要有这一层：主力交互是"AI 推给你的块"，但人总有想自己找东西的时候。
 * 右键就是那个"我想自己来"的入口 —— 不占屏幕、不打断当前的块，随手一按就出来。
 */
export interface MenuItem {
  id: string
  label: string
  hint?: string
  tone?: 'default' | 'accent' | 'danger'
  disabled?: boolean
}

const props = defineProps<{
  x: number
  y: number
  title: string
  items: MenuItem[]
}>()

const emit = defineEmits<{ (e: 'pick', id: string): void; (e: 'close'): void }>()

const el = ref<HTMLElement | null>(null)

/** 别让菜单跑出屏幕 —— 靠边右键时往里收 */
function place() {
  const node = el.value
  if (!node) return
  const r = node.getBoundingClientRect()
  const dx = props.x + r.width > window.innerWidth - 12 ? window.innerWidth - props.x - r.width - 12 : 0
  const dy = props.y + r.height > window.innerHeight - 12 ? window.innerHeight - props.y - r.height - 12 : 0
  node.style.transform = `translate(${Math.min(0, dx)}px, ${Math.min(0, dy)}px)`
}

watch(() => [props.x, props.y, props.items.length], () => requestAnimationFrame(place))
onMounted(() => {
  requestAnimationFrame(place)
  const onKey = (e: KeyboardEvent) => e.key === 'Escape' && emit('close')
  document.addEventListener('keydown', onKey)
  onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
})
</script>

<template>
  <div
    ref="el"
    class="menu mo-pop"
    :style="{ left: `${x}px`, top: `${y}px` }"
    role="menu"
    :aria-label="title"
    @contextmenu.prevent
  >
    <p class="menu__title label">{{ title }}</p>
    <button
      v-for="it in items"
      :key="it.id"
      class="item"
      type="button"
      role="menuitem"
      :class="it.tone ? `item--${it.tone}` : ''"
      :disabled="it.disabled"
      @click="emit('pick', it.id)"
    >
      <span class="item__label">{{ it.label }}</span>
      <span v-if="it.hint" class="label item__hint">{{ it.hint }}</span>
    </button>
  </div>
</template>

<style scoped>
.menu {
  position: fixed;
  z-index: var(--z-toast);
  min-width: 236px; padding: 6px;
  /* 右键菜单：白纸 + 1px 墨线。粗框在这一稿里没有位置 */
  border: var(--bw) solid var(--ink-1); border-radius: var(--r-md);
  background: var(--n-1);
  box-shadow: none;
}
.menu__title { padding: var(--s2) var(--s3) 6px; color: var(--ink-3); }
.item {
  width: 100%; display: flex; align-items: baseline; justify-content: space-between; gap: var(--s4);
  padding: 8px var(--s3); border-radius: var(--r-sm);
  text-align: left; font-size: var(--fs-small); color: var(--ink-1);
  transition: background var(--mo-fast) var(--mo-out);
}
.item:hover:not(:disabled) { background: var(--fill-hover); }
.item:disabled { opacity: 0.4; cursor: not-allowed; }
.item__hint { color: var(--ink-3); }
.item--accent .item__label { color: var(--accent); font-weight: 500; }
.item--danger .item__label { color: var(--warn); }
</style>

