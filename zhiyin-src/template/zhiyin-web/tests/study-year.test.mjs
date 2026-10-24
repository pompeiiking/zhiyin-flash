import test from 'node:test'
import assert from 'node:assert/strict'
import { STUDY_YEAR_OPTIONS, initialOnboardingQuestion, personalizedStudyYearEntries, studyYearCode, studyYearIntro, studyYearLabel } from '../src/lib/study-year.ts'

const entries = [
  ['confused', '不清楚', 1],
  ['verify_direction', '验证方向', 2],
  ['undecided', '比较方向', 3],
  ['how_to_act', '开始行动', 4],
  ['stuck', '解决卡点', 5],
  ['review_due', '回顾调整', 6],
  ['free_chat', '直接开聊', 7],
].map(([code, label, sort_order]) => ({ code, label, sort_order }))

test('学习阶段代码与中文值使用同一套路由口径', () => {
  assert.equal(studyYearCode('year_3'), 'year_3')
  assert.equal(studyYearCode('大三'), 'year_3')
  assert.equal(studyYearLabel('year_3'), '大三')
  assert.match(studyYearIntro('大三'), /实习/)
})

test('学习阶段只提供大一到大四', () => {
  assert.deepEqual(STUDY_YEAR_OPTIONS.map(option => option.label), ['大一', '大二', '大三', '大四'])
  for (const retired of ['大五／五年制', '研究生', '其他阶段']) {
    assert.equal(studyYearCode(retired), null)
  }
})

test('大一和大四获得不同的默认咨询方向，且都保留自由交流', () => {
  const freshman = personalizedStudyYearEntries(entries, '大一')
  const senior = personalizedStudyYearEntries(entries, '大四')

  assert.equal(freshman[0].code, 'confused')
  assert.equal(senior[0].code, 'how_to_act')
  assert.match(freshman[0].label, /兴趣与优势/)
  assert.match(senior[0].label, /校招/)
  assert.ok(freshman.some(entry => entry.code === 'free_chat'))
  assert.ok(senior.some(entry => entry.code === 'free_chat'))
})

test('没有学习阶段时保留服务端下发的原始入口顺序和文案', () => {
  const result = personalizedStudyYearEntries(entries, '')
  assert.deepEqual(result.map(entry => entry.label), entries.map(entry => entry.label))
})

test('首次进入先问能否学信网核验；核验过/已有内容时各有归属', () => {
  const empty = { studyYear: '', hasSession: false, hasTurns: false, hasPending: false }
  assert.equal(initialOnboardingQuestion({ ...empty, chsiTouched: false }), 'verify')
  assert.equal(initialOnboardingQuestion({ ...empty, chsiTouched: true }), 'year')
  assert.equal(initialOnboardingQuestion({ ...empty, studyYear: '大一', chsiTouched: false }), null)
  assert.equal(initialOnboardingQuestion({ ...empty, hasSession: true, chsiTouched: false }), null)
  assert.equal(initialOnboardingQuestion({ ...empty, hasTurns: true, chsiTouched: false }), null)
  assert.equal(initialOnboardingQuestion({ ...empty, hasPending: true, chsiTouched: false }), null)
})
