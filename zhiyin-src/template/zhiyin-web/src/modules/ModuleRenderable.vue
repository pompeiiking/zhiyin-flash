<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import ModuleContent from './ModuleContent.vue'
import { listModules, type ModuleView, type ModuleResult } from './client'
const props = defineProps<{ kind: string; payload: Record<string, unknown> }>()
const entry = ref<ModuleView>()
let active = true
async function refresh() { try { const rows = await listModules('conversation'); if (active) entry.value = rows.find(x => `module.${x.manifest.id}` === props.kind && x.effective_enabled && x.manifest.conversation) } catch { if (active) entry.value = undefined } }
let timer: ReturnType<typeof setInterval>
onMounted(() => { void refresh(); timer = setInterval(refresh, 15000) })
onBeforeUnmount(() => { active = false; clearInterval(timer) })
</script>
<template><ModuleContent v-if="entry" :module="entry" :result="(payload as unknown as ModuleResult)" slot-name="conversation" readonly /></template>
