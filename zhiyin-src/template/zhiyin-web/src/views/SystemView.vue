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

/**
 * 使用指南的正文（#9）。原来这里只有 6 个链接标签，新生看不出"每一步做什么、点哪里、
 * 做完在哪看结果"。每步固定三段：做什么（what）、点哪个按钮（how）、产出在哪（output）。
 */
const guideSteps = [
  {
    title: '说明当前问题', to: '/chat',
    what: '在对话框里用大白话讲你现在的情况：年级、专业、眼下最想解决的问题。页面给的快捷选项可以点，但不用照模板说。',
    how: '点「咨询对话」或下面的「开始咨询」，输入后按回车发送。',
    output: '聊完一轮，右侧的画像会同步记下新信息，页面顶部会显示采集进度。',
  },
  {
    title: '核对画像与资料', to: '/profile',
    what: '逐条核对系统记下的专业、年级、成绩、兴趣和卡点是不是真的符合你。资料越准，后面的判断越有依据。',
    how: '打开「个人画像」，不对的条目点开修改，缺的按页面提示补上；学籍、成绩、课表也可以从「应用工具」单独导入。',
    output: '一份你能确认的"我的资料"。',
  },
  {
    title: '核对报告依据', to: '/report',
    what: '报告先给总体判断，再逐条给依据。带「待验证」的条目不是结论，而是需要你在现实中验证的问题。',
    how: '点页头的「重新读取」拿最新报告；点报告里的蓝色文字可以展开这条判断的依据与来源。',
    output: '一份知道"依据在哪、还缺什么"的诊断报告，也可以导出 JSON 保存。',
  },
  {
    title: '比较并确认方向', to: '/directions',
    what: '方向方案会给出几套选择：主攻是最想投入的方向，平行是同时准备的方向，保底是万一不顺仍能接受的方向。',
    how: '在「方向方案」里逐个比较目标、依据和风险，确认一套；觉得信息不够就回到对话补。',
    output: '一个你确认过的主攻方向。',
  },
  {
    title: '安排阶段行动', to: '/plan',
    what: '把选定的方向拆成阶段目标，再把本周要做的事排进今日行动。每件事都写清"做到什么程度算完成"。',
    how: '打开「阶段计划」新建阶段，用「安排新任务」加任务并填截止时间；今天要做的会出现在「今日行动」。',
    output: '阶段计划和今天就能开始的第一件事。',
  },
  {
    title: '记录结果与调整', to: '/review',
    what: '做完任务后回到复盘页，写清事实、原因和下一步。发现方向不合适就回去改方向，不用怕推翻前面的选择。',
    how: '在「复盘记录」里选任务填写并保存；完成情况会同步进「完成记录」。',
    output: '一条可回看的调整记录，和一份真实的完成记录。',
  },
]

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
    const [workspace, notes, report, action] = await Promise.allSettled([
      backendClient.workspace(),
      backendClient.notes(),
      featureEnabled('report_full_text') ? backendClient.report().catch(e => {
        if (e instanceof BackendError && e.code === 1002) return null
        throw e
      }) : Promise.resolve(null),
      backendClient.action().catch(e => {
        if (e instanceof BackendError && e.code === 1002) return null
        throw e
      }),
    ])
    if (workspace.status === 'rejected') throw workspace.reason
    if (notes.status === 'rejected') throw notes.reason
    const reportValue = report.status === 'fulfilled' ? report.value : null
    const actionValue = action.status === 'fulfilled' ? action.value : null
    const account = demo.state.account || '当前账号'
    const day = new Intl.DateTimeFormat('sv-SE').format(new Date())
    // 「我的全部资料」= 画像 + 学业 + 待办 + 阶段计划/任务 + 当前报告。
    // 计划这次没读到就不写假数据，导出提示里如实说明，不继续称"全部"。
    const body = {
      exported_at: new Date().toISOString(),
      account,
      source: 'GET /app/bootstrap + /app/notes + /app/report/full-text + /app/plan/action',
      profile: workspace.value.profile_panel,
      academic: workspace.value.academic_panel,
      notes: notes.value,
      action_plan: actionValue,
      report: reportValue,
    }
    const url = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json;charset=utf-8' }))
    const a = document.createElement('a'); a.href = url; a.download = `职引-资料-${account}-${day}.json`; a.rel = 'noopener'
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    status.value = actionValue
      ? `已导出「${account}」的资料（含阶段计划与任务）。`
      : `已导出「${account}」的资料；阶段计划这次没读取到，文件里没有写入计划，可稍后重试补全。`
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
              <article class="settings-export-all"><span><UiIcon name="download" :size="21"/></span><div><h3>我的全部资料</h3><p>画像、学业、待办、阶段计划与任务，以及当前报告的 JSON 副本</p></div><button class="btn" :disabled="busy" @click="exportData">导出</button></article>
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
    <section v-else-if="key === 'guide'" class="ws-paper guide-page">
      <h2>从第一次咨询到下一步行动</h2>
      <p class="guide-intro">这个平台帮你在"不知道自己适合什么"的时候，用对话把情况说清楚，再给出有依据的判断和今天就能做的下一步。下面六步不用一次做完，先做第 1 步就有产出；每一步都写了做什么、点哪里、做完去哪看。</p>
      <ol class="guide-flow">
        <li v-for="(step, index) in guideSteps" :key="step.title">
          <span class="guide-flow__index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
          <div class="guide-flow__copy">
            <h3><RouterLink :to="step.to">{{ step.title }}</RouterLink></h3>
            <p>{{ step.what }}</p>
            <p class="guide-flow__how"><strong>怎么做：</strong>{{ step.how }}</p>
            <p class="guide-flow__out"><strong>做完在哪看：</strong>{{ step.output }}</p>
          </div>
        </li>
      </ol>
      <p class="guide-tools">需要单独核验学籍、导入成绩或课表时，去「应用工具」页，每个工具都写明了读什么、给你什么、什么时候用。</p>
      <div class="ws-inline-actions"><RouterLink class="btn" to="/chat">开始咨询</RouterLink><RouterLink class="btn" to="/profile">核对画像</RouterLink><RouterLink class="btn" to="/directions">比较方向</RouterLink><RouterLink class="btn" to="/tools">打开应用工具</RouterLink></div>
      <DetailPopover title="状态与术语" label="查看状态与术语"><template #trigger>状态与术语</template><dl><dt>待验证</dt><dd>目前证据还不够，需要你在现实中做一次尝试后再回来更新，不是最终结论。</dd><dt>主攻 / 平行 / 保底</dt><dd>主攻是最想投入的方向，平行是同时准备的方向，保底是万一不顺仍能接受的方向。</dd><dt>已读</dt><dd>看过提醒，不代表事项已处理。</dd><dt>待重新计算</dt><dd>依赖资料已变化，旧报告保留原版，需要生成新版。</dd><dt>个人待办</dt><dd>自己记录的安排，与阶段计划任务分别保存。</dd><dt>待支持</dt><dd>功能入口保留，尚缺相应服务能力。</dd></dl></DetailPopover>
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
.guide-page h2 { font-size:22px; }
.guide-intro { max-width:64em; margin-top:10px; color:var(--c-text-2); font-size:14px; line-height:1.85; }
.guide-flow { display:grid; gap:14px; margin:22px 0 18px; padding:0; list-style:none; }
.guide-flow>li { display:grid; grid-template-columns:34px minmax(0,1fr); gap:12px; padding:16px 16px 15px; border:1px solid var(--c-border); border-radius:14px; background:var(--c-surface-2); }
.guide-flow__index { padding-top:2px; color:var(--c-primary); font-size:13px; font-weight:650; font-variant-numeric:tabular-nums; }
.guide-flow__copy { min-width:0; }
.guide-flow__copy h3 { font-size:16px; font-weight:650; }
.guide-flow__copy h3 a { color:var(--c-primary); }
.guide-flow__copy>p { margin-top:6px; color:var(--c-text-2); font-size:13px; line-height:1.8; }
.guide-flow__how strong,.guide-flow__out strong { color:var(--c-text); font-weight:600; }
.guide-flow__out { color:var(--c-text-2); }
.guide-tools { margin:0 0 16px; padding:12px 14px; border-left:3px solid var(--c-primary-border); border-radius:0 10px 10px 0; background:var(--c-primary-weak-2); color:var(--c-text-2); font-size:13px; line-height:1.75; }
@media(max-width:600px){.guide-flow>li{grid-template-columns:minmax(0,1fr);gap:4px}.guide-flow__index{padding-top:0}.guide-page h2{font-size:20px}}
@media(max-width:960px){.settings-identity{grid-template-columns:52px minmax(0,1fr) auto;grid-template-rows:auto auto}.settings-identity__avatar{grid-row:1/3}.settings-identity__name{grid-column:2;grid-row:1}.settings-identity__state{grid-column:2;grid-row:2;justify-content:flex-start}.settings-identity>.btn{grid-column:3;grid-row:1/3}.settings-layout{grid-template-columns:1fr}.settings-data{position:static;order:-1}.settings-data nav{grid-template-columns:repeat(3,minmax(0,1fr))}.settings-data nav>a{grid-template-columns:38px minmax(0,1fr)}.settings-data nav>a>svg{display:none}}
@media(max-width:700px){.settings-export-grid article{grid-template-columns:40px minmax(0,1fr)}.settings-export-grid article>.btn,.settings-export-options{grid-column:1/-1}.settings-export-options{display:grid;grid-template-columns:1fr 1fr}.settings-export-options label{display:grid}.settings-export-grid select{width:100%;min-width:0}.settings-data nav{grid-template-columns:1fr}}
@media(max-width:560px){.settings-identity{grid-template-columns:48px minmax(0,1fr);grid-template-rows:auto auto auto;padding:14px}.settings-identity__avatar{grid-row:1;width:48px;height:48px}.settings-identity__name{grid-column:2;grid-row:1}.settings-identity__state{grid-column:1/-1;grid-row:2;gap:6px}.settings-identity>.btn{grid-column:1/-1;grid-row:3;width:100%}.settings-identity__state>span{min-height:34px}.settings-block,.settings-data{padding:16px}.settings-export-options{grid-template-columns:1fr}.settings-export-grid article{padding:12px}.settings-export-grid article>.btn{width:100%}}
</style>
