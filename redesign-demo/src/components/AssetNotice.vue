<script setup lang="ts">
import { computed } from 'vue'
import { backendDemo } from '../lib/backend-demo'
const changes = computed(() => backendDemo.state.assetChanges)
</script>
<template><aside v-if="changes.profileKeys.length || changes.direction" class="asset-notice" role="status"><strong>相关内容需要重新核对</strong><p>{{ changes.direction ? '方向选择已有变化。' : '' }}{{ changes.profileKeys.length ? '已有'+changes.profileKeys.length+'项个人信息更正。' : '' }}当前示例报告与阶段计划仍使用原内容。</p><div class="ws-inline-actions"><RouterLink class="ws-text-link" to="/report?focus=versions">核对报告版本与更新状态</RouterLink><RouterLink class="ws-text-link" to="/profile">查看个人信息</RouterLink></div></aside></template>
