import { computed, nextTick, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { FieldRow } from './use-profile-fields'
import type { Conclusion } from './use-profile-conclusions'

interface ProfileNavigationDeps {
  profileTab: Ref<'facts' | 'judgments' | 'gaps' | 'sources'>
  conclusionMap: ComputedRef<Record<string, Conclusion>>
  fieldDeps: ComputedRef<Record<string, string[]>>
  reduced: () => boolean
}

export function useProfileNavigation(deps: ProfileNavigationDeps) {
  const { profileTab, conclusionMap, fieldDeps, reduced } = deps

  /** 双向高亮：悬停/聚焦一边，另一边的关联项要看得见 */
  const hoverField = ref<string | null>(null)
  const hoverConclusion = ref<string | null>(null)
  const lingerConclusion = ref<string | null>(null)

  /**
   * 行内展开的状态。
   * v8 把「撑起哪些判断」和「原始依据与操作」合并成**一次行内展开**：
   * 整行可点 → 展开后里面既有关系（撑起的判断，可跳）、也有来历（证据）与动作（≥44px）。
   * 所以"钉住关系高亮"不再是第二个小按钮，它就是"这一行开着的时候"。
   */
  const openField = ref<string | null>(null)
  const openConclusion = ref<string | null>(null)

  const activeField = computed(() => hoverField.value ?? openField.value)
  const activeConclusion = computed(() => hoverConclusion.value ?? lingerConclusion.value)
  const litFields = computed(() => new Set(activeConclusion.value ? conclusionMap.value[activeConclusion.value]?.deps.map((dep) => dep.key) ?? [] : []))
  const litConclusions = computed(() => new Set(activeField.value ? fieldDeps.value[activeField.value] ?? [] : []))

  /** A 段：一行一次展开（键盘由 <button> 原生负责 Enter / Space） */

  /** B 段：一条判断一次展开 */
  function toggleConclusion(key: string) { openConclusion.value = openConclusion.value === key ? null : key }
  /**
   * B 段整行可点：点在第一行按钮以外的位置（依赖 chip、留白）也展开。
   * 展开区里的任何点击都不切换——读原文、选字、点动作行时不会被误收起。
   */
  function conclRowClick(event: MouseEvent, key: string) {
    const target = event.target as HTMLElement | null
    if (!target) return
    if (target.closest('.p7-concl__more-body')) return
    if (target.closest('button:not(.p7-concl__hit), a[href], [role="button"]')) return
    toggleConclusion(key)
  }
  function toggleLingerConclusion(key: string) { lingerConclusion.value = lingerConclusion.value === key ? null : key }

  const conclusionEls = new Map<string, HTMLElement>()
  function bindConclusion(key: string, el: Element | null) {
    if (el instanceof HTMLElement) conclusionEls.set(key, el)
    else conclusionEls.delete(key)
  }
  const flashId = ref('')
  let flashTimer = 0
  async function jumpToConclusion(key: string) {
    openField.value = null
    await nextTick()
    profileTab.value = 'judgments'
    await nextTick()
    conclusionEls.get(key)?.scrollIntoView({ block: 'center', behavior: reduced() ? 'instant' : 'smooth' })
    flashId.value = key
    window.clearTimeout(flashTimer)
    flashTimer = window.setTimeout(() => { flashId.value = '' }, 1400)
  }

  /** B 段的缺口标记 → C 段那条缺口：滚过去 + 闪一下，让"堵在哪"有落点 */
  const gapFlash = ref('')
  let gapTimer = 0
  async function jumpToGap(key: string) {
    profileTab.value = 'gaps'
    await nextTick()
    document.querySelector(`[data-gap="${key}"]`)?.scrollIntoView({ block: 'center', behavior: reduced() ? 'instant' : 'smooth' })
    gapFlash.value = key
    window.clearTimeout(gapTimer)
    gapTimer = window.setTimeout(() => { gapFlash.value = '' }, 1400)
  }

  /** B 段 → A 段：滚到全量资料里的对应字段并展开。 */
  async function jumpToField(key: string) {
    profileTab.value = 'facts'
    await nextTick()
    openField.value = key
    await nextTick()
    const el = document.querySelector<HTMLElement>(`.p7-row[data-key="${key}"]`)
    el?.scrollIntoView({ block: 'center', behavior: reduced() ? 'instant' : 'smooth' })
  }

  const fieldReading=ref<FieldRow|null>(null)
  async function readField(row:FieldRow){openField.value=null;await nextTick();fieldReading.value=row}
  async function readAnalysis(){openField.value=null;await nextTick();profileTab.value='judgments'}

  function stopJumpTimers() {
    window.clearTimeout(flashTimer)
    window.clearTimeout(gapTimer)
  }

  return {
    hoverField, hoverConclusion, lingerConclusion, openField, openConclusion,
    activeField, activeConclusion, litFields, litConclusions,
    toggleConclusion, conclRowClick, toggleLingerConclusion, bindConclusion,
    flashId, jumpToConclusion, gapFlash, jumpToGap, jumpToField,
    fieldReading, readField, readAnalysis, stopJumpTimers,
  }
}
