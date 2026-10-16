import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'

test('pagination preserves mutation position, clamps shrinking collections and resets changed filters',async()=>{
 const code=ts.transpileModule(readFileSync(new URL('../src/lib/paged-items.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
 const exports={}
 vm.runInNewContext(code,{exports,require:()=>({...vue,onMounted:()=>{},onUnmounted:()=>{}})})
 const rows=vue.ref(Array.from({length:13},(_,id)=>({id,done:false}))),query=vue.ref('')
 const source=vue.computed(()=>rows.value.filter(item=>String(item.id).includes(query.value)))
 const scope=vue.effectScope()
 const state=scope.run(()=>exports.usePagedItems(source,6,()=>query.value))
 state.page.value=2;rows.value[6]={id:6,done:true};await vue.nextTick()
 assert.equal(state.page.value,2);assert.equal(state.paged.value[0].done,true)
 state.page.value=3;rows.value=rows.value.slice(0,12);await vue.nextTick();assert.equal(state.page.value,2)
 query.value='1';await vue.nextTick();assert.equal(state.page.value,1)
 rows.value=[];await vue.nextTick();assert.equal(state.page.value,1);assert.equal(state.paged.value.length,0)
 scope.stop()
})
