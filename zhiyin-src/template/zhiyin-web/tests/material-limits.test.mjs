import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { ref } from 'vue'

const source = readFileSync(new URL('../src/lib/use-conversation-materials.ts', import.meta.url), 'utf8')
const exports = {}
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
  exports,
  require(name) {
    if (name === 'vue') return { ref }
    if (name === '../store') return { demo: { state: { currentSessionId: '' } } }
    if (name === '../api/backend-client') return { backendClient: { material: async () => ({ material_id: 'm', name: 'x' }) } }
    if (name === './use-conversation-errors') return { errorCode: () => 0, friendlyError: e => String(e), TECHNICAL_ERROR: /$^/ }
    throw new Error(`Unexpected import: ${name}`)
  },
})
const { TEXT_SUFFIXES, MAX_MATERIALS, materialRejection } = exports

test('the frontend material whitelist matches the backend whitelist', () => {
  for (const suffix of ['txt', 'csv', 'json', 'md', 'py', 'js', 'ts', 'html', 'css', 'rst', 'tex']) {
    assert.equal(TEXT_SUFFIXES.has(suffix), true, suffix)
  }
  for (const suffix of ['vue', 'jsonl', 'java', 'cpp', 'go', 'rs', 'scss', 'srt', 'properties']) {
    assert.equal(TEXT_SUFFIXES.has(suffix), false, suffix)
    assert.match(materialRejection({ name: `x.${suffix}`, size: 10 }), /不支持/)
  }
  assert.equal(materialRejection({ name: 'x.png', size: 10 }), '')
  assert.equal(MAX_MATERIALS, 5)
})
