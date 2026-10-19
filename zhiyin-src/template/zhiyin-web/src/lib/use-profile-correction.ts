import { computed, nextTick, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { backendClient } from '../api/backend-client'
import { backendDemo } from './backend-demo'
import { demo } from '../store'
import type { ProfileFieldView } from '../api/backend-types'
import type { FieldRow, LiveProfilePanel, LiveProfileOriginals } from './use-profile-fields'

const MAX_CHARS = 40

interface ProfileCorrectionDeps {
  live: ComputedRef<boolean>
  livePanel: ComputedRef<LiveProfilePanel>
  originalLive: ComputedRef<LiveProfileOriginals>
  serviceError: Ref<string>
  openField: Ref<string | null>
  fieldValue: (row: FieldRow) => string
  inspect: (key: string, label: string) => void
}

export function useProfileCorrection(deps: ProfileCorrectionDeps) {
  const { live, livePanel, originalLive, serviceError, openField, fieldValue, inspect } = deps

  /* ═══════════════════════════════════════════════════════════════════════════
   * 9. 更正：40 字上限、错误提示、写回 demo / service
   * ======================================================================== */

  const correction = ref<FieldRow | null>(null)
  const value = ref('')
  const correctionError = ref('')
  const correctionVersion = ref<string|null>(null)
  const correctionLatest = ref<ProfileFieldView | null>(null)
  const correctionConflictRows = computed(() => correction.value && correctionLatest.value ? [{
    label: correction.value.label,
    latest: String(correctionLatest.value.value ?? '未填写'),
    mine: value.value.trim() || '未填写',
  }] : [])

  async function inspectField(row: FieldRow) {
    openField.value = null
    await nextTick()
    inspect(row.key, row.label)
  }

  function edit(row: FieldRow) {
    openField.value = null
    correction.value = row
    correctionVersion.value = livePanel.value?.fields?.find(item => item.key === row.key)?.updated_at ?? null
    correctionLatest.value = null
    value.value = fieldValue(row)
    correctionError.value = ''
  }

  async function save() {
    if (!value.value.trim()) { correctionError.value = '请填写更正后的信息。'; return }
    if (value.value.trim().length > MAX_CHARS) { correctionError.value = '更正内容最多 40 个字。'; return }
    if (correction.value && live.value) {
      const field = correction.value
      const previous = livePanel.value?.fields?.find((item) => item.key === field.key)
      serviceError.value = ''
      try {
        const updated = await backendClient.correct(field.key, value.value.trim(), correctionVersion.value)
        if (previous && !originalLive.value[field.key]) backendDemo.rememberProfileOriginal(field.key)
        const workspace = JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace))
        workspace.profile_panel.fields = workspace.profile_panel.fields.map((item: ProfileFieldView) => (item.key === updated.key ? updated : item))
        backendDemo.setWorkspace(workspace)
        correctionLatest.value = null
      } catch (error) {
        correctionError.value = error instanceof Error ? error.message : '更正没有保存成功，输入仍保留，请重试。'
        if ((error as { code?: number }).code === 1003) {
          try {
            const workspace = await backendClient.workspace()
            if (!workspace.profile_panel?.fields) throw new Error('最新画像不完整')
            backendDemo.setWorkspace(workspace)
            correctionLatest.value = workspace.profile_panel.fields.find(item => item.key === field.key) ?? null
          } catch {
            correctionError.value += ' 最新记录暂未取得，请稍后重试。'
          }
        }
        return
      }
    }
    if (correction.value) demo.updateProfileField(correction.value.key, value.value)
    correction.value = null
  }

  async function confirmCorrectionConflict() {
    if (!correctionLatest.value) return
    correctionVersion.value = correctionLatest.value.updated_at
    correctionLatest.value = null
    await save()
  }

  return {
    correction, value, correctionError, correctionVersion, correctionLatest,
    correctionConflictRows, inspectField, edit, save, confirmCorrectionConflict,
  }
}
