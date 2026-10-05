<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
const initialRevision = ref('')
const nextRevision = ref('')
const dismissedRevision = ref('')
const pageUrl = window.location.href
let active = true
let timer: ReturnType<typeof setInterval>
async function check() {
  try {
    const response = await fetch('/version.json', { cache: 'no-store' })
    if (!response.ok) return
    const value = await response.json() as { revision?: unknown }
    if (!active || typeof value.revision !== 'string' || !value.revision) return
    if (!initialRevision.value) initialRevision.value = value.revision
    else if (value.revision !== initialRevision.value) nextRevision.value = value.revision
    else nextRevision.value = ''
  } catch { /* Development servers may not expose a deployed version file. */ }
}
onMounted(() => { void check(); timer = setInterval(check, 15000); window.addEventListener('focus', check) })
onBeforeUnmount(() => { active = false; clearInterval(timer); window.removeEventListener('focus', check) })
</script>
<template>
  <aside v-if="nextRevision && nextRevision !== dismissedRevision" class="version-notice" aria-label="新版本提示" role="status"><div><strong>职引有新版本可用</strong><p>当前页面和未提交输入会保留。可以在新标签页使用新版，完成手头操作后再关闭此页。</p></div><a :href="pageUrl" target="_blank" rel="noopener">在新标签页更新 ↗</a><button type="button" @click="dismissedRevision = nextRevision">稍后</button></aside>
</template>
<style scoped>
.version-notice { position:fixed; bottom:20px; left:50%; transform:translateX(-50%); z-index:2000; display:flex; align-items:center; gap:14px; width:min(900px,calc(100% - 32px)); padding:18px 20px; border:1px solid #93b7a4; border-radius:14px; background:#f4faf4; color:#25362c; box-shadow:0 8px 30px #16291f26; }.version-notice strong { font-size:15px; }.version-notice p { margin:5px 0 0; font-size:12px; line-height:1.6; }.version-notice a { color:#176647; white-space:nowrap; font-size:13px; }.version-notice button { border:1px solid #c9d5cc; border-radius:7px; padding:8px 12px; background:white; white-space:nowrap; cursor:pointer; } @media(max-width:640px) { .version-notice { flex-wrap:wrap; }.version-notice div { width:100%; } }
</style>
