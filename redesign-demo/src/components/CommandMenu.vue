<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { demo } from '../store'
import { WORKSPACE_ITEMS, WORKSPACE_TOOLS } from '../lib/workspace-nav'
import { skin } from '../lib/theme'
import { SCENARIOS } from '../data/scenarios'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
interface Item { label: string; hint: string; run: () => void }
const open = ref(false)
const query = ref('')
const cursor = ref(0)
const field = ref<HTMLInputElement | null>(null)
const router = useRouter()
const commands = computed<Item[]>(() => [
  ...[...WORKSPACE_ITEMS, ...WORKSPACE_TOOLS].map((s) => ({ label: s.label, hint: s.hint, run: () => { router.push(s.to) } })),
  ...SCENARIOS.map((s) => ({ label: '使用场景：' + s.grade, hint: s.focus, run: () => demo.setGrade(s.id) })),
  { label: '主题：浅色', hint: '外观设置', run: () => skin.setTheme('light') },
  { label: '主题：深色', hint: '外观设置', run: () => skin.setTheme('dark') },
  { label: '主题：跟随系统', hint: '外观设置', run: () => skin.setTheme('system') },
  { label: '主色：河大蓝', hint: '外观设置', run: () => skin.setAccent('blue') },
  { label: '主色：河大红', hint: '外观设置', run: () => skin.setAccent('red') },
  { label: '风格：极简', hint: '外观设置', run: () => skin.setStyle('plain') },
  { label: '风格：柔和', hint: '外观设置', run: () => skin.setStyle('soft') },
  { label: '风格：紧凑', hint: '外观设置', run: () => skin.setStyle('dense') },
  { label: '复位演示数据', hint: '恢复预置状态', run: () => demo.resetDemo() },
  { label: '恢复操作引导', hint: '重新查看各页使用提示', run: () => demo.resetGuide() },
])
const results = computed(() => commands.value.filter((c) => (c.label + c.hint).toLowerCase().includes(query.value.trim().toLowerCase())))
watch(query, () => { cursor.value = 0 })
function show() { open.value = true; query.value = ''; cursor.value = 0 }
function hide() { open.value = false }
function run(index: number) { const command = results.value[index]; if (command) { hide(); command.run() } }
function onKey(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); open.value ? hide() : show(); return }
  if (!open.value) return
  if (event.key === 'Escape') { event.preventDefault(); hide() }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (results.value.length) cursor.value = (cursor.value + (event.key === 'ArrowDown' ? 1 : -1) + results.value.length) % results.value.length
    void nextTick(() => document.getElementById('ws-command-' + cursor.value)?.scrollIntoView({ block: 'nearest' }))
  }
  if (event.key === 'Enter' && event.target === field.value) { event.preventDefault(); run(cursor.value) }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
defineExpose({ show })
</script>
<template>
  <InfoSheet :open="open" title="搜索与跳转" @close="hide" @opened="field?.focus()">
    <label class="ws-command-search"><UiIcon name="search" /><input ref="field" v-model="query" placeholder="找页面、切年级、换外观…" aria-label="搜索命令" /></label>
    <div class="ws-command-results"><button v-for="(item, index) in results" :id="'ws-command-' + index" :key="item.label + index" class="ws-command-item" :class="{ 'ws-command-item--on': cursor === index }" @mouseenter="cursor = index" @click="run(index)"><strong>{{ item.label }}</strong><span>{{ item.hint }}</span></button><p v-if="!results.length" class="ws-muted">没有匹配的功能，换个词试试。</p></div>
    <p class="ws-muted" style="margin-top: var(--sp-4)">↑ ↓ 选择 · Enter 打开 · Esc 关闭</p>
  </InfoSheet>
</template>
