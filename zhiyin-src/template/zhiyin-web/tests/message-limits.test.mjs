import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/message-limits.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports, Array })
const { MAX_MESSAGE_CHARS, messageLengthError } = exports

test('message length accepts the backend limit', () => {
  assert.equal(MAX_MESSAGE_CHARS, 16000)
  assert.equal(messageLengthError('你好'), '')
  assert.equal(messageLengthError('x'.repeat(16000)), '')
})

test('message length rejects overlong input without silently truncating it', () => {
  const issue = messageLengthError('x'.repeat(16001))
  assert.match(issue, /最多 16000 字/)
  assert.match(issue, /现在有 16001 字/)
})

test('message length counts Unicode code points, matching the backend', () => {
  assert.equal(messageLengthError('😀'.repeat(16000)), '')
  assert.match(messageLengthError('😀'.repeat(16001)), /16000/)
})
