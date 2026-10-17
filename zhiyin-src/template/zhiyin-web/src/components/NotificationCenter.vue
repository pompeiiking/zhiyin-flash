<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {studentApi,type Notice} from '../api/student-capabilities'
import {refreshNotifications} from '../lib/system-data'
import {dateKey} from '../lib/action-insights.mjs'
import {usePagedItems} from '../lib/paged-items'
import ResultPager from './ResultPager.vue'
import DetailPopover from './DetailPopover.vue'
import StatusBanner from './StatusBanner.vue'

/**
 * 提醒页（#11 / #22）。
 *
 * 两条改动：
 *  1. 后端会为同一件事重复投递提醒（标题+正文完全相同、只差时间），三张卡片读起来一模一样。
 *     这里按"标题+正文"合并成一张，卡片上写明"同一条提醒 N 次"，展开后列出每条的时间与编号，
 *     不需要的重复项也能看到自己是哪一条。
 *  2. 「看看是什么」（后端 action.label）原来只是一个跳走链接，看完回来仍是未读，像点了没反应。
 *     现在它先就地展开详情（时间、编号、状态、去对应页面的入口），并在点开时用
 *     POST /app/notifications/{id}/read 标记已读；同内容的多条一起标，顶部未读数随之减少。
 *     已标读的卡片在这一屏保留（justRead），避免点完立刻消失、看不到展开了什么。
 */

type NoticeGroup = { key: string; notice: Notice; items: Notice[]; ids: string[] }
type NoticeState = 'pending' | 'read' | 'later' | 'done'

const notices=ref<Notice[]>([]),query=ref(''),filter=ref('pending'),busy=ref(false),error=ref(''),status=ref('')
const snooze=ref<Record<string,string>>({}),snoozeError=ref<Record<string,string>>({})
const justRead=ref<string[]>([])
const expanded=ref<string[]>([])
const tabs=[{key:'pending',label:'未读提醒'},{key:'read',label:'已读历史'},{key:'later',label:'稍后处理'},{key:'done',label:'已处理'}]
const statusLabels:Record<string,string>={pending:'待处理',read:'已读',later:'稍后处理',done:'已处理'}
/** 当前分类 + 本屏刚点开的已读项（点开后不立刻消失，便于看到展开的详情）。 */
const visible=computed(()=>notices.value.filter(n=>n.status===filter.value||(filter.value==='pending'&&justRead.value.includes(n.id))))
const filtered=computed(()=>visible.value.filter(n=>[n.title,n.body,dateKey(n.occurred_at)].join(' ').includes(query.value.trim())))
const groups=computed<NoticeGroup[]>(()=>{
  const map=new Map<string,Notice[]>()
  for(const notice of filtered.value){
    const key=[notice.title,notice.body??''].join('\u0000')
    const hit=map.get(key)
    if(hit)hit.push(notice)
    else map.set(key,[notice])
  }
  return [...map.entries()].map(([key,items])=>({key,notice:items[0]!,items,ids:items.map(i=>i.id)}))
})
const {page,paged}=usePagedItems(groups,5,()=>[query.value,filter.value])
const actionRoute=(n:Notice)=>n.action?.kind==='intel'?'/intel?from=reminders':''

function occurredText(n:Notice){
  if(!n.occurred_at)return ''
  const date=new Date(n.occurred_at)
  return Number.isNaN(date.getTime())?'':date.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})
}
function noticeCode(n:Notice){return (n.id||'').replace(/^msg_/,'').slice(-6).toUpperCase()}
function statusLabel(state:string){return statusLabels[state]??state}
function isExpanded(key:string){return expanded.value.includes(key)}

async function load(){
  busy.value=true;error.value='';status.value=''
  try{
    notices.value=await studentApi.notifications()
    justRead.value=[];expanded.value=[]
    await refreshNotifications(notices.value)
  }catch(e){error.value=(e as Error).message}finally{busy.value=false}
}

function markUpdated(updated:Notice[]){
  const byId=new Map(updated.map(u=>[u.id,u]))
  notices.value=notices.value.map(v=>byId.get(v.id)??v)
}

