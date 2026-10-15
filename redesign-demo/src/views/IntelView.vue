<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import type { IntelItemView } from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import DetailPopover from '../components/DetailPopover.vue'
import IntelArticle from '../components/IntelArticle.vue'
import CareerMatchPanel from '../components/CareerMatchPanel.vue'
import StatusBanner from '../components/StatusBanner.vue'
import EmptyState from '../components/EmptyState.vue'
import ResultPager from '../components/ResultPager.vue'
import { usePagedItems } from '../lib/paged-items'
const query=ref(''),remoteQuery=ref(''),kind=ref('all'),status=ref(''),error=ref(''),busy=ref(false),matchOpen=ref(false),retrieveOpen=ref(false)
const selectedId=ref(''),reading=ref<IntelItemView|null>(null)
const items=computed(()=>backendDemo.state.intel.filter(i=>(kind.value==='all'||i.kind===kind.value)&&((i.title??'')+' '+(i.text??'')).includes(query.value.trim())))
const {page,paged}=usePagedItems(items,6)
const selected=computed(()=>paged.value.find(i=>i.id===selectedId.value)??paged.value[0]??null)
const kinds=computed(()=>[...new Map(backendDemo.state.intel.map(i=>[i.kind??'other',i.kind_label??'其他资讯'])).entries()])
function select(item:IntelItemView){selectedId.value=item.id;if(window.matchMedia('(max-width: 900px)').matches)reading.value={...item}}
function clearFilter(){query.value='';kind.value='all'}
function facts(q:string){query.value=q;kind.value='all';matchOpen.value=false}
async function read(id:string){const item=backendDemo.state.intel.find(i=>i.id===id);if(!item)return;clearFilter();await nextTick();page.value=Math.floor(items.value.findIndex(i=>i.id===id)/6)+1;select(item);matchOpen.value=false}
async function load(refresh=false){if(busy.value)return;busy.value=true;error.value='';try{const result=refresh?await backendClient.refreshIntel(remoteQuery.value.trim()):await backendClient.intel(remoteQuery.value.trim());if(!result||!Array.isArray(result.items))throw new Error('Incomplete intel');backendDemo.setIntel(result.items);clearFilter();status.value='已读取 '+result.items.length+' 条资讯';retrieveOpen.value=false}catch{error.value='资讯没有读取成功，请重试。现有条目与筛选仍保留。'}finally{busy.value=false}}
const VERIFY:Record<string,{title:string;detail:string}[]> = {
  career:[
    {title:'核对来源与发布日',detail:'职业探索笔记帮助准备问题；申请岗位需要核对招聘方原始公告与有效期。'},
    {title:'核对学历与专业门槛',detail:'逐项核对学历、专业与实践条件，区分必须满足的要求与优先条件。'},
    {title:'核对职责、地点、待遇与期限',detail:'本条没有给出地点、待遇、招聘期限与投递方式；这些必须来自真实招聘来源才可用于选择。'},
  ],
  industry:[
    {title:'核对两类的真实职责描述',detail:'用两个当前开放岗位的职责说明逐条比较，保留来源与发布日期。'},
    {title:'核对结论的适用范围',detail:'这条讲的是工作方式的差别，不构成"哪类更有前景"的判断。'},
  ],
  education:[
    {title:'核对需要的材料',detail:'学籍核验需要本人授权的在线验证码；本人整理的资料不等于核验通过。'},
    {title:'核对更新时间',detail:'学校、专业、年级与更新时间缺一项就无法判断这条资料还算不算数。'},
  ],
  campus:[
    {title:'核对时间、地点与报名方式',detail:'参与活动前，请向学校核对最新时间、地点与报名方式。'},
    {title:'核对参与门槛',detail:'部分活动需要先完成安全培训或年级限制，原文没有给出。'},
  ],
  guide:[
    {title:'核对适用范围',detail:'这是通用写法，不针对某个岗位；套用前先确认岗位要求的表达习惯。'},
    {title:'回填到自己的材料',detail:'缺数据的地方保留待补充，不要用推测数字补满。'},
  ],
}
function verifyPoints(item?:IntelItemView|null){return VERIFY[item?.kind??'']??[{title:'核对来源与时间',detail:'确认这条来自哪个来源、什么时候读取，再决定要不要用它。'}]}

