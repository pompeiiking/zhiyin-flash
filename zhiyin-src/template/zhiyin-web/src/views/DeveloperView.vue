<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import { jsonRequest, type DeveloperContext, type ModuleView, type ReleaseJob } from '@/modules/client'
import ModuleHost from '@/modules/ModuleHost.vue'
import GettingStarted from '@/developer/GettingStarted.vue'
import ProjectsVersions from '@/developer/ProjectsVersions.vue'
import Workflows from '@/developer/Workflows.vue'
import { platformStatus, type PlatformStatus } from '@/developer/client'
import '@/developer/developer.css'

const context = ref<DeveloperContext>()
const isWorkbench = computed(() => context.value?.environment === 'workbench')
const navigation = computed(() => [
  ...(isWorkbench.value ? [{ id: 'start', label: '开始开发' }, { id: 'projects', label: '项目与版本' }] : []),
  { id: 'modules', label: '模块列表' }, { id: 'workflows', label: '数据编排' },
  { id: 'checks', label: '接入检查' }, { id: 'preview', label: '调试预览' },
  ...(isWorkbench.value ? [{ id: 'releases', label: '发布记录' }] : []),
])
const workbenchUrl = new URL('/developer', window.location.href)
workbenchUrl.port = '5174'
const modules = ref<ModuleView[]>([])
const checks = ref<Record<string, any>[]>([])
const jobs = ref<ReleaseJob[]>([])
const tab = ref(sessionStorage.getItem('zhiyin_developer_tab') || 'start')
watch(tab, value => sessionStorage.setItem('zhiyin_developer_tab', value))
const platform = ref<PlatformStatus>()
const platformError = ref('')
const selectedId = ref('')
const selected = computed(() => modules.value.find(m => m.manifest.id === selectedId.value))
type ModuleKind = NonNullable<ModuleView['manifest']['kind']>
const category = ref<'all' | ModuleKind>('all')
const categoryLabels: Record<ModuleKind, string> = { application: '应用模块', tool: '技能组件', hybrid: '应用与技能' }
function moduleKind(module: ModuleView): ModuleKind { return module.manifest.kind || 'application' }
const moduleNames = computed(() => new Map(modules.value.map(module => [module.manifest.id, module.manifest.name])))
const moduleRows = computed(() => {
  const rows: { module: ModuleView; depth: number; path: string[] }[] = []
  const visited = new Set<string>()
  const append = (module: ModuleView, path: string[]) => {
    if (visited.has(module.manifest.id)) return
    visited.add(module.manifest.id)
    rows.push({ module, depth: path.length, path })
    for (const child of modules.value.filter(item => item.manifest.parent_id === module.manifest.id)) append(child, [...path, module.manifest.name])
  }
  for (const module of modules.value.filter(item => !item.manifest.parent_id || !moduleNames.value.has(item.manifest.parent_id))) append(module, [])
  for (const module of modules.value) append(module, [])
  return rows.filter(row => category.value === 'all' || moduleKind(row.module) === category.value)
})
function enabledLabel(module: ModuleView) {
  if (module.effective_enabled) return '已启用'
  return module.policy.enabled ? '因所属模块停用而不可用' : '未启用'
}
const mode = ref<'fixture' | 'live'>('fixture')
const fixture = ref('normal')
const commit = ref('')
const kind = ref<'deploy' | 'rollback' | 'check'>('deploy')
const error = ref('')
const message = ref('')
const busy = ref(false)
const administrator = computed(() => context.value?.role === 'admin')
async function refreshPlatform() { if (!isWorkbench.value) return; try { const value = await platformStatus(); if (alive) { platform.value = value; platformError.value = '' } } catch (e) { if (alive) platformError.value = String(e) } }
let alive = true
let poll: ReturnType<typeof setInterval>
const stateLabel: Record<string, string> = { requested:'待管理员确认', queued:'等待执行器', running:'执行中', succeeded:'成功', failed:'失败', rolled_back:'失败，已恢复原版本' }
async function load() {
  const ctx = await api<DeveloperContext>('/developer/context')
  if (!alive) return
  context.value = ctx
  if (!navigation.value.some(item => item.id === tab.value)) tab.value = isWorkbench.value ? 'start' : 'modules'
  const [ms, cs, js] = await Promise.all([api<ModuleView[]>('/developer/modules'), api<Record<string, any>[]>('/developer/checks'), isWorkbench.value ? api<ReleaseJob[]>('/developer/releases') : Promise.resolve<ReleaseJob[]>([])])
  if (!alive) return
  modules.value = ms; checks.value = cs; jobs.value = js
  if (!selectedId.value && ms.length) selectedId.value = ms[0].manifest.id
  await refreshPlatform()
}
async function run(action: () => Promise<unknown>, success: string) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await action(); await load(); message.value = success }
  catch (e) { error.value = String(e) }
  finally { busy.value = false }
}
function check() { void run(() => api('/developer/checks', { method:'POST' }), '已完成当前源码的模块检查。完整测试可在发布页提交检查任务。') }
function save(module: ModuleView) { void run(() => api(`/developer/modules/${module.manifest.id}/policy`, jsonRequest('PUT', module.policy)), '权限配置已保存。') }
function release() {
  const key = `module-release:${commit.value.trim()}:${kind.value}`
  const requestId = sessionStorage.getItem(key) || crypto.randomUUID()
  sessionStorage.setItem(key, requestId)
  void run(() => api('/developer/releases', jsonRequest('POST', { commit:commit.value.trim(), kind:kind.value, request_id:requestId })), '任务已创建，管理员确认后由执行器处理。')
}
function approve(job: ReleaseJob) { void run(() => api(`/developer/releases/${job.id}/approve`, { method:'POST' }), '任务已加入执行队列。') }
onMounted(() => {
  void run(load, '')
  poll = setInterval(async () => {
    if (!isWorkbench.value || busy.value) return
    try { const value = await api<ReleaseJob[]>('/developer/releases'); if (alive) jobs.value = value; await refreshPlatform() }
    catch (e) { if (alive) error.value = String(e) }
  }, 5000)
})
onBeforeUnmount(() => { alive = false; clearInterval(poll) })
</script>
<template>
  <main class="developer">
    <header class="dev-header"><div><RouterLink to="/">← 职引</RouterLink><h1>{{ !context || isWorkbench ? '模块开发工作台' : context.environment === 'staging' ? '测试环境模块管理' : '模块管理' }}</h1><p>{{ !context || isWorkbench ? '开发组件、验证完整数据流，将通过验收的版本部署到职引。' : '管理当前环境已安装模块的启停与授权，编排数据流并调试真实组件。' }}</p></div>
      <div v-if="context" class="identity">{{ context.user_id }} · {{ administrator ? '管理员' : '开发者' }}<small>{{ context.environment }}</small></div>
    </header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="message" class="notice success" role="status">{{ message }}</p>
    <p v-if="!context && !error">正在核对开发权限…</p>
    <template v-if="context">
      <section v-if="isWorkbench" class="dev-summary"><span><small>工作台构建</small><code>{{ context.revision }}</code></span><span><small>测试环境实际运行版本</small><code>{{ platform?.environment.revision || '尚未确认运行版本' }}</code><a v-if="platform?.environment.url" :href="platform.environment.url" target="_blank" rel="noopener"> 打开环境 ↗</a></span><span><small>自动验收执行器</small>{{ platform ? platform.worker.healthy ? '在线' : '离线或尚无心跳' : '正在读取' }}<small v-if="platform">待处理 {{ platform.pending_versions }} 个版本 · 最近心跳 {{ platform.worker.last_seen || '无' }}</small></span></section>
      <section v-else class="dev-summary"><span><small>当前环境构建</small><code>{{ context.revision }}</code></span><span>新安装模块默认停用，由管理员在「模块列表」独立授权并启用。<small>配置仅影响当前环境；上传版本与维护发布请前往工作台。</small><a :href="workbenchUrl.href" target="_blank" rel="noopener">前往开发工作台上传与发布 ↗</a></span></section>
      <p v-if="isWorkbench && platformError" class="notice error" role="alert">无法确认平台运行状态：{{ platformError }}</p>
      <nav aria-label="开发工作台"><button v-for="item in navigation" :key="item.id" :class="{active:tab===item.id}" @click="tab=item.id">{{ item.label }}</button></nav>
      <GettingStarted v-if="isWorkbench && tab==='start'" :account="context.user_id" @projects="tab='projects'" />
      <ProjectsVersions v-if="isWorkbench && tab==='projects'" :administrator="administrator" :account="context.user_id" :platform="platform" @changed="refreshPlatform" @releases="tab='releases'" />
      <Workflows v-if="tab==='workflows'" :modules="modules" :administrator="administrator" />
      <section v-if="tab==='modules'">
        <div class="module-filters"><label>模块分类<select aria-label="模块分类" v-model="category"><option value="all">全部类型</option><option v-for="(label, value) in categoryLabels" :key="value" :value="value">{{ label }}</option></select></label><p>共 {{ moduleRows.length }} 个模块。应用提供完整功能，技能供智能体调用；所属应用停用后，其下组件同步不可用。</p></div>
        <div class="module-grid">
        <article v-for="{ module, depth, path } in moduleRows" :key="module.manifest.id" class="dev-card" :class="{ 'child-module': depth > 0 }" :style="{ '--module-depth': Math.min(depth, 3) }">
          <div class="module-meta"><span class="badge category-badge">{{ categoryLabels[moduleKind(module)] }}</span><small>{{ path.length ? `归属：${path.join(' / ')}` : '平台直属模块' }}</small></div>
          <div class="row"><h2>{{ module.manifest.name }}</h2><span class="badge" :class="{ blocked: module.policy.enabled && !module.effective_enabled }">{{ enabledLabel(module) }}</span></div>
          <p>{{ module.manifest.description }}</p><small>{{ module.manifest.owner }} · v{{ module.manifest.version }} · {{ module.manifest.id }}</small>
          <p v-if="(module.blocked_by || []).length" class="blocked-reason">不可用原因：{{ (module.blocked_by || []).map(id => moduleNames.get(id) || id).join('、') }} 未启用。</p>
          <fieldset :disabled="!administrator || busy"><legend>平台授权</legend>
            <p class="permission-help">每个模块独立授权，所属应用的权限不会自动授予此模块。</p>
            <label><input type="checkbox" v-model="module.policy.enabled" />启用模块</label>
            <label v-for="read in module.manifest.reads" :key="read"><input type="checkbox" v-model="module.policy.reads" :value="read" />读取 {{ read }}</label>
            <label v-for="action in module.manifest.actions" :key="action"><input type="checkbox" v-model="module.policy.actions" :value="action" />操作 {{ action }}</label>
            <template v-if="module.manifest.tool"><p>允许使用工具的智能体</p><label v-for="agent in context.agents" :key="agent.id"><input type="checkbox" v-model="module.policy.agents" :value="agent.id" />{{ agent.name }}</label></template>
          </fieldset>
          <div class="row"><button @click="selectedId=module.manifest.id; tab='preview'">{{ module.manifest.kind === 'tool' ? '调试技能' : '预览模块' }}</button><button v-if="administrator" class="primary" :disabled="busy" @click="save(module)">保存配置</button></div>
        </article>
        </div><p v-if="!moduleRows.length">此分类下还没有模块。</p>
      </section>
      <section v-if="tab==='checks'">
        <div class="row"><div><h2>当前构建的接入检查</h2><p>检查声明、依赖边界、示例数据和输出格式；完整测试在发布前执行。</p></div><button class="primary" :disabled="busy" @click="check">运行检查</button></div>
        <article v-for="item in checks" :key="item.id" class="dev-card check"><div class="row"><strong>{{ item.passed ? '检查通过' : '需要修改' }}</strong><small>{{ item.created_at }} · {{ item.actor }}</small></div><p>构建 {{ item.source_revision }}</p><ul><li v-for="problem in item.errors" :key="problem.module+problem.message">{{ problem.module }} / {{ problem.file }}：{{ problem.message }}</li></ul></article>
        <p v-if="!checks.length">还没有检查记录。</p>
      </section>
      <section v-if="tab==='preview'">
        <div class="preview-controls"><label>模块<select aria-label="模块" v-model="selectedId"><option v-for="module in modules" :key="module.manifest.id" :value="module.manifest.id">{{ module.manifest.name }} · {{ categoryLabels[moduleKind(module)] }}</option></select></label>
          <label>数据模式<select aria-label="数据模式" v-model="mode"><option value="fixture">模拟数据</option><option v-if="context.live_preview" value="live">当前测试账号的真实数据</option></select></label>
          <label v-if="mode==='fixture'">场景<select aria-label="场景" v-model="fixture"><option value="normal">正常</option><option value="empty">无数据</option><option value="error">读取失败</option></select></label></div>
        <p v-if="selected?.manifest.kind === 'tool'">技能由平台提供当前账号身份和获授权的数据，调试结果以 JSON 展示。{{ mode === 'fixture' ? '当前使用模拟数据，不写入业务数据。' : '当前读取独立测试数据库；与正式调用使用相同的权限检查。' }}</p>
        <p v-else>{{ mode==='fixture' ? '模拟预览不写入业务数据。点击卡片详情检查完整界面。' : '当前账号位于独立测试数据库，详情中的操作会真实更新该账号的数据。' }}</p>
        <div class="preview-area"><ModuleHost v-if="selected" :key="selected.manifest.id" :module="selected" preview :mode="mode" :fixture="fixture" /></div>
      </section>
      <section v-if="isWorkbench && tab==='releases'">
        <p>模块版本通过验收后可从「项目与版本」发布。这里保留整应用提交的维护发布与回退；候选实例健康检查通过后才切换入口。</p>
        <form class="dev-card release-form" @submit.prevent="release"><h2>提交检查或发布任务</h2><p>填写已提交的完整 Git SHA。本地未提交修改不会进入发布。</p>
          <label>提交版本<input v-model="commit" required pattern="[a-f0-9]{40}" minlength="40" maxlength="40" placeholder="40 位 Git 提交号" /></label>
          <label>操作<select v-model="kind"><option value="deploy">构建并部署测试环境</option><option value="check">仅运行完整检查</option><option value="rollback">恢复已成功部署的版本</option></select></label>
          <button class="primary" :disabled="busy || context.environment!=='workbench'">创建任务</button>
          <p v-if="context.environment!=='workbench'">请在开发工作台提交发布任务。</p>
        </form>
        <article v-for="job in jobs" :key="job.id" class="dev-card job"><div class="row"><strong>{{ stateLabel[job.status] || job.status }} · {{ job.stage }}</strong><button v-if="administrator && job.status==='requested'" :disabled="busy" @click="approve(job)">确认执行</button></div>
          <p><code>{{ job.commit }}</code></p><small>{{ job.kind }} · {{ job.actor }} · {{ job.created_at }}</small>
          <p v-if="job.result?.url"><a :href="String(job.result.url)" target="_blank" rel="noopener">打开测试环境 ↗</a></p>
          <details><summary>执行日志（{{ job.events?.length || 0 }}）</summary><pre v-for="(event,index) in job.events" :key="index">{{ event.stage }} {{ event.message }}</pre></details>
        </article>
        <p v-if="!jobs.length">还没有发布任务。</p>
      </section>
    </template>
  </main>
