import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as vue from 'vue'

function setup(api = {}) {
  const { descriptor } = parse(readFileSync(new URL('../src/components/ChsiPdfImport.vue', import.meta.url), 'utf8'))
  const code = ts.transpileModule(compileScript(descriptor, { id: 'ChsiPdfImport' }).content,
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const changes = [], exports = {}
  const modules = {
    vue: { ...vue, onBeforeUnmount: () => {} },
    '../api/backend-client': { backendClient: api },
    '../lib/backend-demo': { backendDemo: { markProfileChange: key => changes.push(key), setWorkspace() {} } },
  }
  vm.runInNewContext(code, { exports, FormData, Date, setTimeout: () => 1, clearTimeout() {}, require: key => modules[key] ?? {} })
  return { state: exports.default.setup({}, { expose() {}, emit() {} }), changes }
}
const preview = {
  preview_id: 'id', expires_at: '2099-01-01T00:00:00Z', can_import: true,
  requires_ownership_confirmation: true, warnings: [], fields: [
    { key: 'school', selected: true, selectable: true },
    { key: 'major', selected: false, selectable: true },
    { key: 'student_name', selected: false, selectable: false },
  ],
}

test('study year preview labels a derivation separately and never substitutes the current year', () => {
  const { state } = setup()
  assert.equal(state.previewValueLabel('study_year'), '按入学日期推算')
  assert.equal(state.previewValue('study_year', '大三'), '大三')
  assert.equal(state.previewValue('study_year', null), '无法推算，请核对当前年级')
  assert.equal(state.previewValueLabel('school'), '报告')
  assert.equal(state.previewValue('school', '测试大学'), '测试大学')
})

test('PDF preview selects missing fields and requires ownership confirmation', async () => {
  const { state } = setup({ chsiPdfPreview: async () => preview })
  state.file.value = new Blob(['pdf'])
  await state.parse()
  assert.deepEqual([...state.selected.value], ['school'])
  assert.equal(state.canConfirm.value, false)
  state.ownership.value = true
  assert.equal(state.canConfirm.value, true)
})

test('successful import survives workspace refresh failure without a second import', async () => {
  let commits = 0
  const { state, changes } = setup({ chsiPdfPreview: async () => preview,
    chsiPdfConfirm: async body => { commits++; assert.deepEqual([...body.selected_keys], ['school']);
      return { imported: ['school'], retained: ['major'], skipped: [], message: '报告材料已导入，待在线核验。' } },
    workspace: async () => { throw Error('unavailable') },
  })
  state.file.value = new Blob(['pdf']); await state.parse(); state.ownership.value = true
  await state.confirm()
  assert.equal(commits, 1)
  assert.ok(state.receipt.value)
  assert.ok(state.refreshError.value.includes('导入已完成'))
  await state.refresh()
  assert.equal(commits, 1)
  assert.deepEqual(changes, ['school'])
})

test('CHSI verified indicator requires explicit verification and an online source', () => {
  const source = readFileSync(new URL('../src/lib/backend-demo.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const exports = {}
  vm.runInNewContext(compiled, { exports, Date, URL, require: key => key === 'vue' ? vue : { rememberSession() {} } })
  const store = exports.backendDemo
  const field = { source: 'record', verification: 'record', evidence: ['https://www.chsi.com.cn/xlcx/bgcx.jsp'] }
  store.setWorkspace({ profile_panel: { fields: [field] } })
  assert.equal(store.chsiVerified.value, false)
  store.setWorkspace({ profile_panel: { fields: [{ ...field, verification: 'verified' }] } })
  assert.equal(store.chsiVerified.value, true)
})
