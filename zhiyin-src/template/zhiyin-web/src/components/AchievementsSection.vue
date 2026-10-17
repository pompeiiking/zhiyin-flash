<script setup lang="ts">
import { featureEnabled } from '../lib/features'
import { computed, onMounted, ref } from 'vue'
import { growthRecords } from '../lib/growth-records'
import { loadAchievements, systemData } from '../lib/system-data'
import DetailPopover from './DetailPopover.vue'
import StatusBanner from './StatusBanner.vue'
import UiIcon from './UiIcon.vue'

const props = withDefaults(defineProps<{ autoLoad?: boolean }>(), { autoLoad: true })
const busy = ref(false)
const error = ref('')
const loaded = computed(() => systemData.achievements !== null)
const records = computed(() => growthRecords.value)
const completed = computed(() => records.value.filter(record => record.done))
const pending = computed(() => records.value.filter(record => !record.done))
const completedCount = computed(() => systemData.achievements?.unlocked ?? completed.value.length)
const totalCount = computed(() => systemData.achievements?.total ?? records.value.length)
const completedRecords = computed(() => [...completed.value].sort((left, right) => {
  const timeDifference = new Date(right.at ?? 0).getTime() - new Date(left.at ?? 0).getTime()
  return timeDifference || left.order - right.order
}))
const latestCompleted = computed(() => completedRecords.value[0] ?? null)
const completedGroups = computed(() => {
  const groups = new Map<string, { label: string; items: typeof completedRecords.value }>()
  completedRecords.value.forEach(record => {
    const date = record.at ? new Date(record.at) : null
    const validDate = date && !Number.isNaN(date.getTime()) ? date : null
    const key = validDate
      ? `${validDate.getFullYear()}-${validDate.getMonth() + 1}-${validDate.getDate()}`
      : 'unknown'
    const existing = groups.get(key)
    if (existing) existing.items.push(record)
    else groups.set(key, { label: validDate ? formatGroupDate(validDate) : '日期未提供', items: [record] })
  })
  return [...groups.entries()].map(([key, group]) => ({ key, ...group }))
})

function formatClock(value: string | null) {
  if (!value) return '时间未提供'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未提供'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date)
}

function formatDateTime(value: string | null) {
  if (!value) return '时间未提供'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未提供'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  }).format(date)
}

function formatGroupDate(date: Date) {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const sameDay = (left: Date, right: Date) => left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth() && left.getDate() === right.getDate()
  const exact = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }).format(date)
  if (sameDay(date, today)) return `今天，${exact}`
  if (sameDay(date, yesterday)) return `昨天，${exact}`
  return exact
}

async function refresh() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await loadAchievements()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '完成记录读取失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  if (props.autoLoad) void refresh()
})
</script>