/** 兼容单条调用（旧测试与其他入口）：只给一条 Notice 时包成"只有一条的组"。 */
function asGroup(target: NoticeGroup | Notice): NoticeGroup {
  const maybe = target as NoticeGroup
  if (Array.isArray(maybe.items) && maybe.notice) return maybe
  const notice = target as Notice
  return { key: notice.id, notice, items: [notice], ids: [notice.id] }
}

/** 对合并后的一组做状态变更：组里每一条都改，数量在提示里写清楚。 */
async function change(target: NoticeGroup | Notice, state: NoticeState) {
  const group = asGroup(target)
  if(busy.value)return
  status.value='';snoozeError.value[group.notice.id]=''
  let until:string|null=null
  if(state==='later'){
    const raw=snooze.value[group.notice.id]
    if(!raw||!Number.isFinite(new Date(raw).getTime())||new Date(raw).getTime()<=Date.now()){
      snoozeError.value[group.notice.id]='请选择未来的提醒时间。';return
    }
    until=new Date(raw).toISOString()
  }
  busy.value=true;error.value=''
  try{
    const updated=await Promise.all(group.items.map(n=>studentApi.notification(n.id,{status:state,snoozed_until:state==='later'?until:null})))
    markUpdated(updated)
    if(state!=='read')justRead.value=justRead.value.filter(id=>!group.ids.includes(id))
    status.value=group.items.length>1?`已更新 ${group.items.length} 条同内容提醒的状态。`:'提醒状态已保存。'
    await refreshNotifications(notices.value)
  }catch(e){error.value=(e as Error).message}finally{busy.value=false}
}

/** 「看看是什么」：就地展开详情；第一次点开时把组内待处理项一起标为已读。 */
async function reveal(group:NoticeGroup){
  if(isExpanded(group.key)){
    expanded.value=expanded.value.filter(key=>key!==group.key)
    return
  }
  expanded.value=[...expanded.value,group.key]
  const pending=group.items.filter(n=>n.status==='pending')
  if(!pending.length)return
  busy.value=true;error.value=''
  try{
    const updated=await Promise.all(pending.map(n=>studentApi.notification(n.id,{status:'read'})))
    markUpdated(updated)
    justRead.value=[...new Set([...justRead.value,...updated.map(u=>u.id)])]
    status.value=pending.length>1?'已标为已读（同内容的几条一起标记），可在「已读历史」回看。':'已标为已读，可在「已读历史」回看。'
    await refreshNotifications(notices.value)
  }catch(e){error.value=(e as Error).message}finally{busy.value=false}
}

