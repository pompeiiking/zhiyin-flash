import test from 'node:test'
import assert from 'node:assert/strict'
import {localDateTime,reviewDraft,measurementPercent} from '../src/lib/form-values.mjs'

test('local form dates tolerate missing data and preserve local date and time',()=>{
  assert.equal(localDateTime(null),'')
  assert.equal(localDateTime('not-a-date'),'')
  const date=new Date(2026,9,16,9,30)
  assert.equal(localDateTime(date.toISOString()),'2026-10-16T09:30')
})
test('switching review tasks replaces all adjustment fields including an absent deadline',()=>{
  const first=reviewDraft({text:'第一件事',due_date:new Date(2026,9,18,12).toISOString()})
  const second=reviewDraft({text:'第二件事',due_date:null})
  assert.equal(first.due,'2026-10-18T12:00')
  assert.deepEqual(second,{text:'第二件事',due:''})
  assert.deepEqual(reviewDraft(),{text:'',due:''})
})
test('measurement scale distinguishes zero from missing or malformed values',()=>{
  assert.equal(measurementPercent({value:0}),0)
  assert.equal(measurementPercent({value:3,minimum:1,maximum:5}),50)
  assert.equal(measurementPercent({value:100}),100)
  for(const m of [{value:1,minimum:1,maximum:1},{value:5,minimum:10,maximum:0},{value:NaN},{value:101},{value:-1}])assert.equal(measurementPercent(m),null)
})
