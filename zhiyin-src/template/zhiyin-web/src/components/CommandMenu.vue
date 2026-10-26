<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { WORKSPACE_ITEMS, PORTAL_LINK, DIRECTORY_PAGES } from '../lib/workspace-nav'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
import { isComposingKey } from '../lib/scroll-intent'
import { isDeveloperRole } from '../lib/auth'
interface Item { label: string; hint: string; run: () => void }
const open = ref(false)
const query = ref('')
const cursor = ref(0)
const field = ref<HTMLInputElement | null>(null)
const router = useRouter()
const commands = computed<Item[]>(() => [
  // 学生任务与低频辅助入口共用唯一模型，内部预览页不进入日常搜索。
  // 这里不再提供「外观」命令：外观的唯一入口是账号菜单 → 外观（PLAN §3.5）。
  ...[...WORKSPACE_ITEMS, ...DIRECTORY_PAGES, PORTAL_LINK].map((s) => ({ label: s.label, hint: s.hint, run: () => { router.push(s.to) } })),
  ...(isDeveloperRole() ? [{ label: '管理台', hint: '模块、发布与运行状态', run: () => { void router.push('/admin') } }] : []),
])
const results = computed(() => commands.value.filter((c) => (c.label + c.hint).toLowerCase().includes(query.value.trim().toLowerCase())))
watch(query, () => { cursor.value = 0 })
function show() { open.value = true; query.value = ''; cursor.value = 0 }
function hide() { open.value = false }
function run(index: number) { const command = results.value[index]; if (command) { hide(); command.run() } }
function onKey(event: KeyboardEvent) {
  if (isComposingKey(event)) return
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
  <InfoSheet shape="panel" :open="open" title="搜索与跳转" @close="hide" @opened="field?.focus()">
    <label class="ws-command-search"><UiIcon name="search" /><input ref="field" v-model="query" placeholder="搜索页面或功能…" aria-label="搜索命令" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="ws-command-results" :aria-activedescendant="results.length ? 'ws-command-' + cursor : undefined" /></label>
    <div id="ws-command-results" class="ws-command-results" role="listbox" aria-label="页面与功能"><button v-for="(item, index) in results" :id="'ws-command-' + index" :key="item.label + index" class="ws-command-item" role="option" :aria-selected="cursor === index" :class="{ 'ws-command-item--on': cursor === index }" @mouseenter="cursor = index" @click="run(index)"><strong>{{ item.label }}</strong><span>{{ item.hint }}</span></button><p v-if="!results.length" class="ws-muted">没有匹配的功能，换个词试试。</p></div>
    <p class="ws-muted" style="margin-top: var(--sp-4)">↑ ↓ 选择 · Enter 打开 · Esc 关闭</p>
  </InfoSheet>
</template>
