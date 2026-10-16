import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function load(name) {
  const source=readFileSync(new URL(`../src/lib/${name}.ts`,import.meta.url),'utf8')
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const exports={}
  vm.runInNewContext(code,{exports})
  return exports
}
const {profilePriority,exactProfileKeys}=load('profile-organization')
const {agentKeyOf,consultantLabel}=load('consultant')

test('school import order cannot push career facts behind academic metadata',()=>{
  const fields=['school','degree_level','courses','interest','skills','experience','values','duration']
  assert.deepEqual(fields.sort((a,b)=>profilePriority(a)-profilePriority(b)).slice(0,4),['interest','skills','experience','values'])
  assert.ok(profilePriority('new_backend_field')<profilePriority('duration'))
})

test('report-level and direction-set associations do not become per-conclusion evidence',()=>{
  const edges=[{to_asset:'report',via_profile_keys:['school','major']},{to_asset:'direction_plan',via_profile_keys:['skills']},{to_asset:'analysis.1',via_profile_keys:['experience','experience']}]
  assert.deepEqual([...exactProfileKeys(edges,'analysis.2')],[])
  assert.deepEqual([...exactProfileKeys(edges,'plan-1')],[])
  assert.deepEqual([...exactProfileKeys(edges,'analysis.1')],['experience'])
})

test('every registered backend speaker keeps its own avatar and display identity',()=>{
  const registry=JSON.parse(readFileSync(new URL('../../data/registry/agents.json',import.meta.url),'utf8'))
  const agents=Array.isArray(registry)?registry:registry.items
  assert.ok(agents?.length)
  for(const agent of agents){
    assert.equal(agentKeyOf(agent.name),agent.id)
    assert.equal(agentKeyOf(agent.id),agent.id)
    assert.equal(agentKeyOf(consultantLabel(agent.name)),agent.id)
  }
})
