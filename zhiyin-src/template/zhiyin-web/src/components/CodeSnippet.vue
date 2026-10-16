<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import UiIcon from './UiIcon.vue'
const props = defineProps<{ code: string; language?: string }>()
const copied = ref(false), error = ref(''), wrap = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
async function copy() {
  error.value = ''
  try {
    await navigator.clipboard.writeText(props.code)
    copied.value = true; clearTimeout(timer)
    timer = setTimeout(() => { copied.value = false }, 2500)
  } catch { error.value = '复制失败，请选择代码后手动复制。' }
}
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <section class="code-snippet" aria-label="代码片段">
    <header><span>{{ language || '代码' }}</span><div><button type="button" :aria-pressed="wrap" @click="wrap = !wrap">换行</button><button type="button" :aria-label="copied ? '代码已复制' : '复制代码'" @click="copy"><UiIcon :name="copied ? 'check' : 'copy'" :size="14" />{{ copied ? '已复制' : '复制' }}</button></div></header>
    <pre :class="{ 'code-snippet__wrap': wrap }" tabindex="0" aria-label="代码内容"><code>{{ code }}</code></pre>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
.code-snippet {min-width:0;max-width:100%;border:1px solid var(--c-border);border-radius:12px;overflow:hidden;background:var(--c-surface-2);}
.code-snippet header {display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px;border-bottom:1px solid var(--c-border);font-size:12px;color:var(--c-text-2);}
.code-snippet header>span {overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.code-snippet header>div {display:flex;flex-shrink:0;}
.code-snippet button {display:flex;align-items:center;gap:6px;min-width:44px;min-height:44px;padding:4px 8px;background:none;border:0;color:inherit;cursor:pointer;}
.code-snippet button:hover,.code-snippet button[aria-pressed=true] {color:var(--c-primary);background:var(--c-primary-weak);}
.code-snippet pre {margin:0;padding:16px;max-height:420px;overflow:auto;white-space:pre;font:13px/1.7 Consolas,'SFMono-Regular',monospace;color:var(--c-text);tab-size:2;}
.code-snippet pre.code-snippet__wrap {white-space:pre-wrap;overflow-wrap:anywhere;}
.code-snippet p {padding:0 12px 12px;font-size:12px;color:var(--c-text-2);}
</style>