onMounted(load)
</script>
<template>
  <section class="restored-notifications">
    <div class="ws-section-head">
      <div class="ws-inline-actions"><button v-for="tab in tabs" :key="tab.key" class="btn" :aria-pressed="filter===tab.key" @click="filter=tab.key">{{tab.label}} {{notices.filter(n=>n.status===tab.key).length}}</button></div>
      <button class="btn" :disabled="busy" @click="load">刷新提醒</button>
    </div>
    <StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load"/>
    <p v-if="status" role="status">{{status}}</p>
    <p v-if="busy" class="ws-muted" role="status">正在同步提醒…</p>
    <label class="information-search">查找提醒<input v-model="query" type="search" placeholder="事项、内容或日期"/></label>
    <article v-for="g in paged" :key="g.key" class="c2-reminder">
      <header class="ws-section-head">
        <h2>{{g.notice.title}}</h2>
        <time>{{occurredText(g.notice) || dateKey(g.notice.occurred_at)}}</time>
      </header>
      <p class="c2-reminder__meta">
        <span v-if="g.items.length>1">同一条提醒出现了 {{g.items.length}} 次，已合并展示</span>
        <span v-else>编号 {{noticeCode(g.notice)}}</span>
        <span v-if="g.notice.status!=='pending'" class="c2-reminder__state">{{statusLabel(g.notice.status)}}</span>
      </p>
      <p>{{g.notice.body}}</p>
      <p v-if="g.notice.status==='later'&&g.notice.snoozed_until" class="ws-muted">再次提醒：{{new Date(g.notice.snoozed_until).toLocaleString()}}</p>
      <section v-if="isExpanded(g.key)" class="c2-reminder__detail" aria-label="提醒详情">
        <h3>这条提醒的记录</h3>
        <ul class="c2-reminder__records">
          <li v-for="(item,index) in g.items" :key="item.id">
            <span class="c2-reminder__no">第 {{index+1}} 条</span>
            <time>{{occurredText(item) || dateKey(item.occurred_at) || '时间未记录'}}</time>
            <span>{{statusLabel(item.status)}}</span>
            <small>编号 {{noticeCode(item)}}</small>
          </li>
        </ul>
        <p class="ws-muted">看过提醒不等于事情已经处理：需要处理请点「标为已处理」，或去对应页面操作。</p>
        <div class="ws-inline-actions">
          <RouterLink v-if="actionRoute(g.notice)" class="btn" :to="actionRoute(g.notice)">去职业探索看相关资讯</RouterLink>
          <RouterLink v-if="g.notice.related_task_id" class="btn" to="/plan">核对阶段计划</RouterLink>
        </div>
      </section>
      <div class="ws-inline-actions">
        <button class="btn" :disabled="busy" @click="reveal(g)">{{isExpanded(g.key)?'收起详情':(g.notice.action?.label||'看看是什么')}}</button>
        <button v-if="g.notice.status==='pending'" class="btn" :disabled="busy" @click="change(g,'read')">标为已读</button>
        <button v-if="g.notice.status!=='done'" class="btn" :disabled="busy" @click="change(g,'done')">标为已处理</button>
        <button v-if="g.notice.status!=='pending'" class="btn" :disabled="busy" @click="change(g,'pending')">恢复待处理</button>
        <DetailPopover title="稍后再提醒" side="right">
          <template #trigger>稍后处理</template>
          <label class="ws-field">提醒时间<input v-model="snooze[g.notice.id]" type="datetime-local"/></label>
          <button class="btn" :disabled="busy||!snooze[g.notice.id]" @click="change(g,'later')">保存提醒时间</button>
          <p v-if="snoozeError[g.notice.id]" class="ws-field-error" role="alert">{{snoozeError[g.notice.id]}}</p>
          <p>仅调整提醒状态，不自动完成关联任务。</p>
        </DetailPopover>
        <DetailPopover title="关联信息" side="right">
          <template #trigger>关联信息</template>
          <p>{{g.notice.body}}</p>
          <p v-if="g.notice.action?.label" class="ws-muted">提醒里的操作：{{g.notice.action.label}}</p>
          <RouterLink class="ws-text-link" to="/plan">核对阶段计划</RouterLink>
        </DetailPopover>
      </div>
    </article>
    <p v-if="!filtered.length&&!busy&&!error" class="ws-empty">{{query?'没有匹配的提醒。':'此分类暂无提醒。'}}</p>
    <ResultPager v-model:page="page" :total="groups.length" :size="5" label="提醒"/>
  </section>
</template>

<style scoped>
.restored-notifications > .information-search { margin: 24px 0; }
.restored-notifications [aria-pressed='true'] { border-color: var(--c-primary); background: var(--c-primary-weak); color: var(--c-primary); }
.c2-reminder h2 { min-width: 0; font-size: var(--fs-16); overflow-wrap: anywhere; }
.c2-reminder time { flex: none; white-space: nowrap; }
.c2-reminder__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin: 6px 0 8px; color: var(--c-text-3); font-size: var(--fs-12); }
.c2-reminder__state { padding: 1px 8px; border: 1px solid var(--c-border); border-radius: 999px; background: var(--c-surface-2); color: var(--c-text-2); }
.c2-reminder__detail { margin-top: 14px; padding: 14px 16px; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface-2); }
.c2-reminder__detail h3 { font-size: var(--fs-14); font-weight: 600; }
.c2-reminder__detail > p { margin-top: 8px; font-size: var(--fs-13); line-height: 1.7; }
.c2-reminder__records { display: grid; gap: 6px; margin: 10px 0 0; padding: 0; list-style: none; }
.c2-reminder__records li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; padding: 7px 10px; border-radius: 8px; background: var(--c-surface); color: var(--c-text-2); font-size: var(--fs-12); }
.c2-reminder__records small { color: var(--c-text-3); }
.c2-reminder__no { color: var(--c-primary); font-weight: 600; }
.c2-reminder__detail .ws-inline-actions { margin-top: 12px; }
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
