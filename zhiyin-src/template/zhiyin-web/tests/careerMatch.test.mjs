import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const compiled = ts.transpileModule(readFileSync(new URL('../src/lib/careerMatch.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText
const { isMatchAccepted, saveMatchAcceptance } = await import(`data:text/javascript,${encodeURIComponent(compiled)}`)
const result = { recommendation_id: 'current', actions: ['核验 SQL', '整理项目证据'] }
const plan = { phases: [{ tasks: result.actions.map((text, index) => ({ text, task_id: `match_current_${index}` })) }] }

test('已采纳来自持久计划中的全部任务，刷新后仍能确认', () => {
  assert.equal(isMatchAccepted(result, plan), true)
  assert.equal(isMatchAccepted(result, null), false)
  assert.equal(isMatchAccepted(result, { phases: [{ tasks: [plan.phases[0].tasks[0]] }] }), false)
  assert.equal(isMatchAccepted({ ...result, recommendation_id: 'new' }, plan), false)
})

test('保存失败或没有返回全部真实任务时，不应用计划或显示成功', async () => {
  let applied = 0
  const apply = () => applied++
  await assert.rejects(saveMatchAcceptance(result, async () => { throw new Error('保存失败') }, apply), /保存失败/)
  await assert.rejects(saveMatchAcceptance(result, async () => ({ phases: [] }), apply), /没有确认/)
  assert.equal(applied, 0)
})

test('保存成功后应用服务端返回的计划，提交的是本次推荐编号', async () => {
  let applied
  let submitted
  const saved = await saveMatchAcceptance(result, async (id) => { submitted = id; return plan }, (value) => { applied = value })
  assert.equal(submitted, 'current')
  assert.equal(saved, plan)
  assert.equal(applied, plan)
})

const component = readFileSync(new URL('../src/components/console/MatchOverlay.vue', import.meta.url), 'utf8')
const script = component.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
const ast = ts.createSourceFile('MatchOverlay.ts', script, ts.ScriptTarget.Latest, true)
const handler = ast.statements.find((item) => ts.isFunctionDeclaration(item) && item.name?.text === 'decide')
const handlerJs = ts.transpileModule(handler.getText(ast), {}).outputText

function clickHandler(save) {
  const events = []
  const saving = { value: false }
  const error = { value: '' }
  const session = {
    applyActionPlan(value) { events.push(['plan', value]) },
    acceptSuggestion(id) { events.push(['accept', id]) },
    dismissSuggestion(id) { events.push(['dismiss', id]) },
    openDrawer(...args) { events.push(['drawer', ...args]) },
  }
  const click = new Function('saving', 'error', 'session', 'saveMatchAcceptance', 'acceptCareerMatch', `${handlerJs}; return decide`)(
    saving, error, session, saveMatchAcceptance, save,
  )
  return { click, saving, error, events }
}

test('实际采纳按钮写入失败后仍允许重试，不记录采纳成功', async () => {
  const state = clickHandler(async () => { throw new Error('网络断开') })
  await state.click('accept', result)
  assert.equal(state.saving.value, false)
  assert.equal(state.error.value, '网络断开')
  assert.deepEqual(state.events, [])
})

test('实际采纳按钮等待保存并阻止连续点击；成功提示引用真实任务', async () => {
  let finish
  let writes = 0
  const state = clickHandler(() => { writes++; return new Promise((resolve) => { finish = resolve }) })
  const pending = state.click('accept', result)
  await state.click('accept', result)
  assert.equal(writes, 1)
  assert.deepEqual(state.events, [])
  finish(plan)
  await pending
  assert.deepEqual(state.events[1], ['accept', 'current'])
  assert.deepEqual(state.events[2][3].map((item) => item.detail), result.actions)
})
