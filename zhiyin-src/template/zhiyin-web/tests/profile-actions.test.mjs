import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function fixture(client) {
  const workspace = {profile_panel: {fields: [], clues: [{id: 'c1'}], conflicts: [{id: 'r1'}]}}
  const backendDemo = {state: {liveWorkspace: workspace}, setWorkspace(value) {this.state.liveWorkspace = value}}
  const modules = {
    vue: {ref: value => ({value}), computed: read => ({get value() {return read()}})},
    '../store': {demo: {state: {profileEdits: {}}}},
    '../data/student': {PROFILE_FIELDS: []},
    './server-copy': {profileLabel: (_key, label) => label},
    './backend-demo': {backendDemo},
    '../api/backend-client': {backendClient: client},
  }
  const source = readFileSync(new URL('../src/lib/use-profile-fields.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText
  const exports = {}
  vm.runInNewContext(code, {exports, Error, require: name => {
    assert.ok(modules[name], `Unexpected dependency: ${name}`)
    return modules[name]
  }})
  const fields = exports.useProfileFields({live: {value: true}, livePanel: {value: workspace.profile_panel},
    originalLive: {value: {}}, progress: {value: {known: 0, total: 0, gap: 0}}, getFieldDeps: () => ({})})
  return {fields, backendDemo}
}

test('a failed clue denial stays local, preserves the clue and can be retried', async () => {
  let fail = true
  const {fields, backendDemo} = fixture({denyProfileClue: async () => {
    if (fail) throw new Error('网络暂时不可用，请重试。')
  }})
  await assert.doesNotReject(fields.denyClue('c1'))
  assert.equal(fields.profileActionError.value, '网络暂时不可用，请重试。')
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.clues.length, 1)
  assert.equal(fields.profileActionsPending.value.length, 0)
  fail = false
  await fields.denyClue('c1')
  assert.equal(fields.profileActionError.value, '')
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.clues.length, 0)
})

test('opposite choices for a pending conflict cannot be submitted together', async () => {
  let release
  let calls = 0
  const waiting = new Promise(resolve => {release = resolve})
  const {fields} = fixture({resolveProfileConflict: async () => {calls++; await waiting},
    workspace: async () => ({profile_panel: {fields: [], conflicts: []}})})
  const first = fields.resolveConflict('r1', 'revision')
  assert.equal(fields.profileActionsPending.value.length, 1)
  await fields.resolveConflict('r1', 'current')
  assert.equal(calls, 1)
  release()
  await first
  assert.equal(fields.profileActionsPending.value.length, 0)
})

test('failed conflict saving retains the proposal instead of failing the page', async () => {
  const {fields, backendDemo} = fixture({resolveProfileConflict: async () => {throw new Error('服务暂时不可用')}})
  await assert.doesNotReject(fields.resolveConflict('r1', 'current'))
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.conflicts.length, 1)
  assert.equal(fields.profileActionError.value, '服务暂时不可用')
})

test('failed refresh after a committed decision reports saved state and removes the obsolete proposal', async () => {
  const {fields, backendDemo} = fixture({resolveProfileConflict: async () => {},
    workspace: async () => {throw new Error('读取失败')}})
  await assert.doesNotReject(fields.resolveConflict('r1', 'revision'))
  assert.match(fields.profileActionError.value, /^裁定已保存/)
  assert.equal(backendDemo.state.liveWorkspace.profile_panel.conflicts.length, 0)
})
