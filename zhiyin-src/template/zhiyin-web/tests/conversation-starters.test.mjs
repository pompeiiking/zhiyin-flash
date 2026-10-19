import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// 执行组件的真实入口函数；网络、流式发送与 Vue ref 由测试替身控制。
const component = readFileSync(new URL('../src/views/ConversationView.vue', import.meta.url), 'utf8')
const script = component.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
const ast = ts.createSourceFile('ConversationView.ts', script, ts.ScriptTarget.Latest, true)
const functions = ast.statements.filter(node => ts.isFunctionDeclaration(node) && ['create', 'start'].includes(node.name?.text)).map(node => node.getText(ast)).join('\n')
const executable = ts.transpileModule(functions, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText

function fixture({ fail = false, wait } = {}) {
 const entries = [], messages = [], events = []
 const ref = value => ({ value })
 const context = {
  thinking: ref(false), uploading: ref(false), restoring: ref(false), startingTopic: ref(false),
  systemData: { busy: false, shellReady: true }, choosingTopic: ref(true), pending: ref(null), requestError: ref(''),
  input: ref({ focus() { events.push('focus') } }),
  newSession: async (code, fresh) => { entries.push({ code, fresh }); if (wait) await wait; if (fail) throw new Error('创建失败') },
  clearTopicQuery() { events.push('clear-query') }, loadShell: async () => { events.push('shell') },
  friendlyError: e => e.message, nextTick: fn => Promise.resolve().then(fn),
  send: async (retry, choice) => { events.push('send'); messages.push(choice.text) },
 }
 vm.createContext(context); vm.runInContext(executable, context)
 return { context, entries, messages, events }
}

test('preset starts a fresh session then sends exactly the selected personalized question', async () => {
 const f = fixture()
 await f.context.start('verify_direction', '了解专业可以走向哪里')
 assert.deepEqual(f.entries, [{ code: 'verify_direction', fresh: true }])
 assert.deepEqual(f.messages, ['了解专业可以走向哪里'])
 assert.ok(f.events.indexOf('shell') < f.events.indexOf('send'))
 assert.equal(f.context.startingTopic.value, false)
})

test('free chat creates a fresh blank session without sending its label', async () => {
 const f = fixture(); await f.context.start('free_chat', '聊聊当前的困惑')
 assert.equal(f.entries.length, 1); assert.equal(f.messages.length, 0)
 assert.ok(f.events.includes('focus'))
})

test('failed creation never sends the preset into the previously selected session', async () => {
 const f = fixture({ fail: true }); await f.context.start('confused', '认识自己的兴趣与优势')
 assert.equal(f.messages.length, 0); assert.equal(f.context.requestError.value, '创建失败')
 assert.equal(f.context.choosingTopic.value, true); assert.equal(f.context.startingTopic.value, false)
})

test('rapid repeated clicks create and send only once', async () => {
 let release
 const f = fixture({ wait: new Promise(resolve => { release = resolve }) })
 const first = f.context.start('confused', '认识自己的兴趣与优势')
 await f.context.start('verify_direction', '了解专业可以走向哪里')
 release(); await first
 assert.equal(f.entries.length, 1); assert.deepEqual(f.messages, ['认识自己的兴趣与优势'])
})

test('unready, restoring, uploading and active conversation guards never dispatch a preset', async () => {
 for (const guard of ['thinking', 'uploading', 'restoring', 'busy', 'shellReady']) {
  const f = fixture()
  if (guard === 'busy') f.context.systemData.busy = true
  else if (guard === 'shellReady') f.context.systemData.shellReady = false
  else f.context[guard].value = true
  await f.context.start('confused', '认识自己的兴趣与优势')
  assert.equal(f.entries.length, 0, guard); assert.equal(f.messages.length, 0, guard)
 }
})
