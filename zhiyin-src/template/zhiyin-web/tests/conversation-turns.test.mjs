import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/conversation-turns.ts', import.meta.url),'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports})
const {replyTurns, withGuide, answerParts} = exports
const badge = {name:'顾问',agent_id:'agent'}
test('live reply joins guidance without a second reply or duplicated text',()=>{
 const result=replyTurns({badge,messages:[{role:'agent',agent_name:'顾问',text:'结论'}],guide:{text:'结论',question:'追问',options:[{option_id:'o',label:'选择',value:0}]}},'r')
 assert.equal(result.length,1);assert.equal(result[0].guideText,undefined);assert.equal(result[0].question,'追问');assert.equal(result[0].optionRefs[0].value,0)
})
test('restored guidance does not attach to an older reply before a user message',()=>{
 const prior=[{id:'1',from:'host',speaker:'顾问',text:'旧结论'},{id:'2',from:'me',text:'新问题'}]
 const result=withGuide(prior,{badge,guide:{text:'新引导'}},'g')
 assert.equal(result.length,3);assert.equal(prior[0].guideText,undefined);assert.equal(result[2].guideText,'新引导')
})
test('distinct speaker is not silently merged; missing cards stay absent',()=>{
 const result=withGuide([{id:'1',from:'host',speaker:'别的顾问',text:'结论'}],{badge,guide:{text:'引导'}},'g')
 assert.equal(result.length,2);assert.equal(result[0].renderables,undefined)
})
test('text hierarchy preserves complete sentences and all source content',()=>{
 const text='这是需要完整保留的第一句话。后面还有详细说明。'
 const parts=answerParts(text);assert.equal(parts.lead,'');assert.equal(parts.body,text)
 const long='没有标点'.repeat(40);assert.equal(answerParts(long).body,long)
})
test('pipeline and asset status stay attached to the latest answer',()=>{
 const result=withGuide([{id:'1',from:'host',speaker:'顾问',text:'结论'}],{badge,guide:{kind:'question'},pipeline_cards:[{stage:'collect',title:'了解情况',status:'done'}],changed_assets:[{asset_id:'a',asset_type:'profile',created_at:'2026-01-01',version:2}]},'g')
 assert.equal(result[0].pipelineCards[0].title,'了解情况')
 assert.equal(result[0].changedAssets[0].version,2)
})
