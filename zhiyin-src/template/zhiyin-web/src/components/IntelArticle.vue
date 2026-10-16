<script setup lang="ts">
import { computed } from 'vue'
import type { IntelItemView } from '../api/backend-types'
import UiIcon from './UiIcon.vue'

const props = defineProps<{ item: IntelItemView }>()

const kindLabel = computed(() => ({
  speciality: '专业信息',
  occupation: '职业方向',
  career_case: '校友去向',
  job_requirement: '岗位要求',
  industry: '行业情况',
}[props.item.kind ?? ''] ?? props.item.kind_label ?? '参考资料'))

const contentTitle = computed(() => {
  if (props.item.kind === 'speciality') return '专业介绍与毕业去向'
  if (props.item.kind === 'occupation') return '职业介绍与能力要求'
  if (props.item.kind === 'career_case') return '校友经历'
  return '资料详情'
})

const sourceNotice = computed(() => props.item.kind === 'speciality' || props.item.kind === 'career_case'
  ? '这是一份公开参考资料，请结合自己的情况理解，不把单一信息当作选择结论。'
  : '职业与招聘信息可能随时间变化，请以原始来源的最新内容为准。')

const DATE = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })

function safeSource(url?: string) {
  return url && /^https?:\/\//i.test(url) ? url : undefined
}

function formatDate(value?: string) {
  if (!value) return '时间待补充'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间待补充' : DATE.format(date)
}
</script>

<template>
  <article class="intel-article">
    <header>
      <span class="intel-article__kind">{{ kindLabel }}</span>
      <h2>{{ item.title || '未命名岗位资料' }}</h2>
      <div class="intel-article__byline">
        <span>{{ item.source_name || '来源待补充' }}</span>
        <i aria-hidden="true"></i>
        <time :datetime="item.fetched_at">{{ formatDate(item.fetched_at) }}</time>
      </div>
    </header>

    <section class="intel-article__content" aria-labelledby="intel-article-content-title">
      <h3 id="intel-article-content-title">{{ contentTitle }}</h3>
      <p v-if="item.text">{{ item.text }}</p>
      <p v-else class="intel-article__missing">这条资料暂时没有正文，请前往原始来源核对。</p>
    </section>

    <footer>
      <p>{{ sourceNotice }}</p>
      <a v-if="safeSource(item.source_url)" class="btn btn--primary" :href="safeSource(item.source_url)" target="_blank" rel="noopener noreferrer">
        查看原始来源 <UiIcon name="arrow" :size="16" />
      </a>
      <span v-else class="intel-article__missing">原始链接待补充</span>
    </footer>
  </article>
</template>

<style scoped>
.intel-article { width: 100%; min-width: 0; }
.intel-article header { padding-bottom: 24px; border-bottom: 1px solid var(--c-border); }
.intel-article__kind { display: inline-flex; align-items: center; min-height: 26px; padding: 0 9px; border: 1px solid var(--c-primary-border); border-radius: 999px; background: var(--c-primary-weak); color: var(--c-primary); font-size: 11px; font-weight: 650; }
.intel-article h2 { max-width: 30em; margin-top: 12px; font-size: clamp(20px, 2.2vw, 27px); font-weight: 700; line-height: 1.45; text-wrap: balance; overflow-wrap: anywhere; }
.intel-article__byline { display: flex; align-items: center; gap: 9px; margin-top: 13px; color: var(--c-text-3); font-size: 12px; }
.intel-article__byline i { width: 3px; height: 3px; border-radius: 50%; background: currentColor; }
.intel-article__content { padding: 24px 0 28px; }
.intel-article__content h3 { margin-bottom: 13px; font-size: 14px; font-weight: 700; }
.intel-article__content p { max-width: 62em; color: var(--c-text-2); font-size: 14px; line-height: 1.9; white-space: pre-line; overflow-wrap: anywhere; }
.intel-article footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding-top: 20px; border-top: 1px solid var(--c-border); }
.intel-article footer > p { max-width: 36em; color: var(--c-text-3); font-size: 12px; line-height: 1.7; }
.intel-article footer .btn { display: inline-flex; flex: none; align-items: center; gap: 7px; }
.intel-article__missing { color: var(--c-text-3); }

@media (max-width: 640px) {
  .intel-article h2 { font-size: 21px; }
  .intel-article footer { align-items: stretch; flex-direction: column; }
  .intel-article footer .btn { justify-content: center; width: 100%; }
}
</style>
