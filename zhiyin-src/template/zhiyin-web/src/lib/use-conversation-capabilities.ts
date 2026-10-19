import { computed, ref, watch } from 'vue'
import { backendClient } from '../api/backend-client'
import { friendlyError } from './use-conversation-errors'
import type { CapabilitiesView, CapabilityItemView } from '../api/backend-types'

/** 能力面板：可用 / 未启用（原因）/ 替代；打开浮层时读取清单。 */
export function useConversationCapabilities() {
  // ---- F9 能力面板：可用 / 未启用（原因）/ 替代 ----
  const capabilitiesOpen = ref(false)
  const capabilitiesLoading = ref(false), capabilitiesError = ref('')
  const capabilities = ref<CapabilitiesView | null>(null)
  const capabilityItems = computed<CapabilityItemView[]>(() => capabilities.value?.items ?? [])
  /** 能力状态：未接入（联网/检索这类需要配置的能力）与未启用分开说，避免暗示"可用"。 */
  function capabilityStatus(item: CapabilityItemView) {
    if (item.available) return '可用'
    const text = `${item.key || ''} ${item.label || ''} ${item.reason || ''}`
    return /联网|在线检索|外部检索|web|search|internet/i.test(text) ? '未接入' : '未启用'
  }
  async function loadCapabilities(force = false) {
    if (capabilitiesLoading.value) return
    if (capabilities.value && !force) return
    capabilitiesLoading.value = true
    capabilitiesError.value = ''
    try {
      capabilities.value = await backendClient.capabilities()
    } catch (e) {
      capabilitiesError.value = friendlyError(e)
    } finally { capabilitiesLoading.value = false }
  }
  watch(capabilitiesOpen, open => { if (open) void loadCapabilities() })
  return { capabilitiesOpen, capabilitiesLoading, capabilitiesError, capabilities, capabilityItems, capabilityStatus, loadCapabilities }
}
