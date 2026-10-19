import { computed, ref } from 'vue'
import { backendClient } from '../api/backend-client'
import { backendDemo } from './backend-demo'
import { demo } from '../store'

export function useProfileWorkspace() {
  /* ═══════════════════════════════════════════════════════════════════════════
   * 2. 读取与更正（能力与原来一致：demo / service 双模式，逐条更正写回）
   * ======================================================================== */

  const isVerified = computed(() => backendDemo.chsiVerified.value)
  const loading = ref(false)
  const serviceError = ref('')
  const relatedError = ref('')
  const livePanel = computed(() => backendDemo.state.liveWorkspace?.profile_panel)
  /** 是不是"服务这次真的给了档案"。缺口清单、依赖边都以这次读取为准，不用演示数据兜底。 */
  const live = computed(() => backendDemo.state.dataMode === 'service')
  const originalLive = computed(() => backendDemo.state.profileOriginals)

  async function loadWorkspace() {
    if (loading.value) return
    loading.value = true
    serviceError.value = ''
    relatedError.value = ''
    try {
      const data = await backendClient.workspace()
      if (!data?.profile_panel) throw new Error('Incomplete profile')
      backendDemo.setWorkspace(data)
      const results=await Promise.allSettled([backendClient.report(),backendClient.directions()])
      if(results[0].status==='fulfilled')backendDemo.setReport(results[0].value)
      if(results[1].status==='fulfilled')backendDemo.setLiveDirections(results[1].value)
      const unavailable=[]
      if(results[0].status==='rejected')unavailable.push('分析报告')
      if(results[1].status==='rejected')unavailable.push('方向方案')
      if(unavailable.length)relatedError.value=`个人资料已读取，但${unavailable.join('和')}暂时没有更新；下方判断可能不完整。`
    } catch {
      serviceError.value = '最新档案暂时没有取得，请重试。现有内容仍保留。'
    } finally {
      loading.value = false
    }
  }

  /** 已有 / 总数 / 缺口：demo 走画像池切片；service 优先用本轮采集清单（学校、专业、层次、在读状态都在里面），
   *  清单缺席时才退回画像面板的 fields + gaps。这样"资料完整度"与页面上的"待补充"字段是同一口径。 */
  const progress = computed(() => {
    if (!live.value) return demo.use.profileProgress.value
    const collection = backendDemo.state.liveWorkspace?.collection_panel?.items ?? []
    const gap = collection.filter((item) => !item.got).length
    if (collection.length) return { known: collection.length - gap, total: collection.length, gap }
    const fields = livePanel.value?.fields?.length ?? 0
    const gaps = livePanel.value?.gaps?.length ?? 0
    return { known: fields, total: fields + gaps, gap: gaps }
  })

  return {
    loading, serviceError, relatedError, live, livePanel, originalLive,
    isVerified, progress, loadWorkspace,
  }
}
