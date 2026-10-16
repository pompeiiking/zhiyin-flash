<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useRoute} from 'vue-router'
import {backendClient} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import {systemData,loadRecords} from '../lib/system-data'
import {actionRows,dateKey,deadline} from '../lib/action-insights.mjs'
import {usePagedItems} from '../lib/paged-items'
import PageHeading from '../components/PageHeading.vue'
import DetailPopover from '../components/DetailPopover.vue'
import CapabilityGap from '../components/CapabilityGap.vue'
import ResultPager from '../components/ResultPager.vue'
import StatusBanner from '../components/StatusBanner.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
const route=useRoute(),busy=ref(false),error=ref(''),status=ref('')
const tasks=computed(()=>actionRows(backendDemo.state.liveAction))
const completed=computed(()=>tasks.value.filter(t=>t.done))
const pending=computed(()=>tasks.value.filter(t=>!t.done))
const overdue=computed(()=>pending.value.filter(t=>deadline(t.due_date).overdue))
const selectedId=ref(''),reason=ref(''),memo=ref(''),query=ref(''),filter=ref('all')
const choices=['任务太大','方法不对','方向要重估','其他','尚不确定']
const selected=computed(()=>tasks.value.find(t=>t.task_id===selectedId.value))
const prefix=computed(()=>selected.value?'【任务复盘:'+selected.value.task_id+'】':'')
const saved=computed(()=>backendDemo.state.notes.filter(n=>prefix.value&&n.text.startsWith(prefix.value)).slice().sort((a,b)=>b.created_at.localeCompare(a.created_at)))
const noteBody=computed(()=>prefix.value+reason.value+'｜'+memo.value.trim())
const memoLimit=computed(()=>Math.max(0,200-prefix.value.length-reason.value.length-1))
watch(selectedId,()=>{reason.value='';memo.value='';status.value=''})
const records=computed(()=>[
 ...completed.value.map(t=>({id:'task-'+t.task_id,title:t.text,date:t.done_at||'',kind:'done',label:'任务完成',body:t.phase})),
 ...systemData.events.filter(e=>!(e.type==='milestone_done'&&completed.value.some(t=>t.task_id===e.related_task_id))).map(e=>({id:'event-'+e.id,title:e.title,date:e.occurred_at||'',kind:'event',label:'系统记录',body:e.detail||''})),
 ...backendDemo.state.notes.filter(n=>n.text.startsWith('【任务复盘:')).map(n=>({id:'note-'+n.id,title:tasks.value.find(t=>n.text.startsWith('【任务复盘:'+t.task_id+'】'))?.text||'历史任务复盘',date:n.created_at,kind:'review',label:'个人复盘说明',body:n.text.slice(n.text.indexOf('】')+1)}))
].sort((a,b)=>b.date.localeCompare(a.date)))
const filtered=computed(()=>records.value.filter(r=>(filter.value==='all'||r.kind===filter.value)&&[r.title,r.body,r.date].join(' ').includes(query.value.trim())))
const {page,paged}=usePagedItems(filtered,5)
const explanation=computed(()=>reason.value==='任务太大'?'先讨论如何拆成能开始的小步骤。':reason.value==='方法不对'?'把已经尝试的方法与结果一起带入咨询。':reason.value==='方向要重估'?'结合实际进展重新比较方向。':'先记录实际情况，再决定如何调整。')
const question=computed(()=>'我想复盘任务「'+(selected.value?.text||'')+'」，阶段：'+(selected.value?.phase||'')+'。我认为的原因：'+(reason.value||'尚不确定')+'。实际情况：'+memo.value)
async function load(){if(busy.value)return;busy.value=true;error.value='';try{const results=await Promise.allSettled([backendClient.action(),backendClient.notes(),loadRecords()]);if(results[0].status==='fulfilled')backendDemo.setAction(results[0].value);if(results[1].status==='fulfilled')backendDemo.setNotes(results[1].value);const failure=results.find(r=>r.status==='rejected');if(failure?.status==='rejected')throw failure.reason}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function save(){if(busy.value||!selected.value||!reason.value||noteBody.value.length>200)return;busy.value=true;error.value='';try{backendDemo.upsertNote(await backendClient.addNote({kind:'todo',text:noteBody.value}));status.value='复盘说明已保存到个人记录，刷新后仍可查看。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function adjustment(){if(busy.value||!selected.value)return;const text=(reason.value==='任务太大'?'拆小一步：':'核对方法：')+selected.value.text;if(text.length>200){error.value='任务标题过长，请在个人待办中缩短后添加。';return}busy.value=true;error.value='';try{backendDemo.upsertNote(await backendClient.addNote({kind:'todo',text}));status.value='调整待办已保存，尚未排入阶段计划。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
onMounted(load)
</script>
<template><div class="ws-page review-page"><PageHeading title="复盘与记录" description="回看真实执行结果，再决定怎样调整。"><button class="btn" :disabled="busy" @click="load">刷新记录</button><RouterLink class="btn" to="/home">回到今日行动</RouterLink></PageHeading><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load"/><p v-if="status" class="desk-status" role="status">{{status}}</p>
<AchievementsSection v-if="route.query.view==='achievements'"/><template v-else>
<section class="review-overview"><button @click="filter='done'"><strong>{{completed.length}}</strong><span>已完成任务</span></button><button @click="selectedId=overdue[0]?.task_id||''"><strong>{{overdue.length}}</strong><span>已过截止日且未完成</span></button><button @click="filter='review'"><strong>{{records.filter(r=>r.kind==='review').length}}</strong><span>个人复盘说明</span></button><CapabilityGap title="部分完成与正式复盘状态" reason="任务接口没有部分完成状态，也没有复盘结论字段。已过截止日不自动判定为失败；复盘说明使用个人记录保存。"/></section>
<div class="ws-two-columns"><section class="ws-paper"><h2>选择一件事复盘</h2><label class="ws-field">任务<select v-model="selectedId" :disabled="busy"><option value="">选择已完成或未完成的任务</option><optgroup label="尚未完成"><option v-for="t in pending" :key="t.task_id" :value="t.task_id">{{t.text}} · {{deadline(t.due_date).label}}</option></optgroup><optgroup label="已完成"><option v-for="t in completed" :key="t.task_id" :value="t.task_id">{{t.text}}</option></optgroup></select></label>
<template v-if="selected"><p class="ws-muted">{{selected.phase}} · {{selected.done?'已完成':'未完成'}} · {{dateKey(selected.due_date)||'未设日期'}}</p><fieldset class="review-reasons"><legend>你认为主要原因是什么？</legend><label v-for="choice in choices" :key="choice"><input v-model="reason" :disabled="busy" type="radio" name="review-reason" :value="choice"/>{{choice}}</label></fieldset><form @submit.prevent="save"><label class="ws-field">实际情况<textarea v-model="memo" :disabled="busy" :maxlength="memoLimit" rows="3" placeholder="发生了什么、试过什么、得到什么反馈…"/></label><small class="ws-muted">保存为账号内的个人复盘说明，不会自动改变任务状态。</small><div class="ws-inline-actions ws-section"><button class="btn btn--primary" :disabled="busy||!reason||noteBody.length>200">保存复盘说明</button><RouterLink class="btn" :to="'/chat?question='+encodeURIComponent(question)">咨询调整方案</RouterLink></div></form><section v-if="reason" class="ws-review-result"><p>{{explanation}}</p><RouterLink v-if="reason==='方向要重估'" class="btn" to="/directions">重新比较方向</RouterLink><button v-else-if="reason==='任务太大'||reason==='方法不对'" class="btn" :disabled="busy" @click="adjustment">添加调整待办</button></section><section v-if="saved.length" class="ws-section"><h3>这项任务的已保存说明</h3><article v-for="n in saved" :key="n.id"><time class="ws-muted">{{dateKey(n.created_at)}}</time><p>{{n.text.slice(prefix.length)}}</p></article></section></template><p v-else class="ws-empty">选择一项真实任务，核对进展并记录你的判断。</p></section>
<aside class="review-side"><section><h2>近期完成</h2><ul class="ws-mini-list"><li v-for="t in completed.slice().sort((a,b)=>(b.done_at||'').localeCompare(a.done_at||'')).slice(0,4)" :key="t.task_id">{{t.text}}<small class="ws-muted">{{dateKey(t.done_at)||'完成时间未提供'}}</small></li></ul><p v-if="!completed.length" class="ws-muted">还没有已完成任务。</p></section><section class="ws-section"><h2>记录与调整</h2><RouterLink class="ws-text-link" to="/notes">查看个人待办与复盘说明</RouterLink><RouterLink class="ws-text-link" to="/reminders">查看真实提醒</RouterLink><CapabilityGap title="复盘结论回写计划" reason="目前可以记录说明、咨询和保存调整待办；还没有按任务保存结构化归因、复盘状态或直接拆分计划任务的接口。"/></section></aside></div>
<section class="ws-section review-records"><div class="ws-section-head"><h2>执行与成长记录</h2><RouterLink to="/achievements">成长记录</RouterLink></div><div class="review-record-tools"><label class="information-search">查找记录<input v-model="query" type="search" placeholder="任务、日期或复盘关键词"/></label><label class="ws-field">记录类型<select v-model="filter"><option value="all">全部记录</option><option value="done">任务完成</option><option value="review">个人复盘说明</option><option value="event">系统记录</option></select></label></div><ol class="ws-timeline"><li v-for="r in paged" :key="r.id"><time>{{dateKey(r.date)||'未提供日期'}}</time><div class="ws-timeline__content"><strong>{{r.title}}</strong><DetailPopover :title="r.title" :label="'查看记录：'+r.title" side="right"><template #trigger>记录详情</template><p>{{r.body||'没有补充说明。'}}</p><p class="ws-muted">{{r.label}} · {{r.date?new Date(r.date).toLocaleString('zh-CN'):'时间未提供'}}</p></DetailPopover></div><span class="ws-timeline__state">{{r.label}}</span></li></ol><p v-if="!filtered.length&&!busy" class="ws-empty">没有符合条件的记录。</p><ResultPager v-model:page="page" :total="filtered.length" :size="5" label="复盘记录"/></section></template></div></template>
<style scoped>.review-overview{display:flex;flex-wrap:wrap;gap:20px;margin:24px 0 32px}.review-overview>button{display:grid;gap:8px;text-align:left;min-width:160px;padding:16px;border-bottom:2px solid var(--c-border);background:transparent;color:var(--c-text)}.review-overview strong{font-size:32px;color:var(--c-primary)}.review-overview span{font-size:var(--fs-12)}.review-reasons{display:flex;flex-wrap:wrap;gap:12px;border:0;margin:20px 0}.review-reasons legend{margin-bottom:12px}.review-reasons label{display:flex;gap:5px;align-items:center;min-height:40px}.review-record-tools{display:flex;flex-wrap:wrap;gap:20px;align-items:end;margin:16px 0}.review-record-tools .information-search{flex:1;min-width:200px}.review-side small{display:block;margin-top:6px}.ws-timeline__content :deep(.detail-trigger){display:block;margin-top:8px}</style>
