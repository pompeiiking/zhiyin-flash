/**
 * 生成客户端请求标识。
 *
 * `crypto.randomUUID()` 只在安全上下文（HTTPS 或 localhost）里存在。演示时
 * 手机通过局域网 IP 打开（`http://192.168.1.13:5173`）属于非安全上下文，
 * 这个函数是 undefined —— 直接调用会让发送、上传、保存等 17 处一起抛
 * `TypeError`，界面只剩全局兜底的红条。这里的退回路径用的是
 * `crypto.getRandomValues`（非安全上下文也可用）；它也不存在时才用
 * Math.random，保证功能可用，而不是让整个页面卡死。
 */
export function randomId(): string {
  const crypto = globalThis.crypto
  if (crypto && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID()
    } catch {
      // 某些 WebView 暴露了函数但调用即抛；继续走退回路径。
    }
  }
  const bytes = new Uint8Array(16)
  if (crypto && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256)
  }
  // RFC 4122 第 4 版：第 6 字节高 4 位是版本号，第 8 字节高 2 位是变体。
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
