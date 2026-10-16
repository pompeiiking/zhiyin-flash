import test from 'node:test'
import {webcrypto} from 'node:crypto'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as vue from 'vue'

for (const concurrent of [false,true]) test('new task retry preserves identity; concurrent creation='+concurrent,async()=>{
  const {descriptor}=parse(readFileSync(new URL('../src/components/TaskEditor.vue',import.meta.url),'utf8'))
  const code=ts.transpileModule(compileScript(descriptor,{id:'TaskEditor'}).content,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
  const plan=vue.reactive({phases:[{id:'first',name:'阶段一',tasks:[]},{id:'selected',name:'当前阶段',tasks:[]}]})
  const calls=[]
  const client={saveTask:async(body,id)=>{calls.push({body,id});return {phases:[{id:'first',tasks:[]},{id:'selected',tasks:[...(concurrent?[{task_id:'other-task',text:'其他标签的任务'}]:[]),{task_id:'saved-task',text:body.text}]}]}}}
  const modules={vue,'../lib/form-values.mjs':{localDateTime:()=>''},'../api/student-capabilities':{studentApi:client},'../lib/backend-demo':{backendDemo:{state:{liveAction:plan},setAction:next=>plan.phases=next.phases}}}
  const exports={};vm.runInNewContext(code,{exports,crypto:webcrypto,require:path=>modules[path]??{}})
  const state=exports.default.setup({phaseId:'selected'},{expose:()=>{}})
  state.open.value=true;await vue.nextTick()
  assert.equal(state.phase.value,'selected')
  state.text.value='测试任务';await state.save();await state.save()
  assert.equal(calls[0].body.phase_id,'selected')
  assert.equal(calls[1].id,concurrent?undefined:'saved-task')
  assert.equal(calls[0].body.client_request_id,calls[1].body.client_request_id)
  assert.equal(calls[1].body.expected_task?.text,concurrent?undefined:'测试任务')
})
