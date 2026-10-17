<script setup lang="ts">
import { computed } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const changes = computed(() => backendDemo.state.assetChanges)
const hasChanges = computed(() => changes.value.profileKeys.length > 0 || changes.value.direction)
/**
 * 「确认无需重算」：这一轮变更是本页/本会话记录下来的（画像更正、选择方向）。
 * 用户核对过版本、确认本次变更不影响当前结论后，应当能自己消掉这条提示，
 * 而不是每次回到首页/计划/报告都反复出现（深度测试 D9）。
 * 只清展示标记，不改后端数据、不动已有报告/计划结论。
 */
function dismiss() {
  backendDemo.clearAssetChanges()
}
</script>
<template><aside v-if="hasChanges" class="asset-notice" role="status"><UiIcon name="info" :size="17"/><span>资料已变化，报告与计划待核对</span><DetailPopover title="资料变更与更新状态" label="查看资料变更说明"><p>{{ changes.direction ? '方向选择已有变化。' : '' }}{{ changes.profileKeys.length ? '已有'+changes.profileKeys.length+'项个人信息更正。' : '' }}报告与阶段计划仍沿用原版本，尚未随本次变更更新。</p><p>如果核对版本后确认这次变更不影响当前结论，可以点「确认无需重算」，这些页面就不再提示。</p><RouterLink class="ws-text-link" to="/profile">查看个人信息</RouterLink></DetailPopover><button class="ws-text-link asset-notice__dismiss" type="button" @click="dismiss">确认无需重算</button><RouterLink class="ws-text-link" to="/report?focus=versions">核对版本<UiIcon name="arrow" :size="14"/></RouterLink></aside></template>

<style scoped>
.asset-notice__dismiss{border:0;background:transparent;padding:0;font:inherit;color:var(--c-text-2);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.asset-notice__dismiss:hover{color:var(--c-primary)}
@media(max-width:600px){.asset-notice__dismiss{min-height:44px}}
</style>
