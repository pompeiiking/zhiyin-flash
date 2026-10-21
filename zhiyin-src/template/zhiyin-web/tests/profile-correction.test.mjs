import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function fixture(correct, options = {}) {
  const field = {key: 'experience', value: '旧经历', updated_at: '2026-10-20T00:00:00Z', source: 'conversation'}
  const workspace = {profile_panel: {fields: [field], clues: [{id: 'old', field_keys: ['experience'], status: 'proposed'}]}}
  const backendDemo = {changed: [], markProfileChange(key) {this.changed.push(key)}, state: {liveWorkspace: workspace}, rememberProfileOriginal() {}, setWorkspace(next) { this.state.liveWorkspace = next }}
  const demoWrites = []
  const modules = {
    vue: {ref: value => ({value}), computed: read => ({get value() {return read()}}), nextTick: async () => {}},
    '../api/backend-client': {backendClient: {correct, workspace: options.workspace || (async () => backendDemo.state.liveWorkspace), deleteProfileField: options.deleteProfileField}},
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
  const serviceError = {value: ''}
  const state = exports.useProfileCorrection({live: {value: true}, livePanel: {value: workspace.profile_panel},
    originalLive: {value: {}}, serviceError, openField: {value: null}, fieldValue: row => row.value, inspect() {}, refreshRelated: options.refreshRelated})
  state.edit(field)
  return {state, backendDemo, demoWrites, serviceError, field}
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

test('correction refreshes derived clues without requiring a page reload', async () => {
  const latest = {profile_panel: {fields: [{key: 'experience', value: '新经历'}], clues: [{id: 'old', status: 'invalid'}]}}
  const {state, backendDemo} = fixture(async () => latest.profile_panel.fields[0], {workspace: async () => latest})
  state.value.value = '新经历'
  await state.save()
  assert.equal(backendDemo.state.liveWorkspace, latest)
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.clues[0].status, 'invalid')
})

test('a saved correction followed by failed refresh does not offer to repeat the write', async () => {
  const {state, backendDemo, serviceError} = fixture(async () => ({key: 'experience', value: '新经历'}), {workspace: async () => {throw new Error('offline')}})
  state.value.value = '新经历'
  await state.save()
  assert.equal(state.correction.value, null)
  assert.match(serviceError.value, /修改已保存/)
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.clues.length, 0)
})

test('deletion refreshes all derived state and retains committed deletion on refresh failure', async () => {
  const {state, backendDemo, serviceError, field} = fixture(async () => {}, {deleteProfileField: async () => {}, workspace: async () => {throw new Error('offline')}})
  state.askDelete(field)
  await state.confirmDelete()
  assert.equal(state.deleting.value, null)
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.fields.length, 0)
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.clues.length, 0)
  assert.match(serviceError.value, /修改已保存/)
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


test('a committed change marks dependent judgments stale and refreshes related assets', async () => {
  let refreshed = 0
  const {state, backendDemo} = fixture(async () => ({key: 'experience', value: '新经历'}), {refreshRelated: async () => {refreshed++}})
  state.value.value = '新经历'
  await state.save()
  assert.deepEqual(backendDemo.changed, ['experience'])
  assert.equal(refreshed, 1)
})

test('multi-value corrections send individual items and preserve item-specific preference attributes', async () => {
  let sent
  const {state, field} = fixture(async (key, value, version, attributes) => {
    sent = {value, attributes}
    return {key, value, attributes}
  })
  field.value = ['编程', '录入']
  field.attributes = {items: [{value: '编程', polarity: 'like'}, {value: '录入', polarity: 'dislike'}]}
  state.edit(field)
  assert.equal(state.value.value, '编程\n录入')
  state.value.value = '编程\n录入\n绘画'
  await state.save()
  assert.equal(JSON.stringify(sent.value), JSON.stringify(['编程', '录入', '绘画']))
  assert.equal(sent.attributes.items[1].polarity, 'dislike')
})

test('a deletion version conflict refreshes current data before another confirmation', async () => {
  const latest = {profile_panel: {fields: [{key: 'experience', value: '另一页的新版本'}]}}
  const {state, field, backendDemo} = fixture(async () => {}, {
    deleteProfileField: async () => {throw Object.assign(new Error('版本变化'), {code: 1003})},
    workspace: async () => latest,
  })
  state.askDelete(field)
  await state.confirmDelete()
  assert.equal(backendDemo.state.liveWorkspace, latest)
  assert.match(state.deleteError.value, /核对后再次确认/)
  assert.notEqual(state.deleting.value, null)
})
