import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function runtime(fetcher) {
  const storage = new Map([['zhiyin_token', 'test-token']])
  const events = []
  const globals = { AbortController, URLSearchParams, Headers, FormData, Event, TextDecoder, Object, setTimeout, clearTimeout,
    fetch: fetcher, localStorage: {getItem:k=>storage.get(k)},
    window: {dispatchEvent:e=>events.push(e.type)} }
  const modules = {}
  const ops = JSON.parse(readFileSync(new URL('../src/api/operations.json',import.meta.url)))
  for (const file of ['backend-client','backend-stream','client']) {
    const source = readFileSync(new URL(`../src/api/${file}.ts`,import.meta.url),'utf8')
    const code = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText
    const exports = {}
    vm.runInNewContext(code,{...globals,exports,require:p=>p==='./operations.json'?ops:modules[p]})
    modules['./'+file]=exports
  }
  return {...modules['./backend-client'],...modules['./backend-stream'],...modules['./client'],storage,events}
}
const json = (data,code=0,status=200)=>new Response(JSON.stringify({code,data,message:code?'拒绝请求':'ok'}),{status,headers:{'Content-Type':'application/json'}})
const sse = frames=>new Response(frames.map(f=>'data: '+JSON.stringify(f)+'\n\n').join(''),{headers:{'Content-Type':'text/event-stream'}})

test('uses real URL, bearer token, method and escaped query',async()=>{
  const calls=[];const app=runtime(async(...args)=>{calls.push(args);return json({items:[]})})
  await app.backendClient.intel('软件 & 实习')
  assert.equal(calls[0][0],'/api/v1/app/intel?q='+encodeURIComponent('软件 & 实习').replaceAll('%20','+'))
  assert.equal(calls[0][1].headers.Authorization,'Bearer test-token')
})
test('business failures never return sample data',async()=>{
  const app=runtime(async()=>json(null,1002))
  await assert.rejects(app.backendClient.workspace(),e=>e.code===1002)
})
test('401 invalidates authentication, failed login does not invalidate another session',async()=>{
  const app=runtime(async()=>json(null,1004,401))
  await assert.rejects(app.backendClient.bootstrap())
  assert.ok(app.events.includes('zhiyin:unauthorized'))
  app.events.length=0
  await assert.rejects(app.backendClient.authenticate('login',{account:'qa',password:'wrong'}))
  assert.equal(app.events.length,0)
})

test('anonymous old-page 401 requests do not clear an in-progress login form',async()=>{
  for(const invoke of [app=>app.backendClient.bootstrap(),app=>app.api('/developer/context'),app=>app.streamBackend('brief',{},()=>{})]) {
    const app=runtime(async()=>json(null,1004,401))
    app.storage.delete('zhiyin_token')
    await assert.rejects(invoke(app),e=>e.code===1004)
    assert.equal(app.events.length,0)
  }
})

test('anonymous business and streaming auth errors still reject without resetting login state',async()=>{
  for(const invoke of [app=>app.backendClient.bootstrap(),app=>app.api('/developer/context'),app=>app.streamBackend('brief',{},()=>{})]) {
    const app=runtime(async()=>json(null,1004,200))
    app.storage.delete('zhiyin_token')
    await assert.rejects(invoke(app),e=>e.code===1004)
    assert.equal(app.events.length,0)
  }
  const app=runtime(async()=>sse([{error:{code:1004,message:'未登录'}}]))
  app.storage.delete('zhiyin_token')
  await assert.rejects(app.streamBackend('brief',{},()=>{}),e=>e.code===1004)
  assert.equal(app.events.length,0)
})
test('late results cannot populate another account',async()=>{
  let release;const app=runtime(()=>new Promise(resolve=>release=resolve))
  const pending=app.backendClient.notes();app.storage.set('zhiyin_token','other');release(json([]))
  await assert.rejects(pending,e=>e.code===1004)
})
test('conversation preserves client message identity and option/material IDs',async()=>{
  let sent;const app=runtime(async(_url,init)=>{sent=JSON.parse(init.body);return json({})})
  const request={task_id:'t',client_msg_id:'retry-stable',message:'hello',option_id:'o',material_ids:['m']}
  await app.backendClient.message(request)
  assert.deepEqual(sent,request)
})
test('explicit cancellation aborts the underlying request',async()=>{
  const app=runtime(async(_url,init)=>new Promise((_ok,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('aborted')))))
  const controller=new AbortController(),pending=app.backendClient.message({message:'x',task_id:'t'},controller.signal)
  controller.abort();await assert.rejects(pending,e=>e.code===1007)
})
test('SSE progress is not success; terminal result is required',async()=>{
  const app=runtime(async()=>sse([{pct:50,note:'读取中'}]))
  await assert.rejects(app.streamBackend('brief',{},()=>{}),e=>e.code===1007)
})
test('SSE consumes progress and returns the terminal result',async()=>{
  const progress=[];const app=runtime(async()=>sse([{pct:10},{result:{data:{headline:'真实结果'}}}]))
  const result=await app.streamBackend('brief',{},p=>progress.push(p))
  assert.equal(result.data.headline,'真实结果');assert.equal(progress.length,1)
})
test('SSE authentication errors invalidate the session',async()=>{
  const app=runtime(async()=>sse([{error:{code:1004,message:'会话已过期'}}]))
  await assert.rejects(app.streamBackend('brief',{},()=>{}),e=>e.code===1004)
  assert.deepEqual(app.events,['zhiyin:unauthorized'])
})

