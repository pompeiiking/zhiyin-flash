import test from 'node:test'
import assert from 'node:assert/strict'
import {webcrypto} from 'node:crypto'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as vue from 'vue'

test('phase edits retain their original snapshot after a failed save',async()=>{
  const {descriptor}=parse(readFileSync(new URL('../src/components/PhaseEditor.vue',import.meta.url),'utf8'))
  const code=ts.transpileModule(compileScript(descriptor,{id:'PhaseEditor'}).content,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
  const plan=vue.reactive({phases:[{id:'one',name:'原阶段',depends_on:[],tasks:[]}]})
  const calls=[]
  const modules={vue,'../lib/action-insights.mjs':{dateKey:()=>''},'../api/student-capabilities':{studentApi:{savePhase:async(body,id)=>{calls.push({body,id});throw new Error('阶段已在其他页面更新')}}},'../lib/backend-demo':{backendDemo:{state:{liveAction:plan}}}}
  const exports={};vm.runInNewContext(code,{exports,crypto:webcrypto,require:path=>modules[path]??{}})
  const state=exports.default.setup({phaseId:'one'},{expose:()=>{}})
  state.open.value=true;await vue.nextTick()
  state.name.value='我的草稿'
  plan.phases[0].name='另一个标签的改动'
  await state.save();await state.save()
  assert.equal(calls[0].body.expected_phase.name,'原阶段')
  assert.equal(calls[1].body.expected_phase.name,'原阶段')
  assert.equal(calls[1].body.client_request_id,calls[0].body.client_request_id)
  assert.equal(state.name.value,'我的草稿')
  assert.match(state.error.value,/其他页面更新/)
})
