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
    '../api/backend-client':{backendClient:{action:async()=>{throw Error('计划读取失败')}}},
    '../lib/form-values.mjs':formValues,
    // 统一日期格式化的最小替身：测试断言语义，不核对具体排版。
    '../lib/format':{formatDate:v=>v?String(v).slice(0,10):'',formatDateTime:v=>v?String(v).replace('T',' ').slice(0,16):''},
    '../lib/form-conflict':{conflictRows:()=>[],rebaseForm:(draft,original,latest)=>({...latest,...draft})},
    '../lib/action-insights.mjs':insights,
    '../lib/backend-demo':{backendDemo:{state:vue.reactive({liveAction:plan})}},
    '../lib/system-data':{refreshNotifications:async()=>{}},
    '../lib/paged-items':{usePagedItems:source=>({page:vue.ref(1),paged:source})},
  }
  const exports={}
  vm.runInNewContext(code,{exports,crypto:globalThis.crypto,require:path=>{
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
  const app=setup('DirectionScoring',{saveWeights:async value=>{writes++;const {expected,...saved}=value;return saved},compare:async()=>{throw Error('读取失败')}})
  try{
    app.state.data.value={weights:{...app.state.draft.value},plans:[]}
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

test('a weight conflict keeps the draft and rebases it on the latest snapshot',async()=>{
  const conflict=Object.assign(new Error('记录已变化'),{code:1003});const writes=[];let attempt=0
  const latest={major:1,jobs:1,salary:1,stability:1,location:4}
  const app=setup('DirectionScoring',{saveWeights:async value=>{writes.push(value);if(++attempt===1)throw conflict;const {expected,...saved}=value;return saved},weights:async()=>latest,compare:async()=>({weights:{major:3,jobs:1,salary:1,stability:1,location:4},plans:[]})})
  try{
    app.state.data.value={weights:{major:1,jobs:1,salary:1,stability:1,location:1},plans:[]}
    app.state.original.value={...app.state.data.value.weights};app.state.draft.value={...app.state.original.value,major:3}
    await app.state.save()
    assert.equal(app.state.draft.value.major,3);assert.equal(app.state.latest.value.location,4)
    await app.state.confirmConflict()
    assert.equal(writes[1].expected.location,4);assert.equal(writes[1].major,3)
  }finally{app.stop()}
})

test('a semester conflict keeps local fields and retries against the latest semester',async()=>{
  const conflict=Object.assign(new Error('记录已变化'),{code:1003});const writes=[];let attempt=0
  const initial={first_monday:'2026-09-07',weeks:20,timezone:'Asia/Shanghai',periods:[{number:1,start:'08:00',end:'08:45'}],weekly_available_minutes:600}
  const latest={...initial,weeks:18}
  const app=setup('ScheduleCapacity',{saveSemester:async value=>{writes.push(value);if(++attempt===1)throw conflict;const {expected,...saved}=value;return saved},semester:async()=>latest,workload:async()=>({configured:true,weeks:[],conflicts:[],missing:[]})},{date:'2026-10-17'})
  try{
    app.state.setupReady.value=true;app.state.original.value=initial;app.state.first.value=initial.first_monday;app.state.weeks.value=22;app.state.periods.value=initial.periods;app.state.capacity.value=600
    await app.state.save();assert.equal(app.state.weeks.value,22);assert.equal(app.state.latest.value.weeks,18)
    await app.state.confirmConflict();assert.equal(writes[1].expected.weeks,18);assert.equal(writes[1].weeks,22)
  }finally{app.stop()}
})

test('a measurement conflict preserves the entered value and retries with latest records',async()=>{
  const conflict=Object.assign(new Error('记录已变化'),{code:1003});const writes=[];let attempt=0
  const original={key:'fit',label:'适配度',value:50,minimum:0,maximum:100,threshold:null,source:'原记录',method:'量表',measured_at:'2026-10-16T00:00:00Z',origin:'self_report'}
  const latest={...original,value:60,source:'另一标签页'}
  const batches={items:[{asset_type:'report',version:1,subject_id:'report',measurements:[latest]}],history:[]}
  const app=setup('MeasurementPanel',{saveMeasurements:async value=>{writes.push(value);if(++attempt===1)throw conflict;return value},measurements:async()=>batches},{assetType:'report',version:1,subjectId:'report',dimensions:[{key:'fit',label:'适配度'}]})
  try{
    app.state.records.value={items:[{asset_type:'report',version:1,subject_id:'report',measurements:[original]}],history:[]};app.state.key.value='fit';await vue.nextTick();app.state.value.value=70;app.state.source.value='本次填写';app.state.method.value='量表';app.state.when.value='2026-10-17T10:00'
    await app.state.save();assert.equal(app.state.value.value,70);assert.equal(app.state.conflictLatest.value.value,60)
    await app.state.confirmConflict();assert.equal(writes[1].expected[0].value,60);assert.equal(writes[1].measurements[0].value,70)
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
    app.state.original.value={proactive_reminders:true}
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

test('review retry keeps request identity and distinguishes saved write from failed refresh',async()=>{
  const writes=[];let attempts=0
  const app=setup('StructuredReview',{saveReview:async(value)=>{writes.push(value);if(++attempts===1)throw Error('响应丢失');return {...value,id:'r',updated_at:'2026-10-17T00:00:00Z'}},reviews:async()=>{throw Error('刷新失败')}},{},{phases:[{id:'p',tasks:[{task_id:'a',text:'任务',due_date:'2026-10-20T10:00:00Z'}]}]})
  try{
    app.state.selectedId.value='a';await vue.nextTick()
    app.state.reason.value='时间不足';app.state.result.value='adjust';app.state.adjustedDate.value=''
    await app.state.save();await app.state.save()
    assert.ok(writes[0].client_request_id)
    assert.equal(writes[0].client_request_id,writes[1].client_request_id)
    assert.equal(writes[1].adjustment.due_date,null)
    assert.equal(writes[1].expected_task.text,'任务')
    assert.equal(app.state.editing.value,'r')
    assert.match(app.state.status.value,/已保存.*暂未刷新/)
    assert.equal(app.state.error.value,'刷新失败')
  }finally{app.stop()}
})

test('successful review apply is not reported as failed when the following plan read fails',async()=>{
  let applied=0
  const app=setup('StructuredReview',{applyReview:async()=>{applied++}})
  try{
    await app.state.apply({id:'r',result:'adjust'})
    assert.equal(applied,1)
    assert.match(app.state.status.value,/已保存.*暂未刷新/)
    assert.equal(app.state.error.value,'')
  }finally{app.stop()}
})
