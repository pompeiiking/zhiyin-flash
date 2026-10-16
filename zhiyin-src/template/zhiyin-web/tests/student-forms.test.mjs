import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as vue from 'vue'
import * as formValues from '../src/lib/form-values.mjs'
import * as insights from '../src/lib/action-insights.mjs'

// Exercise the actual SFC setup and async handlers without a browser or live writes.
function setup(name,api={},props={},plan={phases:[]}){
  const {descriptor}=parse(readFileSync(new URL(`../src/components/${name}.vue`,import.meta.url),'utf8'))
  const script=compileScript(descriptor,{id:name})
  const code=ts.transpileModule(script.content,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const modules={
    vue:{...vue,useId:()=>name,onMounted:()=>{},onBeforeUnmount:()=>{}},
    '../api/student-capabilities':{studentApi:api},
    '../lib/form-values.mjs':formValues,
    '../lib/action-insights.mjs':insights,
    '../lib/backend-demo':{backendDemo:{state:vue.reactive({liveAction:plan})}},
    '../lib/system-data':{refreshNotifications:async()=>{}},
    '../lib/paged-items':{usePagedItems:source=>({page:vue.ref(1),paged:source})},
  }
  const exports={}
  vm.runInNewContext(code,{exports,require:path=>{
    if(path in modules)return modules[path]
    if(path.endsWith('.vue')||path==='../api/backend-client')return {}
    throw new Error('Unmocked import '+path)
  }})
  const scope=vue.effectScope()
  const state=scope.run(()=>exports.default.setup(vue.reactive(props),{expose:()=>{},emit:()=>{}}))
  return {state,stop:()=>scope.stop()}
}
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}

test('an older workload request cannot replace the current date or clear its loading state',async()=>{
  const older=deferred(),newer=deferred();let count=0
  const app=setup('ScheduleCapacity',{workload:()=>++count===1?older.promise:newer.promise},{date:'2026-10-16'})
  try{
    const first=app.state.load(),second=app.state.load()
    older.resolve({configured:true,weeks:[{start:'old'}]});await first
    assert.equal(app.state.data.value,null)
    assert.equal(app.state.loading.value,true)
    newer.resolve({configured:true,weeks:[{start:'current'}]});await second
    assert.equal(app.state.data.value.weeks[0].start,'current')
    assert.equal(app.state.loading.value,false)
  }finally{app.stop()}
})

test('saving weights reports a successful write separately from a failed recalculation read',async()=>{
  let writes=0
  const app=setup('DirectionScoring',{saveWeights:async()=>{writes++},compare:async()=>{throw Error('读取失败')}})
  try{
    await app.state.save()
    assert.equal(writes,1)
    assert.match(app.state.status.value,/已保存.*暂未更新/)
    assert.equal(app.state.error.value,'读取失败')
    assert.equal(app.state.busy.value,false)
    app.state.draft.value={major:0,jobs:0,salary:0,stability:0,location:0}
    await app.state.save()
    assert.equal(writes,1)
    assert.match(app.state.error.value,/至少保留/)
  }finally{app.stop()}
})

test('switching the selected review task clears a previous adjusted deadline',async()=>{
  const plan={phases:[{id:'p',name:'阶段',tasks:[{task_id:'a',text:'任务 A',due_date:'2026-10-20T10:00:00Z'},{task_id:'b',text:'任务 B'}]}]}
  const app=setup('StructuredReview',{}, {},plan)
  try{
    app.state.selectedId.value='a';await vue.nextTick()
    assert.notEqual(app.state.adjustedDate.value,'')
    app.state.adjustedDate.value='2026-11-01T12:00'
    app.state.selectedId.value='b';await vue.nextTick()
    assert.equal(app.state.adjustedText.value,'任务 B')
    assert.equal(app.state.adjustedDate.value,'')
  }finally{app.stop()}
})

test('a failed preference save clears a previous success message and preserves edits',async()=>{
  const app=setup('AccountPreferences',{savePreferences:async()=>{throw Error('保存失败')}})
  try{
    app.state.values.value={proactive_reminders:false}
    app.state.status.value='上次保存成功'
    await app.state.save()
    assert.equal(app.state.status.value,'')
    assert.equal(app.state.values.value.proactive_reminders,false)
    assert.equal(app.state.error.value,'保存失败')
  }finally{app.stop()}
})

test('a reminder cannot be snoozed into the past and uses its own date draft',async()=>{
  const writes=[]
  const app=setup('NotificationCenter',{notification:async(id,value)=>{writes.push({id,value});return {id,...value}}})
  try{
    app.state.snooze.value={a:'2000-01-01T09:00',b:'2099-01-01T09:00'}
    await app.state.change({id:'a'},'later')
    assert.equal(writes.length,0)
    assert.match(app.state.snoozeError.value.a,/未来/)
    await app.state.change({id:'b'},'later')
    assert.equal(writes.length,1)
    assert.equal(writes[0].id,'b')
    assert.equal(new Date(writes[0].value.snoozed_until).getFullYear(),2099)
  }finally{app.stop()}
})


test('an applied review can be revised without creating another record and the prior version remains',async()=>{
  const previous={id:'r',task_id:'a',task_text:'任务 A',reason:'达到预期',note:'原记录',result:'complete',history:[],applied_at:'2026-10-16T09:00:00Z'}
  let current=previous;const writes=[]
  const app=setup('StructuredReview',{reviews:async()=>({items:[current]}),saveReview:async(value,id)=>{writes.push({value,id});current={...value,id,task_text:'任务 A',applied_at:null,history:[previous]};return current}}, {},{phases:[{id:'p',tasks:[{task_id:'a',text:'任务 A',done:true}]}]})
  try{
    await app.state.load();await app.state.edit(previous)
    app.state.note.value='修订内容';app.state.result.value='continue';await app.state.save()
    assert.equal(writes[0].id,'r');assert.equal(writes[0].value.note,'修订内容')
    assert.equal(app.state.selectedReview.value.history[0].note,'原记录')
    assert.equal(app.state.pendingReviews.value.length,0)
    assert.equal(app.state.selectedReview.value.note,'修订内容')
  }finally{app.stop()}
})
