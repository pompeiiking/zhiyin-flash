<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
const query = ref('')
const status = ref('')
const matchOpen = ref(false)
const items = computed(() => backendDemo.state.intel.filter(i => (i.title + ' ' + i.text + ' ' + i.kind_label).includes(query.value.trim())))
function refresh() { backendDemo.loadIntelSample(); status.value = '已加载资料来源的演示条目。它们不是实时岗位搜索结果。' }
</script>
<template>
  <div class="ws-page">
    <PageHeading title="岗位资讯" description="检索职业与就业资讯，核对信息来源和获取时间。"><button class="btn" @click="matchOpen = true"><UiIcon name="compass" :size="16" />职业匹配</button></PageHeading>
    <div class="ws-two-columns">
      <section class="ws-paper"><form class="desk-note-form" style="margin-top: 0" @submit.prevent="refresh"><label for="desk-intel-query" class="sr-only">筛选资讯</label><input id="desk-intel-query" v-model="query" placeholder="找专业、职业或核验信息…" /><button class="btn btn--primary" type="submit"><UiIcon name="search" :size="16" />读取示例</button></form><p v-if="status" class="desk-status" role="status">{{ status }}</p><template v-if="items.length"><article v-for="item in items" :key="item.id" class="desk-intel-item"><h2>{{ item.title }}</h2><p>{{ item.text }}</p><div class="desk-intel-item__source"><span>{{ item.kind_label }} · {{ new Date(item.fetched_at ?? '').toLocaleDateString('zh-CN') }}</span><a class="ws-text-link" :href="item.source_url" target="_blank" rel="noopener noreferrer">{{ item.source_name }}<UiIcon name="arrow" :size="16" /></a></div></article></template><div v-else class="ws-empty"><UiIcon name="compass" :size="40" /><h3 style="margin-top: var(--sp-4)">{{ backendDemo.state.intel.length ? '这批资料里暂时没有匹配的内容' : '还没有取回外部资料' }}</h3><p>正式后端会按主题与画像筛选，只展示能找到来源链接的条目。</p><button v-if="!backendDemo.state.intel.length" class="ws-text-button" @click="refresh">加载资讯示例<UiIcon name="arrow" :size="16" /></button><button v-else class="ws-text-button" @click="query = ''">清除筛选</button></div></section>
      <aside class="ws-aside"><section><h2>资讯与方向分析</h2><p>资讯给出外部事实。与你的能力、经历怎样对应，需要回到报告与方向方案。</p><RouterLink class="ws-text-link" to="/directions">查看方向方案<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>来源与时效</h2><p>正式条目会保留来源名称、原链接与取回时间。没有来源的内容不展示。</p></section></aside>
    </div><p class="ws-demo-note">演示来源卡不含实时招聘事实。当前未发起真实外部搜索。</p>
    <InfoSheet :open="matchOpen" title="职业匹配" @close="matchOpen = false"><p>职业匹配会把已有画像与职业信息放在一起比较，包括契合依据、排序和推荐。</p><p class="ws-muted ws-section">当前可查看预置的方向方案。真实匹配矩阵由后端生成。</p><RouterLink class="btn btn--primary ws-section" to="/directions" @click="matchOpen = false">查看方向示例<UiIcon name="arrow" :size="16" /></RouterLink></InfoSheet>
  </div>
</template>
