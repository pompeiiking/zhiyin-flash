<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import type { AcademicCourseView, AcademicGradeView } from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import InfoSheet from '../components/InfoSheet.vue'
import { parseAcademicTable } from '../lib/academic-parser'
import AcademicVerification from '../components/AcademicVerification.vue'
import { backendClient } from '../api/backend-client'
import PanelTabs from '../components/PanelTabs.vue'
import UiIcon from '../components/UiIcon.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import StatTile from '../components/StatTile.vue'
import SourceChip from '../components/SourceChip.vue'
import StatusBanner from '../components/StatusBanner.vue'
import type { ProfileSource } from '../api/backend-types'
import { hasCourseTime, courseTimeLabel } from '../lib/academic'
const academic = computed(() => backendDemo.state.academic)
const tab = ref('overview')
const importOpen = ref(false)
const verifyOpen = ref(false)
const importMode = ref<'text'|'file'|'table'>('table')
const importStage = ref<'select' | 'review'>('select')
const revokeOpen = ref(false)
const prepared = ref<{ courses: AcademicCourseView[]; grades: AcademicGradeView[]; school: string; term: string } | null>(null)
const courseText = ref('')
const gradeText = ref('')
const courseFile = ref<File | null>(null)
const gradeFile = ref<File | null>(null)
const school = ref('河北大学')
const term = ref('2026–2027 学年秋季')
const preparedFromSample=ref(false)
const saveOnline=ref(false),importCommitted=ref(false),serviceError=ref('')
const error = ref('')
const verifyError = ref('')
const status = ref('')
const saving = ref(false)
const scheduled = computed(() => academic.value?.courses?.filter(hasCourseTime)?.length ?? 0)
/* 数据来源 → SourceChip 的枚举：本页只有"教务记录"这一档成立
   （预置示例是本地快照，但它模拟的仍是教务台账；来源枚举不明是 U3 记的缺口）。 */
