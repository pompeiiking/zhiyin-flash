<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const changes = computed(() => backendDemo.state.assetChanges)
const localHasChanges = computed(() => changes.value.profileKeys.length > 0 || changes.value.direction)
// 资料变化后是否"待核对"以**服务端资产版本**为准：本地标记只能提示"刚改过"，
// 真正是否已经重算，只有版本上的 needs_recompute 知道 —— 否则重算后横幅清不掉，
// 或页面改字段后横幅根本不出现（本轮两种实测都出现过）。
const serverStale = ref<Array<'report' | 'direction_plan' | 'action_plan'> | null>(null)
const dismissed = ref(false)
const route = useRoute()

async function loadStale() {
  const found: Array<'report' | 'direction_plan' | 'action_plan'> = []
  for (const type of ['report', 'direction_plan', 'action_plan'] as const) {
    try {
      const versions = await backendClient.versions(type)
      if (versions?.[0]?.needs_recompute) found.push(type)
    } catch { /* 读不到版本时保留本地提示，不把"未知"当"无需核对" */ }
  }
  serverStale.value = found
}
function refresh() { dismissed.value = false; void loadStale() }
onMounted(() => { void loadStale() })
watch(() => changes.value.profileKeys.length, () => { if (changes.value.profileKeys.length) refresh() })
watch(() => changes.value.direction, value => { if (value) refresh() })
watch(() => backendDemo.state.liveReport?.version, () => void loadStale())
watch(() => route.fullPath, () => { dismissed.value = false; void loadStale() })

const labels: Record<string, string> = { report: '报告', direction_plan: '方向方案', action_plan: '阶段计划' }
const staleLabel = computed(() => {
  const list = serverStale.value ?? []
  return list.map(type => labels[type]).filter(Boolean).join('、')
})
const hasChanges = computed(() => {
  if (dismissed.value) return false
  if (serverStale.value !== null) return serverStale.value.length > 0
  return localHasChanges.value
})
const noticeText = computed(() => {
  const label = staleLabel.value
  return label ? `资料已变化，${label}待核对` : '资料已变化，报告与阶段计划待核对'
})
/**
 * 「确认无需重算」：用户核对过版本后可以自己消掉这条提示。
 * 只清展示标记，不改后端数据、不动已有报告/计划结论；下一次资料再变化会重新提示。
 */
function dismiss() {
  backendDemo.clearAssetChanges()
  dismissed.value = true
}
</script>
<template><aside v-if="hasChanges" class="asset-notice" role="status"><UiIcon name="info" :size="17"/><span>{{ noticeText }}</span><DetailPopover title="资料变更与更新状态" label="查看资料变更说明"><p>{{ changes.direction ? '方向选择已有变化。' : '' }}{{ changes.profileKeys.length ? '已有'+changes.profileKeys.length+'项个人信息更正。' : '' }}相关报告与阶段计划可能仍沿用原版本，尚未随本次变化更新。</p><p>如果核对版本后确认这次变化不影响当前结论，可以点「确认无需重算」，这些页面就不再提示。</p><RouterLink class="ws-text-link" to="/profile">查看个人信息</RouterLink></DetailPopover><button class="ws-text-link asset-notice__dismiss" type="button" @click="dismiss">确认无需重算</button><RouterLink class="ws-text-link" to="/report?focus=versions">核对版本<UiIcon name="arrow" :size="14"/></RouterLink></aside></template>

<style scoped>
.asset-notice__dismiss{border:0;background:transparent;padding:0;font:inherit;color:var(--c-text-2);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.asset-notice__dismiss:hover{color:var(--c-primary)}
@media(max-width:600px){.asset-notice__dismiss{min-height:44px}}
</style>
