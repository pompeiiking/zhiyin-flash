<script setup lang="ts">
import DetailPopover from './DetailPopover.vue'
import { computed, ref, onMounted } from 'vue'
import { growthRecords } from '../lib/growth-records'
import {loadRecords} from '../lib/system-data'
const error=ref('')
onMounted(()=>loadRecords().catch(e=>{error.value=e.message}))
import UiIcon from './UiIcon.vue'
const query=ref('')
const records=computed(()=>growthRecords.value.filter(r=>(r.title+' '+r.topic+' '+r.source).includes(query.value.trim())))
const completed=computed(()=>growthRecords.value.filter(r=>r.done))
const topicLink=(topic:string)=>topic==='做决定'?'/directions':topic==='去做'?'/home':topic==='回头看'?'/review':'/chat'
</script>
<template>
<p v-if="error" class="ws-field-error" role="alert">{{error}} <button @click="loadRecords().catch(e=>error=e.message)">重新读取</button></p><section class="growth-overview"><div><h2>每一步，都有记录</h2><p>从了解自己到采取行动，回看已经发生的改变。</p></div><div class="growth-overview__count"><strong>{{ completed.length }}</strong><span>/ {{ growthRecords.length }} 项已完成</span></div></section>
<section class="growth-workspace"><header class="growth-workspace__toolbar"><h2>成长足迹</h2><label class="intelligence-search"><UiIcon name="search" :size="16"/><input v-model="query" type="search" aria-label="查找成长记录" placeholder="查找名称、主题或来源"/></label></header>
<div class="growth-milestones"><article v-for="r in records" :key="r.id" class="growth-milestone" :class="{'is-complete':r.done}" :data-record-id="r.id"><span class="growth-milestone__mark"><UiIcon :name="r.done?'check':'review'" :size="20"/></span><div class="growth-milestone__body"><span class="growth-milestone__topic">{{ r.topic }}</span><h3>{{ r.title }}</h3><p>{{ r.done ? (r.at ? new Date(r.at).toLocaleDateString('zh-CN') : '已记录') : '等待行动记录' }}</p><DetailPopover :title="r.title+' · 完成依据'" :label="'查看'+r.title+'完成依据'"><template #trigger>查看依据<UiIcon name="info" :size="14"/></template><p>{{ r.source }} · {{ r.method }}</p><ul><li v-for="line in r.evidence" :key="line">{{ line }}</li></ul><p>{{ r.next }}</p></DetailPopover></div><RouterLink v-if="!r.done" :to="r.id==='academic-verification'?'/academic':topicLink(r.topic)" class="growth-milestone__action" :aria-label="'继续：'+r.title"><UiIcon name="arrow" :size="18"/></RouterLink></article></div>
<p v-if="!records.length" class="ws-muted">没有匹配的记录，请调整关键词。</p>
</section>
</template>
