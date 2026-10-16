<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {backendClient} from '../api/backend-client'
import {refreshNotifications} from '../lib/system-data'
import type {CoachNotificationView} from '../api/backend-types'
import {dateKey} from '../lib/action-insights.mjs'
import {usePagedItems} from '../lib/paged-items'
import ResultPager from './ResultPager.vue'
import DetailPopover from './DetailPopover.vue'
import CapabilityGap from './CapabilityGap.vue'
import StatusBanner from './StatusBanner.vue'
const notices=ref<CoachNotificationView[]>([]),receipts=ref<CoachNotificationView[]>([]),query=ref(''),filter=ref('pending'),busy=ref(false),error=ref(''),status=ref('')
const actionRoute=(n:CoachNotificationView)=>n.action?.kind==='intel'?'/intel':''
const tabs=[{key:'pending',label:'未读提醒'},{key:'read',label:'本次已读'},{key:'later',label:'稍后处理'},{key:'done',label:'已处理'}]
const source=computed(()=>filter.value==='pending'?notices.value:filter.value==='read'?receipts.value:[])
const filtered=computed(()=>source.value.filter(n=>[n.title,n.body,dateKey(n.occurred_at)].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,5)
async function load(){if(busy.value)return;busy.value=true;error.value='';try{notices.value=await backendClient.notifications();await refreshNotifications()}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function read(n:CoachNotificationView){if(busy.value)return;busy.value=true;error.value='';try{const receipt=await backendClient.notificationRead(n.id);if(!receipt.read)throw new Error('未能确认已读状态。');notices.value=notices.value.filter(item=>item.id!==n.id);receipts.value=[n,...receipts.value.filter(item=>item.id!==n.id)];status.value='已标为已读，尚不代表该事项已处理。';await refreshNotifications()}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
onMounted(load)
</script>
<template><section class="restored-notifications"><div class="ws-section-head"><div class="ws-inline-actions"><button v-for="tab in tabs" :key="tab.key" class="btn" :aria-pressed="filter===tab.key" @click="filter=tab.key">{{tab.label}}<span v-if="tab.key==='pending'"> {{notices.length}}</span><span v-if="tab.key==='read'"> {{receipts.length}}</span></button></div><button class="btn" :disabled="busy" @click="load">{{busy?'正在读取…':'刷新提醒'}}</button></div><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load"/><p v-if="status" class="desk-status" role="status">{{status}}</p>
<label class="information-search">查找提醒<input v-model="query" type="search" placeholder="事项、内容或日期"/></label>
<p v-if="filter==='read'" class="ws-muted">仅显示本次打开页面后、已由服务确认的已读回执。历史已读列表尚未开放，离开或刷新后不保留此展示。</p>
<template v-if="filter==='later'||filter==='done'"><p class="ws-empty">{{filter==='later'?'稍后处理':'处理记录'}}尚未开放，当前不能读取或保存这类状态。</p><CapabilityGap title="稍后、已处理与恢复待处理" reason="当前提醒服务仅支持未读列表与标记已读，没有稍后时间、处理状态、恢复和历史查询接口。"/></template>
<article v-for="n in paged" :key="n.id" class="c2-reminder"><header class="ws-section-head"><h2>{{n.title}}</h2><time class="ws-muted">{{dateKey(n.occurred_at)||'未提供日期'}}</time></header><p>{{n.body}}</p><div class="ws-inline-actions"><button v-if="filter==='pending'" class="btn" :disabled="busy" @click="read(n)">标为已读</button><RouterLink v-if="actionRoute(n)" class="btn" :to="actionRoute(n)">{{typeof n.action?.label==='string'?n.action.label:'查看相关资讯'}}</RouterLink><RouterLink class="btn" :to="'/chat?question='+encodeURIComponent('我想处理这条提醒：'+n.title+'。'+(n.body||''))">讨论这件事</RouterLink><DetailPopover title="关联信息" :label="'查看提醒关联：'+n.title" side="right"><template #trigger>关联信息</template><p>{{n.body}}</p><p class="ws-muted">{{n.related_task_id?'这条提醒包含关联任务，处理前请核对具体事项。':'当前没有返回关联任务。'}}</p><RouterLink class="ws-text-link" to="/plan">核对阶段计划</RouterLink></DetailPopover><CapabilityGap title="稍后再看 / 标记已处理" reason="尚不能保存稍后时间或处理结果。标记已读不会自动完成任务，也不会新增行动。"/></div></article>
<p v-if="!filtered.length&&!busy&&(filter==='pending'||filter==='read')" class="ws-empty">{{query?'没有匹配的提醒。':filter==='pending'?'当前没有未读提醒。':'本次还没有已读回执。'}}</p><ResultPager v-model:page="page" :total="filtered.length" :size="5" label="提醒"/><RouterLink class="ws-text-link" to="/settings">提醒偏好与设置</RouterLink></section></template>
<style scoped>.restored-notifications>.information-search{margin:24px 0}.restored-notifications [aria-pressed=true]{border-color:var(--c-primary);background:var(--c-primary-weak);color:var(--c-primary)}.c2-reminder h2{font-size:var(--fs-16)}.c2-reminder .ws-inline-actions{margin-top:16px;gap:12px}</style>
