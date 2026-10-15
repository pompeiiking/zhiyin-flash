<script setup lang="ts">
import type { IntelItemView } from '../api/backend-types'
import ReadableText from './ReadableText.vue'
import UiIcon from './UiIcon.vue'
defineProps<{ item: IntelItemView; checks: {title:string;detail:string}[] }>()
const safeSource=(url?:string)=>url&&/^https?:\/\//i.test(url)?url:undefined
</script>
<template>
  <article class="intel-reader">
    <header class="intel-reader__header">
      <span class="intel-reader__kind">{{ item.kind_label || '资讯' }}</span>
      <h2>{{ item.title || '资讯正文' }}</h2>
      <p>{{ item.source_name || '来源待核对' }}<span v-if="item.fetched_at"> · 读取于 {{ item.fetched_at.slice(0,10) }}</span></p>
      <a v-if="safeSource(item.source_url)" class="btn btn--primary" :href="safeSource(item.source_url)" target="_blank" rel="noopener noreferrer">打开原始来源 <UiIcon name="arrow" :size="16"/></a>
    </header>
    <section class="intel-reader__body"><h3>资讯内容</h3><ReadableText :text="item.text || '本条资讯未提供正文。'"/></section>
    <section class="intel-reader__checks"><h3>使用前核对</h3><ul><li v-for="check in checks" :key="check.title"><UiIcon name="check" :size="16"/><div><strong>{{ check.title }}</strong><p>{{ check.detail }}</p></div></li></ul></section>
    <p v-if="!safeSource(item.source_url)" class="intel-reader__source">本条未提供原始来源链接。申请岗位前，请以招聘方最新公告为准。</p>
  </article>
</template>
