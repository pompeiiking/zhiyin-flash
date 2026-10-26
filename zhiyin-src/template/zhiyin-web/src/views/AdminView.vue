<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandMark from '@/components/BrandMark.vue'
import UiIcon from '@/components/UiIcon.vue'
import { auth, isDeveloperRole } from '@/lib/auth'
import { BackendError } from '@/api/backend-client'
import AdminOverview from '@/admin/AdminOverview.vue'
import AdminModules from '@/admin/AdminModules.vue'
import AdminWorkflows from '@/admin/AdminWorkflows.vue'
import AdminReleases from '@/admin/AdminReleases.vue'
import AdminSystem from '@/admin/AdminSystem.vue'
import { adminClient } from '@/admin/client'
import type { AdminContext, CheckRecord, ModuleView, PlatformStatus, ReleaseJob } from '@/admin/client'
import '@/admin/admin.css'

type TabId = 'overview' | 'modules' | 'workflows' | 'releases' | 'system'
const tabs: { id: TabId; label: string; hint: string; icon: string; title: string; description: string }[] = [
  { id: 'overview', label: '总览', hint: '运行状态与待办', icon: 'apps', title: '运行总览', description: '先看现在需要处理什么，再决定是否发布、调整授权或检查环境。' },
  { id: 'modules', label: '模块与授权', hint: '启用与数据范围', icon: 'shield', title: '模块与授权', description: '每个模块独立授权；这里能看清它为什么可用、为什么受阻，以及被授予了什么。' },
  { id: 'workflows', label: '数据编排', hint: '连接模块与流程', icon: 'path', title: '数据编排', description: '把输入、模块读取和末端业务操作连成一条可验证的流程。' },
  { id: 'releases', label: '发布与验收', hint: '确认与执行记录', icon: 'document', title: '发布与验收', description: '确认发布任务、查看执行进度与失败位置。失败会保留原版本。' },
  { id: 'system', label: '系统与环境', hint: '配置与开关', icon: 'settings', title: '系统与环境', description: '核对运行版本、执行器与动态配置；所有状态来自真实接口。' },
]

const route = useRoute()
const router = useRouter()
const context = ref<AdminContext>()
const modules = ref<ModuleView[]>([])
const checks = ref<CheckRecord[]>([])
const jobs = ref<ReleaseJob[]>([])
const platform = ref<PlatformStatus>()
const loading = ref(true)
const refreshing = ref(false)
const forbidden = ref(false)
const error = ref('')
const partialError = ref('')
const actionMessage = ref('')
const actionError = ref('')
const systemMessage = ref('')
const systemError = ref('')
const lastUpdated = ref('')
const acting = ref(false)
const tab = ref<TabId>(normalizeTab(route.query.tab))

let alive = true
let messageTimer: ReturnType<typeof setTimeout> | undefined

function normalizeTab(value: unknown): TabId {
  return tabs.some(item => item.id === value) ? value as TabId : 'overview'
}
const current = computed(() => tabs.find(item => item.id === tab.value) || tabs[0])
const administrator = computed(() => context.value?.role === 'admin')
const roleLabel = computed(() => administrator.value ? '管理员' : context.value?.role === 'developer' ? '开发者' : '未授权')
const nickname = computed(() => auth.state.bootstrap?.identity?.nickname || auth.state.bootstrap?.identity?.user_id || '当前账号')
const environment = computed(() => context.value?.environment || '')
const environmentLabel = computed(() => {
  const value = environment.value
  return ({ workbench: '开发工作台', staging: '测试环境', production: '正式环境', local: '本地环境' } as Record<string, string>)[value] || value || '正在确认'
})
const roleAllowed = computed(() => isDeveloperRole())

function notify(message: string) {
  actionMessage.value = message
  actionError.value = ''
  if (messageTimer) clearTimeout(messageTimer)
  messageTimer = setTimeout(() => { actionMessage.value = '' }, 5000)
}

function fail(reason: unknown) {
  actionError.value = reason instanceof Error ? reason.message : String(reason)
}