test('late developer results and 401 responses cannot overwrite or log out the new account',async()=>{
  for (const response of [json({role:'admin'}),json(null,1004,401)]) {
    let release;const app=runtime(()=>new Promise(resolve=>release=resolve))
    const pending=app.api('/developer/context');app.storage.set('zhiyin_token','new-account');release(response)
    await assert.rejects(pending,e=>e.code===1004)
    assert.deepEqual(app.events,[])
  }
})

test('late SSE authentication errors cannot invalidate a different account',async()=>{
  for (const response of [sse([{error:{code:1004,message:'expired'}}]),json(null,1004,401)]) {
    let release;const app=runtime(()=>new Promise(resolve=>release=resolve))
    const pending=app.streamBackend('dimension',{params:{dimension_id:'interest'}},()=>{})
    app.storage.set('zhiyin_token','new-account');release(response)
    await assert.rejects(pending,e=>e.code===1004)
    assert.deepEqual(app.events,[])
  }
})

test('account switch while reading response bodies rejects old results and auth errors',async()=>{
  for (const invoke of [app=>app.backendClient.workspace(),app=>app.api('/developer/context'),app=>app.streamBackend('brief',{},()=>{})]) {
    let release;let started;const reading=new Promise(resolve=>started=resolve)
    const app=runtime(async()=>({ok:true,status:200,headers:new Headers({'Content-Type':'application/json'}),json:()=>{started();return new Promise(resolve=>release=resolve)}}))
    const pending=invoke(app);await reading;app.storage.set('zhiyin_token','new-account');release({code:1004,message:'expired'})
    await assert.rejects(pending,e=>e.code===1004)
    assert.deepEqual(app.events,[])
  }
})

test('chat SSE preserves request identity and delivers partial UTF8 text before terminal result',async()=>{
 let sent, push
 const stream=new ReadableStream({start(c){push=c}})
 const progress=[]
 const app=runtime(async(_url,init)=>{sent=JSON.parse(init.body);return new Response(stream,{headers:{'Content-Type':'text/event-stream'}})})
 const request={task_id:'real-session',message:'问题',client_msg_id:'stable-id',material_ids:['file']}
 const pending=app.streamBackend('messageStream',{body:request},f=>progress.push(f))
 const bytes=new TextEncoder().encode('data: {"text":"真实"}\r\n\r\n')
 for(const byte of bytes) push.enqueue(new Uint8Array([byte]))
 await new Promise(resolve=>setTimeout(resolve,0))
 assert.equal(progress[0].text,'真实');assert.deepEqual(sent,request)
 push.enqueue(new TextEncoder().encode('data: {"result":{"task_id":"real-session"}}\n\n'));push.close()
 assert.equal((await pending).task_id,'real-session')
})
test('permission denial preserves login across student, developer and streaming transports',async()=>{
  const app=runtime(async()=>json(null,1008,403))
  await assert.rejects(app.backendClient.workspace())
  await assert.rejects(app.api('/developer/context'))
  await assert.rejects(app.streamBackend('portraitAnalysis',{}))
  assert.deepEqual(app.events,[])
  assert.equal(app.storage.get('zhiyin_token'),'test-token')
})

test('lost or invalid save response is reported as unconfirmed, not a parser error',async()=>{
  const app=runtime(async()=>new Response('',{status:502}))
  await assert.rejects(app.api('/app/plan/action/tasks',{method:'POST',body:'{}'}),e=>e.code===1007&&e.message.includes('保存结果尚未确认'))
})
