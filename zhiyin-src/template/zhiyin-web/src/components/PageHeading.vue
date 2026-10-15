<script setup lang="ts">
import DetailPopover from './DetailPopover.vue'
defineProps<{ title: string; description: string }>()
</script>
<template>
  <header class="ws-heading">
    <div class="ws-heading__identity"><h1>{{ title }}</h1><DetailPopover :title="title + ' · 页面说明'" :label="'查看' + title + '说明'"><p>{{ description }}</p><div v-if="$slots.meta" class="ws-heading__meta"><slot name="meta" /></div></DetailPopover></div>
    <div v-if="$slots.default" class="ws-heading__actions"><slot /></div>
  </header>
</template>
