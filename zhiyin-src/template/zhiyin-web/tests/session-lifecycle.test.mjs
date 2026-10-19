import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const source=ts.transpileModule(readFileSync(new URL('../src/lib/system-data.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
function fixture({pointer='blank',current='',failure}={}) {
 const state={currentSessionId:current,chatBusy:false,chatTurns:[]}
 const session={task_id:'older',task_name:'已有对话'}
 const reads=[],entries=[],storage=new Map([['zhiyin-current-session',pointer]])
 class BackendError extends Error {constructor(message,code){super(message);this.code=code}}
 const check=async id=>{reads.push(id);if(id===pointer&&failure)throw new BackendError(failure.message,failure.code)}
 const backendClient={sessions:async()=>({sessions:[session],current_task_id:'older'}),turns:async id=>{await check(id);return[]},enter:async(...args)=>{entries.push(args);return{task_id:'new'}},action:async()=>null,notes:async()=>[],workspace:async()=>null}
 const backendDemo={state:{currentSessionId:current,sessions:[session]},setSessions(sessions,id){this.state.sessions=sessions;if(id)this.state.currentSessionId=id},selectSession(id){this.state.currentSessionId=id},setCurrentSession(session){this.state.currentSessionId=session.task_id;this.state.sessions.unshift(session)},saveTurns(){},setAction(){},setNotes(){},setWorkspace(){}}
 const demo={state,setChatTurns(turns,id){state.chatTurns=turns;state.currentSessionId=id},setNotices(){}}
 const imports={
  '../api/student-capabilities':{studentApi:{sessionSnapshot:async id=>{await check(id);return null},notifications:async()=>[]}},
  './conversation-turns':{mapMessage:m=>m,withGuide:turns=>turns},vue:{reactive:x=>x},
  '../api/backend-client':{backendClient,BackendError},'./auth':{auth:{state:{bootstrap:{task_entries:[{code:'free_chat'}]}}}},
  './features':{featureEnabled:()=>true},'./backend-demo':{backendDemo},'../store':{demo},
 }
 const exports={}
 vm.runInNewContext(source,{exports,Error,require:name=>{assert.ok(imports[name],name);return imports[name]},window:{addEventListener(){}},sessionStorage:{getItem:key=>storage.get(key),removeItem:key=>storage.delete(key)}})
 return {api:exports,state,reads,entries,storage,backendDemo}
}

test('refresh restores the explicitly selected empty session omitted from history',async()=>{
 const f=fixture();await f.api.loadShell()
 assert.equal(f.state.currentSessionId,'blank')
 assert.equal(f.backendDemo.state.sessions[0].task_id,'older')
 assert.ok(f.reads.includes('blank'));assert.ok(!f.reads.includes('older'))
})
test('a deleted or other-account tab pointer falls back through owned reads',async()=>{
 const f=fixture({failure:{code:1002,message:'会话不存在'}});await f.api.loadShell()
 assert.equal(f.state.currentSessionId,'older');assert.equal(f.storage.has('zhiyin-current-session'),false)
 assert.ok(f.reads.includes('blank')&&f.reads.includes('older'))
})
test('a temporary read failure never silently opens another conversation',async()=>{
 const f=fixture({failure:{code:1007,message:'网络不可用'}});await f.api.loadShell()
 assert.equal(f.state.currentSessionId,'');assert.equal(f.api.systemData.error,'网络不可用')
 assert.ok(!f.reads.includes('older'));assert.equal(f.storage.get('zhiyin-current-session'),'blank')
})
test('refreshing the shell preserves a newly created current session',async()=>{
 const f=fixture({current:'blank'});await f.api.loadShell()
 assert.equal(f.state.currentSessionId,'blank');assert.equal(f.reads.length,0)
})
test('fresh creation sends the new-session flag and clears the previous transcript',async()=>{
 const f=fixture({current:'older'});f.state.chatTurns=[{text:'旧正文'}]
 await f.api.newSession('free_chat',true)
 assert.equal(f.entries.length,1);assert.equal(f.entries[0][0],'free_chat');assert.equal(f.entries[0][1],true)
 assert.equal(f.state.currentSessionId,'new');assert.equal(f.state.chatTurns.length,0)
 assert.ok(f.backendDemo.state.sessions.some(s=>s.task_id==='older'))
})
