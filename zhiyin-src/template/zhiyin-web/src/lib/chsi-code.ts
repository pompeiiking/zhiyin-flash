const CODE_PATTERNS = [/^\d{12}$/, /^[AX][A-Z0-9]{15}$/]

export function normalizeChsiCode(raw: string): string {
  return String(raw || '').replace(/[\s\-_]/g, '').toUpperCase()
}

/** Returns a user-facing reason, or an empty string when the code may be submitted. */
export function chsiCodeError(raw: string): string {
  const code = normalizeChsiCode(raw)
  if (!code) return '请填写在线验证码。'
  if (!CODE_PATTERNS.some(pattern => pattern.test(code))) {
    return '这串码的格式不对：应为 12 位数字，或以 A / X 开头的 16 位码。'
  }
  return ''
}
