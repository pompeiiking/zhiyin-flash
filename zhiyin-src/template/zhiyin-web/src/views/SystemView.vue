<script setup lang="ts">
import {computed,ref} from 'vue'
import {useRoute} from 'vue-router'
import {auth} from '../lib/auth'
import {demo} from '../store'
import {backendClient} from '../api/backend-client'
import NotificationCenter from '../components/NotificationCenter.vue'
import CapabilityGap from '../components/CapabilityGap.vue'
import {BackendError} from '../api/backend-client'
import {skin} from '../lib/theme'
import PageHeading from '../components/PageHeading.vue'
import StatusBanner from '../components/StatusBanner.vue'
import DetailPopover from '../components/DetailPopover.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
const route=useRoute(),key=computed(()=>String(route.name)),error=ref(''),status=ref(''),busy=ref(false)
const asset=ref<'report'|'direction_plan'|'action_plan'>('report'),format=ref<'pdf'|'docx'>('pdf')
const titles:Record<string,string>={settings:'账号设置',reminders:'提醒',guide:'使用指南',achievements:'成长记录'}
async function exportAsset(){if(busy.value)return;busy.value=true;error.value='';status.value='';try{const result=await backendClient.exportAsset(asset.value,format.value);status.value=result.message || (result.available?'导出已生成，请按服务提供的方式获取。':'导出暂不可用。')}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function logout(){try{await auth.logout()}catch(e){error.value=(e as Error).message}}
async function exportData(){if(busy.value)return;busy.value=true;error.value='';status.value='';try{const [workspace,notes,report]=await Promise.all([backendClient.workspace(),backendClient.notes(),backendClient.report().catch(e=>{if(e instanceof BackendError&&e.code===1002)return null;throw e})]);const body={exported_at:new Date().toISOString(),profile:workspace.profile_panel,academic:workspace.academic_panel,notes,report};const url=URL.createObjectURL(new Blob([JSON.stringify(body,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='职引-我的资料.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.value='已导出刚从账号读取的资料。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template><div class="ws-page"><PageHeading :title="titles[key]||'账号'" description=""/><StatusBanner v-if="error" tone="error" :message="error"/><StatusBanner v-if="status" tone="info" :message="status"/>
<div v-if="key==='settings'" class="c2-system-layout"><main>
<section class="ws-paper"><h2>{{demo.state.account}}</h2><p>对话和个人资料保存在当前账号。</p><button class="btn" @click="logout">退出登录</button></section>
<section class="ws-paper"><h2>外观</h2><p>仅保存在此浏览器，不影响个人资料。</p><div class="ws-inline-actions"><button class="btn" :aria-pressed="skin.state.accent==='blue'" @click="skin.setAccent('blue')">校徽蓝</button><button class="btn" :aria-pressed="skin.state.accent==='red'" @click="skin.setAccent('red')">官网红</button></div><label class="ws-field">主题<select :value="skin.state.theme" @change="skin.setTheme(($event.target as HTMLSelectElement).value as 'light'|'dark'|'system')"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label><button class="btn" @click="skin.reset();status='已恢复默认外观。'">恢复默认外观</button></section>
<section class="ws-paper"><h2>提醒与资料偏好</h2><p class="ws-muted">以下设置尚未开放，开关不表示当前生效状态。</p><fieldset disabled class="pending-preferences"><label><input type="checkbox"/>主动提醒</label><label>安静时间，从<input type="time"/></label><label>到<input type="time"/></label><label><input type="checkbox"/>学校资料参与分析</label><label><input type="checkbox"/>上传材料参与分析</label></fieldset><CapabilityGap title="保存提醒与资料使用偏好" reason="暂未提供偏好读取与保存接口，不能确定当前开关状态；学校资料撤回仍可在学籍与资料页操作。"/></section><section class="ws-paper"><h2>个人资料导出</h2><p>导出账号中的画像、学业资料、个人记录及已有报告。</p><button class="btn" :disabled="busy" @click="exportData">导出我的资料（JSON）</button></section><section class="ws-paper"><h2>资产导出</h2><p class="ws-muted">PDF / Word 文件生成暂未开放；报告页可使用浏览器打印保存 PDF。</p><label class="ws-field">内容<select v-model="asset"><option value="report">诊断报告</option><option value="direction_plan">方向方案</option><option value="action_plan">行动计划</option></select></label><label class="ws-field">格式<select v-model="format"><option value="pdf">PDF</option><option value="docx">Word</option></select></label><button class="btn" :disabled="busy" @click="exportAsset">{{busy?'正在请求…':'请求导出'}}</button></section></main><aside><section class="ws-paper"><h2>管理资料</h2><RouterLink class="ws-text-link" to="/academic">导入或撤回学业资料</RouterLink><RouterLink class="ws-text-link" to="/profile">更正个人画像</RouterLink><RouterLink v-if="['admin','developer'].includes(auth.state.bootstrap?.identity?.role||'')" class="ws-text-link" to="/developer">开发者管理</RouterLink></section></aside></div>
<NotificationCenter v-else-if="key==='reminders'"/>
<AchievementsSection v-else-if="key==='achievements'"/>
<section v-else-if="key==='guide'" class="ws-paper"><h2>从咨询开始</h2><ol class="guide-flow"><li><RouterLink to="/chat">说明当前问题</RouterLink></li><li><RouterLink to="/profile">核对画像与资料</RouterLink></li><li><RouterLink to="/report">核对报告依据</RouterLink></li><li><RouterLink to="/directions">比较并确认方向</RouterLink></li><li><RouterLink to="/plan">安排阶段行动</RouterLink></li><li><RouterLink to="/review">记录结果与调整</RouterLink></li></ol><p>说明当前问题，核对资料，比较方向，再执行计划。每项判断的来源可在旁侧详情中核对。</p><div class="ws-inline-actions"><RouterLink class="btn" to="/chat">开始咨询</RouterLink><RouterLink class="btn" to="/profile">核对画像</RouterLink><RouterLink class="btn" to="/directions">比较方向</RouterLink></div><DetailPopover title="状态与术语" label="查看状态与术语"><template #trigger>状态与术语</template><dl><dt>已读</dt><dd>看过提醒，不代表事项已处理。</dd><dt>待重新计算</dt><dd>依赖资料已变化，旧报告保留原版。</dd><dt>个人待办</dt><dd>自己记录的安排，与阶段计划任务分别保存。</dd><dt>待支持</dt><dd>功能入口保留，尚缺相应服务能力。</dd></dl></DetailPopover><DetailPopover v-for="faq in auth.state.bootstrap?.faqs" :key="faq.code" :title="faq.question" :label="faq.question"><template #trigger>{{faq.question}}</template><p>{{faq.answer}}</p></DetailPopover></section>
</div></template>

<style scoped>.guide-flow{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin:20px 0;padding-left:24px}.guide-flow a{display:inline-block;padding:10px 0;color:var(--c-primary)}.pending-preferences{display:grid;gap:16px;margin:16px 0;padding:16px;border:1px solid var(--c-border)}.pending-preferences label{display:flex;align-items:center;gap:12px;color:var(--c-text-3)}</style>
