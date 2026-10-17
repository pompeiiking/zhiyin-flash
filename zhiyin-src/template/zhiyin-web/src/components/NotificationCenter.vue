<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {studentApi,type Notice} from '../api/student-capabilities'
import {refreshNotifications} from '../lib/system-data'
import {dateKey} from '../lib/action-insights.mjs'
import {usePagedItems} from '../lib/paged-items'
import ResultPager from './ResultPager.vue'
import DetailPopover from './DetailPopover.vue'
import StatusBanner from './StatusBanner.vue'
const notices=ref<Notice[]>([]),query=ref(''),filter=ref('pending'),busy=ref(false),error=ref(''),status=ref('')
const snooze=ref<Record<string,string>>({}),snoozeError=ref<Record<string,string>>({})
const tabs=[{key:'pending',label:'未读提醒'},{key:'read',label:'已读历史'},{key:'later',label:'稍后处理'},{key:'done',label:'已处理'}]
const filtered=computed(()=>notices.value.filter(n=>n.status===filter.value&&[n.title,n.body,dateKey(n.occurred_at)].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,5,()=>[query.value,filter.value])
const actionRoute=(n:Notice)=>n.action?.kind==='intel'?'/intel':''
async function load(){busy.value=true;error.value='';try{notices.value=await studentApi.notifications();await refreshNotifications(notices.value)}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function change(n:Notice,state:'pending'|'read'|'later'|'done'){if(busy.value)return;status.value='';snoozeError.value[n.id]='';if(state==='later'&&(!snooze.value[n.id]||!Number.isFinite(new Date(snooze.value[n.id]).getTime())||new Date(snooze.value[n.id]).getTime()<=Date.now())){snoozeError.value[n.id]='请选择未来的提醒时间。';return}busy.value=true;error.value='';try{const updated=await studentApi.notification(n.id,{status:state,snoozed_until:state==='later'&&snooze.value[n.id]?new Date(snooze.value[n.id]).toISOString():null});notices.value=notices.value.map(v=>v.id===n.id?updated:v);status.value='提醒状态已保存。';await refreshNotifications(notices.value)}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
onMounted(load)
</script>
<template><section class="restored-notifications"><div class="ws-section-head"><div class="ws-inline-actions"><button v-for="tab in tabs" :key="tab.key" class="btn" :aria-pressed="filter===tab.key" @click="filter=tab.key">{{tab.label}} {{notices.filter(n=>n.status===tab.key).length}}</button></div><button class="btn" :disabled="busy" @click="load">刷新提醒</button></div><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load"/><p v-if="status" role="status">{{status}}</p><p v-if="busy" class="ws-muted" role="status">正在同步提醒…</p><label class="information-search">查找提醒<input v-model="query" type="search" placeholder="事项、内容或日期"/></label><article v-for="n in paged" :key="n.id" class="c2-reminder"><header class="ws-section-head"><h2>{{n.title}}</h2><time>{{dateKey(n.occurred_at)}}</time></header><p>{{n.body}}</p><p v-if="n.status==='later'&&n.snoozed_until" class="ws-muted">再次提醒：{{new Date(n.snoozed_until).toLocaleString()}}</p><div class="ws-inline-actions"><button v-if="n.status==='pending'" class="btn" :disabled="busy" @click="change(n,'read')">标为已读</button><button v-if="n.status!=='done'" class="btn" :disabled="busy" @click="change(n,'done')">标为已处理</button><button v-if="n.status!=='pending'" class="btn" :disabled="busy" @click="change(n,'pending')">恢复待处理</button><DetailPopover title="稍后再提醒" side="right"><template #trigger>稍后处理</template><label class="ws-field">提醒时间<input v-model="snooze[n.id]" type="datetime-local"/></label><button class="btn" :disabled="busy||!snooze[n.id]" @click="change(n,'later')">保存提醒时间</button><p v-if="snoozeError[n.id]" class="ws-field-error" role="alert">{{snoozeError[n.id]}}</p><p v-if="error" class="ws-field-error" role="alert">{{error}}</p><p v-if="status" role="status">{{status}}</p><p>仅调整提醒状态，不自动完成关联任务。</p></DetailPopover><RouterLink v-if="actionRoute(n)" class="btn" :to="actionRoute(n)">{{n.action?.label||'查看相关资讯'}}</RouterLink><DetailPopover title="关联信息" side="right"><template #trigger>关联信息</template><p>{{n.body}}</p><RouterLink class="ws-text-link" to="/plan">核对阶段计划</RouterLink></DetailPopover></div></article><p v-if="!filtered.length&&!busy&&!error" class="ws-empty">{{query?'没有匹配的提醒。':'此分类暂无提醒。'}}</p><ResultPager v-model:page="page" :total="filtered.length" :size="5" label="提醒"/></section></template>
<style scoped>
.restored-notifications > .information-search { margin: 24px 0; }
.restored-notifications [aria-pressed='true'] { border-color: var(--c-primary); background: var(--c-primary-weak); color: var(--c-primary); }
.c2-reminder h2 { min-width: 0; font-size: var(--fs-16); overflow-wrap: anywhere; }
.c2-reminder time { flex: none; white-space: nowrap; }
.c2-reminder .ws-inline-actions { margin-top: 16px; gap: 12px; }

@media (max-width: 600px) {
  .restored-notifications > .ws-section-head { align-items: stretch; flex-direction: column; }
  .restored-notifications > .ws-section-head .ws-inline-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .restored-notifications > .ws-section-head .btn { width: 100%; }
  .c2-reminder .ws-section-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 10px; }
  .c2-reminder .ws-inline-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .c2-reminder .ws-inline-actions > * { width: 100%; min-width: 0; }
}
</style>
