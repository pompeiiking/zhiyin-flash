<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PlatformStatus, ReleaseJob } from './client'
import { jobStatus, JOB_KIND, shortTime, sortJobs } from './model'

const props = defineProps<{
  jobs: ReleaseJob[]
  platform?: PlatformStatus
  administrator: boolean
  environment?: string
  busy?: boolean
}>()
const emit = defineEmits<{ approve: [job: ReleaseJob]; refresh: [] }>()

type Filter = 'all' | 'requested' | 'running' | 'closed' | 'failed'
const filter = ref<Filter>('all')
const expanded = ref('')

const filtered = computed(() => {
  const rows = sortJobs(props.jobs)
  return rows.filter(job => {
    if (filter.value === 'requested') return job.status === 'requested'
    if (filter.value === 'running') return job.status === 'running' || job.status === 'queued'
    if (filter.value === 'failed') return job.status === 'failed' || job.status === 'rolled_back'
    if (filter.value === 'closed') return ['succeeded', 'failed', 'rolled_back'].includes(job.status)
    return true
  })
})
const pending = computed(() => props.jobs.filter(job => job.status === 'requested').length)
const canApprove = computed(() => props.administrator && props.environment === 'workbench')

function toggle(job: ReleaseJob) {
  expanded.value = expanded.value === job.id ? '' : job.id
}
</script>

<template>
  <section aria-labelledby="admin-releases-title">
    <header class="admin-section__head" style="padding-left:0;padding-right:0">
      <div>
        <h2 id="admin-releases-title" class="admin-section__title">发布记录</h2>
        <p class="admin-section__hint">按状态筛选；展开记录查看执行器事件与失败位置。</p>
      </div>
      <span class="admin-count">{{ jobs.length }} 条记录</span>
    </header>

    <div class="admin-stats" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <article class="admin-stat" :class="{ 'is-warn': pending }">
        <span class="admin-stat__value">{{ pending }}</span>
        <span class="admin-stat__label">待确认</span>
        <span class="admin-stat__note">确认后才进入执行队列</span>
      </article>
      <article class="admin-stat">
        <span class="admin-stat__value">{{ jobs.filter(job => ['running', 'queued'].includes(job.status)).length }}</span>
        <span class="admin-stat__label">执行中</span>
        <span class="admin-stat__note">执行器 {{ platform?.worker.healthy ? '在线' : '离线或尚无心跳' }}</span>
      </article>
      <article class="admin-stat is-muted">
        <span class="admin-stat__value">{{ jobs.length }}</span>
        <span class="admin-stat__label">任务记录</span>
        <span class="admin-stat__note">保留最近 100 条</span>
      </article>
    </div>

    <div class="admin-toolbar">
      <div class="admin-filters" role="group" aria-label="发布状态筛选">
        <button type="button" class="admin-filter" :aria-pressed="filter === 'all'" @click="filter = 'all'">全部</button>
        <button type="button" class="admin-filter" :aria-pressed="filter === 'requested'" @click="filter = 'requested'">待确认</button>
        <button type="button" class="admin-filter" :aria-pressed="filter === 'running'" @click="filter = 'running'">执行中</button>
        <button type="button" class="admin-filter" :aria-pressed="filter === 'closed'" @click="filter = 'closed'">已结束</button>
        <button type="button" class="admin-filter" :aria-pressed="filter === 'failed'" @click="filter = 'failed'">失败</button>
      </div>
      <span class="admin-count">{{ filtered.length }} 条</span>
    </div>

    <p v-if="!canApprove" class="admin-banner" role="status">
      当前环境是「{{ environment || '未确认' }}」，发布确认只能在开发工作台执行。这里保留只读记录。
    </p>

    <div v-if="filtered.length" class="admin-job-list" style="margin-top:14px;border-top:1px solid var(--c-border)">
      <article v-for="job in filtered" :key="job.id" class="admin-job">
        <div class="admin-job__top">
          <span class="admin-status" :class="'is-' + jobStatus(job.status).tone">{{ jobStatus(job.status).label }}</span>
          <strong>{{ JOB_KIND[job.kind] || job.kind }}</strong>
          <button v-if="job.status === 'requested' && canApprove" type="button" class="admin-btn admin-btn--sm admin-btn--primary" :disabled="busy" @click="emit('approve', job)">确认执行</button>
          <button v-if="job.events?.length || job.result && Object.keys(job.result).length" type="button" class="admin-btn admin-btn--sm admin-btn--ghost" style="margin-left:auto" @click="toggle(job)">{{ expanded === job.id ? '收起详情' : '查看详情' }}</button>
        </div>
        <div class="admin-job__meta">
          <code :title="job.commit">{{ job.commit.slice(0, 10) }}</code>
          <span>{{ job.actor }}</span>
          <span>{{ shortTime(job.created_at) }}</span>
          <span v-if="job.stage">{{ job.stage }}</span>
        </div>
        <div v-if="job.result?.url" class="admin-job__events">
          <p><a :href="String(job.result.url)" target="_blank" rel="noopener">打开测试环境 ↗</a></p>
        </div>
        <div v-if="expanded === job.id" class="admin-job__events">
          <p v-for="(event, index) in job.events" :key="index"><strong>{{ event.stage || '事件' }}</strong> {{ event.message }}</p>
          <p v-if="!job.events?.length && job.result && Object.keys(job.result).length"><strong>执行结果</strong> {{ JSON.stringify(job.result) }}</p>
        </div>
      </article>
    </div>
    <div v-else class="admin-empty">
      <strong>没有匹配的发布记录</strong>
      <span>{{ jobs.length ? '换一个状态筛选。' : '还没有提交过发布任务。' }}</span>
    </div>
  </section>
</template>
