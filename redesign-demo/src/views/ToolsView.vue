<script setup lang="ts">
import registry from '../data/backend-registry.json'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import ModuleCatalog from '../components/ModuleCatalog.vue'
</script>
<template>
  <div class="ws-page"><PageHeading title="应用工具" description="把常用功能放在手边，数据仍来自同一份计划与记录。" /><ModuleCatalog/><details class="ws-context"><summary>查看演示工具入口</summary><div class="ws-directory"><RouterLink v-for="m in registry.modules" :key="m.id" :to="m.id === 'action_progress' ? '/plan' : '/review?view=achievements'"><strong>{{ m.name }}</strong><span>{{ m.description }}</span><UiIcon name="arrow" /></RouterLink></div><p class="ws-demo-note">以下为预置演示入口；上方目录读取已发布且启用的应用。</p></details></div>
</template>
