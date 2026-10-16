import test from 'node:test'
import assert from 'node:assert/strict'
import {actionRows,actionStatusMatches,dateKey,deadline,taskGroup,directionRanking} from '../src/lib/action-insights.mjs'

test('deadline treats the whole due date as today, not overdue at midnight',()=>{
  const now=new Date(2026,9,16,22,50)
  assert.deepEqual(deadline('2026-10-16',now),{label:'今天截止',days:0,overdue:false})
  assert.equal(deadline('2026-10-15',now).days,-1)
  assert.equal(deadline('2026-10-17',now).days,1)
  assert.equal(deadline(null,now).days,null)
  assert.equal(dateKey('unknown'),'')
})
test('unfinished, future and unknown dates do not imply waiting or partial completion',()=>{
  const now=new Date(2026,9,16)
  assert.equal(taskGroup({done:false,due_date:'2026-10-17'},now),'upcoming')
  assert.equal(taskGroup({done:false},now),'undated')
  assert.equal(taskGroup({done:false,due_date:'2026-10-15'},now),'overdue')
  assert.equal(taskGroup({done:true,due_date:'2026-10-15'},now),'done')
})
test('phase membership is explicit and input objects are not mutated',()=>{
  const task=Object.freeze({task_id:'t',text:'任务',done:false})
  const plan={phases:[{name:'第一阶段',tasks:[task]},{name:'空阶段',tasks:[]}]}
  assert.deepEqual(actionRows(plan),[{...task,phase:'第一阶段',phaseIndex:0}])
  assert.equal('phase' in task,false)
  assert.deepEqual(actionRows(null),[])
})
test('task status filters are mutually exclusive',()=>{
  const pending={done:false,status:'pending'}
  const progress={done:false,status:'in_progress'}
  const waiting={done:false,status:'waiting'}
  const done={done:true,status:'completed'}
  assert.equal(actionStatusMatches(pending,'pending'),true)
  assert.equal(actionStatusMatches(progress,'pending'),false)
  assert.equal(actionStatusMatches(waiting,'pending'),false)
  assert.equal(actionStatusMatches(progress,'in_progress'),true)
  assert.equal(actionStatusMatches(waiting,'waiting'),true)
  assert.equal(actionStatusMatches(done,'done'),true)
  assert.equal(actionStatusMatches(done,'all'),true)
  assert.equal(actionStatusMatches(done,'pending'),false)
})
test('rank only valid backend scores; unknown values remain unknown and inputs remain unchanged',()=>{
  const plans=[{id:'unknown',match_score:null},{id:'zero',match_score:0},{id:'high',match_score:.8},{id:'invalid',match_score:90}]
  assert.deepEqual(directionRanking(plans,'score').map(p=>p.id),['high','zero','unknown','invalid'])
  assert.deepEqual(plans.map(p=>p.id),['unknown','zero','high','invalid'])
  assert.equal(plans[0].match_score,null)
  assert.deepEqual(directionRanking(plans,'original'),plans)
})
import { taskStatusLabel } from '../src/lib/action-insights.mjs'
test('review preserves pending and waiting states independently of deadlines', () => {
  assert.equal(taskStatusLabel({status:'pending',due_date:'2000-01-01'}), '未开始')
  assert.equal(taskStatusLabel({status:'waiting'}), '等待中')
  assert.equal(taskStatusLabel({status:'in_progress'}), '进行中')
  assert.equal(taskStatusLabel({status:'completed'}), '已完成')
  assert.equal(taskStatusLabel({done:true,status:'waiting'}), '已完成')
  assert.equal(taskStatusLabel({}), '未开始')
})
test('timestamps use local calendar dates while date-only values remain unchanged', () => {
  const local = new Date(2026, 9, 17, 0, 30)
  assert.equal(dateKey(local.toISOString()), '2026-10-17')
  assert.equal(dateKey('2026-10-17'), '2026-10-17')
  assert.equal(dateKey('invalid'), '')
})
