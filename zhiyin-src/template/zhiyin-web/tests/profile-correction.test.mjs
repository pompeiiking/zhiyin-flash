import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function fixture(correct) {
  const field = {key: 'experience', value: '旧经历', updated_at: '2026-10-20T00:00:00Z', source: 'conversation'}
  const workspace = {profile_panel: {fields: [field]}}
  const backendDemo = {state: {liveWorkspace: workspace}, rememberProfileOriginal() {}, setWorkspace(next) { this.state.liveWorkspace = next }}
  const demoWrites = []
  const modules = {
    vue: {ref: value => ({value}), computed: read => ({get value() {return read()}}), nextTick: async () => {}},
    '../api/backend-client': {backendClient: {correct}},
    './backend-demo': {backendDemo},
    '../store': {demo: {updateProfileField(...args) {demoWrites.push(args)}}},
  }
  const source = readFileSync(new URL('../src/lib/use-profile-correction.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText
  const exports = {}
  vm.runInNewContext(code, {exports, Error, require: name => {
    assert.ok(modules[name], `Unexpected dependency: ${name}`)
    return modules[name]
  }})
  const state = exports.useProfileCorrection({live: {value: true}, livePanel: {value: workspace.profile_panel},
    originalLive: {value: {}}, serviceError: {value: ''}, openField: {value: null}, fieldValue: row => row.value, inspect() {}})
  state.edit(field)
  return {state, backendDemo, demoWrites}
}

test('long live-profile corrections are sent intact and never written to demo data', async () => {
  const text = '课程项目中复现问题并比较方案、完成验证和记录原因。'.repeat(8)
  let sent
  const {state, backendDemo, demoWrites} = fixture(async (key, value, version) => {
    sent = {key, value, version}
    return {key, value, updated_at: '2026-10-20T01:00:00Z', source: 'user_edit'}
  })
  state.value.value = text
  await state.save()
  assert.equal(sent.value, text)
  assert.equal(sent.version, '2026-10-20T00:00:00Z')
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.fields[0].value, text)
  assert.equal(state.correction.value, null)
  assert.equal(demoWrites.length, 0)
})

test('a server validation failure keeps the correction and does not change the saved profile', async () => {
  const {state, backendDemo, demoWrites} = fixture(async () => { throw new Error('经历最多 12000 个字') })
  state.value.value = '经'.repeat(12001)
  await state.save()
  assert.equal(state.correctionError.value, '经历最多 12000 个字')
  assert.equal(state.value.value.length, 12001)
  assert.notEqual(state.correction.value, null)
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.fields[0].value, '旧经历')
  assert.equal(demoWrites.length, 0)
})