async function load({ quiet = false } = {}) {
  if (!roleAllowed.value) {
    forbidden.value = true
    loading.value = false
    return
  }
  if (quiet) refreshing.value = true
  else loading.value = true
  error.value = ''
  partialError.value = ''
  try {
    const [ctx, mods, chks, releases, status] = await Promise.allSettled([
      adminClient.context(),
      adminClient.modules(),
      adminClient.checks(),
      adminClient.releases(),
      adminClient.platform(),
    ])
    if (!alive) return
    if (ctx.status === 'rejected') {
      const reason = ctx.reason
      if (reason instanceof BackendError && (reason.code === 1008 || /403|权限/.test(reason.message))) {
        forbidden.value = true
      } else {
        error.value = reason instanceof Error ? reason.message : String(reason)
      }
      loading.value = false
      return
    }
    context.value = ctx.value
    const missing: string[] = []
    if (mods.status === 'fulfilled') modules.value = mods.value
    else missing.push('模块')
    if (chks.status === 'fulfilled') checks.value = chks.value
    else missing.push('接入检查')
    if (releases.status === 'fulfilled') jobs.value = releases.value
    else missing.push('发布记录')
    if (status.status === 'fulfilled') platform.value = status.value
    else missing.push('运行状态')
    partialError.value = missing.length ? `部分数据本次未读取：${missing.join('、')}。可以稍后刷新，其他数据仍按真实结果展示。` : ''
    lastUpdated.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date())
  } finally {
    if (alive) {
      loading.value = false
      refreshing.value = false
    }
  }
}

async function reloadModules() {
  try {
    modules.value = await adminClient.modules()
    checks.value = await adminClient.checks()
    const status = await adminClient.platform().catch(() => undefined)
    if (status) platform.value = status
  } catch (reason) {
    fail(reason)
  }
}

async function approve(job: ReleaseJob) {
  if (acting.value) return
  acting.value = true
  actionError.value = ''
  try {
    await adminClient.approve(job.id)
    notify(`已确认「${job.kind === 'check' ? '完整检查' : '发布'}」任务，等待执行器处理。`)
    const [releases, status] = await Promise.allSettled([adminClient.releases(), adminClient.platform()])
    if (releases.status === 'fulfilled') jobs.value = releases.value
    if (status.status === 'fulfilled') platform.value = status.value
  } catch (reason) {
    fail(reason)
  } finally {
    acting.value = false
  }
}

async function runChecks() {
  if (acting.value) return
  acting.value = true
  actionError.value = ''
  try {
    await adminClient.runChecks()
    notify('已完成当前构建的接入检查。')
    checks.value = await adminClient.checks()
  } catch (reason) {
    fail(reason)
  } finally {
    acting.value = false
  }
}

async function reloadConfig() {
  if (acting.value) return
  acting.value = true
  systemError.value = ''
  systemMessage.value = ''
  try {
    await adminClient.reloadConfig()
    systemMessage.value = '动态配置已重新加载。'
    notify('动态配置已重新加载。')
  } catch (reason) {
    systemError.value = reason instanceof Error ? reason.message : String(reason)
  } finally {
    acting.value = false
  }
}

function selectTab(next: TabId) {
  tab.value = next
  const query = { ...route.query }
  if (next === 'overview') delete query.tab
  else query.tab = next
  void router.replace({ query })
}

