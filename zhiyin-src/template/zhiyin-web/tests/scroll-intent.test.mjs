import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/scroll-intent.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports })
const { createScrollIntent, isComposingKey } = exports

test('upward input takes control before another streamed frame arrives', () => {
  const intent = createScrollIntent()
  intent.release(1000)
  assert.equal(intent.pinned, false)
  assert.equal(intent.update(0, 1100), false)
  assert.equal(intent.update(180, 1200), false)
})
test('returning near the bottom resumes streaming follow after gesture settles', () => {
  const intent = createScrollIntent()
  intent.release(1000)
  assert.equal(intent.update(20, 1200), true)
  assert.equal(intent.update(90, 1300), false)
})
test('explicit jump overrides cooldown, without letting the next frame steal manual scroll', () => {
  const intent = createScrollIntent()
  intent.release(1000); intent.pin()
  assert.equal(intent.update(0, 1010), true)
  intent.release(1020)
  assert.equal(intent.update(5, 1030), false)
})
test('IME commit is never treated as send or command selection', () => {
  assert.equal(isComposingKey({ isComposing: true }), true)
  assert.equal(isComposingKey({ isComposing: false, keyCode: 229 }), true)
  assert.equal(isComposingKey({ isComposing: false, keyCode: 13 }), false)
})
