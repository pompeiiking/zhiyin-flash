<script setup lang="ts">
import { demo } from '../store'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
</script>
<template>
  <InfoSheet :open="demo.state.noticeOpen" title="提醒" @close="demo.closeNotice()">
    <template v-if="demo.use.activeNotice.value">
      <p class="ws-muted">{{ demo.use.activeNotice.value.kind }}</p><h3 class="ws-section-title" style="margin-top: var(--sp-4)">{{ demo.use.activeNotice.value.title }}</h3><p style="margin-top: var(--sp-4)">{{ demo.use.activeNotice.value.body }}</p>
      <div class="ws-inline-actions"><button class="btn btn--primary" @click="demo.resolveNotice()">{{ demo.use.activeNotice.value.action }}</button><button class="ws-text-button" @click="demo.dismissNotice()">{{ demo.use.activeNotice.value.secondary ?? '先不安排' }}</button></div>
      <button v-if="demo.use.noticeLeft.value" class="ws-text-button" @click="demo.nextNotice()">还有 {{ demo.use.noticeLeft.value }} 条，看下一条<UiIcon name="arrow" :size="16" /></button>
    </template>
    <div v-else class="ws-empty"><h3>眼前没有需要处理的提醒</h3><p>有重要时间节点时，会在这里告诉你。</p></div>
  </InfoSheet>
</template>