watch(() => route.query.tab, value => { tab.value = normalizeTab(value) })
watch(tab, () => {
  actionMessage.value = ''
  actionError.value = ''
})
onMounted(() => { void load() })
onBeforeUnmount(() => {
  alive = false
  if (messageTimer) clearTimeout(messageTimer)
})
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-rail" aria-label="管理台导航">
      <RouterLink to="/admin" class="admin-rail__brand" aria-label="职引管理台">
        <BrandMark />
        <span class="admin-rail__product">管理台</span>
      </RouterLink>

      <div v-if="!forbidden" class="admin-rail__env">
        <strong>当前环境</strong>
        <span><i class="admin-env-dot" :class="platform?.worker.healthy ? 'is-ok' : platform ? 'is-warn' : ''" aria-hidden="true" />{{ environmentLabel }}</span>
        <span v-if="context" :title="context.revision"><code>{{ context.revision.slice(0, 10) }}</code></span>
      </div>

      <nav v-if="!forbidden" class="admin-nav" aria-label="管理台功能">
        <button v-for="item in tabs" :key="item.id" type="button" class="admin-nav__item" :aria-current="tab === item.id ? 'page' : undefined" @click="selectTab(item.id)">
          <span class="admin-nav__icon"><UiIcon :name="item.icon" :size="17" /></span>
          <span class="admin-nav__copy"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
        </button>
      </nav>

      <div class="admin-rail__foot">
        <div class="admin-identity"><strong>{{ nickname }}</strong><span>{{ roleLabel }}</span></div>
        <RouterLink v-if="!forbidden" class="admin-link" to="/developer">开发工作台 <UiIcon name="arrow" :size="13" /></RouterLink>
        <RouterLink class="admin-link" to="/chat">返回学生端 <UiIcon name="arrow" :size="13" /></RouterLink>
      </div>
    </aside>

    <main id="main-content" class="admin-main" tabindex="-1">
      <div class="admin-content">
        <template v-if="forbidden">
          <header class="admin-header">
            <div>
              <p class="admin-eyebrow">管理台</p>
              <h1 class="admin-title">当前账号没有管理权限</h1>
              <p class="admin-subtitle">管理台只向管理员和开发者开放。学生功能与已保存资料不受影响；需要权限时请联系管理员。</p>
            </div>
            <div class="admin-header__actions">
              <RouterLink class="admin-btn admin-btn--primary" to="/chat">回到咨询</RouterLink>
              <RouterLink class="admin-btn" to="/settings">查看账号</RouterLink>
            </div>
          </header>
        </template>

        <template v-else>
          <header class="admin-header">
            <div>
              <p class="admin-eyebrow">管理台 / {{ current.label }}</p>
              <h1 class="admin-title">{{ current.title }}</h1>
              <p class="admin-subtitle">{{ current.description }}</p>
            </div>
            <div class="admin-header__actions">
              <span class="admin-updated">{{ lastUpdated ? `上次读取 ${lastUpdated}` : '正在读取运行状态' }}</span>
              <button type="button" class="admin-btn" :disabled="refreshing" @click="load({ quiet: true })"><UiIcon name="refresh" :size="14" />{{ refreshing ? '正在刷新…' : '刷新' }}</button>
              <RouterLink class="admin-btn admin-btn--ghost admin-mobile-dev" to="/developer">开发工作台</RouterLink>
              <RouterLink class="admin-btn admin-btn--ghost admin-mobile-back" to="/chat">返回学生端</RouterLink>
            </div>
          </header>

          <p v-if="error" class="admin-banner is-error" role="alert">{{ error }}<button type="button" class="admin-btn admin-btn--sm" @click="load()">重试</button></p>
          <p v-if="partialError" class="admin-banner" role="status">{{ partialError }}</p>
          <p v-if="actionError" class="admin-banner is-error" role="alert">{{ actionError }}</p>
          <p v-else-if="actionMessage" class="admin-banner is-success" role="status">{{ actionMessage }}</p>

          <div v-if="loading && !context" class="admin-loading" role="status" aria-label="正在读取管理数据">
            <span /><span /><span />
          </div>

          <template v-else-if="context">
            <AdminOverview v-if="tab === 'overview'" :context="context" :modules="modules" :jobs="jobs" :checks="checks" :platform="platform" :busy="acting" @navigate="selectTab" @approve="approve" @run-checks="runChecks" />
            <AdminModules v-else-if="tab === 'modules'" :modules="modules" :agents="context.agents" :administrator="administrator" @changed="reloadModules" @notify="notify" />
            <AdminWorkflows v-else-if="tab === 'workflows'" :modules="modules" :administrator="administrator" />
            <AdminReleases v-else-if="tab === 'releases'" :jobs="jobs" :platform="platform" :administrator="administrator" :environment="environment" :busy="acting" @approve="approve" @refresh="load({ quiet: true })" />
            <AdminSystem v-else-if="tab === 'system'" :context="context" :platform="platform" :feature-flags="auth.state.bootstrap?.feature_flags || {}" :administrator="administrator" :busy="acting" :message="systemMessage" :error="systemError" @reload-config="reloadConfig" />
          </template>

          <div v-else-if="!error" class="admin-empty" style="margin-top:24px">
            <strong>还没有读取到管理数据</strong>
            <span>请刷新重试；如果当前环境没有装配模块平台，管理台会在这里如实说明，而不是展示示例模块。</span>
          </div>
        </template>
      </div>
    </main>
  </div>
</template>
