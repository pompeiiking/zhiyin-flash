import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/conversation-presentation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Set})
const {conversationPresentation:present,partialReplySpeaker,journeyState}=exports
const snapshot={task_id:'s1',stage:'collect',badge:{name:'信息采集顾问'}}

test('live focus is provisional and failed/stopped runs return to the confirmed stage',()=>{
  assert.equal(present('s1',snapshot,undefined,'act',true).stage,'act')
  assert.equal(present('s1',snapshot,undefined,'act',false).stage,'collect')
  assert.equal(present('s1',{...snapshot,stage:'review'},undefined,'act',false).stage,'review')
  assert.equal(present('s1',snapshot,undefined,'invalid',true).stage,'collect')
})
test('session switches cannot reuse another conversation identity or focus',()=>{
  const session={task_id:'s2',stage:'act',lead_agent_name:'行动规划顾问'}
  const result=present('s2',snapshot,session,'',false)
  assert.equal(result.stage,'act');assert.equal(result.host,'行动规划顾问')
})
test('stopping a partial reply preserves its actual streaming speaker',()=>{
  assert.equal(partialReplySpeaker('path_planner','信息采集顾问'),'path_planner')
  assert.equal(partialReplySpeaker(undefined,'信息采集顾问'),'信息采集顾问')
})
test('journey marks earlier stages as past, current as current and later as future',()=>{
  const stages=['collect','diagnose','decide','act','review']
  assert.equal(journeyState(stages,'decide','collect'),'past')
  assert.equal(journeyState(stages,'decide','diagnose'),'past')
  assert.equal(journeyState(stages,'decide','decide'),'current')
  assert.equal(journeyState(stages,'decide','act'),'future')
  assert.equal(journeyState(stages,'collect','review'),'future')
  assert.equal(journeyState(stages,'review','collect'),'past')
  assert.equal(journeyState(stages,'invalid','collect'),'future')
})
