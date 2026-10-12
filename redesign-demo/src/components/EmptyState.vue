<script setup lang="ts">
import WorkspaceMotif from './WorkspaceMotif.vue'
withDefaults(defineProps<{ title: string; description: string; kind?: 'chat' | 'notes' | 'intel' }>(), { kind: 'notes' })
</script>
<template><div class="exp-empty"><WorkspaceMotif :kind="kind" /><h2>{{ title }}</h2><p>{{ description }}</p><div v-if="$slots.default" class="exp-empty__actions"><slot /></div></div></template>