</script>
<template>
<div class="ws-page intel-page intelligence-workspace">
<PageHeading title="岗位资讯" description="查找方向相关资讯，核对岗位条件与来源。"><button class="btn" @click="matchOpen=true">职业匹配</button><button class="btn btn--primary" @click="retrieveOpen=true"><UiIcon name="search" :size="16"/>检索资讯</button></PageHeading>
<StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="load()"/>
<StatusBanner v-if="status" tone="success" :message="status" @dismiss="status=''"/>
<div class="intelligence-toolbar"><label class="intelligence-search"><UiIcon name="search" :size="18"/><input v-model="query" aria-label="查找资讯" placeholder="搜索岗位、方向或关键词"/></label><DetailPopover title="资讯类别" label="打开资讯筛选与排序"><template #trigger><UiIcon name="settings" :size="16"/>{{ kind==='all'?'全部类别':kinds.find(k=>k[0]===kind)?.[1] }}</template><div class="intelligence-filters"><button :aria-pressed="kind==='all'" @click="kind='all'">全部类别 <span>{{ backendDemo.state.intel.length }}</span></button><button v-for="[key,label] in kinds" :key="key" :aria-pressed="kind===key" @click="kind=key">{{ label }} <span>{{ backendDemo.state.intel.filter(i=>i.kind===key).length }}</span></button></div></DetailPopover><button v-if="query||kind!=='all'" class="ws-text-button" @click="clearFilter">清空筛选</button><span class="intelligence-total">{{ items.length }} 条资讯</span></div>
<div v-if="items.length" class="intelligence-body">
<section class="intelligence-results" aria-label="资讯列表"><div class="intelligence-results__scroll"><button v-for="item in paged" :key="item.id" class="intelligence-result" :class="{'is-selected':selected?.id===item.id}" :aria-pressed="selected?.id===item.id" @click="select(item)"><span class="intelligence-result__kind">{{ item.kind_label || '资讯' }}</span><strong>{{ item.title || '资讯正文' }}</strong><span class="intelligence-result__preview">{{ item.text }}</span><span class="intelligence-result__foot"><span>{{ item.source_name || '来源待核对' }}</span><time>{{ item.fetched_at?.slice(5,10) || '日期待补充' }}</time></span></button></div><ResultPager v-model:page="page" :total="items.length" :size="6" label="资讯"/></section>
<section class="intelligence-detail" aria-label="资讯详情"><IntelArticle v-if="selected" :item="selected" :checks="verifyPoints(selected)"/></section>
</div>
<EmptyState v-else kind="intel" title="没有匹配的资讯" description="调整关键词或类别，或检索新的资讯。" :next="false"><button class="btn" @click="clearFilter">清空筛选</button></EmptyState>
<InfoSheet :open="reading!==null" shape="sheet" :title="reading?.title || '资讯详情'" @close="reading=null"><IntelArticle v-if="reading" :item="reading" :checks="verifyPoints(reading)"/></InfoSheet>
<InfoSheet :open="retrieveOpen" title="检索资讯" @close="retrieveOpen=false"><form class="remote-search" @submit.prevent="load()"><label class="ws-field">职业、方向或关键词<input v-model="remoteQuery" maxlength="200" placeholder="输入想了解的方向"/></label><button class="btn btn--primary" :disabled="busy">{{ busy?'正在读取…':'检索' }}</button><button class="btn" type="button" :disabled="busy" @click="load(true)">刷新资讯</button></form><p class="ws-muted">检索失败时保留当前资讯；每条内容保留各自来源。</p></InfoSheet>
<InfoSheet :open="matchOpen" shape="panel" title="职业匹配" @close="matchOpen=false"><CareerMatchPanel :facts="backendDemo.state.intel" @read="read" @facts="facts"/></InfoSheet>
</div>
</template>
