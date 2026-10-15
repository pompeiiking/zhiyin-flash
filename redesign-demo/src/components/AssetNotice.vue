<script setup lang="ts">
import { computed } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const changes = computed(() => backendDemo.state.assetChanges)
</script>
<template><aside v-if="changes.profileKeys.length || changes.direction" class="asset-notice" role="status"><UiIcon name="info" :size="17"/><span>资料已变化，报告与计划待核对</span><DetailPopover title="资料变更与更新状态" label="查看资料变更说明"><p>{{ changes.direction ? '方向选择已有变化。' : '' }}{{ changes.profileKeys.length ? '已有'+changes.profileKeys.length+'项个人信息更正。' : '' }}报告与阶段计划仍沿用原版本，尚未随本次变更更新。</p><RouterLink class="ws-text-link" to="/profile">查看个人信息</RouterLink></DetailPopover><RouterLink class="ws-text-link" to="/report?focus=versions">核对版本<UiIcon name="arrow" :size="14"/></RouterLink></aside></template>
