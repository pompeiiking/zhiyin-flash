<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { auth } from '../lib/auth'
import { featureEnabled, routeEnabled } from '../lib/features'
import { demo } from '../store'
import { backendClient, BackendError } from '../api/backend-client'
import AccountPreferences from '../components/AccountPreferences.vue'
import { downloadExport } from '../api/student-capabilities'
import NotificationCenter from '../components/NotificationCenter.vue'
import { skin } from '../lib/theme'
import PageHeading from '../components/PageHeading.vue'
import StatusBanner from '../components/StatusBanner.vue'
import DetailPopover from '../components/DetailPopover.vue'
import AchievementsSection from '../components/AchievementsSection.vue'
import UiIcon from '../components/UiIcon.vue'

const route = useRoute()
const key = computed(() => String(route.name))
const error = ref('')
const status = ref('')
const busy = ref(false)
const asset = ref<'report'|'direction_plan'|'action_plan'>('report')
const format = ref<'pdf'|'docx'>('pdf')
const titles: Record<string,string> = { settings:'账号设置', reminders:'提醒', guide:'使用指南', achievements:'完成记录' }
const descriptions: Record<string,string> = {
  settings:'管理当前身份、提醒方式、资料使用范围与导出。',
  reminders:'集中查看尚待处理和已经读过的提醒。',
  guide:'按真实任务了解各页面之间的衔接方式。',
  achievements:'核对由真实行动形成的完成记录与下一步。',
}
const skinLabel = computed(() => `${skin.state.accent === 'red' ? '红色' : '蓝色'} · ${skin.state.theme === 'system' ? '跟随系统' : skin.state.theme === 'dark' ? '深色' : '浅色'}`)

