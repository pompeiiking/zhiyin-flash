import { computed, nextTick, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { backendClient } from '../api/backend-client'
import { backendDemo } from './backend-demo'
import { demo } from '../store'
import type { ProfileFieldView } from '../api/backend-types'
import type { FieldRow, LiveProfilePanel, LiveProfileOriginals } from './use-profile-fields'

interface ProfileCorrectionDeps {
  live: ComputedRef<boolean>
  livePanel: ComputedRef<LiveProfilePanel>
  originalLive: ComputedRef<LiveProfileOriginals>
  serviceError: Ref<string>
  openField: Ref<string | null>
  fieldValue: (row: FieldRow) => string
  inspect: (key: string, label: string) => void
  refreshRelated?: () => Promise<void>
}

export function useProfileCorrection(deps: ProfileCorrectionDeps) {
  const { live, livePanel, originalLive, serviceError, openField, fieldValue, inspect } = deps

  /* ═══════════════════════════════════════════════════════════════════════════
   * 9. 更正：服务端按记录类型校验、错误提示、写回 demo / service
   * ======================================================================== */

  const correction = ref<FieldRow | null>(null)
  const value = ref('')
  const correctionError = ref('')
  const correctionVersion = ref<string|null>(null)
  const correctionLatest = ref<ProfileFieldView | null>(null)
  const saveBusy = ref(false)
  const correctionAttributes = ref<Record<string, unknown>>({})
  const preferenceItems = computed(() => (correctionAttributes.value.items ?? []) as {value: string; polarity?: string; state?: string}[])
  const multiple = computed(() => Array.isArray(livePanel.value?.fields?.find(item => item.key === correction.value?.key)?.value)
    || ['interest', 'career_focus', 'ability'].includes(correction.value?.entryType ?? ''))

  async function refreshAfterWrite(key: string) {
    backendDemo.markProfileChange(key)
    // The write committed: immediately remove dependent stale interpretations,
    // then replace all derived state with the authoritative workspace.
    const workspace = JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace))
    if (workspace?.profile_panel?.clues) {
      workspace.profile_panel.clues = workspace.profile_panel.clues.filter((clue: {field_keys?: string[]}) => !clue.field_keys?.includes(key))
      backendDemo.setWorkspace(workspace)
    }
    try {
      if (deps.refreshRelated) {
        await deps.refreshRelated()
        return
      }
      const latest = await backendClient.workspace()
      if (!latest?.profile_panel) throw new Error('Incomplete profile')
      backendDemo.setWorkspace(latest)
    } catch {
      serviceError.value = '修改已保存，但最新判断暂未读取，请重试读取档案。'
    }
  }
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
    const original = livePanel.value?.fields?.find(item => item.key === row.key)
    correctionAttributes.value = JSON.parse(JSON.stringify(original?.attributes ?? {}))
    const raw = original?.value
    if (['interest', 'career_focus'].includes(row.entryType) && !Array.isArray(correctionAttributes.value.items)) {
      const common = correctionAttributes.value
      correctionAttributes.value = {items: (Array.isArray(raw) ? raw : [raw]).filter(Boolean).map(item => ({value: item, ...common}))}
    }
    value.value = Array.isArray(raw) ? raw.join('\n') : fieldValue(row)
    correctionError.value = ''
  }

  async function save() {
    if (saveBusy.value) return
    if (!value.value.trim()) { correctionError.value = '请填写更正后的信息。'; return }
    if (correction.value && live.value) {
      const field = correction.value
      const previous = livePanel.value?.fields?.find((item) => item.key === field.key)
      serviceError.value = ''
      saveBusy.value = true
      try {
        const nextValue = multiple.value ? value.value.split(/\n/).map(item => item.trim()).filter(Boolean) : value.value.trim()
        const updated = await backendClient.correct(field.key, nextValue, correctionVersion.value, correctionAttributes.value)
        if (previous && !originalLive.value[field.key]) backendDemo.rememberProfileOriginal(field.key)
        const workspace = JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace))
        if (workspace?.profile_panel?.fields) {
          workspace.profile_panel.fields = workspace.profile_panel.fields.map((item: ProfileFieldView) => (item.key === updated.key ? updated : item))
          backendDemo.setWorkspace(workspace)
        }
        correctionLatest.value = null
        correction.value = null
        await refreshAfterWrite(field.key)
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
      } finally {
        saveBusy.value = false
      }
    }
    if (correction.value && !live.value) demo.updateProfileField(correction.value.key, value.value)
    correction.value = null
  }

  async function confirmCorrectionConflict() {
    if (!correctionLatest.value) return
    correctionVersion.value = correctionLatest.value.updated_at
    correctionLatest.value = null
    await save()
  }

  /* ------------------------------------------------------------------ *
   * 删除一条画像：用户可以查看、更正，也可以删除（设计第 7/9 节）。
   * 删除后这条不再作为咨询依据；相关判断由服务端标记待核对。
   * ------------------------------------------------------------------ */

  const deleting = ref<FieldRow | null>(null)
  const deleteBusy = ref(false)
  const deleteError = ref('')

  function askDelete(row: FieldRow) {
    deleting.value = row
    deleteError.value = ''
  }

  function closeDelete() {
    if (!deleteBusy.value) deleting.value = null
  }

  async function confirmDelete() {
    if (!deleting.value) return
    if (!live.value) {
      deleteError.value = '演示数据不支持删除，请连接真实档案后再试。'
      return
    }
    const field = deleting.value
    deleteBusy.value = true
    deleteError.value = ''
    try {
      const version = livePanel.value?.fields?.find((item) => item.key === field.key)?.updated_at ?? null
      await backendClient.deleteProfileField(field.key, version)
      const workspace = JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace))
      if (workspace?.profile_panel?.fields) {
        workspace.profile_panel.fields = workspace.profile_panel.fields.filter((item: ProfileFieldView) => item.key !== field.key)
      }
      if (workspace) backendDemo.setWorkspace(workspace)
      deleting.value = null
      await refreshAfterWrite(field.key)
    } catch (error) {
      deleteError.value = error instanceof Error ? error.message : '删除没有成功，这条记录仍然保留，请重试。'
      if ((error as {code?: number}).code === 1003) {
        try {
          backendDemo.setWorkspace(await backendClient.workspace())
          deleteError.value += ' 已读取最新记录，请核对后再次确认删除。'
        } catch { deleteError.value += ' 最新记录未取得，请重试读取档案。' }
      }
    } finally {
      deleteBusy.value = false
    }
  }

  return {
    correction, value, correctionAttributes, preferenceItems, multiple, correctionError, correctionVersion, correctionLatest, saveBusy,
    correctionConflictRows, inspectField, edit, save, confirmCorrectionConflict,
    deleting, deleteBusy, deleteError, askDelete, closeDelete, confirmDelete,
  }
}
