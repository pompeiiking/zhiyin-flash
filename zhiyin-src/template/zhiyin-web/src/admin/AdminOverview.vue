<script setup lang="ts">
import { computed } from 'vue'
import type { AdminContext, CheckRecord, ModuleView, PlatformStatus, ReleaseJob } from './client'
import { adminStats, attentionItems, jobStatus, JOB_KIND, shortTime, sortJobs } from './model'

const props = defineProps<{
  context?: AdminContext
  modules: ModuleView[]
  jobs: ReleaseJob[]
  checks: CheckRecord[]
  platform?: PlatformStatus
  busy?: boolean
}>()
const emit = defineEmits<{
  navigate: [tab: 'modules' | 'workflows' | 'releases' | 'system']
  approve: [job: ReleaseJob]
  runChecks: []
}>()

const stats = computed(() => adminStats(props.modules, props.jobs, props.checks, props.platform))
const attention = computed(() => attentionItems(stats.value, props.modules, props.checks, props.platform))
const recentJobs = computed(() => sortJobs(props.jobs).slice(0, 5))
const latestCheck = computed(() => props.checks[0])
const canApprove = computed(() => props.context?.role === 'admin' && props.context?.environment === 'workbench')
const environment = computed(() => {
  const value = props.context?.environment || ''
  return ({ workbench: '开发工作台', staging: '测试环境', production: '正式环境', local: '本地环境' } as Record<string, string>)[value] || value || '尚未确认'
})
const workerLabel = computed(() => {
  if (!props.platform) return '尚未读取'
  return props.platform.worker.healthy ? '在线' : '离线或尚无心跳'
})
const checkLabel = computed(() => {
  if (!latestCheck.value) return '尚未运行'
  return latestCheck.value.passed === false ? '最近一次未通过' : '最近一次通过'
})
</script>

