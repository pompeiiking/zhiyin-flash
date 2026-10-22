/**
 * 对话消息的输入上限。
 *
 * 与后端 `MessageRequest.message` 的 16000 字上限一致。放在发送前拦截，
 * 而不是等 Pydantic 回一句通用的“有填写项不符合要求”：那条提示既不说
 * 上限，也不会把已经清空的输入还给他。
 */
export const MAX_MESSAGE_CHARS = 16000

/** 超限时返回一句带当前字数的中文；未超限返回空串。 */
export function messageLengthError(text: string): string {
  const length = Array.from(String(text ?? '')).length
  if (length <= MAX_MESSAGE_CHARS) return ''
  return `一条消息最多 ${MAX_MESSAGE_CHARS} 字，现在有 ${length} 字。请删短后再发送。`
}
