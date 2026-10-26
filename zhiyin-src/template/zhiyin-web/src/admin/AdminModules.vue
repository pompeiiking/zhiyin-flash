<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import UiIcon from '@/components/UiIcon.vue'
import type { ModulePolicy, ModuleView } from './client'
import { adminClient } from './client'
import { MODULE_KIND_LABEL, moduleGrantSummary, moduleKind, moduleStatus } from './model'

const props = defineProps<{
  modules: ModuleView[]
  agents: { id: string; name: string }[]
  administrator: boolean
}>()
const emit = defineEmits<{ changed: []; notify: [message: string] }>()

type Filter = 'all' | 'application' | 'tool' | 'disabled' | 'blocked'
const query = ref('')
const filter = ref<Filter>('all')
const selectedId = ref('')
const drawer = ref<HTMLElement | null>(null)
const dirty = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const form = reactive<ModulePolicy>({ enabled: false, reads: [], actions: [], agents: [], revision: 0 })

const filters: { id: Filter; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'application', label: '应用' },
  { id: 'tool', label: '技能' },
  { id: 'disabled', label: '未启用' },
  { id: 'blocked', label: '受阻' },
]

const parentNames = computed(() => new Map(props.modules.map(module => [module.manifest.id, module.manifest.name])))
const selected = computed(() => props.modules.find(module => module.manifest.id === selectedId.value))
const blockedBy = computed(() => selected.value?.blocked_by ?? [])
const moduleReads = computed(() => selected.value?.manifest.reads ?? [])
const moduleActions = computed(() => selected.value?.manifest.actions ?? [])

const filtered = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return props.modules.filter(module => {
    const kind = moduleKind(module)
    if (filter.value === 'disabled' && module.policy.enabled) return false
    if (filter.value === 'blocked' && !(module.policy.enabled && !module.effective_enabled)) return false
    if (filter.value === 'application' && kind !== 'application') return false
    if (filter.value === 'tool' && kind !== 'tool') return false
    if (!keyword) return true
    const haystack = [module.manifest.name, module.manifest.id, module.manifest.owner, module.manifest.description].join(' ').toLowerCase()
    return haystack.includes(keyword)
  })
})

function parentName(module: ModuleView) {
  const id = module.manifest.parent_id
  return id ? parentNames.value.get(id) || id : '平台直属'
}

function select(module: ModuleView) {
  selectedId.value = module.manifest.id
  Object.assign(form, {
    enabled: module.policy.enabled,
    reads: [...(module.policy.reads ?? [])],
    actions: [...(module.policy.actions ?? [])],
    agents: [...(module.policy.agents ?? [])],
    revision: module.policy.revision ?? 0,
  })
  dirty.value = false
  error.value = ''
  message.value = ''
  void nextTick(() => drawer.value?.focus())
}

function close() {
  if (saving.value) return
  selectedId.value = ''
  dirty.value = false
  error.value = ''
  message.value = ''
}

function markDirty() {
  dirty.value = true
  message.value = ''
}

async function save() {
  const module = selected.value
  if (!module || saving.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    await adminClient.savePolicy(module.manifest.id, { ...form, revision: module.policy.revision })
    dirty.value = false
    message.value = '授权配置已保存。刷新后模块状态会按所属应用重新计算。'
    emit('notify', `已保存「${module.manifest.name}」的授权配置。`)
    emit('changed')
    Object.assign(form, { revision: (module.policy.revision ?? 0) + 1 })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason)
  } finally {
    saving.value = false
  }
}

watch(() => props.modules, () => {
  if (selected.value && !dirty.value) {
    Object.assign(form, {
      enabled: selected.value.policy.enabled,
      reads: [...(selected.value.policy.reads ?? [])],
      actions: [...(selected.value.policy.actions ?? [])],
      agents: [...(selected.value.policy.agents ?? [])],
      revision: selected.value.policy.revision ?? 0,
    })
  }
})
</script>