<template>
  <div class="admin-stats" aria-label="运行概况">
    <article class="admin-stat">
      <span class="admin-stat__value">{{ stats.modules }}</span>
      <span class="admin-stat__label">已安装模块</span>
      <span class="admin-stat__note">{{ stats.enabled }} 个实际可用</span>
    </article>
    <article class="admin-stat" :class="{ 'is-warn': stats.requested }">
      <span class="admin-stat__value">{{ stats.requested }}</span>
      <span class="admin-stat__label">待确认发布</span>
      <span class="admin-stat__note">{{ stats.requested ? '确认后才进入执行队列' : '没有积压的发布任务' }}</span>
    </article>
    <article class="admin-stat" :class="{ 'is-warn': stats.blocked }">
      <span class="admin-stat__value">{{ stats.blocked }}</span>
      <span class="admin-stat__label">已授权但受阻</span>
      <span class="admin-stat__note">所属应用未启用时出现</span>
    </article>
    <article class="admin-stat" :class="{ 'is-muted': !stats.failedChecks }">
      <span class="admin-stat__value">{{ stats.failedChecks }}</span>
      <span class="admin-stat__label">检查未通过</span>
      <span class="admin-stat__note">{{ checkLabel }}</span>
    </article>
  </div>

  <div class="admin-overview">
    <div class="admin-overview__main">
      <section class="admin-section" aria-labelledby="admin-attention-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-attention-title" class="admin-section__title">现在需要处理</h2>
            <p class="admin-section__hint">只列会阻塞使用或需要管理员确认的事项。</p>
          </div>
          <span class="admin-status" :class="attention.length ? 'is-warn' : 'is-ok'">{{ attention.length ? attention.length + ' 项' : '已清空' }}</span>
        </header>
        <div class="admin-section__body">
          <div v-if="attention.length" class="admin-attention">
            <article v-for="item in attention" :key="item.id" class="admin-attention__item">
              <span class="admin-attention__dot" :class="'is-' + item.tone" aria-hidden="true" />
              <div class="admin-attention__copy">
                <strong>{{ item.title }}</strong>
                <p>{{ item.detail }}</p>
              </div>
              <button type="button" class="admin-btn admin-btn--sm admin-attention__action" @click="emit('navigate', item.tab)">{{ item.action }}</button>
            </article>
          </div>
          <div v-else class="admin-empty">
            <strong>当前没有需要处理的事项</strong>
            <span>发布队列、模块授权和接入检查都没有新的阻塞项。</span>
          </div>
        </div>
      </section>

      <section class="admin-section" aria-labelledby="admin-jobs-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-jobs-title" class="admin-section__title">最近发布</h2>
            <p class="admin-section__hint">发布任务必须由管理员确认；确认后才会交给执行器。</p>
          </div>
          <button type="button" class="admin-btn admin-btn--sm" @click="emit('navigate', 'releases')">全部记录</button>
        </header>
        <div class="admin-section__body">
          <div v-if="recentJobs.length" class="admin-job-list">
            <article v-for="job in recentJobs" :key="job.id" class="admin-job">
              <div class="admin-job__top">
                <span class="admin-status" :class="'is-' + jobStatus(job.status).tone">{{ jobStatus(job.status).label }}</span>
                <strong>{{ JOB_KIND[job.kind] || job.kind }}</strong>
                <button v-if="job.status === 'requested' && canApprove" type="button" class="admin-btn admin-btn--sm admin-btn--primary" :disabled="busy" @click="emit('approve', job)">确认执行</button>
              </div>
              <div class="admin-job__meta">
                <code :title="job.commit">{{ job.commit.slice(0, 10) }}</code>
                <span>{{ job.actor }}</span>
                <span>{{ shortTime(job.created_at) }}</span>
                <span v-if="job.stage">{{ job.stage }}</span>
              </div>
            </article>
          </div>
          <div v-else class="admin-empty">
            <strong>还没有发布记录</strong>
            <span>在开发工作台提交构建或检查任务后，记录会出现在这里。</span>
          </div>
        </div>
      </section>
    </div>

    <aside class="admin-overview__side" aria-label="运行状态与快捷操作">
      <section class="admin-section" aria-labelledby="admin-health-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-health-title" class="admin-section__title">运行状态</h2>
            <p class="admin-section__hint">读取自当前环境和执行器，不是估算值。</p>
          </div>
        </header>
        <div class="admin-section__body">
          <dl class="admin-health">
            <div class="admin-health__row"><dt>环境</dt><dd>{{ environment }}</dd></div>
            <div class="admin-health__row"><dt>构建版本</dt><dd><code>{{ context?.revision || '尚未读取' }}</code></dd></div>
            <div class="admin-health__row"><dt>执行器</dt><dd>{{ workerLabel }}</dd></div>
            <div class="admin-health__row"><dt>最近心跳</dt><dd>{{ shortTime(platform?.worker.last_seen) }}</dd></div>
            <div class="admin-health__row"><dt>待处理版本</dt><dd>{{ stats.pendingVersions }}</dd></div>
            <div class="admin-health__row"><dt>接入检查</dt><dd>{{ checkLabel }}</dd></div>
          </dl>
        </div>
      </section>

      <section class="admin-section" aria-labelledby="admin-actions-title">
        <header class="admin-section__head">
          <div>
            <h2 id="admin-actions-title" class="admin-section__title">快捷操作</h2>
            <p class="admin-section__hint">动作会写入真实环境；失败时保留当前状态。</p>
          </div>
        </header>
        <div class="admin-section__body">
          <div class="admin-stack" style="margin-top:0">
            <button type="button" class="admin-btn" :disabled="busy" @click="emit('runChecks')">运行接入检查</button>
            <button type="button" class="admin-btn" @click="emit('navigate', 'modules')">管理模块授权</button>
            <button type="button" class="admin-btn admin-btn--ghost" @click="emit('navigate', 'system')">查看系统与环境</button>
          </div>
        </div>
      </section>
    </aside>
  </div>
</template>
