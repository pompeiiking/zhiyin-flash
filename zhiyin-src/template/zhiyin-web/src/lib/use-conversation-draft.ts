import { nextTick, ref, type Ref } from 'vue'
import { demo, toast } from '../store'
import { backendDemo } from './backend-demo'
import type { ChatTurn } from '../data/types'

export type OptionRef = NonNullable<ChatTurn['optionRefs']>[number]
type DraftDeps = {
  flow: Ref<HTMLElement | null>
  input: Ref<HTMLTextAreaElement | null>
  profileOpen: Ref<boolean>
  thinking: Ref<boolean>
}
/** 草稿与材料按当前会话持久化（remember / getDraft）；快捷选项填充的确认与撤销也在这里。 */
export function useConversationDraft({ flow, input, profileOpen, thinking }: DraftDeps) {
  const saved = backendDemo.getDraft(demo.state.currentSessionId)
  const draft = ref(saved.text), attached = ref(saved.materials.map(m => ({ ...m })))
  const selectedOption = ref<NonNullable<ChatTurn['optionRefs']>[number] | null>(null)
  // 快捷选项覆盖草稿：先确认，替换后还能撤销（问题 4）。无草稿时行为完全不变。
  const fillRequest = ref<{ text: string; option?: OptionRef; previousText: string; previousOption: OptionRef | null } | null>(null)
  const replacedDraft = ref<{ text: string; option: OptionRef | null } | null>(null)
  function remember() { backendDemo.saveDraft(demo.state.currentSessionId, draft.value, attached.value, flow.value?.scrollTop ?? null) }
  function resizeInput() { if (input.value) { input.value.style.height = 'auto'; input.value.style.height = Math.min(input.value.scrollHeight, 144) + 'px' } }
  function applyFill(text: string, option?: OptionRef) { draft.value = text; selectedOption.value = option ?? null; profileOpen.value = false; void nextTick(() => input.value?.focus()) }
  function fill(text: string, option?: OptionRef) {
    if (thinking.value) return
    // 已有非空草稿时不能静默覆盖：先让用户确认，替换后仍可撤销。
    if (draft.value.trim() && draft.value.trim() !== text.trim()) {
      fillRequest.value = { text, option, previousText: draft.value, previousOption: selectedOption.value }
      replacedDraft.value = null
      profileOpen.value = false
      return
    }
    applyFill(text, option)
    // 点快捷选项只填入不发送：给一句明确反馈，避免"点了没反应"（深度测试观察项）。
    if (option) toast('已填入输入框，点发送即可。')
  }
  function confirmFillReplace() {
    const request = fillRequest.value
    if (!request) return
    fillRequest.value = null
    applyFill(request.text, request.option)
    replacedDraft.value = { text: request.previousText, option: request.previousOption }
    if (request.option) toast('已替换为所选内容，点发送即可。原草稿可点「撤销替换」恢复。')
  }
  function cancelFillReplace() { fillRequest.value = null }
  function undoFillReplace() {
    const previous = replacedDraft.value
    if (!previous) return
    replacedDraft.value = null
    applyFill(previous.text, previous.option ?? undefined)
  }
  return { draft, attached, selectedOption, fillRequest, replacedDraft, fill, applyFill, confirmFillReplace, cancelFillReplace, undoFillReplace, remember, resizeInput }
}