<template>
  <section aria-labelledby="admin-modules-title">
    <header class="admin-section__head" style="padding-left:0;padding-right:0">
      <div>
        <h2 id="admin-modules-title" class="admin-section__title">模块清单</h2>
        <p class="admin-section__hint">按类型或状态筛选；点击一行查看并调整授权。</p>
      </div>
      <span class="admin-count">{{ filtered.length }} / {{ modules.length }} 个模块</span>
    </header>

    <div class="admin-toolbar">
      <label class="admin-search">
        <UiIcon name="search" :size="15" />
        <span class="sr-only">搜索模块</span>
        <input v-model="query" type="search" placeholder="搜索模块名称、编号或负责人" autocomplete="off" />
      </label>
      <div class="admin-filters" role="group" aria-label="模块筛选">
        <button v-for="item in filters" :key="item.id" type="button" class="admin-filter" :aria-pressed="filter === item.id" @click="filter = item.id">{{ item.label }}</button>
      </div>
    </div>

    <div v-if="filtered.length" class="admin-module-list">
      <button v-for="module in filtered" :key="module.manifest.id" type="button" class="admin-module" :aria-label="`管理模块：${module.manifest.name}`" @click="select(module)">
        <span class="admin-module__name">
          <strong>{{ module.manifest.name }}</strong>
          <span>{{ module.manifest.description }}</span>
        </span>
        <span class="admin-module__kind admin-status">{{ MODULE_KIND_LABEL[moduleKind(module)] }}</span>
        <span class="admin-status" :class="'is-' + moduleStatus(module).tone">{{ moduleStatus(module).label }}</span>
        <span class="admin-module__grant">{{ moduleGrantSummary(module) }}<br><span>{{ parentName(module) }}</span></span>
        <span class="admin-module__action" aria-hidden="true"><UiIcon name="chevron" :size="15" /></span>
      </button>
    </div>
    <div v-else class="admin-empty">
      <strong>没有匹配的模块</strong>
      <span>{{ modules.length ? '换一个筛选条件或搜索词。' : '当前环境还没有登记模块；先到开发工作台安装或发布模块。' }}</span>
    </div>
  </section>

  <Teleport to="body">
    <div v-if="selected" class="admin-drawer-backdrop" aria-hidden="true" @click="close" />
    <aside v-if="selected" ref="drawer" class="admin-drawer" role="dialog" aria-modal="true" aria-labelledby="admin-module-drawer-title" tabindex="-1" @keydown.esc="close">
      <header class="admin-drawer__head">
        <div>
          <p>{{ MODULE_KIND_LABEL[moduleKind(selected)] }} · v{{ selected.manifest.version }}</p>
          <h2 id="admin-module-drawer-title">{{ selected.manifest.name }}</h2>
          <p class="admin-field__hint">{{ selected.manifest.id }} · {{ selected.manifest.owner }}</p>
        </div>
        <button type="button" class="admin-icon-btn" aria-label="关闭模块详情" @click="close"><UiIcon name="close" :size="16" /></button>
      </header>

      <div class="admin-drawer__body">
        <div v-if="blockedBy.length" class="admin-banner is-error" role="alert" style="margin:0 0 18px">
          <span>该模块已授权，但所属应用未启用：{{ blockedBy.map(id => parentNames.get(id) || id).join('、') }}。启用所属应用后才会恢复可用。</span>
        </div>

        <div class="admin-field">
          <div class="admin-switch">
            <div>
              <strong>启用模块</strong>
              <small>停用后学生端与智能体都不能调用；已有配置保留。</small>
            </div>
            <button type="button" class="admin-toggle" :class="{ 'is-on': form.enabled }" role="switch" :aria-checked="form.enabled" aria-label="启用模块" :disabled="!administrator || saving" @click="form.enabled = !form.enabled; markDirty()"><span /></button>
          </div>
        </div>

        <div class="admin-field">
          <span class="admin-field__label">允许读取的数据</span>
          <p class="admin-field__hint">只授予这个模块实际用到的范围，不按应用批量放行。</p>
          <div v-if="moduleReads.length" class="admin-check-grid">
            <label v-for="read in moduleReads" :key="read" class="admin-check">
              <input v-model="form.reads" type="checkbox" :value="read" :disabled="!administrator || saving" @change="markDirty" />
              <span><code>{{ read }}</code></span>
            </label>
          </div>
          <p v-else class="admin-note">这个模块没有声明读取范围。</p>
        </div>

        <div class="admin-field">
          <span class="admin-field__label">允许执行的操作</span>
          <p class="admin-field__hint">操作会写入真实业务数据；未勾选时模块只能读取。</p>
          <div v-if="moduleActions.length" class="admin-check-grid">
            <label v-for="action in moduleActions" :key="action" class="admin-check">
              <input v-model="form.actions" type="checkbox" :value="action" :disabled="!administrator || saving" @change="markDirty" />
              <span><code>{{ action }}</code></span>
            </label>
          </div>
          <p v-else class="admin-note">这个模块没有声明业务操作。</p>
        </div>

        <div v-if="selected.manifest.tool" class="admin-field">
          <span class="admin-field__label">允许使用的智能体</span>
          <p class="admin-field__hint">只有勾选的智能体才能在对话中调用这个技能。</p>
          <div v-if="agents.length" class="admin-check-grid">
            <label v-for="agent in agents" :key="agent.id" class="admin-check">
              <input v-model="form.agents" type="checkbox" :value="agent.id" :disabled="!administrator || saving" @change="markDirty" />
              <span>{{ agent.name }} <code>{{ agent.id }}</code></span>
            </label>
          </div>
          <p v-else class="admin-note">当前还没有可用的智能体。</p>
        </div>

        <div class="admin-field">
          <span class="admin-field__label">模块信息</span>
          <dl class="admin-kv">
            <div><dt>当前版本</dt><dd><code>{{ selected.manifest.version }}</code></dd></div>
            <div><dt>源码修订</dt><dd><code :title="selected.source_revision">{{ (selected.source_revision || '未记录').slice(0, 12) }}</code></dd></div>
            <div><dt>所属应用</dt><dd>{{ parentName(selected) }}</dd></div>
            <div><dt>授权版本</dt><dd>{{ selected.policy.revision || '尚未保存' }}</dd></div>
          </dl>
        </div>

        <p v-if="!administrator" class="admin-banner" role="status">当前账号是开发者，可以查看模块，但只有管理员能保存授权配置。</p>
        <p v-if="error" class="admin-banner is-error" role="alert">{{ error }}</p>
        <p v-else-if="message" class="admin-banner is-success" role="status">{{ message }}</p>
      </div>

      <footer class="admin-drawer__foot">
        <button type="button" class="admin-btn" :disabled="saving" @click="close">关闭</button>
        <button type="button" class="admin-btn admin-btn--primary" :disabled="!administrator || !dirty || saving" @click="save">{{ saving ? '正在保存…' : '保存授权' }}</button>
      </footer>
    </aside>
  </Teleport>
</template>
