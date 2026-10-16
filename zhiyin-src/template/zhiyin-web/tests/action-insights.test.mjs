import test from 'node:test'
import assert from 'node:assert/strict'
import {actionRows,dateKey,deadline,taskGroup,directionRanking} from '../src/lib/action-insights.mjs'

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
test('rank only valid backend scores; unknown values remain unknown and inputs remain unchanged',()=>{
  const plans=[{id:'unknown',match_score:null},{id:'zero',match_score:0},{id:'high',match_score:.8},{id:'invalid',match_score:90}]
  assert.deepEqual(directionRanking(plans,'score').map(p=>p.id),['high','zero','unknown','invalid'])
  assert.deepEqual(plans.map(p=>p.id),['unknown','zero','high','invalid'])
  assert.equal(plans[0].match_score,null)
  assert.deepEqual(directionRanking(plans,'original'),plans)
})
