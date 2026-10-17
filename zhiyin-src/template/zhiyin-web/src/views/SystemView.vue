<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { auth } from '../lib/auth'
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
    const [workspace,notes,report] = await Promise.all([backendClient.workspace(), backendClient.notes(), backendClient.report().catch(e => {
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
    <PageHeading :title="titles[key] || '账号'" :description="key === 'settings' ? '管理当前身份、资料使用范围与导出。' : ''" />
    <StatusBanner v-if="error" tone="error" :message="error" />
    <StatusBanner v-if="status" tone="info" :message="status" />

    <template v-if="key === 'settings'">
      <section class="settings-identity">
        <span aria-hidden="true">{{ demo.state.account.slice(0,1) }}</span>
        <div><p>当前账号</p><h2>{{ demo.state.account }}</h2></div>
        <dl><div><dt>皮肤</dt><dd>{{ skinLabel }}</dd></div><div><dt>资料状态</dt><dd>已连接当前工作空间</dd></div></dl>
        <button class="btn" @click="logout">退出登录</button>
      </section>

      <div class="settings-layout">
        <main class="settings-main">
          <AccountPreferences />
          <section class="settings-block" aria-labelledby="settings-export-title">
            <header><div><p>带走或保存</p><h2 id="settings-export-title">导出资料</h2></div><DetailPopover title="导出说明" label="查看导出说明"><p>个人资料导出为 JSON；报告、方向和计划由服务生成相应文件。导出只读取当前账号的真实数据。</p></DetailPopover></header>
            <div class="settings-export-grid">
              <article><UiIcon name="download" :size="21"/><div><h3>我的全部资料</h3><p>画像、学业、待办和当前报告</p></div><button class="btn" :disabled="busy" @click="exportData">导出 JSON</button></article>
              <article><UiIcon name="report" :size="21"/><div><h3>单项成果</h3><p>选择内容和文件格式</p></div><label>内容<select v-model="asset"><option value="report">诊断报告</option><option value="direction_plan">方向方案</option><option value="action_plan">行动计划</option></select></label><label>格式<select v-model="format"><option value="pdf">PDF</option><option value="docx">Word</option></select></label><button class="btn" :disabled="busy" @click="exportAsset">{{ busy ? '正在请求…' : '请求导出' }}</button></article>
            </div>
          </section>
        </main>
        <aside class="settings-data">
          <p>资料入口</p><h2>更正与补充</h2>
          <RouterLink to="/profile"><UiIcon name="profile" :size="19"/><span><strong>个人画像与学籍</strong><small>核对本人资料和来源</small></span><UiIcon name="arrow" :size="15"/></RouterLink>
          <RouterLink to="/grades"><UiIcon name="academic" :size="19"/><span><strong>成绩记录</strong><small>录入、导入与分析</small></span><UiIcon name="arrow" :size="15"/></RouterLink>
          <RouterLink to="/schedule"><UiIcon name="calendar" :size="19"/><span><strong>课表与时间</strong><small>课程和可投入时间</small></span><UiIcon name="arrow" :size="15"/></RouterLink>
          <RouterLink v-if="['admin','developer'].includes(auth.state.bootstrap?.identity?.role || '')" to="/developer"><UiIcon name="settings" :size="19"/><span><strong>开发者管理</strong><small>模块与接入检查</small></span><UiIcon name="arrow" :size="15"/></RouterLink>
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
.settings-identity { display:grid; grid-template-columns:54px minmax(180px,1fr) minmax(280px,1.4fr) auto; align-items:center; gap:16px; padding:20px 22px; border:1px solid var(--c-border); border-radius:18px; background:linear-gradient(110deg,var(--c-primary-weak),var(--c-surface) 46%); }
.settings-identity>span { display:grid; place-items:center; width:54px; height:54px; border-radius:16px; background:var(--c-primary); color:var(--c-on-primary); font-size:20px; font-weight:600; }
.settings-identity p,.settings-data>p,.settings-block>header p { color:var(--c-primary); font-size:11px; font-weight:600; }
.settings-identity h2 { margin-top:3px; font-size:20px; }
.settings-identity dl { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.settings-identity dl>div { padding-left:14px; border-left:1px solid var(--c-border); }
.settings-identity dt { color:var(--c-text-3); font-size:11px; }
.settings-identity dd { margin-top:4px; font-size:13px; }
.settings-layout { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:24px; margin-top:24px; align-items:start; }
.settings-main { display:grid; gap:20px; min-width:0; }
.settings-block,.settings-data { padding:22px; border:1px solid var(--c-border); border-radius:18px; background:var(--c-surface); }
.settings-block>header { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; }
.settings-block h2,.settings-data h2 { margin-top:3px; font-size:20px; }
.settings-export-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:18px; }
.settings-export-grid article { display:grid; grid-template-columns:28px minmax(0,1fr); align-items:start; gap:10px; padding:16px; border:1px solid var(--c-border); border-radius:14px; background:var(--c-surface-2); }
.settings-export-grid article>div { min-height:54px; }
.settings-export-grid h3 { font-size:14px; }
.settings-export-grid p { margin-top:3px; color:var(--c-text-3); font-size:12px; line-height:1.55; }
.settings-export-grid article>.btn,.settings-export-grid article>label { grid-column:1/-1; }
.settings-export-grid label { display:flex; align-items:center; justify-content:space-between; gap:12px; color:var(--c-text-2); font-size:12px; }
.settings-export-grid select { min-width:130px; min-height:40px; }
.settings-data { position:sticky; top:20px; }
.settings-data>a { display:grid; grid-template-columns:24px minmax(0,1fr) 18px; align-items:center; gap:10px; min-height:64px; border-bottom:1px solid var(--c-border); color:var(--c-text-2); }
.settings-data>a:hover { color:var(--c-primary); text-decoration:none; }
.settings-data strong,.settings-data small { display:block; }
.settings-data strong { color:var(--c-text); font-size:13px; }
.settings-data small { margin-top:3px; color:var(--c-text-3); font-size:11px; }
.guide-flow { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); margin:20px 0; padding-left:24px; }
.guide-flow a { display:inline-block; padding:10px 0; color:var(--c-primary); }
@media(max-width:860px){.settings-identity{grid-template-columns:54px minmax(0,1fr) auto}.settings-identity dl{grid-column:1/-1}.settings-layout{grid-template-columns:1fr}.settings-data{position:static;order:-1}.settings-export-grid{grid-template-columns:1fr}}
@media(max-width:560px){.settings-identity{grid-template-columns:48px minmax(0,1fr);padding:16px}.settings-identity>span{width:48px;height:48px}.settings-identity>.btn{grid-column:1/-1}.settings-identity dl{grid-template-columns:1fr}.settings-export-grid article{padding:14px}.settings-block,.settings-data{padding:18px}}
</style>
