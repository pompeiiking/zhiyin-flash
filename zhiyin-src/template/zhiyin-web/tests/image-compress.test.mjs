import test from 'node:test'
import assert from 'node:assert/strict'
import {
  IMAGE_MAX_SIDES, IMAGE_QUALITIES, IMAGE_UPLOAD_LIMIT,
  compressedImageName, formatBytes, isImageFile, needsImageCompression,
} from '../src/lib/image-compress.ts'

test('只有超过 2MB 的图片才进入压缩流程', () => {
  assert.equal(needsImageCompression({ size: IMAGE_UPLOAD_LIMIT + 1, type: 'image/jpeg', name: 'a.jpg' }), true)
  assert.equal(needsImageCompression({ size: IMAGE_UPLOAD_LIMIT, type: 'image/jpeg', name: 'a.jpg' }), false)
  assert.equal(needsImageCompression({ size: 3_000_000, type: 'application/pdf', name: 'a.pdf' }), false)
  assert.equal(needsImageCompression({ size: 3_000_000, type: '', name: '截图.PNG' }), true)
  assert.equal(isImageFile({ type: 'image/webp', name: 'x' }), true)
  assert.equal(isImageFile({ type: 'text/plain', name: 'x.txt' }), false)
})

test('压缩输出使用 WebP/JPEG 扩展名，不保留奇怪的原始后缀', () => {
  assert.equal(compressedImageName('IMG_1234.JPG', 'image/webp'), 'IMG_1234.webp')
  assert.equal(compressedImageName('成绩单.png', 'image/jpeg'), '成绩单.jpg')
  assert.equal(compressedImageName('photo', 'image/webp'), 'photo.webp')
})

test('压缩策略先保尺寸再降质量，避免把表格文字直接缩小', () => {
  assert.deepEqual([...IMAGE_MAX_SIDES], [2400, 2000, 1600])
  assert.equal(IMAGE_QUALITIES[0], 0.92)
  assert.ok(IMAGE_QUALITIES.every((quality, index) => index === 0 || quality < IMAGE_QUALITIES[index - 1]))
  assert.equal(formatBytes(2_500_000), '2.5 MB')
  assert.equal(formatBytes(850), '850 B')
})
