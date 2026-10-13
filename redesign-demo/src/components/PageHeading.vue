<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { WORKSPACE_GROUPS } from '../lib/workspace-nav'
const route = useRoute()
const group = computed(() => WORKSPACE_GROUPS.find(g => g.items.some(i => i.paths.includes(route.path)))?.label)
defineProps<{ title: string; description: string }>()
</script>
<template>
  <header class="ws-heading">
    <div><h1>{{ title }}</h1><p><span v-if="group" class="page-context">{{ group }} · </span>{{ description }}</p></div>
    <div v-if="$slots.default" class="ws-heading__actions"><slot /></div>
  </header>
</template>
