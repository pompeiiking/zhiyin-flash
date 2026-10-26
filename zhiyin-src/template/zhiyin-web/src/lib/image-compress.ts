/** 手机照片 → 可上传图片：在上传前压到后端 2MB 限制以内。 */

export const IMAGE_UPLOAD_LIMIT = 2_000_000
export const IMAGE_MAX_SIDES = [2400, 2000, 1600] as const
export const IMAGE_QUALITIES = [0.92, 0.86, 0.8, 0.72, 0.64] as const

const IMAGE_TYPE = /^image\//
const UNSUPPORTED_PHOTO = /heic|heif/i

export function isImageFile(file: Pick<File, 'type' | 'name'>): boolean {
  return IMAGE_TYPE.test(file.type) || /\.(png|jpe?g|gif|webp)$/i.test(file.name)
}

export function needsImageCompression(file: Pick<File, 'size' | 'type' | 'name'>, limit = IMAGE_UPLOAD_LIMIT): boolean {
  return isImageFile(file) && file.size > limit
}

export function compressedImageName(name: string, mime = 'image/webp'): string {
  const extension = mime === 'image/jpeg' ? 'jpg' : 'webp'
  const base = name.replace(/\.[^./\\]+$/, '') || 'photo'
  return `${base}.${extension}`
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  if (bytes >= 1_000) return `${Math.round(bytes / 1_000)} KB`
  return `${bytes} B`
}

type LoadedImage = ImageBitmap | HTMLImageElement

async function loadImage(file: File): Promise<{ image: LoadedImage; release: () => void }> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file)
      return { image: bitmap, release: () => bitmap.close?.() }
    } catch {
      // Safari 等实现可能对某些格式不支持 createImageBitmap，退回 <img>。
    }
  }
  const url = URL.createObjectURL(file)
  const image = new Image()
  image.decoding = 'async'
  image.src = url
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('decode-failed'))
    })
  } catch (error) {
    URL.revokeObjectURL(url)
    throw error
  }
  return { image, release: () => URL.revokeObjectURL(url) }
}

function canvasToBlob(canvas: HTMLCanvasElement, mime: string, quality: number): Promise<Blob | null> {
  return new Promise(resolve => canvas.toBlob(resolve, mime, quality))
}

/**
 * 只在图片超过限制时压缩。
 *
 * 策略是**先保留原图尺寸**，逐档降低质量；质量降到 0.64 仍超限才缩小边长。
 * 成绩单/课表截图里的文字最怕一上来就缩小，所以不按“手机照片尺寸”直接砍半。
 * 输出优先 WebP（文字边缘比 JPEG 稳、体积更小），浏览器不支持时退回 JPEG。
 */
export async function prepareImageForUpload(file: File, limit = IMAGE_UPLOAD_LIMIT): Promise<{
  file: File
  compressed: boolean
  originalBytes: number
}> {
  if (!needsImageCompression(file, limit)) return { file, compressed: false, originalBytes: file.size }
  if (UNSUPPORTED_PHOTO.test(file.type) || UNSUPPORTED_PHOTO.test(file.name)) {
    throw new Error('这张照片可能是 HEIC/实况格式，浏览器无法直接压缩。请在相册里另存为 JPEG，或截取表格区域后再上传。')
  }
  const loaded = await loadImage(file).catch(() => {
    throw new Error('这张图片暂时无法读取。请换一张 JPEG/PNG，或截取表格区域后再上传。')
  })
  const { image, release } = loaded
  try {
    const sourceWidth = 'width' in image ? image.width : 0
    const sourceHeight = 'height' in image ? image.height : 0
    if (!sourceWidth || !sourceHeight) throw new Error('图片尺寸读不出来，请换一张图片。')
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')
    if (!context) throw new Error('当前浏览器无法压缩这张图片，请换一张较小的截图。')
    let mime = 'image/webp'
    let best: Blob | null = null
    for (const maxSide of IMAGE_MAX_SIDES) {
      const scale = Math.min(1, maxSide / Math.max(sourceWidth, sourceHeight))
      canvas.width = Math.max(1, Math.round(sourceWidth * scale))
      canvas.height = Math.max(1, Math.round(sourceHeight * scale))
      context.clearRect(0, 0, canvas.width, canvas.height)
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      for (const quality of IMAGE_QUALITIES) {
        const blob = await canvasToBlob(canvas, mime, quality)
        if (!blob) continue
        // 有的浏览器把不支持的 WebP 悄悄编成 PNG，类型不对就改用 JPEG。
        if (blob.type && !blob.type.startsWith(mime)) {
          mime = 'image/jpeg'
          continue
        }
        best = blob
        if (blob.size <= limit) {
          return {
            file: new File([blob], compressedImageName(file.name, mime), { type: mime, lastModified: Date.now() }),
            compressed: true,
            originalBytes: file.size,
          }
        }
      }
    }
    if (best && best.size <= limit) {
      return {
        file: new File([best], compressedImageName(file.name, mime), { type: mime, lastModified: Date.now() }),
        compressed: true,
        originalBytes: file.size,
      }
    }
    throw new Error('照片压缩后仍超过 2MB。请只截取表格区域，或改用粘贴表格。')
  } finally {
    release()
  }
}
