<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import type { AcademicCourseView, AcademicGradeView } from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import InfoSheet from '../components/InfoSheet.vue'
import UiIcon from '../components/UiIcon.vue'
import { hasCourseTime, courseTimeLabel } from '../lib/academic'
const academic = computed(() => backendDemo.state.academic)
const tab = ref('overview')
const importOpen = ref(false)
const verifyOpen = ref(false)
const importMode = ref('text')
const courseText = ref('')
const gradeText = ref('')
const courseFile = ref<File | null>(null)
const gradeFile = ref<File | null>(null)
const school = ref('河北大学')
const term = ref('2026–2027 学年秋季')
const verifyCode = ref('')
const error = ref('')
const verifyError = ref('')
const status = ref('')
const saving = ref(false)
const scheduled = computed(() => academic.value?.courses?.filter(hasCourseTime)?.length ?? 0)
function openImport() { importOpen.value = true; error.value = '' }
async function read(file: File | null, text: string) {
  if (importMode.value === 'text') return text
  if (!file) return ''
  if (file.size > 2_000_000) throw new Error('每份文件需小于 2MB。')
  if (!file.name.toLowerCase().endsWith('.json')) throw new Error('演示导入支持 JSON。教务网页与表格原文由正式后端解析。')
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
    const courseSource = await read(courseFile.value, courseText.value)
    const gradeSource = await read(gradeFile.value, gradeText.value)
    if (courseSource.length > 200_000 || gradeSource.length > 200_000) throw new Error('每栏最多 20 万字，请去掉无关内容。')
    if (!courseSource.trim() && !gradeSource.trim()) throw new Error('至少提供一份课表或成绩数据。')
    const courses = rows<AcademicCourseView>(courseSource, 'courses')
    const grades = rows<AcademicGradeView>(gradeSource, 'grades')
    backendDemo.setAcademic(courses, grades, school.value, term.value)
    importOpen.value = false
    status.value = '演示已读取 ' + courses.length + ' 门课程，其中 ' + courses.filter(hasCourseTime).length + ' 门带完整上课时间；' + grades.length + ' 条成绩。'
  } catch (e) { error.value = e instanceof SyntaxError ? 'JSON 格式还不完整。可以先加载课表示例查看效果。' : (e as Error).message }
  finally { saving.value = false }
}
function revoke() { backendDemo.revokeAcademic(); status.value = '演示的课表和成绩快照已清空，日历与课表也会同步更新。' }
function verify() {
  if (!verifyCode.value.trim()) { verifyError.value = '请填写在线验证码，演示可使用示例值。'; return }
  backendDemo.verifySample(); verifyOpen.value = false; status.value = '已展示核验结果示例，未提交真实验证码。'
}
</script>
<template>
  <div class="ws-page">
    <PageHeading title="学籍与资料" description="管理学校信息、课程与成绩快照，并核验学籍资料。"><button class="btn btn--primary" @click="openImport"><UiIcon name="upload" :size="16" />导入课表与成绩</button></PageHeading>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-section-head"><div><h2>{{ academic ? academic.school : '暂无学校资料' }}</h2><p>{{ academic ? academic.term : '导入课程与成绩，为时间安排和个人画像提供依据。' }}</p></div><UiIcon name="academic" :size="32" /></div>
        <p v-if="status" class="desk-status" role="status">{{ status }}</p>
        <div class="ws-tabs" aria-label="学校资料视图" style="margin-top: var(--sp-5)"><button :aria-pressed="tab === 'overview'" @click="tab = 'overview'">资料概况</button><button :aria-pressed="tab === 'courses'" @click="tab = 'courses'">课程表</button><button :aria-pressed="tab === 'grades'" @click="tab = 'grades'">成绩记录</button></div>
        <template v-if="academic">
          <dl v-if="tab === 'overview'" class="ws-facts"><div><dt>已有课程</dt><dd>{{ academic.courses?.length ?? 0 }} 门</dd></div><div><dt>可排进课表</dt><dd>{{ scheduled }} 门</dd></div><div><dt>成绩记录</dt><dd>{{ academic.grades?.length ?? 0 }} 条</dd></div><div><dt>导入时间</dt><dd>{{ new Date(academic.imported_at ?? '').toLocaleDateString('zh-CN') }}</dd></div><div><dt>数据来源</dt><dd>自己导入的快照</dd></div><div><dt>学籍核验</dt><dd>{{ backendDemo.state.chsiChecked ? '已展示核验示例' : '待核验' }}</dd></div></dl>
          <div v-else-if="tab === 'courses'" class="desk-table-wrap ws-section"><table class="desk-table"><thead><tr><th>课程</th><th>上课时间</th><th>地点</th></tr></thead><tbody><tr v-for="c in academic.courses" :key="c.name + c.weekday"><td>{{ c.name }}</td><td>{{ courseTimeLabel(c) }}</td><td>{{ c.place || '未提供' }}</td></tr></tbody></table><p v-if="!academic.courses?.length" class="ws-empty ws-muted">这份快照没有课程，可继续导入。</p></div>
          <div v-else class="desk-table-wrap ws-section"><table class="desk-table"><thead><tr><th>课程</th><th>成绩</th><th>学分</th><th>学期</th></tr></thead><tbody><tr v-for="g in academic.grades" :key="g.name + g.term"><td>{{ g.name }}</td><td>{{ g.score || '未提供' }}</td><td>{{ g.credit || '—' }}</td><td>{{ g.term || '未提供' }}</td></tr></tbody></table><p v-if="!academic.grades?.length" class="ws-empty ws-muted">这份快照没有成绩，可继续导入。</p></div>
          <div class="ws-inline-actions"><RouterLink class="ws-text-link" to="/schedule">查看日历与课表<UiIcon name="arrow" :size="16" /></RouterLink><button class="ws-text-button" @click="revoke">撤回导入资料</button></div>
        </template>
        <div v-else class="ws-empty"><UiIcon name="academic" :size="42" /><h3 style="margin-top: var(--sp-4)">还没有学校资料</h3><p>支持导入课表与成绩，也可加载演示数据。</p><button class="btn" style="margin-top: var(--sp-4)" @click="backendDemo.loadAcademicSample(); status = '已加载课表与成绩的演示样例。'">加载课表示例</button></div>
      </section>
      <aside class="ws-aside"><section><h2>核对学籍</h2><p>去学信网获取在线验证码，用它核对学籍信息。全程无需账号密码。</p><button class="ws-text-button" @click="verifyOpen = true; verifyError = ''"><UiIcon name="shield" :size="18" />提供在线验证码</button></section><section><h2>课程时间完整性</h2><p>课程数量与带上课时间的课程分别显示，缺少时间的记录不会被放进课表。</p></section><section><h2>撤回资料</h2><p>正式后端会同时清空课表、成绩快照与对应画像摘要。这里演示资料与日历的同步变化。</p></section></aside>
    </div>
    <p class="ws-demo-note">预置示例。演示不提交真实验证码或文件；正式学校资料解析与核验由后端完成。</p>
    <InfoSheet :open="importOpen" title="导入课表与成绩" wide @close="!saving && (importOpen = false)"><p class="ws-muted">演示接受 JSON 数组或包含 courses / grades 的对象。正式后端还支持教务原文与文件解析。</p><div class="ws-tabs" style="margin-top: var(--sp-4)"><button :aria-pressed="importMode === 'text'" @click="importMode = 'text'">粘贴文本</button><button :aria-pressed="importMode === 'file'" @click="importMode = 'file'">上传文件</button></div><form @submit.prevent="submit"><div class="ws-chart-grid"><label class="ws-field">学校<input v-model="school" maxlength="120" /></label><label class="ws-field">学期<input v-model="term" maxlength="40" /></label></div><template v-if="importMode === 'text'"><label class="ws-field">课表 JSON（可留空）<textarea v-model="courseText" :maxlength="200000" placeholder='[{"name":"材料分析","weekday":1,"start_period":1,"end_period":2}]' /></label><label class="ws-field">成绩 JSON（可留空）<textarea v-model="gradeText" :maxlength="200000" placeholder='[{"name":"材料基础","score":"86","credit":"3"}]' /></label></template><template v-else><label class="ws-field">课表文件（JSON，小于 2MB）<input type="file" accept=".json" @change="courseFile = ($event.target as HTMLInputElement).files?.[0] ?? null" /></label><label class="ws-field">成绩文件（JSON，小于 2MB）<input type="file" accept=".json" @change="gradeFile = ($event.target as HTMLInputElement).files?.[0] ?? null" /></label></template><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><div class="ws-inline-actions"><button class="btn btn--primary" :disabled="saving" type="submit">{{ saving ? '正在读取…' : '演示导入' }}</button><button class="ws-text-button" type="button" @click="backendDemo.loadAcademicSample(); importOpen = false; status = '已加载课表与成绩的演示样例。'">直接加载示例</button></div></form></InfoSheet>
    <InfoSheet :open="verifyOpen" title="核对学籍资料" @close="verifyOpen = false"><p class="ws-muted">演示只展示核验结果，不发送验证码。不要填写学信网账号或密码。</p><form @submit.prevent="verify"><label class="ws-field">在线验证码<input v-model="verifyCode" autocomplete="off" placeholder="演示可填写 DEMO-2026" maxlength="80" /></label><p v-if="verifyError" class="ws-field-error" role="alert">{{ verifyError }}</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">查看核验示例</button><a class="ws-text-link" href="https://www.chsi.com.cn/" target="_blank" rel="noopener noreferrer">去学信网</a></div></form></InfoSheet>
  </div>
</template>
