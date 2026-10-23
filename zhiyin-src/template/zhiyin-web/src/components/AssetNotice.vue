<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import { latestAssetVersion } from '../lib/asset-version'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const changes = computed(() => backendDemo.state.assetChanges)
const localHasChanges = computed(() => changes.value.profileKeys.length > 0 || changes.value.direction)
// 资料变化后是否"待核对"以**服务端资产版本**为准：本地标记只能提示"刚改过"，
// 真正是否已经重算，只有版本上的 needs_recompute 知道 —— 否则重算后横幅清不掉，
// 或页面改字段后横幅根本不出现（本轮两种实测都出现过）。
type AssetType = 'report' | 'direction_plan' | 'action_plan'
const serverStale = ref<AssetType[] | null>(null)
const staleReadFailed = ref(false)
const dismissed = ref(false)
const route = useRoute()
const DISMISS_KEY = 'zhiyin:asset-notice-dismissed'
const dismissedSignatures = ref<Partial<Record<AssetType, string>>>(readDismissed())
const staleSignatures = ref<Partial<Record<AssetType, string>>>({})
function readDismissed(): Partial<Record<AssetType, string>> {
  try {
    const raw = JSON.parse(localStorage.getItem(DISMISS_KEY) ?? '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch { return {} }
}
function signature(type: AssetType, version: number, reason: string) {
  // A new version or a new reason is a new decision. The same stale version the
  // user already reviewed stays dismissed across pages and reloads.
  return `${type}:${version}:${reason}`
}
/**
 * 每页只提示与本页资产有关的“待核对”：
 * 报告页不因为方向方案过期就挡住报告；否则刚重算完报告仍看到旧横幅，
 * 用户会以为重算没生效。方向/计划各自在自己的页面提示。
 */
const pageTypes = computed<Array<'report' | 'direction_plan' | 'action_plan'>>(() => {
  if (route.name === 'report') return ['report']
  if (route.name === 'directions') return ['direction_plan']
  if (route.name === 'plan') return ['action_plan']
  return ['report', 'direction_plan', 'action_plan']
})

async function loadStale() {
  const found: AssetType[] = []
  const signatures: Partial<Record<AssetType, string>> = {}
  let failed = false
  for (const type of pageTypes.value) {
    try {
      const versions = await backendClient.versions(type)
      if (!Array.isArray(versions)) throw new Error('Incomplete versions')
      const latest = latestAssetVersion(versions)
      if (!latest) {
        // An empty list is not proof that there is nothing to review.
        failed = true
        continue
      }
      const currentSignature = signature(type, latest.version, latest.recompute_reason ?? '')
      signatures[type] = currentSignature
      if (latest.needs_recompute && dismissedSignatures.value[type] !== currentSignature) found.push(type)
    } catch {
      // 读不到版本时不能把“未知”当成“无需核对”；保留本地变化提示。
      failed = true
    }
  }
  staleSignatures.value = signatures
  staleReadFailed.value = failed
  serverStale.value = found
}
function refresh() { dismissed.value = false; void loadStale() }
onMounted(() => { void loadStale() })
watch(() => changes.value.profileKeys.length, () => { if (changes.value.profileKeys.length) refresh() })
watch(() => changes.value.direction, value => { if (value) refresh() })
watch(() => backendDemo.state.liveReport?.version, () => void loadStale())

const labels: Record<string, string> = { report: '报告', direction_plan: '方向方案', action_plan: '阶段计划' }
const staleLabel = computed(() => {
  const list = serverStale.value ?? []
  return list.map(type => labels[type]).filter(Boolean).join('、')
})
const hasChanges = computed(() => {
  if (dismissed.value) return false
  if (serverStale.value !== null) {
    if (serverStale.value.length > 0) return true
    // 版本读取失败时服务端的“无待核对”不可信，仍按本地变化提示。
    return staleReadFailed.value && localHasChanges.value
  }
  return localHasChanges.value
})
const canDismiss = computed(() => (serverStale.value?.length ?? 0) > 0)
const noticeText = computed(() => {
  const label = staleLabel.value
  if (label) return `资料或方向已变化，${label}待核对`
  return staleReadFailed.value
    ? '资料或方向已变化，但版本状态暂时无法核对'
    : '资料或方向已变化，报告与阶段计划待核对'
})
/**
 * 「确认无需重算」：只记住用户已经核对过这个具体版本，不改后端数据、
 * 不动已有报告/计划结论，也不清掉画像页自己的更正标记。
 * 新版本或新的重算原因会生成新签名，提示会重新出现。
 */
function dismiss() {
  const next = { ...dismissedSignatures.value }
  for (const type of serverStale.value ?? []) {
    const current = staleSignatures.value[type]
    if (current) next[type] = current
  }
  dismissedSignatures.value = next
  try { localStorage.setItem(DISMISS_KEY, JSON.stringify(next)) } catch { /* 私人模式等不可用 */ }
  dismissed.value = true
}
</script>
<template><aside v-if="hasChanges" class="asset-notice" role="status"><UiIcon name="info" :size="17"/><span>{{ noticeText }}</span><DetailPopover title="资料变更与更新状态" label="查看资料变更说明"><p>{{ changes.direction ? '方向选择已有变化。' : '' }}{{ changes.profileKeys.length ? '已有'+changes.profileKeys.length+'项个人信息更正。' : '' }}相关报告与阶段计划可能仍沿用原版本，尚未随本次变化更新。</p><p>如果核对版本后确认这次变化不影响当前结论，可以点「确认无需重算」，这些页面就不再提示。</p><RouterLink class="ws-text-link" to="/profile">查看个人信息</RouterLink></DetailPopover><button v-if="canDismiss" class="ws-text-link asset-notice__dismiss" type="button" @click="dismiss">确认无需重算</button><RouterLink class="ws-text-link" to="/report?focus=versions">核对版本<UiIcon name="arrow" :size="14"/></RouterLink></aside></template>

<style scoped>
.asset-notice__dismiss{border:0;background:transparent;padding:0;font:inherit;color:var(--c-text-2);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.asset-notice__dismiss:hover{color:var(--c-primary)}
@media(max-width:600px){.asset-notice__dismiss{min-height:44px}}
</style>
