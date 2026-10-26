<script setup lang="ts">
import Workflows from '@/developer/Workflows.vue'
import type { ModuleView } from './client'
import '@/developer/developer.css'

defineProps<{ modules: ModuleView[]; administrator: boolean }>()
</script>

<template>
  <section aria-labelledby="admin-workflows-title">
    <h2 id="admin-workflows-title" class="sr-only">数据编排</h2>
    <div class="developer admin-embed">
      <Workflows :modules="modules" :administrator="administrator" />
    </div>
  </section>
</template>

<style scoped>
.admin-embed :deep(.dev-actions h2) {
  display: none;
}
.admin-embed :deep(.dev-actions:first-child) {
  margin-top: 4px;
}
</style>
