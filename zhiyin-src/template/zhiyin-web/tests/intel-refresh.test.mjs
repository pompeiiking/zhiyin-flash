import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as vue from 'vue'

function setup(client, items=[]) {
  const {descriptor}=parse(readFileSync(new URL('../src/views/IntelView.vue',import.meta.url),'utf8'))
  const script=compileScript(descriptor,{id:'IntelView'})
  const code=ts.transpileModule(script.content,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const data=vue.reactive({intel:items})
  const modules={vue:{...vue,onMounted:()=>{}},'../api/backend-client':{backendClient:client},'../lib/backend-demo':{backendDemo:{state:data,setIntel:items=>data.intel=items}}}
  const exports={}
  vm.runInNewContext(code,{exports,require:path=>modules[path]??{}})
  return {state:exports.default.setup({}, {expose:()=>{}}),data}
}
test('explicit refresh uses the refresh endpoint and replaces results with service data',async()=>{
  let calls=0
  const app=setup({intel:async()=>{throw Error('must not read cache')},refreshIntel:async()=>{calls++;return {items:[{id:'live',kind:'occupation',title:'实际返回'}]}}})
  await app.state.load(true)
  assert.equal(calls,1)
  assert.equal(app.data.intel[0].id,'live')
  assert.equal(app.state.selectedId.value,'live')
  assert.match(app.state.status.value,/1 条/)
})
test('failed refresh preserves previous results and retains refresh intent for retry',async()=>{
  const app=setup({refreshIntel:async()=>{throw Error('upstream unavailable')}},[{id:'existing'}])
  await app.state.load(true)
  assert.equal(app.data.intel[0].id,'existing')
  assert.equal(app.state.lastRefresh.value,true)
  assert.equal(app.state.status.value,'')
  assert.match(app.state.error.value,/更新失败/)
  assert.equal(app.state.busy.value,false)
})
test('empty refresh is an explicit empty result, not synthetic careers or success count',async()=>{
  const app=setup({refreshIntel:async()=>({items:[]})},[{id:'old'}])
  await app.state.load(true)
  assert.equal(app.data.intel.length,0)
  assert.match(app.state.status.value,/未获取到/)
})
