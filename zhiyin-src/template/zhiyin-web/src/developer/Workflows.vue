<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ModuleView } from '@/modules/client'
import { parseObject, pretty, publishWorkflow, runWorkflow, saveWorkflow, statusLabel, unpublishWorkflow, workflowRuns, workflows, type Workflow, type WorkflowNode, type WorkflowRun } from './client'
const props = defineProps<{ modules: ModuleView[]; administrator: boolean }>()
interface NodeEditor { id: string; module_id: string; module_version: string; operation: 'read' | 'action'; action: string; inputText: string; bindings: { field: string; source: string }[] }
const rows = ref<Workflow[]>([])
const selected = ref<Workflow>()
const form = reactive({ id: '', name: '', schema: '{\n  "type": "object",\n  "properties": {}\n}', nodes: [] as NodeEditor[] })
const runInput = ref('{}')
const mode = ref<'fixture' | 'live'>('fixture')
const confirmActions = ref(false)
const runs = ref<WorkflowRun[]>([])
const result = ref<WorkflowRun>()
const error = ref('')
const message = ref('')
const busy = ref(false)
const hasActions = computed(() => (selected.value?.definition.nodes || []).some(node => node.operation === 'action'))
const dirty = ref(false)
let requestKey = ''
let requestId = ''
function moduleOf(id: string) { return props.modules.find(item => item.manifest.id === id) }
async function perform(action: () => Promise<unknown>, success = '') { if (busy.value) return; busy.value = true; error.value = ''; message.value = ''; try { await action(); message.value = success } catch (e) { error.value = e instanceof Error ? e.message : String(e) } finally { busy.value = false } }
async function refresh() { rows.value = await workflows() }
function edit(workflow?: Workflow) {
  selected.value = workflow; result.value = undefined; runs.value = []; dirty.value = false
  form.id = workflow?.id || ''; form.name = workflow?.name || ''; form.schema = pretty(workflow?.definition.input_schema || { type: 'object', properties: {} })
  form.nodes = (workflow?.definition.nodes || []).map(node => ({ id: node.id, module_id: node.module_id, module_version: node.module_version || '', operation: node.operation || 'read', action: node.action || '', inputText: pretty(node.input || {}), bindings: Object.entries(node.bindings || {}).map(([field, source]) => ({ field, source })) }))
  if (workflow) void perform(async () => { runs.value = await workflowRuns(workflow.id) })
}
function addNode() { const module = props.modules[0]; form.nodes.push({ id: `step_${form.nodes.length + 1}`, module_id: module?.manifest.id || '', module_version: module?.manifest.version || '', operation: 'read', action: '', inputText: '{}', bindings: [] }); dirty.value = true }
function selectModule(node: NodeEditor) { const module = moduleOf(node.module_id); node.module_version = module?.manifest.version || ''; node.action = ''; node.operation = 'read'; dirty.value = true }
function useInstalledVersion(node: NodeEditor) {
  const version = moduleOf(node.module_id)?.manifest.version
  if (busy.value || !version || node.module_version === version) return
  node.module_version = version
  dirty.value = true
}
function buildNodes(): WorkflowNode[] {
  return form.nodes.map(node => {
    const bindings: Record<string, string> = {}
    for (const binding of node.bindings) {
      if (!binding.field.trim() || !binding.source.trim()) throw new Error(`节点 ${node.id} 的输入字段和数据来源都不能为空。`)
      if (binding.field in bindings) throw new Error(`节点 ${node.id} 重复映射字段 ${binding.field}。`)
      bindings[binding.field] = binding.source
    }
    return { id: node.id, module_id: node.module_id, module_version: node.module_version || undefined, operation: node.operation, ...(node.operation === 'action' ? { action: node.action } : {}), input: parseObject(node.inputText, `节点 ${node.id} 的固定输入`), bindings }
  })
}
async function save() { await perform(async () => { const value = await saveWorkflow({ id: form.id, name: form.name, expected_revision: selected.value?.revision || 0, input_schema: parseObject(form.schema, '工作流输入契约'), nodes: buildNodes() }); selected.value = value; dirty.value = false; await refresh() }, '编排已通过结构检查并保存。可先运行模拟数据验证结果。') }
async function publish() { if (!selected.value) return; await perform(async () => { selected.value = await publishWorkflow(selected.value!.id, selected.value!.revision); await refresh() }, '该编排版本已发布。用户调用将使用已发布快照。') }
async function unpublish() { if (!selected.value || selected.value.published_revision == null) return; await perform(async () => { selected.value = await unpublishWorkflow(selected.value!.id, selected.value!.revision); await refresh() }, '已暂停发布，普通用户暂不能运行此编排。草稿和历史记录已保留；升级模块后，请选择新模块版本、保存并重新发布。') }
async function execute() {
  if (!selected.value) return
  await perform(async () => {
    const input = parseObject(runInput.value, '运行输入')
    const key = JSON.stringify([selected.value!.id, selected.value!.revision, input, mode.value, confirmActions.value])
    if (requestKey !== key || !requestId) { requestKey = key; requestId = crypto.randomUUID() }
    result.value = await runWorkflow(selected.value!.id, { input, mode: mode.value, confirm_actions: mode.value === 'live' && confirmActions.value, request_id: requestId, expected_revision: selected.value!.revision })
    requestId = ''
    runs.value = await workflowRuns(selected.value!.id)
  })
}
onMounted(() => { void perform(refresh) })
</script>
<template>
  <section><div class="dev-actions"><h2>数据编排</h2><button :disabled="busy" @click="edit()">新建编排</button><button :disabled="busy" @click="perform(refresh)">刷新列表</button></div><p>连接平台输入与模块结果，按依赖顺序执行。每次运行记录节点输入、真实输出和失败位置；版本不匹配会阻止执行。</p>
    <p v-if="error" class="dev-alert" role="alert">{{ error }}</p><p v-if="message" class="dev-status" role="status">{{ message }}</p>
    <div class="dev-columns"><aside class="project-nav" aria-label="工作流列表"><button v-for="workflow in rows" :key="workflow.id" :disabled="busy" :class="{ active: selected?.id === workflow.id }" @click="edit(workflow)"><strong>{{ workflow.name }}</strong><small>修订 {{ workflow.revision }} · {{ workflow.published_revision != null ? `已发布 ${workflow.published_revision}` : '未发布' }}</small></button><p v-if="!rows.length">先添加节点，创建第一条编排。</p></aside><div>
      <form class="dev-panel dev-form" @submit.prevent="save" @input="dirty = true"><h3>{{ selected ? '编辑编排' : '新建编排' }}</h3><div class="fields"><label>编排编号<input v-model="form.id" :readonly="Boolean(selected)" required pattern="[a-z][a-z0-9_]{1,47}" placeholder="例如 weekly_review" /></label><label>编排名称<input v-model="form.name" required maxlength="80" /></label></div>
        <details><summary>外部输入契约（JSON Schema）</summary><label>输入契约<textarea v-model="form.schema" spellcheck="false" rows="6" /></label></details>
        <article v-for="(node, index) in form.nodes" :key="index" class="workflow-node"><div class="dev-actions"><h4>节点 {{ index + 1 }}</h4><button type="button" @click="form.nodes.splice(index, 1); dirty = true">移除节点</button></div><div class="fields"><label>节点编号<input v-model="node.id" required pattern="[a-z][a-z0-9_]{0,47}" /></label><label>调用模块<select v-model="node.module_id" required @change="selectModule(node)"><option value="" disabled>请选择模块</option><option v-for="module in modules" :key="module.manifest.id" :value="module.manifest.id">{{ module.manifest.name }}{{ module.effective_enabled ? '' : '（未启用）' }}</option></select></label><div class="dev-form"><label>锁定模块版本<input v-model="node.module_version" required pattern="\d+\.\d+\.\d+" /></label><small class="muted">当前安装版本：{{ moduleOf(node.module_id)?.manifest.version || '未安装' }}</small><button v-if="moduleOf(node.module_id) && node.module_version !== moduleOf(node.module_id)?.manifest.version" type="button" :disabled="busy" @click="useInstalledVersion(node)">使用当前安装版本</button></div><label>节点操作<select v-model="node.operation"><option value="read">读取 / 技能执行</option><option v-if="moduleOf(node.module_id)?.manifest.actions?.length" value="action">执行已登记业务操作</option></select></label></div>
          <label v-if="node.operation === 'action'">业务操作<select v-model="node.action" required><option value="" disabled>请选择操作</option><option v-for="action in moduleOf(node.module_id)?.manifest.actions" :key="action" :value="action">{{ action }}</option></select></label>
          <label>固定输入 JSON<textarea v-model="node.inputText" spellcheck="false" rows="3" /></label><strong>从其他数据绑定输入</strong><p class="muted">来源写法：<code>$input/task_id</code> 读取本次运行输入；<code>step_1/data/total</code> 读取另一节点的结果。路径按 JSON Pointer 解析。</p>
          <div v-for="(binding, bindingIndex) in node.bindings" :key="bindingIndex" class="binding-row"><input v-model="binding.field" aria-label="目标输入字段" placeholder="目标字段，例如 total" required /><input v-model="binding.source" aria-label="来源路径" placeholder="step_1/data/total" required /><button type="button" @click="node.bindings.splice(bindingIndex, 1); dirty = true">删除映射</button></div><button type="button" @click="node.bindings.push({ field: '', source: '' }); dirty = true">添加输入映射</button>
        </article>
        <div class="dev-actions"><button type="button" @click="addNode">添加调用节点</button><button class="primary" :disabled="busy || !form.nodes.length">检查并保存编排</button><button v-if="selected" type="button" :disabled="busy || dirty" @click="publish">发布当前修订</button><button v-if="selected?.published_revision != null" type="button" :disabled="busy" @click="unpublish">暂停发布</button></div>
        <p v-if="selected?.published_revision != null" class="muted">普通用户当前使用已发布的修订 {{ selected.published_revision }}。保存草稿不会暂停或替换此快照；暂停发布后普通用户暂不能运行，草稿和历史记录保留。</p><p v-else-if="selected" class="muted">当前未发布，普通用户暂不能运行。可继续编辑和调试草稿；历史记录保留。</p>
        <p class="muted">允许一个末端业务操作节点。先完成读取和结果校验，再执行写入；模拟运行不会写业务数据。编排负责人和管理员可发布或暂停发布。升级被已发布编排锁定的模块前，先暂停相关编排；升级后选择新模块版本、保存并重新发布。</p>
      </form>
      <form v-if="selected" class="dev-panel dev-form" @submit.prevent="execute"><h3>运行修订 {{ selected.revision }}</h3><p v-if="dirty" class="dev-alert">有尚未保存的修改，请先保存再运行。</p><label>运行输入 JSON<textarea v-model="runInput" spellcheck="false" rows="4" /></label><label>运行模式<select v-model="mode" @change="confirmActions = false"><option value="fixture">模拟数据</option><option value="live">当前账号的真实测试数据</option></select></label><label v-if="mode === 'live' && hasActions" class="check-label"><input v-model="confirmActions" type="checkbox" />确认通过已登记操作修改当前测试账号的数据</label><button class="primary" :disabled="busy || dirty || (mode === 'live' && hasActions && !confirmActions)">{{ busy ? '正在运行…' : '运行并检查数据流' }}</button></form>
      <section v-if="result" class="dev-panel" aria-label="编排运行结果"><h3>{{ statusLabel[result.status] || result.status }} · 修订 {{ result.revision }}</h3><p>运行 {{ result.id }} · {{ result.mode === 'fixture' ? '模拟数据' : '真实测试数据' }} · {{ result.action_committed ? '业务操作已提交' : '没有提交业务操作' }}</p><p v-if="result.error" class="dev-alert" role="alert">{{ result.error }}</p><ol class="dev-log"><li v-for="(node, index) in result.trace" :key="index"><strong>{{ node.node_id }} · {{ node.module_id }} · {{ statusLabel[node.status] || node.status }}</strong><p v-if="node.error" class="dev-alert">{{ node.error }}</p><details><summary>查看输入与输出</summary><pre>{{ pretty(node) }}</pre></details></li></ol><details open><summary>最终输出</summary><pre>{{ pretty(result.outputs) }}</pre></details></section>
      <section v-if="selected" class="dev-panel"><h3>运行记录</h3><div v-for="run in runs" :key="run.id" class="dev-actions"><code>{{ run.id }}</code><span class="dev-chip" :class="run.status">{{ statusLabel[run.status] || run.status }}</span><small>修订 {{ run.revision }} · {{ run.mode }}</small><button @click="result = run">查看运行链路</button></div><p v-if="!runs.length">暂无运行记录。</p></section>
    </div></div>
  </section>
</template>
