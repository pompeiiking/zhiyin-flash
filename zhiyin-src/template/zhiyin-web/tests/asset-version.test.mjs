import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/asset-version.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText
const exports = {}
vm.runInNewContext(code, {exports, require: () => { throw new Error('unexpected dependency') }})
const {latestAssetVersion} = exports

const evidenceSource = readFileSync(new URL('../src/lib/evidence-assessment.ts', import.meta.url), 'utf8')
const evidenceCode = ts.transpileModule(evidenceSource, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText
const evidenceExports = {}
vm.runInNewContext(evidenceCode, {exports: evidenceExports, require: () => { throw new Error('unexpected dependency') }})
const {assessmentLabel} = evidenceExports

test('unknown and incomplete assessments never read as complete', () => {
  assert.equal(assessmentLabel({status: 'future_status'}), '状态未知')
  assert.equal(assessmentLabel({status: 'evaluated', score: null}), '评估结果不完整')
  assert.equal(assessmentLabel({status: 'evaluated', score: 0.2}), '20%')
})

test('the newest asset version is selected even when the API returns ascending order', () => {
  const versions = [
    {version: 1, needs_recompute: false},
    {version: 3, needs_recompute: true},
    {version: 2, needs_recompute: true},
  ]
  assert.equal(latestAssetVersion(versions)?.version, 3)
  assert.equal(latestAssetVersion(versions)?.needs_recompute, true)
  assert.equal(latestAssetVersion([]), undefined)
  assert.equal(latestAssetVersion(null), undefined)
})
