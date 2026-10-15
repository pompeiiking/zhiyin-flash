<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { ReleaseJob } from '@/modules/client'
import { createProject, downloadVersion, getVersion, pretty, projects, releaseVersion, retryVersion, saveProject, statusLabel, uploadVersion, versions, type PlatformStatus, type Project, type Version } from './client'
const props = defineProps<{ administrator: boolean; account: string; platform?: PlatformStatus }>()
const emit = defineEmits<{ changed: []; releases: [] }>()
const items = ref<Project[]>([])
const selectedId = ref('')
const selected = computed(() => items.value.find(item => item.id === selectedId.value))
const rows = ref<Version[]>([])
const releaseJobs = ref<ReleaseJob[]>([])
const releaseById = computed(() => new Map(releaseJobs.value.map(job => [job.id, job])))
const releaseLabels: Record<string, string> = { requested: '待管理员确认', queued: '等待发布', running: '正在发布', succeeded: '发布成功', failed: '发布失败', rolled_back: '发布失败，已恢复旧版本' }
const version = ref<Version>()
const showCreate = ref(false)
const create = reactive({ id: '', name: '', description: '' })
const settings = reactive({ name: '', description: '', members: '', trusted: false, auto_deploy: false, revision: 0 })
const channel = ref('main')
const channelVersions = computed(() => rows.value.filter(item => item.channel === channel.value).sort((a, b) => b.created_at.localeCompare(a.created_at)))
const baseVersionId = ref<string | null>(null)
const baseCommit = ref('')
const file = ref<File>()
const fileInput = ref<HTMLInputElement>()
const busy = ref(false)
const error = ref('')
const message = ref('')
const channels = computed(() => [...new Set(['main', ...rows.value.map(item => item.channel)])])
const outdatedBase = computed(() => (channelVersions.value[0]?.id || null) !== baseVersionId.value)
const canEdit = computed(() => props.administrator || selected.value?.owner === props.account)
const installedDeveloperUrl = computed(() => props.platform?.environment.url ? new URL('/developer', props.platform.environment.url).href : '')
let active = true
let timer: ReturnType<typeof setInterval>
let uploadIdentity = ''
let uploadRequestId = ''
function editSettings(project: Project) { Object.assign(settings, { name: project.name, description: project.description, members: project.members.join('\n'), trusted: project.trusted, auto_deploy: project.auto_deploy, revision: project.revision }) }
function releaseOf(item: Version) { return item.release_job_id ? releaseById.value.get(item.release_job_id) : undefined }
function releaseLabel(item: Version) {
  if (!item.release_job_id) return '未发起发布'
  const job = releaseOf(item)
  return job ? releaseLabels[job.status] || job.status : '未在最近发布记录中找到，状态待确认'
}
function canRetry(item: Version) {
  if (item.release_job_id) return ['failed', 'rolled_back'].includes(releaseOf(item)?.status || '')
  return item.status === 'failed'
}
async function reload() {
  const [value, jobs] = await Promise.all([projects(), api<ReleaseJob[]>('/developer/releases')])
  if (!active) return
  items.value = value; releaseJobs.value = jobs
  if (!selectedId.value && value.length) selectedId.value = value[0].id
  if (selectedId.value) await loadVersions(selectedId.value)
}
async function loadVersions(id: string) {
  const value = await versions(id)
  if (!active || id !== selectedId.value) return
  rows.value = value
  if (!file.value) baseVersionId.value = channelVersions.value[0]?.id || null
  if (version.value && value.some(item => item.id === version.value?.id)) {
    const detail = await getVersion(version.value.id)
    if (active && id === selectedId.value && detail.id === version.value?.id) version.value = detail
  }
}
async function perform(action: () => Promise<unknown>, success = '') {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await action(); await reload(); emit('changed'); message.value = success } catch (e) { error.value = e instanceof Error ? e.message : String(e) } finally { busy.value = false }
}
async function selectVersion(row: Version) { await perform(async () => { version.value = await getVersion(row.id) }) }
async function addProject() { await perform(async () => { const value = await createProject(create); selectedId.value = value.id; showCreate.value = false; Object.assign(create, { id: '', name: '', description: '' }) }, '项目已创建，可上传第一个版本。') }
async function updateProject() {
  if (!selected.value) return
  await perform(async () => {
    const value = await saveProject(selectedId.value, { name: settings.name, description: settings.description, revision: settings.revision, members: settings.members.split(/[\s,，]+/).filter(Boolean), trusted: props.administrator ? settings.trusted : selected.value!.trusted, auto_deploy: props.administrator ? settings.auto_deploy : selected.value!.auto_deploy })
    editSettings(value)
  }, '项目设置已保存。')
}
function chooseFile(event: Event) {
  const value = (event.target as HTMLInputElement).files?.[0]
  error.value = ''; file.value = undefined
  if (!value) return
  if (!value.name.toLowerCase().endsWith('.zip')) { error.value = '请选择单模块 ZIP 文件。'; return }
  if (value.size > 2 * 1024 * 1024) { error.value = 'ZIP 压缩包不能超过 2 MiB。'; return }
  file.value = value
}
async function upload() {
  if (!file.value || !selected.value) return
  if (outdatedBase.value) { error.value = '当前分支已有新版本。请先合并修改，再选择最新基线提交，避免覆盖他人的工作。'; return }
  const source = file.value
  const key = [selectedId.value, channel.value, baseVersionId.value, baseCommit.value, source.name, source.size, source.lastModified].join(':')
  if (uploadIdentity !== key) { uploadIdentity = key; uploadRequestId = crypto.randomUUID() }
  await perform(async () => {
    const encoded = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('无法读取 ZIP 文件。')); reader.readAsDataURL(source) })
    version.value = await uploadVersion(selectedId.value, { package_base64: encoded, channel: channel.value, base_version_id: baseVersionId.value, base_commit: baseCommit.value.trim(), request_id: uploadRequestId })
    file.value = undefined; if (fileInput.value) fileInput.value.value = ''
  }, '版本已接收。下面显示服务器的实际检查与执行状态。')
}
watch(selectedId, async id => {
  rows.value = []; version.value = undefined; file.value = undefined; baseVersionId.value = null; channel.value = 'main'; error.value = ''
  if (fileInput.value) fileInput.value.value = ''
  if (selected.value) editSettings(selected.value)
  if (id) try { await loadVersions(id); if (selected.value) editSettings(selected.value) } catch (e) { error.value = String(e) }
})
watch(channel, () => { baseVersionId.value = channelVersions.value[0]?.id || null })
watch(() => props.platform?.base_commit, value => { if (!baseCommit.value && value) baseCommit.value = value }, { immediate: true })
onMounted(() => { void perform(reload); timer = setInterval(() => { if (!busy.value) void reload().catch(e => { if (active) error.value = String(e) }) }, 5000) })
onBeforeUnmount(() => { active = false; clearInterval(timer) })
</script>
<template>
  <section>
    <div class="dev-actions"><h2>项目与版本</h2><button @click="showCreate = !showCreate">{{ showCreate ? '收起新建' : '创建模块项目' }}</button><button :disabled="busy" @click="perform(reload)">刷新状态</button></div>
    <p>每个 ZIP 对应一个不可覆盖的模块版本。feature 分支用于并行开发；main 通过验收后按项目策略发布。</p>
    <p v-if="error" class="dev-alert" role="alert">{{ error }}</p><p v-if="message" class="dev-status" role="status">{{ message }}</p>
    <form v-if="showCreate" class="dev-panel dev-form" @submit.prevent="addProject"><h3>创建项目</h3><div class="fields"><label>项目编号<input v-model="create.id" required pattern="[a-z][a-z0-9_]{1,47}" placeholder="与 manifest.id 相同" /></label><label>项目名称<input v-model="create.name" required maxlength="80" /></label></div><label>项目说明<textarea v-model="create.description" maxlength="1000" /></label><button class="primary" :disabled="busy">创建项目</button></form>
    <div class="dev-columns"><aside class="project-nav" aria-label="项目列表"><button v-for="project in items" :key="project.id" :class="{ active: selectedId === project.id }" @click="selectedId = project.id"><strong>{{ project.name }}</strong><small>{{ project.id }} · {{ project.trusted ? '已获运行授权' : '待运行授权' }}</small></button><p v-if="!items.length">还没有项目，先创建一个。</p></aside>
      <div v-if="selected">
        <section class="dev-panel"><h3>{{ selected.name }}</h3><p>{{ selected.description }}</p><div class="dev-actions"><span class="dev-chip">负责人 {{ selected.owner }}</span><span class="dev-chip">{{ selected.trusted ? '内部授权项目' : '静态接收，等待管理员授权运行' }}</span><span class="dev-chip">{{ selected.auto_deploy ? 'main 自动发布' : '通过后手动发起发布' }}</span></div>
          <details v-if="canEdit"><summary>成员与项目设置</summary><form class="dev-form" @submit.prevent="updateProject"><label>项目名称<input v-model="settings.name" required /></label><label>项目说明<textarea v-model="settings.description" /></label><label>协作成员账号<textarea v-model="settings.members" placeholder="每行一个已存在的账号" /></label><template v-if="administrator"><label class="check-label"><input v-model="settings.trusted" type="checkbox" />允许此内部项目执行代码验收</label><label class="check-label"><input v-model="settings.auto_deploy" type="checkbox" />main 通过验收后自动部署</label></template><p class="muted">成员授权由后端校验。新增能力或不兼容契约仍需先完成配置，不能绕过检查。</p><button :disabled="busy">保存项目设置</button></form></details>
        </section>
        <form class="dev-panel dev-form" @submit.prevent="upload"><h3>上传模块版本</h3><div class="fields"><label>开发分支<input v-model="channel" list="module-channels" required pattern="[a-z][a-z0-9_-]{0,39}" placeholder="main 或 feature-your-name" /><datalist id="module-channels"><option v-for="item in channels" :key="item" :value="item" /></datalist></label><label>分支基线版本<select v-model="baseVersionId"><option :value="null">此分支的第一个版本</option><option v-for="item in channelVersions" :key="item.id" :value="item.id">{{ item.version }} · {{ item.actor }} · {{ item.id.slice(0, 8) }}</option></select></label></div>
          <p v-if="outdatedBase" class="dev-alert">分支已有更新。请合并最新修改后，将基线切换到最新版本。</p>
          <label>平台基线提交<input v-model="baseCommit" required pattern="[a-f0-9]{40}" minlength="40" maxlength="40" placeholder="平台状态提供的 40 位提交号" /></label>
          <label>模块 ZIP 文件<input ref="fileInput" type="file" accept=".zip,application/zip" required @change="chooseFile" /></label><p class="muted">最大 2 MiB，解压后最多 8 MiB / 100 个文件。仅模块声明、Python、Vue、JSON 文件；不要包含依赖目录、密钥、嵌套目录或整个项目。</p>
          <p v-if="!selected.trusted" class="muted">当前项目未获运行授权。上传后保留静态检查结果，执行验收等待管理员授权。</p>
          <button class="primary" :disabled="busy || !file || outdatedBase">{{ busy ? '正在提交…' : '上传并启动自动验收' }}</button>
        </form>
        <section class="dev-panel"><h3>版本记录</h3><div class="dev-table-wrap"><table class="dev-table"><thead><tr><th>版本 / 分支</th><th>验收状态</th><th>发布状态</th><th>提交者</th><th>操作</th></tr></thead><tbody><tr v-for="item in rows" :key="item.id"><td>{{ item.version }}<br /><small>{{ item.channel }}</small></td><td><span class="dev-chip" :class="item.status">{{ statusLabel[item.status] || item.status }}</span><br /><small>{{ item.stage === 'awaiting_trust' ? '等待管理员授权项目执行' : item.stage }}</small></td><td><span class="dev-chip" :class="releaseOf(item)?.status">{{ releaseLabel(item) }}</span><br /><small v-if="releaseOf(item)?.stage">{{ releaseOf(item)?.stage }}</small></td><td>{{ item.actor }}<br /><small>{{ item.created_at }}</small></td><td><button :disabled="busy" @click="selectVersion(item)">查看验收</button></td></tr></tbody></table></div><p v-if="!rows.length">还没有提交版本。</p></section>
        <section v-if="version" class="dev-panel" aria-label="版本验收详情"><h3>{{ version.project_id }} · {{ version.version }} · {{ version.channel }}</h3><p><span class="dev-chip" :class="version.status">{{ statusLabel[version.status] || version.status }}</span> {{ version.stage === 'awaiting_trust' ? '等待管理员授权项目执行' : version.stage }}</p>
          <dl class="version-facts"><dt>发布状态</dt><dd><span class="dev-chip" :class="releaseOf(version)?.status">{{ releaseLabel(version) }}</span><small v-if="releaseOf(version)?.stage"> · {{ releaseOf(version)?.stage }}</small></dd><dt>内容摘要</dt><dd><code>{{ version.digest }}</code></dd><dt>平台基线</dt><dd><code>{{ version.base_commit }}</code></dd><dt>候选提交</dt><dd><code>{{ version.candidate_commit || '尚未生成' }}</code></dd><dt>实际安装版本</dt><dd><code>{{ platform?.environment.revision || '尚未确认运行版本' }}</code></dd></dl>
          <div class="dev-actions"><button :disabled="busy" @click="perform(() => downloadVersion(version!))">下载此版本源码</button><button v-if="canRetry(version)" :disabled="busy" @click="perform(() => retryVersion(version!.id), '已申请重新验收。')">重新验收</button><button v-if="version.status === 'passed' && !version.release_job_id" class="primary" :disabled="busy || !selected.trusted" @click="perform(() => releaseVersion(version!.id), '已提交发布，请在发布记录查看真实部署状态。')">发布已验收版本</button><button v-if="version.release_job_id" @click="emit('releases')">查看发布记录</button></div>
          <p v-if="version.release_job_id && canRetry(version)" class="dev-alert">发布未完成，验收通过不代表已经上线。可重新验收这个不可变版本，通过后按项目策略重新发布。</p><h4>验收门禁</h4><p v-if="!version.report.gates?.length">尚未收到执行器门禁结果。</p><article v-for="(gate, index) in version.report.gates" :key="index" class="dev-panel"><strong>{{ gate.name || gate.id || gate.stage || `门禁 ${index + 1}` }}</strong> <span class="dev-chip" :class="gate.status">{{ statusLabel[gate.status || ''] || gate.status || (gate.passed === true ? '通过' : gate.passed === false ? '失败' : '等待结果') }}</span><p>{{ gate.message }}</p><p v-if="gate.path"><code>{{ gate.path }}</code></p><details><summary>完整诊断</summary><pre>{{ pretty(gate) }}</pre></details></article>
          <details v-if="version.report.preview" open><summary>候选版本数据预览</summary><p class="muted">以下为执行器返回的候选版本数据。交互界面以部署后的测试环境为准。</p><pre>{{ pretty(version.report.preview) }}</pre></details>
          <details><summary>完整验收报告</summary><pre>{{ pretty(version.report) }}</pre></details><h4>执行事件</h4><ol class="dev-log"><li v-for="(event, index) in version.events" :key="index"><strong>{{ event.stage }}</strong><br />{{ event.message }}</li></ol><p v-if="!version.events.length">尚无执行事件。</p>
          <div v-if="version.candidate_commit && version.candidate_commit === platform?.environment.revision && platform?.environment.url"><p><a :href="platform.environment.url" target="_blank" rel="noopener">打开已运行此版本的测试环境 ↗</a></p><p><a :href="installedDeveloperUrl" target="_blank" rel="noopener">进入测试环境模块配置与预览 ↗</a></p><p class="muted">新安装模块默认停用。请管理员在测试环境「模块列表」授予所需能力并启用，再进入「调试预览」或「数据编排」验证；工作台的模块配置不会自动复制过去。</p></div>
        </section>
      </div>
    </div>
  </section>
</template>
