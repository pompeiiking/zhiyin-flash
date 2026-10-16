import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as vue from 'vue'

test('new tasks keep the selected phase and repeated saving updates the same task',async()=>{
  const {descriptor}=parse(readFileSync(new URL('../src/components/TaskEditor.vue',import.meta.url),'utf8'))
  const code=ts.transpileModule(compileScript(descriptor,{id:'TaskEditor'}).content,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
  const plan=vue.reactive({phases:[{id:'first',name:'阶段一',tasks:[]},{id:'selected',name:'当前阶段',tasks:[]}]})
  const calls=[]
  const client={saveTask:async(body,id)=>{calls.push({body,id});return {phases:[{id:'first',tasks:[]},{id:'selected',tasks:[{task_id:'saved-task',text:body.text}]}]}}}
  const modules={vue,'../lib/form-values.mjs':{localDateTime:()=>''},'../api/student-capabilities':{studentApi:client},'../lib/backend-demo':{backendDemo:{state:{liveAction:plan},setAction:next=>plan.phases=next.phases}}}
  const exports={};vm.runInNewContext(code,{exports,require:path=>modules[path]??{}})
  const state=exports.default.setup({phaseId:'selected'},{expose:()=>{}})
  state.open.value=true;await vue.nextTick()
  assert.equal(state.phase.value,'selected')
  state.text.value='测试任务';await state.save();await state.save()
  assert.equal(calls[0].body.phase_id,'selected')
  assert.equal(calls[1].id,'saved-task')
})
