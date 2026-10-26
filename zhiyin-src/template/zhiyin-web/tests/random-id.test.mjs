import test from 'node:test'
import assert from 'node:assert/strict'
import { randomId } from '../src/lib/random-id.ts'

const original = Object.getOwnPropertyDescriptor(globalThis, 'crypto')

function useCrypto(value) {
  Object.defineProperty(globalThis, 'crypto', { value, configurable: true, writable: true })
}

test('安全上下文下优先使用 crypto.randomUUID', () => {
  useCrypto({ randomUUID: () => 'native-id', getRandomValues: () => {} })
  assert.equal(randomId(), 'native-id')
})

test('局域网 HTTP 下没有 randomUUID 时仍返回合法 UUID，而不是抛错', () => {
  useCrypto({
    getRandomValues(bytes) {
      for (let index = 0; index < bytes.length; index += 1) bytes[index] = index
    },
  })
  const id = randomId()
  assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  assert.equal(id, '00010203-0405-4607-8809-0a0b0c0d0e0f')
})

test('randomUUID 存在但调用即抛时也走退回路径', () => {
  useCrypto({
    randomUUID() { throw new TypeError('crypto.randomUUID is not a function') },
    getRandomValues(bytes) {
      for (let index = 0; index < bytes.length; index += 1) bytes[index] = 255 - index
    },
  })
  assert.match(randomId(), /^[0-9a-f-]{36}$/)
})

test('连 crypto.getRandomValues 都没有时仍可用', () => {
  useCrypto(undefined)
  assert.match(randomId(), /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
})

test.after(() => {
  if (original) Object.defineProperty(globalThis, 'crypto', original)
  else delete globalThis.crypto
})
