import test from 'node:test'
import assert from 'node:assert/strict'
import {
  adminStats, attentionItems, jobStatus, moduleGrantSummary, moduleKind, moduleStatus, sortJobs,
} from '../src/admin/model.ts'

function module(id, overrides = {}) {
  return {
    manifest: {
      id, name: id, version: '1.0.0', owner: '平台', description: `${id} 模块`,
      reads: [], actions: [], kind: 'application', ...(overrides.manifest || {}),
    },
    policy: { enabled: true, reads: [], actions: [], agents: [], revision: 1, ...(overrides.policy || {}) },
    source_revision: 'rev',
    effective_enabled: true,
    blocked_by: [],
    ...overrides,
    manifest: {
      id, name: id, version: '1.0.0', owner: '平台', description: `${id} 模块`,
      reads: [], actions: [], kind: 'application', ...(overrides.manifest || {}),
    },
  }
}

test('模块状态区分启用、受阻与未启用', () => {
  assert.deepEqual(moduleStatus(module('a')), { label: '已启用', tone: 'ok' })
  const blocked = module('child', { effective_enabled: false, blocked_by: ['parent'] })
  assert.deepEqual(moduleStatus(blocked), { label: '受阻', tone: 'warn' })
  const disabled = module('off', { policy: { enabled: false, reads: [], actions: [], agents: [], revision: 0 }, effective_enabled: false })
  assert.deepEqual(moduleStatus(disabled), { label: '未启用', tone: 'muted' })
  assert.equal(moduleKind(blocked), 'application')
})

test('授权摘要只读真实授权数量，不编造权限分', () => {
  const item = module('a', { policy: { enabled: true, reads: ['profile'], actions: ['plan.task.set_done'], agents: ['career_advisor'], revision: 2 } })
  assert.equal(moduleGrantSummary(item), '读取 1 · 操作 1 · 智能体 1')
  assert.equal(moduleGrantSummary(module('b')), '尚未授权')
})

test('总览统计从真实模块、发布和检查结果计算', () => {
  const modules = [
    module('a'),
    module('b', { policy: { enabled: true, reads: [], actions: [], agents: [], revision: 1 }, effective_enabled: false, blocked_by: ['a'] }),
    module('c', { policy: { enabled: false, reads: [], actions: [], agents: [], revision: 0 }, effective_enabled: false }),
  ]
  const jobs = [
    { id: 'j1', status: 'requested', commit: 'a'.repeat(40), kind: 'deploy', actor: 'u', request_id: 'r', result: {}, events: [], created_at: '2026-10-26T10:00:00Z' },
    { id: 'j2', status: 'succeeded', commit: 'b'.repeat(40), kind: 'check', actor: 'u', request_id: 'r2', result: {}, events: [], created_at: '2026-10-26T09:00:00Z' },
  ]
  const checks = [{ id: 'c1', passed: false, errors: [{ module: 'a', file: 'x.py', message: '缺少输出契约' }] }]
  const stats = adminStats(modules, jobs, checks, {
    base_commit: 'x', pending_versions: 2,
    worker: { healthy: false, last_seen: null }, environment: { revision: null, url: '' },
  })
  assert.deepEqual(stats, {
    modules: 3, enabled: 1, disabled: 2, blocked: 1, requested: 1,
    failedChecks: 1, pendingVersions: 2, workerHealthy: false,
  })
})

test('待处理列表只列真实阻塞项，并指向对应页面', () => {
  const modules = [
    module('a'),
    module('child', { effective_enabled: false, blocked_by: ['a'] }),
  ]
  const jobs = [{ id: 'j1', status: 'requested', commit: 'a'.repeat(40), kind: 'deploy', actor: 'u', request_id: 'r', result: {}, events: [], created_at: '2026-10-26T10:00:00Z' }]
  const checks = [{ id: 'c1', passed: false, errors: [{ message: '缺少输出契约' }] }]
  const platform = { base_commit: '', pending_versions: 0, worker: { healthy: false, last_seen: null }, environment: { revision: null, url: '' } }
  const stats = adminStats(modules, jobs, checks, platform)
  const items = attentionItems(stats, modules, checks, platform)
  assert.deepEqual(items.map(item => item.id), ['approvals', 'blocked-modules', 'checks', 'worker'])
  assert.equal(items[1].tab, 'modules')
  assert.match(items[1].detail, /child/)
})

test('没有阻塞项时待处理为空', () => {
  const stats = adminStats([module('a')], [], [{ id: 'c', passed: true }], {
    base_commit: '', pending_versions: 0, worker: { healthy: true, last_seen: '2026-10-26T10:00:00Z' }, environment: { revision: null, url: '' },
  })
  assert.deepEqual(attentionItems(stats, [module('a')], [{ id: 'c', passed: true }], {
    base_commit: '', pending_versions: 0, worker: { healthy: true, last_seen: '2026-10-26T10:00:00Z' }, environment: { revision: null, url: '' },
  }), [])
})

test('发布状态有中文标签，记录按时间倒序', () => {
  assert.equal(jobStatus('requested').label, '待确认')
  assert.equal(jobStatus('rolled_back').label, '已回滚')
  const rows = [
    { id: 'old', created_at: '2026-10-25T10:00:00Z' },
    { id: 'new', created_at: '2026-10-26T10:00:00Z' },
  ]
  assert.deepEqual(sortJobs(rows).map(row => row.id), ['new', 'old'])
})
