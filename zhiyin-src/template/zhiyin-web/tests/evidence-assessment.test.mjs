import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/evidence-assessment.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const exports = {}
vm.runInNewContext(code, { exports })
const { assessmentPercent } = exports

test('把握度保留真实零分，最多一位小数，不补小数', () => {
  for (const [score, expected] of [[0, '0%'], [1, '100%'], [.713, '71.3%'], [.9, '90%']]) {
    assert.equal(assessmentPercent({ status: 'evaluated', score }), expected)
  }
})
test('待评估、失效和失败没有百分比，旧 confidence 不兜底', () => {
  for (const status of ['pending', 'processing', 'stale', 'failed', 'insufficient']) {
    assert.equal(assessmentPercent({ status, score: .9, confidence: 1 }), null)
  }
  for (const score of [null, undefined, NaN, Infinity, -1, 1.1, '0.9']) {
    assert.equal(assessmentPercent({ status: 'evaluated', score }), null)
  }
  assert.equal(assessmentPercent({ confidence: 1 }), null)
})