const sourceKind = computed<ProfileSource>(() => 'record')
const sourceLabel = computed(() => backendDemo.state.academicOrigin==='sample' ? '预置示例' : backendDemo.state.academicOrigin==='live' ? (academic.value?.source || '已保存的资料') : '本人核对的本地快照')
const loadingSample = ref(false), refreshingSample = ref(false)
async function loadSample() {
  if (loadingSample.value) return
  loadingSample.value = true
  // 让骨架屏至少有一帧可渲染：同步 setAcademic 会把"正在读"这一态吃掉
  await new Promise((r) => setTimeout(r, 320))
  backendDemo.loadAcademicSample()
  status.value = '已加载课表与成绩的演示样例。'
  loadingSample.value = false
}
function openImport() { importOpen.value = true; importStage.value = 'select'; prepared.value = null; preparedFromSample.value=false; error.value = '';saveOnline.value=false;importCommitted.value=false }
async function loadSaved(){if(saving.value)return;const had=academic.value!==null;saving.value=true;serviceError.value='';if(had)refreshingSample.value=true;try{const result=await backendClient.workspace();if(result.academic_panel===undefined)throw new Error('Incomplete snapshot');backendDemo.setWorkspace(result);status.value='已读取保存的学校资料。'}catch{serviceError.value='已保存资料暂时没有取得，请重试。现有快照仍保留。'}finally{saving.value=false;refreshingSample.value=false}}
async function confirmImport() {
  if (!prepared.value || saving.value) return
  const p = prepared.value
  if(preparedFromSample.value&&saveOnline.value){error.value='示例资料仅用于本地演示，不能提交为个人资料。';return}
  if(saveOnline.value){saving.value=true;error.value='';try{if(!importCommitted.value){const receipt=await backendClient.academic({courses:JSON.stringify(p.courses),grades:JSON.stringify(p.grades),school:p.school,term:p.term});importCommitted.value=true;receipt.wrote_profile?.forEach(key=>backendDemo.markProfileChange(key))}const data=await backendClient.workspace();if(data.academic_panel===undefined)throw new Error('Incomplete snapshot');backendDemo.setWorkspace(data);status.value='资料已保存，最新快照已读取。';importOpen.value=false}catch{error.value=importCommitted.value?'资料已提交，但最新快照暂时没有取得。请读取保存后的资料核对，不会再次提交同一份材料。':'本次提交结果没有确认，输入与原快照保留。请先读取个人资料核对，再决定是否重试。'}finally{saving.value=false}return}
  backendDemo.setAcademic(p.courses, p.grades, p.school, p.term)
  if(preparedFromSample.value)backendDemo.loadAcademicSample()
  status.value = '已确认 ' + p.courses.length + ' 门课程、' + p.grades.length + ' 条成绩。时间不全的课程仍保留在资料列表。'
  importOpen.value = false
}
function prepareSample() {
  preparedFromSample.value=true;saveOnline.value=false
  const sample = backendDemo.academicSample()
  prepared.value = { courses: sample.courses ?? [], grades: sample.grades ?? [], school: school.value.trim() || sample.school || '学校待补充', term: term.value.trim() || sample.term || '学期待补充' }
  importStage.value = 'review'
}
async function read(file: File | null, text: string) {
  if (importMode.value !== 'file') return text
  if (!file) return ''
  if (file.size > 2_000_000) throw new Error('每份文件需小于 2MB。')
  if (!/\.(json|csv|tsv|txt)$/i.test(file.name)) throw new Error('请选择CSV、表格文本或JSON文件。扫描件和二进制表格需要正式资料解析服务。')
  return await file.text()
}
function rows<T>(source: string, key: string): T[] {
  if (!source.trim()) return []
  const parsed: unknown = JSON.parse(source)
  const list: unknown = Array.isArray(parsed) ? parsed : parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>)[key] : null
  if (!Array.isArray(list) || !list.length) throw new Error('请提供非空的 ' + (key === 'courses' ? '课程' : '成绩') + '数组，每条包含 name。')
  for (const item of list) {
    if (!item || typeof item !== 'object' || typeof item.name !== 'string' || !item.name.trim()) throw new Error('每条记录都需要课程名称 name。')
    if (key === 'courses') {
      for (const field of ['weekday', 'start_period', 'end_period']) if (item[field] !== undefined && !Number.isInteger(item[field])) throw new Error('课程时间字段需要整数。')
      if (item.weekday !== undefined && (item.weekday < 0 || item.weekday > 7)) throw new Error('weekday 应为 0–7。')
    } else if (item.score !== undefined && typeof item.score !== 'string') throw new Error('score 请使用字符串，等级制成绩会原样保存。')
  }
  return list as T[]
}
async function submit() {
  error.value = ''; saving.value = true
  try {
    if (!school.value.trim() || !term.value.trim()) throw new Error('请填写学校和学期，方便核对这份资料。')
    const courseSource = await read(courseFile.value, courseText.value)
    const gradeSource = await read(gradeFile.value, gradeText.value)
    if (courseSource.length > 200_000 || gradeSource.length > 200_000) throw new Error('每栏最多 20 万字，请去掉无关内容。')
    if (!courseSource.trim() && !gradeSource.trim()) throw new Error('至少提供一份课表或成绩数据。')
    const isJson = (source: string) => /^\s*[\[{]/.test(source)
    const courses = importMode.value === 'text' || isJson(courseSource) ? rows<AcademicCourseView>(courseSource, 'courses') : parseAcademicTable<AcademicCourseView>(courseSource, 'courses')
    const grades = importMode.value === 'text' || isJson(gradeSource) ? rows<AcademicGradeView>(gradeSource, 'grades') : parseAcademicTable<AcademicGradeView>(gradeSource, 'grades')
    preparedFromSample.value=false
    prepared.value = { courses, grades, school: school.value.trim(), term: term.value.trim() }
    importStage.value = 'review'
  } catch (e) { error.value = e instanceof SyntaxError ? 'JSON 格式还不完整。可以先加载课表示例查看效果。' : (e as Error).message }
  finally { saving.value = false }
}
async function revoke() {if(saving.value)return;if(backendDemo.state.academicOrigin!=='live'){backendDemo.revokeAcademic();revokeOpen.value=false;status.value='本地课表与成绩快照已清空。';return}saving.value=true;serviceError.value='';try{const result=await backendClient.revokeAcademic();if(!result.revoked)throw new Error('Not confirmed');backendDemo.revokeAcademic();backendDemo.markProfileChange('courses');backendDemo.markProfileChange('grades');revokeOpen.value=false;status.value='已撤回保存的学校资料。';try{backendDemo.setWorkspace(await backendClient.workspace())}catch{serviceError.value='资料已撤回，但最新档案尚未取得，请重新读取资料核对。'}}catch{serviceError.value='撤回结果暂时没有确认。原显示内容保留，请先读取最新资料核对。'}finally{saving.value=false}}
</script>
<template>
  <div class="ws-page">
    <PageHeading title="学籍与资料" description="管理学校信息、课程与成绩快照，并核验学籍资料。"><button class="btn" :disabled="saving" @click="loadSaved">{{ saving?'正在处理…':'读取已保存资料' }}</button><button class="btn btn--primary" @click="openImport"><UiIcon name="upload" :size="16" />导入课表与成绩</button></PageHeading>
    <StatusBanner v-if="status" tone="success" class="ws-section" :message="status" @dismiss="status = ''" /><p v-if="serviceError" class="ws-field-error" role="alert">{{ serviceError }}</p><div class="ws-two-columns">
      <section class="ws-paper">
        <section class="c2-academic-sources" aria-label="资料来源与边界"><h2>这些资料是从哪里来的</h2><p>学校档案、课程成绩和本人补充分别保留来源。每条资料能核对什么、还缺什么，在同一张表里查看。</p><table><thead><tr><th scope="col">来源</th><th scope="col">能核对什么</th><th scope="col">还需要什么</th></tr></thead><tbody><tr><th scope="row">学信网</th><td>学校、专业、年级与在读状态</td><td>本人提供在线验证码，再核对学籍</td></tr><tr><th scope="row">课程与成绩</th><td>{{ academic?.courses?.length ?? 0 }} 门课程、{{ academic?.grades?.length ?? 0 }} 条成绩快照</td><td>{{ Math.max(0,(academic?.courses?.length ?? 0)-scheduled) }} 门课的时间待补充；空课格不等于空闲</td></tr><tr><th scope="row">本人上传</th><td>已有的课表、成绩与经历资料</td><td>确认导入后才替换快照；保留本人来源</td></tr></tbody></table></section>
        <div class="ws-section-head"><div><h2>{{ academic ? academic.school : '暂无学校资料' }}</h2><p>{{ academic ? academic.term : '导入课程与成绩，为时间安排和个人画像提供依据。' }}</p></div><UiIcon name="academic" :size="32" /></div>
        <p v-if="status" class="desk-status" role="status">{{ status }}</p>
        <PanelTabs v-model="tab" label="学校资料视图" :items="[{key: 'overview', label: '资料概况'}, {key: 'courses', label: '课程表'}, {key: 'grades', label: '成绩记录'}]">
        <template v-if="academic">
          <div class="academic-refresh" :aria-busy="refreshingSample">
            <SkeletonBlock v-if="refreshingSample" class="academic-refresh__sk" variant="list" :lines="3" />
            <p v-if="refreshingSample" class="sr-only" role="status">正在读取已保存的学校资料，当前快照保留。</p>
            <dl v-if="tab === 'overview'" class="ws-facts academic-facts"><div class="academic-facts__cell"><dt>已有课程</dt><dd><StatTile :value="academic.courses?.length ?? 0" unit="门" label="已有课程" /></dd></div><div class="academic-facts__cell"><dt>可排进课表</dt><dd><StatTile :value="scheduled" unit="门" label="可排进课表" :denominator="academic.courses?.length ?? 0" :progress="academic.courses?.length ? scheduled / academic.courses.length : 0" /></dd></div><div class="academic-facts__cell"><dt>成绩记录</dt><dd><StatTile :value="academic.grades?.length ?? 0" unit="条" label="成绩记录" /></dd></div></dl>
            <div v-if="tab === 'overview'" class="ws-inline-actions academic-source"><SourceChip :source="sourceKind" size="md" /><span class="academic-source__note">{{ sourceLabel }}<template v-if="academic.imported_at"> · 导入于 <time :datetime="academic.imported_at">{{ new Date(academic.imported_at).toLocaleDateString('zh-CN') }}</time></template> · 学籍核验：{{ backendDemo.state.chsiChecked ? '已展示核验示例' : '待核验' }}</span></div>
            <div v-if="tab === 'courses'" class="desk-table-wrap ws-section"><table class="desk-table"><thead><tr><th>课程</th><th>上课时间</th><th>地点</th></tr></thead><tbody><tr v-for="c in academic.courses" :key="c.name + c.weekday"><td>{{ c.name }}</td><td>{{ courseTimeLabel(c) }}</td><td>{{ c.place || '未提供' }}</td></tr></tbody></table><EmptyState v-if="!academic.courses?.length" class="ws-section" kind="academic" size="sm" :heading-level="4" title="这份快照没有课程" description="可以粘贴教务表格，或读取 CSV、JSON 再导入。" /></div>
            <div v-if="tab === 'grades'" class="desk-table-wrap ws-section"><table class="desk-table"><thead><tr><th>课程</th><th>成绩</th><th>学分</th><th>学期</th></tr></thead><tbody><tr v-for="g in academic.grades" :key="g.name + g.term"><td>{{ g.name }}</td><td>{{ g.score || '未提供' }}</td><td>{{ g.credit || '—' }}</td><td>{{ g.term || '未提供' }}</td></tr></tbody></table><EmptyState v-if="!academic.grades?.length" class="ws-section" kind="academic" size="sm" :heading-level="4" title="这份快照没有成绩" description="成绩可以随课表一起导入，等级制成绩会原样保存。" /></div>
            <div class="ws-inline-actions"><RouterLink class="ws-text-link" to="/schedule">查看日历与课表<UiIcon name="arrow" :size="16" /></RouterLink></div>
          </div>
        </template>
        <EmptyState v-else class="ws-section" kind="academic" :heading-level="2" title="还没有学校资料" description="支持导入课表与成绩，也可先加载演示数据看看形状。" action-label="加载课表示例" @action="loadSample" />
        </PanelTabs>
      </section>
      <div class="academic-side">
        <section class="academic-side__verify">
          <h2>核对学籍</h2><p>去学信网获取在线验证码，用它核对学籍信息。全程无需账号密码。</p>
          <button class="btn btn--primary" @click="verifyOpen = true; verifyError = ''"><UiIcon name="shield" :size="18" />提供在线验证码</button>
        </section>
        <Foldable title="课程时间完整性" variant="section" :default-open="false"><p>课程数量与带上课时间的课程分别显示，缺少时间的记录不会被放进课表。</p></Foldable>
        <section class="ws-section academic-side__revoke"><h2>撤回资料</h2><p>正式后端会同时清空课表、成绩快照与对应画像摘要。这里演示资料与日历的同步变化。</p><button class="btn btn--danger" @click="revokeOpen=true"><UiIcon name="shield" :size="18" />撤回导入资料</button></section>
      </div>
    </div>
    <p class="ws-demo-note">示例操作保留在本次演示；读取与保存个人资料、核验个人资料分别按你选择的方式进行，不以示例替代失败结果。</p>
    <InfoSheet :open="importOpen" shape="panel" title="导入课表与成绩" @close="!saving && (importOpen = false)"><p class="ws-muted">选择资料 → 核对结果 → 确认导入。支持复制教务表格，或读取CSV、表格文本与JSON；先核对识别结果，确认前保留原资料。</p><template v-if="importStage==='select'"><div class="ws-tabs" style="margin-top: var(--sp-4)"><button :aria-pressed="importMode === 'table'" @click="importMode = 'table'">粘贴教务表格</button><button :aria-pressed="importMode === 'text'" @click="importMode = 'text'">高级：JSON 文本</button><button :aria-pressed="importMode === 'file'" @click="importMode = 'file'">上传文件</button></div><form @submit.prevent="submit"><div class="ws-chart-grid"><label class="ws-field">学校<input v-model="school" maxlength="120" /></label><label class="ws-field">学期<input v-model="term" maxlength="40" /></label></div><template v-if="importMode === 'text'"><label class="ws-field">课表 JSON（可留空）<textarea v-model="courseText" :maxlength="200000" placeholder='[{"name":"材料分析","weekday":1,"start_period":1,"end_period":2}]' /></label><label class="ws-field">成绩 JSON（可留空）<textarea v-model="gradeText" :maxlength="200000" placeholder='[{"name":"材料基础","score":"86","credit":"3"}]' /></label></template><template v-else-if="importMode === 'table'"><label class="ws-field">课表表格（可留空）<textarea v-model="courseText" :maxlength="200000" rows="6" placeholder="复制带表头的教务表格，例如：课程名称、星期、节次、地点"/></label><label class="ws-field">成绩表格（可留空）<textarea v-model="gradeText" :maxlength="200000" rows="6" placeholder="复制带表头的成绩表格，例如：课程名称、成绩、学分"/></label><p class="ws-muted">保留第一行表头；列可用制表符或逗号分隔。缺少时间的课程会保留为待补充。</p></template><template v-else><label class="ws-field">课表文件（CSV、文本或JSON，小于 2MB）<input type="file" accept=".csv,.tsv,.txt,.json" @change="courseFile = ($event.target as HTMLInputElement).files?.[0] ?? null" /></label><label class="ws-field">成绩文件（CSV、文本或JSON，小于 2MB）<input type="file" accept=".csv,.tsv,.txt,.json" @change="gradeFile = ($event.target as HTMLInputElement).files?.[0] ?? null" /></label></template><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="ws-inline-actions"><button class="btn btn--primary" :disabled="saving" type="submit">{{ saving ? '正在读取…' : '读取并核对' }}</button><button class="ws-text-button" type="button" @click="prepareSample">直接加载示例</button></div></form></template><section v-else-if="prepared" class="import-review"><h3>{{ prepared.school }} · {{ prepared.term }}</h3><p>{{ prepared.courses.length }} 门课程 · {{ prepared.grades.length }} 条成绩</p><p class="ws-muted">其中 {{ prepared.courses.filter(hasCourseTime).length }} 门课程时间完整；缺失的时间保留为待补充。</p><div class="desk-table-wrap"><table class="desk-table"><thead><tr><th>课程</th><th>识别的时间</th><th>地点</th></tr></thead><tbody><tr v-for="(c,i) in prepared.courses" :key="i"><td>{{ c.name }}</td><td>{{ courseTimeLabel(c) }}</td><td>{{ c.place || '未提供' }}</td></tr></tbody></table><table v-if="prepared.grades.length" class="desk-table"><thead><tr><th>课程</th><th>成绩</th><th>学分</th></tr></thead><tbody><tr v-for="(g,i) in prepared.grades" :key="i"><td>{{ g.name }}</td><td>{{ g.score || '未提供' }}</td><td>{{ g.credit || '未提供' }}</td></tr></tbody></table></div><fieldset class="ws-field ws-section"><legend>保存方式</legend><label class="direction-radio"><input v-model="saveOnline" type="radio" :value="false" :disabled="saving||importCommitted"/>仅更新本次演示</label><label class="direction-radio"><input v-model="saveOnline" type="radio" :value="true" :disabled="saving||importCommitted||preparedFromSample"/>保存到个人资料</label></fieldset><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="ws-inline-actions"><button class="btn btn--primary" :disabled="saving" @click="confirmImport">{{ saving?'正在保存…':importCommitted?'读取保存后的资料':'确认导入' }}</button><button class="btn" :disabled="saving||importCommitted" @click="importStage='select'">返回修改</button></div><p class="ws-demo-note">确认前不替换已有快照；按你选择的保存方式更新。资料提交后仅重试读取，不重复提交。</p></section></InfoSheet>
    <InfoSheet :open="revokeOpen" shape="dialog" title="撤回导入资料？" @close="revokeOpen=false"><p>{{ backendDemo.state.academicOrigin==='live'?'将撤回已保存的学校资料，并清空对应课程、成绩与课表。':'将清空本地课程、成绩与课表快照。' }}个人待办和行动记录保留。</p><p v-if="serviceError" class="ws-field-error" role="alert">{{ serviceError }}</p><div class="ws-inline-actions"><button class="btn btn--danger" @click="revoke" :disabled="saving">{{ saving?'正在撤回…':'确认撤回' }}</button><button class="btn" @click="revokeOpen=false">保留资料</button></div></InfoSheet>
    <InfoSheet :open="verifyOpen" shape="panel" title="核对学籍资料" @close="verifyOpen=false"><AcademicVerification @sample="verifyOpen=false;status='已展示核验示例，没有提交真实验证码。'"/></InfoSheet>
  </div>
</template>

<style scoped>
/* 刷新时盖骨架（不摘内容）：.ws-facts 那一块还在 DOM 里，只是暂时不可信 */
.academic-refresh { position: relative; }
.academic-refresh__sk { position: absolute; inset: 0; z-index: 1; background: var(--c-surface); }
/* 三个读数用 StatTile：同一把尺、右对齐、有进度；窄屏落成单列（全局 .ws-facts 只管两列） */
.academic-facts { margin-top: var(--sp-5); }
/* dt 与瓦片自带的 label 重复：视觉上藏掉，读屏仍读得到（用全局 .sr-only，不用 display:none —— 那会把节点从无障碍树里摘掉） */
.academic-facts dt { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.academic-facts__cell { min-width: 0; }
.academic-source__note { font-size: var(--fs-12); color: var(--c-text-3); }
/* 右侧栏：核验入口与撤回都不再藏进折叠，所以要有自己的层次 */
.academic-side { display: grid; gap: var(--sp-5); align-content: start; }
.academic-side__verify h2, .academic-side__revoke h2 { font-size: var(--fs-16); font-weight: var(--fw-semibold); }
.academic-side__verify p, .academic-side__revoke p { margin-top: var(--sp-2); font-size: var(--fs-14); line-height: 1.8; color: var(--c-text-2); }
.academic-side__verify .btn, .academic-side__revoke .btn { margin-top: var(--sp-4); }
@media (max-width: 760px) { .academic-facts { grid-template-columns: minmax(0, 1fr); } }
</style>