async function exportAsset() {
  if (busy.value) return
  busy.value = true; error.value = ''; status.value = ''
  try {
    const result = await backendClient.exportAsset(asset.value, format.value)
    if (result.available && result.object_key) await downloadExport(result.object_key, `职引-${asset.value}.${format.value}`)
    status.value = result.message || (result.available ? '导出已生成，请按服务提供的方式获取。' : '导出暂不可用。')
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function logout() { try { await auth.logout() } catch (e) { error.value = (e as Error).message } }
async function exportData() {
  if (busy.value) return
  busy.value = true; error.value = ''; status.value = ''
  try {
    const [workspace,notes,report] = await Promise.all([backendClient.workspace(), backendClient.notes(), (featureEnabled('report_full_text') ? backendClient.report() : Promise.resolve(null)).catch(e => {
      if (e instanceof BackendError && e.code === 1002) return null
      throw e
    })])
    const body = { exported_at:new Date().toISOString(), profile:workspace.profile_panel, academic:workspace.academic_panel, notes, report }
    const url = URL.createObjectURL(new Blob([JSON.stringify(body,null,2)], { type:'application/json' }))
    const a = document.createElement('a'); a.href = url; a.download = '职引-我的资料.json'; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    status.value = '已导出刚从账号读取的资料。'
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>

<template>
  <div class="ws-page">
    <PageHeading :title="titles[key] || '账号'" :description="descriptions[key] || '管理当前账号。'" />
    <StatusBanner v-if="error" tone="error" :message="error" />
    <StatusBanner v-if="status" tone="info" :message="status" />

    <template v-if="key === 'settings'">
      <section class="settings-identity">
        <span class="settings-identity__avatar" aria-hidden="true">{{ demo.state.account.slice(0,1) }}</span>
        <div class="settings-identity__name"><p>当前登录</p><h2>{{ demo.state.account }}</h2></div>
        <div class="settings-identity__state"><span><i aria-hidden="true" />{{ skinLabel }}</span><span><UiIcon name="check" :size="15" />资料已连接</span></div>
        <button class="btn" @click="logout">退出登录</button>
      </section>

      <div class="settings-layout">
        <main class="settings-main">
          <AccountPreferences />
          <section class="settings-block settings-export" aria-labelledby="settings-export-title">
            <header><div><p>保存副本</p><h2 id="settings-export-title">导出资料</h2></div><DetailPopover title="导出说明" label="查看导出说明"><p>个人资料导出为 JSON；报告、方向和计划由服务生成相应文件。导出只读取当前账号的真实数据。</p></DetailPopover></header>
            <div class="settings-export-grid">
              <article class="settings-export-all"><span><UiIcon name="download" :size="21"/></span><div><h3>我的全部资料</h3><p>画像、学业、待办和当前报告的 JSON 副本</p></div><button class="btn" :disabled="busy" @click="exportData">导出</button></article>
              <article v-if="featureEnabled('export')" class="settings-export-single"><span><UiIcon name="report" :size="21"/></span><div><h3>单项成果</h3><p>生成适合保存或打印的文件</p></div><div class="settings-export-options"><label><span>内容</span><select v-model="asset"><option value="report">诊断报告</option><option value="direction_plan">方向方案</option><option value="action_plan">行动计划</option></select></label><label><span>格式</span><select v-model="format"><option value="pdf">PDF</option><option value="docx">Word</option></select></label></div><button class="btn" :disabled="busy" @click="exportAsset">{{ busy ? '正在请求…' : '生成文件' }}</button></article>
            </div>
          </section>
        </main>
        <aside class="settings-data">
          <header><p>资料入口</p><h2>更正与补充</h2><DetailPopover title="为什么在原页面修改" label="查看资料修改说明" side="left"><p>每类资料在对应页面中展示来源和影响范围，修改时更容易判断是否准确。</p></DetailPopover></header>
          <nav aria-label="资料更正入口">
            <RouterLink to="/profile"><span><UiIcon name="profile" :size="19"/></span><div><strong>个人画像与学籍</strong><small>核对资料和来源</small></div><UiIcon name="arrow" :size="15"/></RouterLink>
            <RouterLink to="/grades"><span><UiIcon name="academic" :size="19"/></span><div><strong>成绩记录</strong><small>录入、导入与分析</small></div><UiIcon name="arrow" :size="15"/></RouterLink>
            <RouterLink v-if="routeEnabled('/schedule')" to="/schedule"><span><UiIcon name="calendar" :size="19"/></span><div><strong>课表与时间</strong><small>课程和可投入时间</small></div><UiIcon name="arrow" :size="15"/></RouterLink>
            <RouterLink v-if="['admin','developer'].includes(auth.state.bootstrap?.identity?.role || '')" to="/developer"><span><UiIcon name="settings" :size="19"/></span><div><strong>开发者管理</strong><small>模块与接入检查</small></div><UiIcon name="arrow" :size="15"/></RouterLink>
          </nav>
        </aside>
      </div>
    </template>

    <NotificationCenter v-else-if="key === 'reminders'" />
    <AchievementsSection v-else-if="key === 'achievements'" />
    <section v-else-if="key === 'guide'" class="ws-paper">
      <h2>从咨询开始</h2>
      <ol class="guide-flow"><li><RouterLink to="/chat">说明当前问题</RouterLink></li><li><RouterLink to="/profile">核对画像与资料</RouterLink></li><li><RouterLink to="/report">核对报告依据</RouterLink></li><li><RouterLink to="/directions">比较并确认方向</RouterLink></li><li><RouterLink to="/plan">安排阶段行动</RouterLink></li><li><RouterLink to="/review">记录结果与调整</RouterLink></li></ol>
      <div class="ws-inline-actions"><RouterLink class="btn" to="/chat">开始咨询</RouterLink><RouterLink class="btn" to="/profile">核对画像</RouterLink><RouterLink class="btn" to="/directions">比较方向</RouterLink></div>
      <DetailPopover title="状态与术语" label="查看状态与术语"><template #trigger>状态与术语</template><dl><dt>已读</dt><dd>看过提醒，不代表事项已处理。</dd><dt>待重新计算</dt><dd>依赖资料已变化，旧报告保留原版。</dd><dt>个人待办</dt><dd>自己记录的安排，与阶段计划任务分别保存。</dd><dt>待支持</dt><dd>功能入口保留，尚缺相应服务能力。</dd></dl></DetailPopover>
    </section>
  </div>
</template>

<style scoped>
.settings-identity { position:relative; display:grid; grid-template-columns:52px minmax(180px,1fr) minmax(260px,auto) auto; align-items:center; gap:16px; min-height:92px; padding:17px 20px; overflow:hidden; border:1px solid color-mix(in srgb,var(--c-primary) 14%,var(--c-border)); border-radius:20px; background:linear-gradient(110deg,var(--c-primary-weak),var(--c-surface) 44%); }
.settings-identity::after { content:''; position:absolute; right:13%; top:-54px; width:180px; height:110px; border-radius:50%; background:color-mix(in srgb,var(--c-primary) 8%,transparent); filter:blur(22px); pointer-events:none; }
.settings-identity__avatar { display:grid; place-items:center; width:52px; height:52px; border-radius:15px; background:var(--c-primary); color:var(--c-on-primary); font-size:19px; font-weight:650; box-shadow:0 10px 24px -16px var(--c-primary); }
.settings-identity__name p,.settings-data header p,.settings-block>header p { color:var(--c-primary); font-size:12px; font-weight:650; }
.settings-identity__name h2 { margin-top:3px; font-size:19px; }
.settings-identity__state { position:relative; z-index:1; display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; }
.settings-identity__state>span { display:inline-flex; align-items:center; gap:7px; min-height:36px; padding:7px 11px; border:1px solid var(--c-border); border-radius:999px; background:color-mix(in srgb,var(--c-surface) 86%,transparent); color:var(--c-text-2); font-size:12px; }
.settings-identity__state i { width:8px; height:8px; border-radius:50%; background:var(--c-primary); box-shadow:0 0 0 4px var(--c-primary-weak); }
.settings-identity>.btn { position:relative; z-index:1; }
.settings-layout { display:grid; grid-template-columns:minmax(0,1fr) 310px; gap:20px; margin-top:20px; align-items:start; }
.settings-main { display:grid; gap:20px; min-width:0; }
.settings-block,.settings-data { padding:20px; border:1px solid var(--c-border); border-radius:20px; background:var(--c-surface); }
.settings-block>header { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; }
.settings-block h2,.settings-data h2 { margin-top:3px; font-size:20px; }
.settings-export-grid { display:grid; gap:10px; margin-top:16px; }
.settings-export-grid article { display:grid; grid-template-columns:40px minmax(0,1fr) auto; align-items:center; gap:12px; min-height:68px; padding:12px 14px; border:1px solid var(--c-border); border-radius:15px; background:var(--c-surface-2); }
.settings-export-grid article>span { display:grid; place-items:center; width:38px; height:38px; border-radius:12px; background:var(--c-surface); color:var(--c-primary); }
.settings-export-grid h3 { font-size:14px; }.settings-export-grid p { margin-top:3px; color:var(--c-text-2); font-size:12px; line-height:1.5; }
.settings-export-options { display:flex; gap:8px; min-height:0!important; }
.settings-export-grid label { display:flex; align-items:center; gap:7px; color:var(--c-text-2); font-size:12px; }
.settings-export-grid select { min-width:130px; min-height:40px; }
.settings-data { position:sticky; top:20px; }
.settings-data>header { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:start; padding:1px 2px 13px; }
.settings-data>header>p,.settings-data>header>h2 { grid-column:1 }.settings-data>header>.detail-trigger{grid-column:2;grid-row:1/3}
.settings-data nav { display:grid; gap:6px; }
.settings-data nav>a { display:grid; grid-template-columns:40px minmax(0,1fr) 18px; align-items:center; gap:10px; min-height:66px; padding:8px; border-radius:13px; color:var(--c-text-2); }
.settings-data nav>a:hover { color:var(--c-primary); background:var(--c-primary-weak); text-decoration:none; }
.settings-data nav>a>span { display:grid; place-items:center; width:38px; height:38px; border-radius:11px; background:var(--c-surface-2); color:var(--c-primary); }
.settings-data nav strong,.settings-data nav small { display:block; }.settings-data nav strong { color:var(--c-text); font-size:13px; }.settings-data nav small { margin-top:3px; color:var(--c-text-2); font-size:12px; }
.guide-flow { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); margin:20px 0; padding-left:24px; }
.guide-flow a { display:inline-block; padding:10px 0; color:var(--c-primary); }
@media(max-width:960px){.settings-identity{grid-template-columns:52px minmax(0,1fr) auto;grid-template-rows:auto auto}.settings-identity__avatar{grid-row:1/3}.settings-identity__name{grid-column:2;grid-row:1}.settings-identity__state{grid-column:2;grid-row:2;justify-content:flex-start}.settings-identity>.btn{grid-column:3;grid-row:1/3}.settings-layout{grid-template-columns:1fr}.settings-data{position:static;order:-1}.settings-data nav{grid-template-columns:repeat(3,minmax(0,1fr))}.settings-data nav>a{grid-template-columns:38px minmax(0,1fr)}.settings-data nav>a>svg{display:none}}
@media(max-width:700px){.settings-export-grid article{grid-template-columns:40px minmax(0,1fr)}.settings-export-grid article>.btn,.settings-export-options{grid-column:1/-1}.settings-export-options{display:grid;grid-template-columns:1fr 1fr}.settings-export-options label{display:grid}.settings-export-grid select{width:100%;min-width:0}.settings-data nav{grid-template-columns:1fr}}
@media(max-width:560px){.settings-identity{grid-template-columns:48px minmax(0,1fr);grid-template-rows:auto auto auto;padding:14px}.settings-identity__avatar{grid-row:1;width:48px;height:48px}.settings-identity__name{grid-column:2;grid-row:1}.settings-identity__state{grid-column:1/-1;grid-row:2;gap:6px}.settings-identity>.btn{grid-column:1/-1;grid-row:3;width:100%}.settings-identity__state>span{min-height:34px}.settings-block,.settings-data{padding:16px}.settings-export-options{grid-template-columns:1fr}.settings-export-grid article{padding:12px}.settings-export-grid article>.btn{width:100%}}
</style>
