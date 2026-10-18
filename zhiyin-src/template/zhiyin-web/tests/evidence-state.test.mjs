import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function load(file) {
  const source = readFileSync(new URL(`../src/lib/${file}`, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  vm.runInNewContext(code, { exports })
  return exports
}

const { toEvidenceState, evidenceLabel } = load('evidence-state.ts')

test('证据状态五态归一：认不出不冒充已核验', () => {
  assert.equal(toEvidenceState('已核验'), 'verified')
  assert.equal(toEvidenceState('学籍核验通过'), 'verified')
  assert.equal(toEvidenceState('待补充'), 'missing')
  assert.equal(toEvidenceState('尚未取得），待补充'), 'missing')
  assert.equal(toEvidenceState('已记录 2 项'), 'recorded')
  assert.equal(toEvidenceState('按资料范围未使用'), 'out-of-scope')
  assert.equal(toEvidenceState('仍需要核对'), 'unverified')
  assert.equal(toEvidenceState(''), 'unverified')
  assert.equal(toEvidenceState(null), 'unverified')
})

test('证据状态文案固定，不随页面变化', () => {
  assert.equal(evidenceLabel('待补充'), '待补充')
  assert.equal(evidenceLabel('已核验'), '已核验')
  assert.equal(evidenceLabel('x'), '待核对')
})
