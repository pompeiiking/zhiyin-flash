<script setup lang="ts">
import registry from '../data/backend-registry.json'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
</script>
<template>
  <div class="ws-page"><PageHeading title="应用工具" description="把常用功能放在手边，数据仍来自同一份计划与记录。" /><section class="ws-paper"><div class="ws-directory"><RouterLink v-for="m in registry.modules" :key="m.id" :to="m.id === 'action_progress' ? '/plan' : '/review?view=achievements'"><strong>{{ m.name }}</strong><span>{{ m.description }}</span><UiIcon name="arrow" /></RouterLink></div></section><p class="ws-demo-note">这里展示后端仓库已提供的两个应用示例。正式环境只显示后端已发布且启用的应用。</p></div>
</template>
