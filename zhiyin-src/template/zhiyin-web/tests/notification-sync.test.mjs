import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

test('shell reminder count uses the same pending state as the management list',async()=>{
 let queue=[],reads=0
 const notices=['pending','read','later','done'].map((status,i)=>({id:String(i),title:status,body:'内容',status}))
 const modules={vue:{reactive:x=>x},'../store':{demo:{setNotices:value=>queue=value}},'../api/student-capabilities':{studentApi:{notifications:async()=>{reads++;return notices}}}}
 const exports={}
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/system-data.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,require:path=>modules[path]??{}})
 await exports.refreshNotifications();assert.equal(queue.length,1);assert.equal(queue[0].id,'0')
 notices[0].status='done';notices[2].status='pending';await exports.refreshNotifications(notices)
 assert.equal(reads,1);assert.equal(queue.length,1);assert.equal(queue[0].id,'2')
})
