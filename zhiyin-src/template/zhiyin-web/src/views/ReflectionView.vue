<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRoute} from 'vue-router'
import {backendClient} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import {systemData,loadRecords} from '../lib/system-data'
import {actionRows,dateKey,deadline} from '../lib/action-insights.mjs'
import {usePagedItems} from '../lib/paged-items'
import type {Review} from '../api/student-capabilities'
import StructuredReview from '../components/StructuredReview.vue'
import PageHeading from '../components/PageHeading.vue'
import DetailPopover from '../components/DetailPopover.vue'
import ResultPager from '../components/ResultPager.vue'
import StatusBanner from '../components/StatusBanner.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
const route=useRoute(),busy=ref(false),error=ref(''),status=ref('')
const tasks=computed(()=>actionRows(backendDemo.state.liveAction))
const completed=computed(()=>tasks.value.filter(t=>t.done))
const pending=computed(()=>tasks.value.filter(t=>!t.done))
const overdue=computed(()=>pending.value.filter(t=>deadline(t.due_date).overdue))
const selectedId=ref(''),query=ref(''),filter=ref('all')
const reviews=ref<Review[]>([])
const records=computed(()=>[
 ...reviews.value.map(r=>({id:r.id,title:r.task_text,date:r.updated_at,kind:'review',label:r.applied_at?'复盘已应用':'任务复盘',body:r.reason+' · '+(r.note||'')})),
 ...completed.value.map(t=>({id:'task-'+t.task_id,title:t.text,date:t.done_at||'',kind:'done',label:'任务完成',body:t.phase})),
 ...systemData.events.filter(e=>!(e.type==='milestone_done'&&completed.value.some(t=>t.task_id===e.related_task_id))).map(e=>({id:'event-'+e.id,title:e.title,date:e.occurred_at||'',kind:'event',label:'系统记录',body:e.detail||''})),
 ...backendDemo.state.notes.filter(n=>n.text.startsWith('【任务复盘:')).map(n=>({id:'note-'+n.id,title:tasks.value.find(t=>n.text.startsWith('【任务复盘:'+t.task_id+'】'))?.text||'历史任务复盘',date:n.created_at,kind:'review',label:'个人复盘说明',body:n.text.slice(n.text.indexOf('】')+1)}))
].sort((a,b)=>b.date.localeCompare(a.date)))
const filtered=computed(()=>records.value.filter(r=>(filter.value==='all'||r.kind===filter.value)&&[r.title,r.body,r.date].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,5)
async function load(){if(busy.value)return;busy.value=true;error.value='';try{const results=await Promise.allSettled([backendClient.action(),backendClient.notes(),loadRecords()]);if(results[0].status==='fulfilled')backendDemo.setAction(results[0].value);if(results[1].status==='fulfilled')backendDemo.setNotes(results[1].value);const failure=results.find(r=>r.status==='rejected');if(failure?.status==='rejected')throw failure.reason}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
onMounted(load)
</script>
<template><div class="ws-page review-page"><PageHeading title="复盘与记录" description="回看真实执行结果，再决定怎样调整。"><button class="btn" :disabled="busy" @click="load">刷新记录</button><RouterLink class="btn" to="/home">回到今日行动</RouterLink></PageHeading><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load"/><p v-if="status" class="desk-status" role="status">{{status}}</p>
<AchievementsSection v-if="route.query.view==='achievements'" :auto-load="false"/><template v-else>
<section class="review-overview"><button @click="filter='done'"><strong>{{completed.length}}</strong><span>已完成任务</span></button><button @click="selectedId=overdue[0]?.task_id||''"><strong>{{overdue.length}}</strong><span>已过截止日且未完成</span></button><button @click="filter='review'"><strong>{{records.filter(r=>r.kind==='review').length}}</strong><span>个人复盘说明</span></button></section>
<StructuredReview :task-id="selectedId" @loaded="reviews=$event"/>
<section class="ws-section review-records"><div class="ws-section-head"><h2>执行与成长记录</h2><RouterLink to="/achievements">完成记录</RouterLink></div><div class="review-record-tools"><label class="information-search">查找记录<input v-model="query" type="search" placeholder="任务、日期或复盘关键词"/></label><label class="ws-field">记录类型<select v-model="filter"><option value="all">全部记录</option><option value="done">任务完成</option><option value="review">个人复盘说明</option><option value="event">系统记录</option></select></label></div><ol class="ws-timeline"><li v-for="r in paged" :key="r.id"><time>{{dateKey(r.date)||'未提供日期'}}</time><div class="ws-timeline__content"><strong>{{r.title}}</strong><DetailPopover :title="r.title" :label="'查看记录：'+r.title" side="right"><template #trigger>记录详情</template><p>{{r.body||'没有补充说明。'}}</p><p class="ws-muted">{{r.label}} · {{r.date?new Date(r.date).toLocaleString('zh-CN'):'时间未提供'}}</p></DetailPopover></div><span class="ws-timeline__state">{{r.label}}</span></li></ol><p v-if="!filtered.length&&!busy" class="ws-empty">没有符合条件的记录。</p><ResultPager v-model:page="page" :total="filtered.length" :size="5" label="复盘记录"/></section></template></div></template>
<style scoped>.review-overview{display:flex;flex-wrap:wrap;gap:20px;margin:24px 0 32px}.review-overview>button{display:grid;gap:8px;text-align:left;min-width:160px;padding:16px;border-bottom:2px solid var(--c-border);background:transparent;color:var(--c-text)}.review-overview strong{font-size:32px;color:var(--c-primary)}.review-overview span{font-size:var(--fs-12)}.review-reasons{display:flex;flex-wrap:wrap;gap:12px;border:0;margin:20px 0}.review-reasons legend{margin-bottom:12px}.review-reasons label{display:flex;gap:5px;align-items:center;min-height:40px}.review-record-tools{display:flex;flex-wrap:wrap;gap:20px;align-items:end;margin:16px 0}.review-record-tools .information-search{flex:1;min-width:200px}.review-side small{display:block;margin-top:6px}.ws-timeline__content :deep(.detail-trigger){display:block;margin-top:8px}</style>
