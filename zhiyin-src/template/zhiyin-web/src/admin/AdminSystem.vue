<script setup lang="ts">
import { computed } from 'vue'
import UiIcon from '@/components/UiIcon.vue'
import type { AdminContext, PlatformStatus } from './client'
import { shortTime } from './model'

const props = defineProps<{
  context?: AdminContext
  platform?: PlatformStatus
  featureFlags: Record<string, boolean>
  administrator: boolean
  busy?: boolean
  message?: string
  error?: string
}>()
const emit = defineEmits<{ reloadConfig: [] }>()

const environment = computed(() => {
  const value = props.context?.environment || ''
  return ({ workbench: '开发工作台', staging: '测试环境', production: '正式环境', local: '本地环境' } as Record<string, string>)[value] || value || '尚未确认'
})
const revisionMismatch = computed(() => {
  const running = props.platform?.environment.revision
  return Boolean(running && props.context?.revision && running !== props.context.revision)
})
const FEATURE_LABELS: Record<string, string> = {
  report_full_text: '完整报告',
  export: '导出资料',
  calendar: '日历与课表',
  achievements: '完成记录',
  mentor: '导师能力（预留）',
  decision_intent_routing: '决策意图分流',
}
const flags = computed(() => Object.entries(props.featureFlags || {}).sort(([left], [right]) => left.localeCompare(right)))
function featureLabel(code: string) {
  return FEATURE_LABELS[code] || code
}
function shortRevision(value?: string | null) {
  if (!value) return '尚未确认'
  return value.length > 12 ? value.slice(0, 12) : value
}
</script>

<template>
  <section aria-labelledby="admin-system-title">
    <header class="admin-section__head" style="padding-left:0;padding-right:0">
      <div>
        <h2 id="admin-system-title" class="admin-section__title">环境概览</h2>
        <p class="admin-section__hint">当前环境、执行器与配置入口；不展示无法验证的“健康分”。</p>
      </div>
      <span class="admin-count">{{ platform?.worker.healthy ? '执行器在线' : platform ? '执行器离线' : '状态待读取' }}</span>
    </header>

    <div class="admin-system-grid">
      <section class="admin-section" aria-labelledby="admin-env-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-env-title" class="admin-section__title">当前环境</h2>
            <p class="admin-section__hint">当前管理台连接的构建与运行版本。</p>
          </div>
          <span class="admin-status" :class="revisionMismatch ? 'is-warn' : 'is-ok'">{{ revisionMismatch ? '版本不一致' : '已确认' }}</span>
        </header>
        <div class="admin-section__body">
          <dl class="admin-kv">
            <div><dt>环境</dt><dd>{{ environment }}</dd></div>
            <div><dt>管理台构建</dt><dd><code :title="context?.revision">{{ shortRevision(context?.revision) }}</code></dd></div>
            <div><dt>环境运行版本</dt><dd><code :title="platform?.environment.revision || undefined">{{ shortRevision(platform?.environment.revision) }}</code></dd></div>
            <div><dt>环境地址</dt><dd><a v-if="platform?.environment.url" :href="platform.environment.url" target="_blank" rel="noopener">打开环境 ↗</a><span v-else>未配置</span></dd></div>
          </dl>
          <p v-if="revisionMismatch" class="admin-banner is-error" role="alert" style="margin:16px 0 0">
            管理台构建与环境实际运行版本不一致。继续发布会把当前提交带到目标环境，请先确认这是预期版本。
          </p>
        </div>
      </section>

      <section class="admin-section" aria-labelledby="admin-worker-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-worker-title" class="admin-section__title">自动验收执行器</h2>
            <p class="admin-section__hint">执行器负责构建、测试和切换候选版本。</p>
          </div>
          <span class="admin-status" :class="platform?.worker.healthy ? 'is-ok' : 'is-warn'">{{ platform ? (platform.worker.healthy ? '在线' : '离线') : '未知' }}</span>
        </header>
        <div class="admin-section__body">
          <dl class="admin-kv">
            <div><dt>最近心跳</dt><dd>{{ shortTime(platform?.worker.last_seen) }}</dd></div>
            <div><dt>待处理版本</dt><dd>{{ platform?.pending_versions ?? '尚未读取' }}</dd></div>
            <div><dt>基线提交</dt><dd><code :title="platform?.base_commit">{{ shortRevision(platform?.base_commit) }}</code></dd></div>
          </dl>
          <p class="admin-note" style="margin-top:14px">执行器离线时，已确认的发布任务会停在队列，不会假装完成。</p>
        </div>
      </section>

      <section class="admin-section" aria-labelledby="admin-config-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-config-title" class="admin-section__title">动态配置</h2>
            <p class="admin-section__hint">重新读取环节口径、气泡编排与采集规则，不重启服务。</p>
          </div>
        </header>
        <div class="admin-section__body">
          <p class="admin-note">配置只在启动和手动重载时读取。修改已发布配置后，用这里让当前进程重新装载。</p>
          <button type="button" class="admin-btn admin-btn--primary" style="margin-top:14px" :disabled="!administrator || busy" @click="emit('reloadConfig')">
            <UiIcon name="refresh" :size="14" /> {{ busy ? '正在重载…' : '重新加载动态配置' }}
          </button>
          <p v-if="!administrator" class="admin-note" style="margin-top:10px">只有管理员能重载服务配置。</p>
          <p v-if="error" class="admin-banner is-error" role="alert">{{ error }}</p>
          <p v-else-if="message" class="admin-banner is-success" role="status">{{ message }}</p>
        </div>
      </section>

      <section class="admin-section admin-flags-section" aria-labelledby="admin-flags-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-flags-title" class="admin-section__title">功能开关</h2>
            <p class="admin-section__hint">来自登录时下发的开关快照；修改由部署配置完成。</p>
          </div>
        </header>
        <div class="admin-section__body">
          <div v-if="flags.length" class="admin-flags">
            <div v-for="[code, enabled] in flags" :key="code" class="admin-flag">
              <span class="admin-flag__copy"><strong>{{ featureLabel(code) }}</strong><code>{{ code }}</code></span>
              <span class="admin-status" :class="enabled ? 'is-ok' : 'is-muted'">{{ enabled ? '已开启' : '已关闭' }}</span>
            </div>
          </div>
          <p v-else class="admin-note">登录快照里没有功能开关。</p>
          <p class="admin-note" style="margin-top:14px">关闭的开关会在接口层拒绝访问；未实现的能力保持关闭，不用界面隐藏来代替权限控制。</p>
        </div>
      </section>
    </div>
  </section>
</template>