</template>
<style scoped>
.module-filters { display:flex; align-items:end; gap:24px; margin-bottom:20px; }.module-filters p { color:#69786d; font-size:13px; margin:0; max-width:620px; }.module-meta { display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px; }.category-badge { color:#176647; }.module-grid .dev-card { margin-inline-start:calc(var(--module-depth, 0) * 24px); }.module-grid .child-module { border-inline-start:3px solid #b2c8b5; }.blocked { background:#fff0dc; color:#87551c; }.blocked-reason { color:#87551c; font-size:13px; }.permission-help { color:#69786d; font-size:12px; margin-top:0; }
.developer { max-width:1280px; margin:0 auto; padding:44px 36px 100px; color:#25362c; }.dev-header { display:flex; align-items:start; justify-content:space-between; gap:24px; }.dev-header h1 { font-size:34px; margin:16px 0 8px; }.dev-header p { color:#69786d; }.identity { padding:12px 18px; border:1px solid #d7dfd6; border-radius:12px; }.identity small { display:block; margin-top:6px; color:#69786d; }.dev-summary { display:flex; flex-wrap:wrap; gap:24px; background:#edf2e8; padding:20px; border-radius:14px; margin:28px 0; }.dev-summary span { min-width:220px; }.dev-summary small { display:block; margin-bottom:6px; } code { font-size:12px; word-break:break-all; } nav { display:flex; gap:8px; border-bottom:1px solid #d7dfd6; padding-bottom:14px; margin-bottom:28px; } button { border:1px solid #ccd7cc; border-radius:8px; padding:9px 16px; cursor:pointer; background:#fffdf8; } button.active,button.primary { background:#176647; color:white; border-color:#176647; } button:disabled { opacity:.5; cursor:wait; }.module-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:22px; }.dev-card { border:1px solid #d7dfd6; border-radius:16px; padding:24px; background:#fffdf8; }.row { display:flex; justify-content:space-between; align-items:center; gap:16px; }.row h2 { font-size:21px; margin:0; }.badge { font-size:12px; padding:5px 8px; background:#eef3e9; border-radius:6px; white-space:nowrap; } p { line-height:1.7; } small { color:#69786d; } fieldset { margin:24px 0; padding:16px; border:1px solid #e0e4db; border-radius:10px; } fieldset label { display:flex; gap:8px; margin:10px 0; font-size:13px; } input[type=checkbox] { accent-color:#176647; width:16px; height:16px; } .notice { padding:14px 18px; border-radius:10px; overflow-wrap:anywhere; }.error { background:#fae9e1; color:#8f321c; }.success { background:#e7f2e4; }.check,.job { margin-top:18px; }.preview-controls { display:flex; gap:18px; flex-wrap:wrap; } label>select,label>input:not([type=checkbox]) { display:block; margin-top:8px; border:1px solid #cbd5c9; background:white; border-radius:8px; padding:10px; min-width:180px; } .preview-area { max-width:560px; margin-top:24px; }.preview-area :deep(.bubble) { position:relative; min-height:280px; }.release-form { display:grid; gap:12px; }.release-form input { width:100%; }.release-form button { justify-self:start; } pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:280px; overflow:auto; background:#f2f4ee; padding:10px; font-size:12px; } details { margin-top:16px; } a { color:#176647; } @media(max-width:760px) { .developer { padding:24px 16px 70px; }.dev-header h1 { font-size:25px; }.module-grid { grid-template-columns:1fr; }nav { overflow:auto; }nav button { white-space:nowrap; }.dev-card { padding:18px; }.dev-summary { gap:14px; }.identity { font-size:12px; } }
.module-grid { grid-template-columns:minmax(0,1fr); } @media(max-width:760px) { .module-filters { align-items:start; flex-direction:column; gap:12px; }.module-grid .dev-card { margin-inline-start:calc(var(--module-depth, 0) * 12px); }.module-grid .row { flex-wrap:wrap; } }
</style>
