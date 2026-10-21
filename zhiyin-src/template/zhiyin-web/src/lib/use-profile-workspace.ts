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
      const results=await Promise.allSettled([backendClient.report(),backendClient.directions(),backendClient.versions('report')])
      if(results[0].status==='fulfilled')backendDemo.setReport(results[0].value)
      if(results[1].status==='fulfilled')backendDemo.setLiveDirections(results[1].value)
      if(results[2].status==='fulfilled')backendDemo.setReportMetadata(results[2].value[0] ?? null)
      const unavailable=[]
      if(results[2].status==='rejected')unavailable.push('判断有效状态')
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
    const present = new Set((livePanel.value?.fields ?? []).map(field => field.key))
    const gaps = new Set((livePanel.value?.gaps ?? []).filter(item => !present.has(item.key)).map(item => item.key))
    for (const item of collection) if (!item.got && !present.has(item.key)) gaps.add(item.key)
    const all = new Set([...present, ...gaps, ...collection.map(item => item.key)])
    return { known: present.size, total: all.size, gap: gaps.size }

  })

  return {
    loading, serviceError, relatedError, live, livePanel, originalLive,
    isVerified, progress, loadWorkspace,
  }
}
