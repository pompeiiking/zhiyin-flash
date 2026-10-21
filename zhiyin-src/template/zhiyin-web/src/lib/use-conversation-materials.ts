import { ref, type Ref } from 'vue'
import { demo } from '../store'
import { backendClient } from '../api/backend-client'
import { errorCode, friendlyError, TECHNICAL_ERROR } from './use-conversation-errors'

/**
 * 材料预校验：能在前端拦住的就不要发请求。
 * 支持文字与静态图片；图片真实内容由服务端解码验证，不能只信扩展名。
 */
export const MAX_MATERIAL_BYTES = 2_000_000
export const TEXT_SUFFIXES = new Set(['txt', 'text', 'csv', 'tsv', 'json', 'jsonl', 'md', 'markdown', 'log', 'xml', 'html', 'htm', 'yaml', 'yml', 'sql', 'ini', 'cfg', 'conf', 'properties', 'py', 'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'vue', 'java', 'c', 'h', 'cpp', 'hpp', 'cs', 'go', 'rs', 'rb', 'php', 'css', 'scss', 'less', 'srt', 'vtt', 'tex', 'bib', 'r'])
const BINARY_LABELS: Record<string, string> = { pdf: 'PDF', doc: 'Word 文档', docx: 'Word 文档', xls: 'Excel 工作簿', xlsx: 'Excel 工作簿', xlsm: 'Excel 工作簿', ppt: 'PPT', pptx: 'PPT', zip: '压缩包', rar: '压缩包', '7z': '压缩包', png: '图片', jpg: '图片', jpeg: '图片', gif: '图片', webp: '图片', bmp: '图片', heic: '图片', svg: '矢量图', exe: '可执行文件', dll: '程序文件', msi: '安装包', bin: '二进制文件', iso: '光盘镜像', mp3: '音频', wav: '音频', mp4: '视频', mov: '视频', avi: '视频', ttf: '字体', otf: '字体', woff: '字体', woff2: '字体', psd: '设计文件' }
export function fileSuffix(name: string) { const index = name.lastIndexOf('.'); return index > 0 ? name.slice(index + 1).toLowerCase() : '' }
export function materialRejection(file: File) {
  const suffix = fileSuffix(file.name)
  if (file.size > MAX_MATERIAL_BYTES) return `「${file.name}」超过 2MB 上限，请截取相关的那一段后再上传。`
  if (!file.size) return `「${file.name}」是空文件，请换一份有内容的文本。`
  if (!suffix || TEXT_SUFFIXES.has(suffix) || ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(suffix)) return ''
  const label = BINARY_LABELS[suffix]
  // 认不出的后缀不抢后端判断权：后端会按内容识别二进制并给出中文说明，别误伤可读文本。
  if (!label) return ''
  if (suffix === 'pdf') return '暂不支持直接读取 PDF：请把需要分析的文字复制为 TXT 后上传，或直接粘贴到输入框。'
  if (label === 'Word 文档' || label === 'Excel 工作簿' || label === 'PPT') return `暂不支持直接读取${label}：请在 Office 里另存为 CSV 或 TXT 后上传。`
  if (label === '图片' || label === '矢量图') return '请选择 PNG、JPEG、静态 GIF 或 WebP 图片。'
  if (label === '压缩包') return '压缩包读不了：请先解压，再上传其中的 TXT、CSV 等文本文件。'
  return `不支持 .${suffix} 文件：对话里只能读取文字，请上传 TXT、CSV、MD 等文本文件。`
}
export function friendlyMaterialError(error: unknown) {
  const message = error instanceof Error ? error.message : ''
  if (errorCode(error) === 413 || /413|entity too large|payload too large/i.test(message)) return '材料超过大小限制（最多 2MB），请截取相关的那一段后再上传。'
  if (errorCode(error) === 422) {
    // 后端对 PDF/Word/Excel 等有专门说明时保留原话；纯校验/技术文案统一成"格式不支持"。
    if (/暂不支持|请复制|请上传|TXT|CSV|图片|PNG|JPEG|WebP/i.test(message) && /[\u4e00-\u9fa5]/.test(message) && !TECHNICAL_ERROR.test(message)) return message
    return '这个文件格式不支持，请上传 PNG、JPEG 图片或 TXT、CSV、MD 等文本文件。'
  }
  return friendlyError(error)
}

type MaterialsDeps = {
  thinking: Ref<boolean>
  attached: Ref<{ id: string; name: string }[]>
  isDisposed: () => boolean
}
/** 上传材料的本地预校验、上传流程与拖拽/粘贴入口；fileInput 引用也归这里。 */
export function useConversationMaterials({ thinking, attached, isDisposed }: MaterialsDeps) {
  const uploading = ref(false), draggingFiles = ref(false)
  const uploadError = ref('')
  const fileInput = ref<HTMLInputElement | null>(null)
  async function upload(event: Event) { await uploadFiles(Array.from((event.target as HTMLInputElement).files ?? [])) }
  async function uploadFiles(files: File[]) {
    if (!files.length || uploading.value) return
    if (thinking.value) {
      uploadError.value = '回复生成中，先等这一轮结束再添加材料。'
      if (fileInput.value) fileInput.value.value = ''
      return
    }
    // 先做格式与大小预校验：能当场说清楚的不发请求（深度测试 DEF-DS-03/04）。
    const problems = files.map(file => materialRejection(file)).filter(Boolean)
    const acceptable = files.filter(file => !materialRejection(file))
    uploadError.value = problems.join(' ')
    if (!acceptable.length) { if (fileInput.value) fileInput.value.value = ''; return }
    uploading.value = true
    const sessionId = demo.state.currentSessionId
    try { for (const file of acceptable) { const material = await backendClient.material(file); if (isDisposed() || sessionId !== demo.state.currentSessionId) return; if (!attached.value.some(item => item.id === material.material_id)) attached.value.push({ id: material.material_id, name: material.name || file.name }) } }
    catch (e) { if (!isDisposed() && sessionId === demo.state.currentSessionId) uploadError.value = friendlyMaterialError(e) }
    finally { uploading.value = false; if (fileInput.value) fileInput.value.value = '' }
  }
  function dragOver(event: DragEvent) {
    if (!event.dataTransfer?.types.includes('Files')) return
    event.preventDefault(); event.dataTransfer.dropEffect = uploading.value || thinking.value ? 'none' : 'copy'; draggingFiles.value = !uploading.value && !thinking.value
  }
  function dropFiles(event: DragEvent) {
    if (!event.dataTransfer?.types.includes('Files')) return
    event.preventDefault(); draggingFiles.value = false; void uploadFiles(Array.from(event.dataTransfer.files))
  }
  function pasteFiles(event: ClipboardEvent) {
    const files = Array.from(event.clipboardData?.files ?? [])
    if (files.length && !event.clipboardData?.getData('text/plain')) { event.preventDefault(); void uploadFiles(files) }
  }
  return { uploading, draggingFiles, uploadError, fileInput, upload, uploadFiles, dragOver, dropFiles, pasteFiles }
}
