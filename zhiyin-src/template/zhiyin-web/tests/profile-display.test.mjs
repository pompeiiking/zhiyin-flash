import test from 'node:test'
import assert from 'node:assert/strict'
import { profileDisplayValue } from '../src/lib/profile-display.ts'

test('纯否定兴趣从 attributes.items 显示，而不是显示成空白', () => {
  const shown = profileDisplayValue([], {
    items: [
      { value: '天天应酬', polarity: 'dislike' },
      { value: '纯销售工作', polarity: 'dislike' },
    ],
  })
  assert.equal(shown, '天天应酬：不喜欢、纯销售工作：不喜欢')
})

test('喜欢与不喜欢的条目同时显示，不重复', () => {
  const shown = profileDisplayValue(['写东西'], {
    items: [
      { value: '写东西', polarity: 'like' },
      { value: '应酬', polarity: 'dislike' },
    ],
  })
  assert.equal(shown, '写东西：喜欢、应酬：不喜欢')
})

test('职业关注沿用同一套逐项状态口径', () => {
  const shown = profileDisplayValue(['算法工程师'], {
    items: [{ value: '算法工程师', state: 'exploring' }],
  })
  assert.equal(shown, '算法工程师：正在了解')
})

test('没有逐项属性时按原值显示', () => {
  assert.equal(profileDisplayValue('某某大学'), '某某大学')
  assert.equal(profileDisplayValue([]), '')
  assert.equal(profileDisplayValue(null), '尚待补充')
})
