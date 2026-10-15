<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRoute} from 'vue-router'
import {auth} from '../lib/auth'
import {demo} from '../store'
import {backendClient} from '../api/backend-client'
import {refreshNotifications} from '../lib/system-data'
import {skin} from '../lib/theme'
import PageHeading from '../components/PageHeading.vue'
import StatusBanner from '../components/StatusBanner.vue'
import DetailPopover from '../components/DetailPopover.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
const route=useRoute(),key=computed(()=>String(route.name)),error=ref(''),status=ref(''),busy=ref(false)
const asset=ref<'report'|'direction_plan'|'action_plan'>('report'),format=ref<'pdf'|'docx'>('pdf')
const titles:Record<string,string>={settings:'账号设置',reminders:'提醒',guide:'使用指南',achievements:'成长记录'}
async function refresh(){error.value='';try{await refreshNotifications()}catch(e){error.value=(e as Error).message}}
async function read(id:string){if(busy.value)return;busy.value=true;error.value='';try{const receipt=await backendClient.notificationRead(id);if(!receipt.read)throw new Error('这条提醒未能标为已读');await refreshNotifications()}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function exportAsset(){if(busy.value)return;busy.value=true;error.value='';status.value='';try{const result=await backendClient.exportAsset(asset.value,format.value);status.value=result.message || (result.available?'导出已生成，请按服务提供的方式获取。':'导出暂不可用。')}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function logout(){try{await auth.logout()}catch(e){error.value=(e as Error).message}}
onMounted(()=>{if(key.value==='reminders')void refresh()})
</script>
<template><div class="ws-page"><PageHeading :title="titles[key]||'账号'" description=""/><StatusBanner v-if="error" tone="error" :message="error"/><StatusBanner v-if="status" tone="info" :message="status"/>
<div v-if="key==='settings'" class="c2-system-layout"><main>
<section class="ws-paper"><h2>{{demo.state.account}}</h2><p>对话和个人资料保存在当前账号。</p><button class="btn" @click="logout">退出登录</button></section>
<section class="ws-paper"><h2>外观</h2><p>仅保存在此浏览器，不影响个人资料。</p><div class="ws-inline-actions"><button class="btn" :aria-pressed="skin.state.accent==='blue'" @click="skin.setAccent('blue')">校徽蓝</button><button class="btn" :aria-pressed="skin.state.accent==='red'" @click="skin.setAccent('red')">官网红</button></div><label class="ws-field">主题<select :value="skin.state.theme" @change="skin.setTheme(($event.target as HTMLSelectElement).value as 'light'|'dark'|'system')"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label></section>
<section class="ws-paper"><h2>资产导出</h2><label class="ws-field">内容<select v-model="asset"><option value="report">诊断报告</option><option value="direction_plan">方向方案</option><option value="action_plan">行动计划</option></select></label><label class="ws-field">格式<select v-model="format"><option value="pdf">PDF</option><option value="docx">Word</option></select></label><button class="btn" :disabled="busy" @click="exportAsset">{{busy?'正在请求…':'请求导出'}}</button></section></main><aside><section class="ws-paper"><h2>管理资料</h2><RouterLink class="ws-text-link" to="/academic">导入或撤回学业资料</RouterLink><RouterLink class="ws-text-link" to="/profile">更正个人画像</RouterLink><RouterLink v-if="['admin','developer'].includes(auth.state.bootstrap?.identity?.role||'')" class="ws-text-link" to="/developer">开发者管理</RouterLink></section></aside></div>
<section v-else-if="key==='reminders'"><button class="btn" @click="refresh">刷新提醒</button><article v-for="n in demo.state.noticeQueue" :key="n.id" class="c2-reminder"><h2>{{n.title}}</h2><p>{{n.body}}</p><button class="btn" :disabled="busy" @click="read(n.id)">标为已读</button></article><p v-if="!demo.state.noticeQueue.length&&!error" class="ws-empty">当前没有未读提醒。</p></section>
<AchievementsSection v-else-if="key==='achievements'"/>
<section v-else-if="key==='guide'" class="ws-paper"><h2>从咨询开始</h2><p>说明当前问题，核对资料，比较方向，再执行计划。每项判断的来源可在旁侧详情中核对。</p><div class="ws-inline-actions"><RouterLink class="btn" to="/chat">开始咨询</RouterLink><RouterLink class="btn" to="/profile">核对画像</RouterLink><RouterLink class="btn" to="/directions">比较方向</RouterLink></div><DetailPopover v-for="faq in auth.state.bootstrap?.faqs" :key="faq.code" :title="faq.question" :label="faq.question"><template #trigger>{{faq.question}}</template><p>{{faq.answer}}</p></DetailPopover></section>
</div></template>
