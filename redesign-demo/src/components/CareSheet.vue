<script setup lang="ts">
import InfoSheet from './InfoSheet.vue'
defineProps<{ host: string; title: string; body: string; action: string; secondary: string; rules: string[] }>()
const emit = defineEmits<{ close: []; action: [] }>()
</script>
<template>
  <InfoSheet :open="true" :title="title" @close="emit('close')">
    <p class="ws-muted">{{ host }}</p><p style="margin-top: var(--sp-5)">{{ body }}</p>
    <details class="ws-fold"><summary>为什么是现在</summary><ul class="ws-mini-list"><li v-for="r in rules" :key="r">{{ r }}</li></ul></details>
    <div class="ws-inline-actions"><button class="btn btn--primary" @click="emit('action')">{{ action }}</button><button class="ws-text-button" @click="emit('close')">{{ secondary }}</button></div>
    <p class="ws-demo-note">这是一次陪伴提醒的示例。选择第一步，会加入当前演示的今日任务。</p>
  </InfoSheet>
</template>
