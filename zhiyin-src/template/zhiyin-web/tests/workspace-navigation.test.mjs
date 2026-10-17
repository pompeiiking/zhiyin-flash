import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { createRouter, createMemoryHistory } from 'vue-router'
import { ref } from 'vue'

let navigationGuard
function load(path, dependencies = {}) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  vm.runInNewContext(code, { exports, require(name) {
    assert.ok(name in dependencies, `Unexpected import: ${name}`)
    return dependencies[name]
  } })
  return exports
}
const nav = load('../src/lib/workspace-nav.ts')
const { router } = load('../src/router.ts', {
  'vue-router': {
    createWebHashHistory: createMemoryHistory,
    createRouter(options) {
      const router = createRouter(options)
      const register = router.beforeEach
      router.beforeEach = guard => { navigationGuard = guard; return register(guard) }
      return router
    },
  },
  vue: { ref },
  './store': { demo: { state: { authed: true } } },
  './lib/auth': { auth: { restore: async () => true } },
  './lib/features': { routeEnabled: () => true },
  './api/backend-client': { backendRequest: async () => ({}) },
  './lib/session-cache': { sessionCacheAvailable: ref(false) },
})

test('every published navigation entry resolves to a real route', () => {
  for (const item of [...nav.WORKSPACE_ITEMS, ...nav.DIRECTORY_PAGES]) {
    const route = router.resolve(item.to)
    assert.ok(route.matched.length, item.to)
    assert.notEqual(route.name, 'not-found', item.to)
  }
})

test('all twelve workspaces have one active item; grades belong to the profile mobile group', () => {
  assert.equal(nav.WORKSPACE_ITEMS.length, 12)
  for (const item of nav.WORKSPACE_ITEMS) {
    const route = { path: item.to, query: {} }
    assert.deepEqual(Array.from(nav.WORKSPACE_ITEMS.filter(i => nav.isNavActive(i, route)), i => i.key), [item.key])
  }
  assert.equal(nav.activeGroup({ path: '/grades', query: {} }).key, 'self')
  assert.equal(nav.isNavActive(nav.MOBILE_TABS.find(i => i.key === 'profile'), { path: '/grades', query: {} }), true)
  assert.equal(nav.WORKSPACE_ITEMS.some(i => i.to === '/academic'), false)
})

test('legacy academic, growth and direction links retain their destination', async () => {
  assert.equal(router.resolve('/academic').matched.at(-1).redirect, '/grades')
  assert.equal(await navigationGuard({ path: '/review', query: { view: 'achievements' } }), '/achievements')
  assert.equal(await navigationGuard({ path: '/report', query: { focus: 'choose' } }), '/directions')
  assert.equal(await navigationGuard({ path: '/report', query: { focus: 'versions' }, meta: {} }), true)
})

test('report reading and direction comparison no longer share a page component', () => {
  const report = router.resolve('/report').matched.at(-1).components.default
  const directions = router.resolve('/directions').matched.at(-1).components.default
  assert.match(String(report), /AssessmentView/)
  assert.match(String(directions), /DirectionsView/)
})
