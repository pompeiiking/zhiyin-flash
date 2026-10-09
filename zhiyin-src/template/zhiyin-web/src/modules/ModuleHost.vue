<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import { useSessionStore } from '@/stores/session'
import ModuleContent from './ModuleContent.vue'
import { moduleData, moduleAction, previewModule, type ModuleView, type ModuleResult, type PreviewMode } from './client'
const props = defineProps<{ module: ModuleView; preview?: boolean; mode?: PreviewMode; fixture?: string }>()
defineEmits<{ close: [] }>()
const session = useSessionStore()
const result = ref<ModuleResult | null>(null)
const error = ref('')
const busy = ref(false)
const detail = ref(false)
const conversation = ref(false)
const skill = computed(() => props.module.manifest.kind === 'tool')
const formattedResult = computed(() => result.value ? JSON.stringify(result.value, null, 2) : '')
const activity = ref<string[]>([])
const inputText = ref('{}')
const input = ref<Record<string, unknown>>({})
function applyInput() {
  try {
    const value: unknown = JSON.parse(inputText.value)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('模块输入必须是 JSON 对象。')
    input.value = value as Record<string, unknown>
    void refresh()
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
}
function log(message: string) { if (props.preview) activity.value = [`${new Date().toLocaleTimeString()} ${message}`, ...activity.value].slice(0, 20) }
let generation = 0
async function refresh() {
  const run = ++generation
  error.value = ''; busy.value = true
  try {
    const data = props.preview ? await previewModule(props.module.manifest.id, props.mode || 'fixture', props.fixture || 'normal', input.value, props.module.manifest.version) : await moduleData(props.module.manifest.id, props.module.manifest.version)
    if (run === generation) { result.value = data; log(`读取成功 · ${props.mode || 'live'} · ${props.fixture || 'normal'}`) }
  } catch (e) { if (run === generation) { error.value = String(e); result.value = null; log(error.value) } }
  finally { if (run === generation) busy.value = false }
}
async function perform(name: string, payload: Record<string, unknown>) {
  if (busy.value || (props.preview && props.mode !== 'live')) return
  const run = ++generation
  busy.value = true; error.value = ''
  try {
    const value = await moduleAction(props.module.manifest.id, name, payload, props.module.manifest.version)
    if (run === generation) { result.value = value; log(`操作成功 · ${name}`); void session.revalidate() }
  } catch (e) { if (run === generation) { error.value = String(e); log(`操作失败 · ${name} · ${error.value}`) } }
  finally { if (run === generation) busy.value = false }
}
watch(() => [props.module.manifest.id, props.module.manifest.version, props.module.policy.revision, props.module.effective_enabled, props.mode, props.fixture, session.dataVersion], refresh, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <Bubble :label="module.manifest.name" :closable="!preview" class="module-host" @close="$emit('close')">
    <header class="module-head"><strong>{{ module.manifest.name }}</strong><button type="button" @click.stop="refresh" :disabled="busy">刷新</button></header>
    <form v-if="preview" class="module-input" @submit.prevent="applyInput"><label>模块输入 JSON<textarea v-model="inputText" aria-label="模块输入 JSON" rows="4" spellcheck="false" /></label><button :disabled="busy" type="submit">运行此输入</button><details><summary>查看输入契约</summary><pre>{{ JSON.stringify(module.manifest.input_schema, null, 2) }}</pre></details></form>
    <p v-if="busy && !result" role="status">正在读取…</p>
    <p v-if="error" role="alert" class="module-error">{{ error }}</p>
    <section v-if="skill && preview" class="skill-preview" aria-label="技能调试">
      <dl><dt>工具名称</dt><dd><code>{{ module.manifest.tool }}</code></dd><dt>输入来源</dt><dd>{{ mode === 'live' ? '平台注入当前测试账号身份，通过授权能力读取业务数据。' : '模板中的模拟数据，按所选场景返回结果。' }}</dd><dt>声明的数据能力</dt><dd>{{ (module.manifest.reads || []).join('、') || '无需读取业务数据' }}</dd><dt>所属应用</dt><dd>{{ module.manifest.parent_id || '无，可独立调用' }}</dd></dl>
      <p>技能供获授权的智能体调用。此处预览技能返回值，不展示首页卡片。</p>
      <h3>返回 JSON</h3><pre v-if="result" aria-label="技能返回 JSON">{{ formattedResult }}</pre><p v-else>{{ busy ? '等待返回结果…' : error ? '执行失败，未返回业务数据。' : '暂无返回结果。' }}</p>
    </section>
    <ModuleContent v-if="result && module.manifest.card && !skill" :module="module" :result="result" readonly />
    <button v-if="result && module.manifest.detail" class="module-open" type="button" @click.stop="conversation = false; detail = true">查看详情 →</button>
    <button v-if="preview && result && !error && module.manifest.conversation" class="module-conversation-open" type="button" @click.stop="detail = false; conversation = true">查看对话结果</button>
    <details v-if="preview"><summary>调试结果与日志</summary><pre v-if="!skill">{{ formattedResult }}</pre><p v-for="(line,index) in activity" :key="index">{{ line }}</p></details>
    <Teleport to="body">
      <div v-if="detail" class="module-backdrop" @click.self="detail = false" @keydown.esc="detail = false">
        <section class="module-dialog module-detail-dialog" role="dialog" aria-modal="true" :aria-label="module.manifest.name" tabindex="-1">
          <header class="module-head"><h2>{{ module.manifest.name }}</h2><button type="button" @click="detail = false">关闭</button></header>
          <p v-if="error" role="alert">{{ error }}</p>
          <p v-if="preview && mode !== 'live'">模拟预览，操作不会写入数据。</p>
          <ModuleContent v-if="result" :module="module" :result="result" slot-name="detail" :readonly="preview && mode !== 'live'" :busy="busy" @action="perform" />
        </section>
      </div>
      <div v-if="conversation && preview && result && !error && module.manifest.conversation" class="module-backdrop" @click.self="conversation = false" @keydown.esc="conversation = false">
        <section class="module-dialog module-conversation-dialog" role="dialog" aria-modal="true" :aria-label="`${module.manifest.name} · 对话结果`" tabindex="-1">
          <header class="module-head"><h2>{{ module.manifest.name }} · 对话结果</h2><button type="button" @click="conversation = false">关闭</button></header>
          <ModuleContent :key="`${module.manifest.id}:conversation:${module.manifest.conversation}`" :module="module" :result="result" slot-name="conversation" readonly />
        </section>
      </div>
    </Teleport>
  </Bubble>
</template>
<style scoped>
.module-input { display:grid; gap:8px; margin-top:12px; font-size:13px; }.module-input label { display:grid; gap:6px; }.module-input textarea { width:100%; min-width:0; box-sizing:border-box; padding:9px; border:1px solid #c9d5cc; border-radius:7px; background:#fff; font-family:monospace; }.module-input button { justify-self:start; padding:7px 12px; border:1px solid #c9d5cc; border-radius:7px; }
.skill-preview { margin-top:18px; font-size:13px; }.skill-preview dl { display:grid; grid-template-columns:100px minmax(0,1fr); gap:10px; }.skill-preview dt { color:#69786d; }.skill-preview dd { margin:0; overflow-wrap:anywhere; }.skill-preview h3 { font-size:15px; }.skill-preview pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:400px; overflow:auto; background:#eef2e9; border-radius:8px; padding:12px; } details pre { white-space:pre-wrap; overflow-wrap:anywhere; }
.module-host { overflow:auto; }.module-head { display:flex; justify-content:space-between; align-items:center; gap:12px; }.module-head button,.module-open,.module-conversation-open { border:1px solid #c9d5cc; border-radius:7px; padding:6px 10px; font-size:12px; }.module-open,.module-conversation-open { margin-top:16px; color:#007a52; }.module-error { color:#a33822; font-size:13px; }.module-backdrop { position:fixed; inset:0; background:#16291f66; display:grid; place-items:center; z-index:1000; padding:20px; }.module-dialog { background:#fcf9f5; padding:26px; border-radius:18px; width:min(640px,100%); max-height:85vh; overflow:auto; }.module-dialog h2 { font-size:22px; }
</style>
