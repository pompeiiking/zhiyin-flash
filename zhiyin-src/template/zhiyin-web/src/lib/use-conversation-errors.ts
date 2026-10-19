/**
 * 统一把技术异常收敛成中文可操作提示（深度测试 DEF：解析异常/英文校验文案漏到对话里）。
 * 中文业务提示原样保留；英文或 JSON/解析类异常一律换成"稍后重试/改格式"的说法。
 */
export const TECHNICAL_ERROR = /(Expected property name|Unexpected token|Unexpected end of JSON|is not valid JSON|JSON\.parse|SyntaxError|TypeError|ReferenceError|Traceback|ValidationError|String should|Input should|failed to fetch|NetworkError|Load failed)/i
export function friendlyError(error: unknown) {
  const message = (error instanceof Error ? error.message : typeof error === 'string' ? error : '').trim()
  if (!message) return '这次操作没有完成，请稍后重试。'
  if (TECHNICAL_ERROR.test(message)) return '服务返回的内容无法识别，请稍后重试；如果正在上传材料，请改用 TXT/CSV 等文本格式。'
  if (!/[\u4e00-\u9fa5]/.test(message)) return '这次操作没有完成，请稍后重试。'
  return message
}
export function errorCode(error: unknown) { return (error as { code?: number } | null)?.code }
