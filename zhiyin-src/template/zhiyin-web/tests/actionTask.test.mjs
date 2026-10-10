import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/actionTask.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText
const { actionTaskForGuide } = await import(`data:text/javascript,${encodeURIComponent(compiled)}`)
const first = { task_id: 'a', text: '部署整个网站', done: false }
const second = { task_id: 'b', text: '写三行 README', done: false }
const plan = { phases: [{ tasks: [first, second] }], next_task: first }

test('完成展示的第二条任务，而不是首个未完成任务', () => {
  assert.equal(actionTaskForGuide(plan, { task_id: 'b', text: second.text }), second)
})

test('引导使用模型 id 时，只按唯一的完整文字对齐', () => {
  assert.equal(actionTaskForGuide(plan, { task_id: 'model-b', text: second.text }), second)
  assert.equal(actionTaskForGuide(plan, { text: ` ${second.text} ` }), second)
})

test('拆小动作不能完成整个计划任务，即便带着父任务 id', () => {
  assert.equal(actionTaskForGuide(plan, { task_id: 'a', text: '先打开网站首页' }), null)
  assert.equal(actionTaskForGuide(plan, { text: '先打开 README 看第一行' }), null)
})

test('重复文字需要明确 id，不能猜测是哪条任务', () => {
  const duplicate = { ...second, task_id: 'c', done: true }
  const duplicates = { phases: [{ tasks: [second, duplicate] }] }
  assert.equal(actionTaskForGuide(duplicates, { text: second.text }), null)
  assert.equal(actionTaskForGuide(duplicates, { task_id: 'b', text: second.text }), second)
})

test('空计划或空引导不产生完成目标', () => {
  assert.equal(actionTaskForGuide(null, { text: first.text }), null)
  assert.equal(actionTaskForGuide(plan, null), null)
  assert.equal(actionTaskForGuide(plan, { text: ' ' }), null)
})

// 执行组件实际的点击处理器，检查写入目标、重复点击与读取失败行为。
const component = readFileSync(new URL('../src/components/console/TalkOverlay.vue', import.meta.url), 'utf8')
const script = component.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
const ast = ts.createSourceFile('TalkOverlay.ts', script, ts.ScriptTarget.Latest, true)
const handler = ast.statements.find((item) => ts.isFunctionDeclaration(item) && item.name?.text === 'markDone')
const handlerJs = ts.transpileModule(handler.getText(ast), {}).outputText

function clickHandler(displayed, currentPlan, overrides = {}) {
  const writes = []
  const messages = []
  const session = {
    chatTyping: false,
    actionPlan: currentPlan,
    applyActionPlan(value) { this.actionPlan = value },
  }
  const completingTask = { value: false }
  const create = new Function('session', 'task', 'completingTask', 'getActionPlan',
    'setActionTaskDone', 'actionTaskForGuide', 'send', 'TASK_DONE', 'console',
    `${handlerJs}; return markDone`)
  const click = create(session, { value: displayed }, completingTask,
    overrides.read ?? (async () => plan),
    overrides.write ?? (async (id, done) => { writes.push({ id, done }); return currentPlan ?? plan }),
    actionTaskForGuide, (message) => messages.push(message), 'done', { warn() {} })
  return { click, writes, messages, completingTask }
}

test('点击完成只写当前展示任务', async () => {
  const state = clickHandler({ task_id: 'b', text: second.text }, plan)
  await state.click()
  assert.deepEqual(state.writes, [{ id: 'b', done: true }])
  assert.deepEqual(state.messages, ['done'])
})

test('微任务和已完成任务只回话，不误勾下一条', async () => {
  for (const [guide, current] of [
    [{ task_id: 'a', text: '先打开网站首页' }, plan],
    [{ task_id: 'b', text: second.text }, { phases: [{ tasks: [{ ...second, done: true }] }] }],
  ]) {
    const state = clickHandler(guide, current)
    await state.click()
    assert.deepEqual(state.writes, [])
    assert.deepEqual(state.messages, ['done'])
  }
})

test('尚未读取计划时先读取，再定位展示任务', async () => {
  const state = clickHandler({ text: second.text }, null)
  await state.click()
  assert.deepEqual(state.writes, [{ id: 'b', done: true }])
})

test('读写失败仍然允许报告结果，并解除按钮锁定', async () => {
  const failure = async () => { throw new Error('unavailable') }
  for (const [current, overrides] of [[null, { read: failure }], [plan, { write: failure }]]) {
    const state = clickHandler({ task_id: 'b', text: second.text }, current, overrides)
    await state.click()
    assert.deepEqual(state.messages, ['done'])
    assert.equal(state.completingTask.value, false)
  }
})

test('写入期间重复点击不会重复完成或发送', async () => {
  let finish
  let writes = 0
  const state = clickHandler({ task_id: 'b', text: second.text }, plan, {
    write: () => { writes++; return new Promise((resolve) => { finish = resolve }) },
  })
  const pending = state.click()
  await state.click()
  assert.equal(writes, 1)
  assert.deepEqual(state.messages, [])
  finish(plan)
  await pending
  assert.deepEqual(state.messages, ['done'])
})
