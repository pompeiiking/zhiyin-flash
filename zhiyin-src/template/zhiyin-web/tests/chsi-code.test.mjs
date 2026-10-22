import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/chsi-code.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports, Set })
const { normalizeChsiCode, chsiCodeError } = exports

test('CHSI code normalization keeps the official formats and strips paste separators', () => {
  assert.equal(normalizeChsiCode(' 1234-5678 9012 '), '123456789012')
  assert.equal(normalizeChsiCode('a1b2 c3d4 e5f6 g7h8'), 'A1B2C3D4E5F6G7H8')
})

test('CHSI code validation catches malformed values before a network request', () => {
  assert.equal(chsiCodeError('123456789012'), '')
  assert.equal(chsiCodeError('A1B2C3D4E5F6G7H8'), '')
  assert.match(chsiCodeError('12345'), /格式不对/)
  assert.match(chsiCodeError('B1234567890123456'), /格式不对/)
  assert.match(chsiCodeError(''), /请填写/)
})
