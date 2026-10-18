import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function load() {
  const source = readFileSync(new URL('../src/lib/format.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  vm.runInNewContext(code, { exports })
  return exports
}

const { formatDate, formatDateTime, formatMonthDay, formatDateRange, formatRelative, formatPercent, formatCount } = load()

test('formatDate: 统一成 YYYY年M月D日，无效值返回空串', () => {
  assert.equal(formatDate(new Date(2026, 9, 18)), '2026年10月18日')
  assert.equal(formatDate('2026-10-18T04:11:00'), '2026年10月18日')
  assert.equal(formatDate(null), '')
  assert.equal(formatDate('not-a-date'), '')
})

test('formatDateTime: 日期 + 24 小时时间', () => {
  assert.match(formatDateTime(new Date(2026, 9, 18, 4, 11)), /^2026年10月18日 0[45]:11$/)
  assert.equal(formatDateTime(''), '')
})

test('formatMonthDay / formatDateRange', () => {
  assert.equal(formatMonthDay(new Date(2026, 9, 18)), '10月18日')
  assert.equal(formatDateRange(new Date(2026, 9, 12), new Date(2026, 9, 18)), '10月12日 — 10月18日')
  assert.equal(formatDateRange(new Date(2025, 11, 31), new Date(2026, 0, 1)), '2025年12月31日 — 2026年1月1日')
})

test('formatRelative: 今天/昨天/N 天前/日期', () => {
  const now = new Date(2026, 9, 18, 12, 0)
  assert.equal(formatRelative(new Date(2026, 9, 18, 1, 0), now), '今天')
  assert.equal(formatRelative(new Date(2026, 9, 17, 23, 0), now), '昨天')
  assert.equal(formatRelative(new Date(2026, 9, 15, 9, 0), now), '3 天前')
  assert.equal(formatRelative(new Date(2026, 7, 2, 9, 0), now), '8月2日')
  assert.equal(formatRelative(new Date(2025, 2, 2, 9, 0), now), '2025年3月2日')
})

test('formatPercent: 比例与百分数统一，非法值给占位', () => {
  assert.equal(formatPercent(1), '100%')
  assert.equal(formatPercent(0.62), '62%')
  assert.equal(formatPercent(62), '62%')
  assert.equal(formatPercent(0.055, 1), '5.5%')
  assert.equal(formatPercent(undefined), '—')
  assert.equal(formatPercent('abc', 0, ''), '')
})

test('formatCount: 数字与单位', () => {
  assert.equal(formatCount(3, '条'), '3 条')
  assert.equal(formatCount('0', '项'), '0 项')
  assert.equal(formatCount(undefined, '项'), '— 项')
})
