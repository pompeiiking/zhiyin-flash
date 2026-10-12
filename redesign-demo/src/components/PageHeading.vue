<script setup lang="ts">
defineProps<{ title: string; description: string }>()
</script>
<template>
  <header class="ws-heading">
    <div><h1>{{ title }}</h1><p>{{ description }}</p></div>
    <div v-if="$slots.default" class="ws-heading__actions"><slot /></div>
  </header>
</template>