<template>
  <section v-if="featureEnabled('achievements')" class="growth-page" aria-label="完成记录">
    <StatusBanner
      v-if="error"
      tone="error"
      title="完成记录暂时没有读到"
      :message="error"
      :retrying="busy"
      :dismissible="false"
      retry-label="重新读取"
      @retry="refresh"
    />

    <div v-if="busy && !loaded" class="growth-loading" role="status" aria-live="polite">
      <span>正在读取完成记录</span>
      <div v-for="index in 3" :key="index" class="growth-loading__row" aria-hidden="true">
        <i></i><div><b></b><small></small></div>
      </div>
    </div>

    <template v-else-if="loaded && records.length">
      <section class="growth-ledger" aria-labelledby="growth-summary-title">
        <div class="growth-ledger__intro">
          <h2 id="growth-summary-title">你做过的关键行动，都有记录</h2>
          <p>记录由系统根据真实行为自动形成，可以随时核对形成条件与时间。</p>
        </div>
        <div class="growth-ledger__summary">
          <p><strong>{{ completedCount }}</strong><span>项已记录</span><small>共 {{ totalCount }} 个关键节点</small></p>
          <p class="growth-ledger__recent">
            <span>最近记录</span>
            <strong>{{ latestCompleted?.title || '还没有记录' }}</strong>
            <time :datetime="latestCompleted?.at || undefined">{{ latestCompleted ? formatDateTime(latestCompleted.at) : '完成关键行动后会出现在这里' }}</time>
          </p>
        </div>
      </section>

      <section v-if="pending.length" class="growth-queue" aria-labelledby="growth-queue-title">
        <header class="growth-section-head">
          <div>
            <h2 id="growth-queue-title">建议补上的记录</h2>
            <p>这些节点不要求依次完成，选择当前最值得推进的一项即可。</p>
          </div>
          <span>{{ pending.length }} 项待补充</span>
        </header>
        <ul class="growth-queue__list">
          <li v-for="record in pending" :key="record.id" class="growth-queue__item" :data-record-id="record.id">
            <span class="growth-queue__mark" aria-hidden="true"><UiIcon name="path" :size="20" /></span>
            <div class="growth-queue__body">
              <div><span>{{ record.stage }}</span><strong>待补充</strong></div>
              <h3>{{ record.title }}</h3>
              <p>{{ record.purpose }}</p>
              <p class="growth-queue__condition"><span>形成条件</span>{{ record.requirement }}</p>
            </div>
            <div class="growth-queue__actions">
              <RouterLink :to="record.to" class="btn btn--primary">
                {{ record.actionLabel }}<UiIcon name="arrow" :size="17" />
              </RouterLink>
              <DetailPopover :title="record.title + '记录说明'" :label="'查看' + record.title + '的记录说明'">
                <template #trigger>记录说明<UiIcon name="info" :size="15" /></template>
                <dl class="growth-detail-list">
                  <dt>记录作用</dt><dd>{{ record.purpose }}</dd>
                  <dt>形成条件</dt><dd>{{ record.requirement }}</dd>
                  <dt>记录状态</dt><dd>待补充</dd>
                  <dt>数据来源</dt><dd>{{ record.source }}</dd>
                </dl>
              </DetailPopover>
            </div>
          </li>
        </ul>
      </section>

      <section v-else class="growth-all-done" aria-label="所有关键行动均已记录">
        <UiIcon name="check" :size="20" />
        <div><strong>关键行动已经全部留下记录</strong><p>可以继续行动，并在复盘中记录新的变化。</p></div>
      </section>

      <section class="growth-archive" aria-labelledby="growth-archive-title">
        <header class="growth-section-head">
          <div>
            <h2 id="growth-archive-title">已经留下的记录</h2>
            <p>按实际形成时间倒序展示，不代表必须按阶段顺序推进。</p>
          </div>
          <button class="ws-text-button" type="button" :disabled="busy" @click="refresh">
            {{ busy ? '正在刷新…' : '刷新记录' }}
          </button>
        </header>
        <div v-if="completedGroups.length" class="growth-archive__groups">
          <section v-for="group in completedGroups" :key="group.key" class="growth-archive__group">
            <header><time>{{ group.label }}</time><span>{{ group.items.length }} 条记录</span></header>
            <ul class="growth-archive__list">
              <li v-for="record in group.items" :key="record.id" class="growth-archive__item" :data-record-id="record.id">
                <time class="growth-archive__time" :datetime="record.at || undefined">{{ formatClock(record.at) }}</time>
                <span class="growth-archive__mark" aria-hidden="true"><UiIcon name="check" :size="18" /></span>
                <div class="growth-archive__body">
                  <span>{{ record.stage }}</span>
                  <h3>{{ record.title }}</h3>
                  <p>{{ record.purpose }}</p>
                </div>
                <div class="growth-archive__meta">
                  <DetailPopover :title="record.title + '记录说明'" :label="'查看' + record.title + '的记录说明'">
                    <template #trigger>记录说明<UiIcon name="info" :size="15" /></template>
                    <dl class="growth-detail-list">
                      <dt>记录作用</dt><dd>{{ record.purpose }}</dd>
                      <dt>形成条件</dt><dd>{{ record.requirement }}</dd>
                      <dt>记录时间</dt><dd>{{ formatDateTime(record.at) }}</dd>
                      <dt>数据来源</dt><dd>{{ record.source }}</dd>
                    </dl>
                  </DetailPopover>
                </div>
              </li>
            </ul>
          </section>
        </div>
        <p v-else class="growth-archive__empty">完成关键行动后，记录会自动出现在这里。</p>
      </section>
    </template>

    <section v-else-if="loaded" class="ws-empty" aria-labelledby="growth-summary-title">
      <h2 id="growth-summary-title">当前没有可用的完成记录</h2>
      <p>服务端暂未返回记录规则，可以稍后重新读取。</p>
      <button class="btn" type="button" :disabled="busy" @click="refresh">重新读取</button>
    </section>
  </section>
</template>
