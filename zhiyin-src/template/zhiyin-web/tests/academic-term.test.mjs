import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/academic-term.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports, Set })
const { parseAcademicTerm, currentAcademicTerm, academicTermState } = exports

test('academic term parser accepts the import formats the backend returns', () => {
  assert.equal(parseAcademicTerm('2026-2027-1').startYear, 2026)
  assert.equal(parseAcademicTerm('2026-2027-1').semester, 1)
  assert.equal(parseAcademicTerm('2016-2017 1').startYear, 2016)
  assert.equal(parseAcademicTerm('2025-2026学年第二学期').semester, 2)
  assert.equal(parseAcademicTerm('学期未导入'), null)
})

test('academic term status distinguishes current, history and upcoming', () => {
  const now = new Date('2026-10-22T12:00:00+08:00')
  assert.equal(currentAcademicTerm(now).startYear, 2026)
  assert.equal(currentAcademicTerm(now).semester, 1)
  assert.equal(academicTermState('2026-2027-1', now), 'current')
  assert.equal(academicTermState('2016-2017-1', now), 'history')
  assert.equal(academicTermState('2027-2028-1', now), 'upcoming')
  assert.equal(academicTermState('2025-2026学年第二学期', now), 'history')
})
