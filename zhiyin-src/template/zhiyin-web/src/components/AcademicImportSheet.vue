<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AcademicCourseView, AcademicGradeView } from '../api/backend-types'
import { backendClient } from '../api/backend-client'
import { parseAcademicTable } from '../lib/academic-parser'
import InfoSheet from './InfoSheet.vue'
import StatusBanner from './StatusBanner.vue'

type Kind = 'courses' | 'grades'
type Row = AcademicCourseView | AcademicGradeView

const props = defineProps<{ open: boolean; kind: Kind; school?: string; term?: string; hasRows?: boolean }>()
const emit = defineEmits<{ close: []; saved: [message: string] }>()

const raw = ref('')
const file = ref<File | null>(null)
const school = ref('')
const term = ref('')
const rows = ref<Row[]>([])
const stage = ref<'edit' | 'review'>('edit')
const busy = ref(false)
const error = ref('')

const noun = computed(() => props.kind === 'courses' ? '课表' : '成绩')
const example = computed(() => props.kind === 'courses'
  ? '课程名称\t星期\t节次\t地点\n高等数学\t周一\t1-2\t教学楼1-201'
  : '课程名称\t成绩\t学分\t绩点\n高等数学\t88\t4\t3.8')

watch(() => props.open, (open) => {
  if (!open) return
  raw.value = ''
  file.value = null
  rows.value = []
  stage.value = 'edit'
  error.value = ''
  school.value = props.school ?? ''
  term.value = props.term ?? ''
})

function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function parseJson(source: string): Row[] {
  const parsed: unknown = JSON.parse(source)
  const list = Array.isArray(parsed) ? parsed : parsed && typeof parsed === 'object'
    ? (parsed as Record<string, unknown>)[props.kind]
    : null
  if (!Array.isArray(list) || !list.length) throw new Error(`JSON 中需要非空的 ${props.kind} 数组。`)
  if (list.some(item => !item || typeof item !== 'object' || typeof item.name !== 'string' || !item.name.trim())) {
    throw new Error('每条记录都需要课程名称 name。')
  }
  return list as Row[]
}

async function preview() {
  error.value = ''
  busy.value = true
  try {
    if (!school.value.trim() || !term.value.trim()) throw new Error('请填写学校和学期，方便日后核对。')
    let source = raw.value
    if (file.value) {
      if (file.value.size > 2_000_000) throw new Error('文件需小于 2MB。')
      if (!/\.(json|csv|tsv|txt)$/i.test(file.value.name)) throw new Error('请选择 JSON、CSV、TSV 或 TXT 文件。')
      source = await file.value.text()
    }
    if (!source.trim()) throw new Error(`请粘贴${noun.value}，或选择一份文件。`)
    if (source.length > 200_000) throw new Error('内容最多 20 万字，请去掉无关部分。')
    rows.value = /^\s*[\[{]/.test(source)
      ? parseJson(source)
      : parseAcademicTable(source, props.kind)
    raw.value = source
    stage.value = 'review'
  } catch (cause) {
    error.value = cause instanceof SyntaxError ? 'JSON 格式不完整，请检查括号和引号。' : (cause as Error).message
  } finally {
    busy.value = false
  }
}

async function save() {
  if (busy.value || !rows.value.length) return
  busy.value = true
  error.value = ''
  try {
    const serialized = JSON.stringify(rows.value)
    const receipt = await backendClient.academic({
      courses: props.kind === 'courses' ? serialized : '',
      grades: props.kind === 'grades' ? serialized : '',
      school: school.value.trim(),
      term: term.value.trim(),
    })
    emit('saved', `已保存 ${props.kind === 'courses' ? receipt.courses : receipt.grades} ${props.kind === 'courses' ? '门课程' : '条成绩'}。`)
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <InfoSheet :open="open" shape="panel" :title="`${hasRows ? '更新' : '导入'}${noun}`" @close="emit('close')">
    <template v-if="stage === 'edit'">
      <p class="import-lead">只会替换当前{{ noun }}，不会改动{{ kind === 'courses' ? '成绩记录' : '日历中的课程' }}。保存前可逐条预览。</p>
      <div class="import-meta">
        <label class="ws-field">学校<input v-model="school" maxlength="120" placeholder="例如：某某大学" /></label>
        <label class="ws-field">学期<input v-model="term" maxlength="40" placeholder="例如：2026-2027-1" /></label>
      </div>
      <label class="ws-field">粘贴{{ noun }}表格<textarea v-model="raw" rows="9" maxlength="200000" :placeholder="example" /></label>
      <label class="import-file"><span>或选择文件</span><input type="file" accept=".json,.csv,.tsv,.txt,text/plain,text/csv,application/json" @change="selectFile" /><small>{{ file?.name || '支持 JSON、CSV、TSV、TXT，最大 2MB' }}</small></label>
      <StatusBanner v-if="error" tone="error" size="sm" :message="error" />
      <div class="ws-inline-actions"><button class="btn btn--primary" type="button" :disabled="busy" @click="preview">{{ busy ? '正在读取…' : '预览识别结果' }}</button><button class="btn" type="button" @click="emit('close')">取消</button></div>
    </template>
    <template v-else>
      <div class="import-review-head"><div><strong>{{ rows.length }}</strong><span>{{ kind === 'courses' ? '门课程' : '条成绩' }}</span></div><p>{{ school }} · {{ term }}</p></div>
      <div class="import-table-wrap"><table><thead><tr><th>课程</th><th v-if="kind === 'courses'">时间</th><th v-if="kind === 'courses'">地点</th><th v-if="kind === 'grades'">成绩</th><th v-if="kind === 'grades'">学分 / 绩点</th></tr></thead><tbody><tr v-for="(row, index) in rows.slice(0, 20)" :key="row.name + index"><td>{{ row.name }}</td><template v-if="kind === 'courses'"><td>{{ (row as AcademicCourseView).weekday ? `周${'一二三四五六日'[(row as AcademicCourseView).weekday! - 1]} · ${(row as AcademicCourseView).start_period || '?'}–${(row as AcademicCourseView).end_period || '?'} 节` : '待补充' }}</td><td>{{ (row as AcademicCourseView).place || '—' }}</td></template><template v-else><td class="import-score">{{ (row as AcademicGradeView).score || '—' }}</td><td>{{ (row as AcademicGradeView).credit || '—' }} / {{ (row as AcademicGradeView).point || '—' }}</td></template></tr></tbody></table></div>
      <p v-if="rows.length > 20" class="ws-muted">这里只预览前 20 条，其余 {{ rows.length - 20 }} 条会一起保存。</p>
      <StatusBanner v-if="error" tone="error" size="sm" :message="error" />
      <div class="ws-inline-actions"><button class="btn btn--primary" type="button" :disabled="busy" @click="save">{{ busy ? '正在保存…' : `确认替换${noun}` }}</button><button class="btn" type="button" :disabled="busy" @click="stage='edit'">返回修改</button></div>
    </template>
  </InfoSheet>
</template>

<style scoped>
.import-lead{margin:0 0 20px;color:var(--c-text-2);font-size:var(--fs-14);line-height:1.75}.import-meta{display:grid;grid-template-columns:1fr 1fr;gap:14px}.import-file{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:8px 12px;margin-top:14px;padding:16px;border:1px dashed var(--c-border-strong);border-radius:var(--r-md);color:var(--c-text-2);font-size:var(--fs-14)}.import-file input{grid-column:1/-1}.import-file small{font-size:var(--fs-12);color:var(--c-text-3)}.ws-inline-actions{margin-top:20px}.import-review-head{display:flex;align-items:end;justify-content:space-between;gap:16px;padding-bottom:18px;border-bottom:1px solid var(--c-border)}.import-review-head div{display:flex;align-items:baseline;gap:8px}.import-review-head strong{font-size:var(--fs-30);font-weight:var(--fw-semibold)}.import-review-head span,.import-review-head p{color:var(--c-text-2);font-size:var(--fs-13)}.import-table-wrap{overflow:auto;margin-top:18px;border:1px solid var(--c-border);border-radius:var(--r-md)}table{width:100%;border-collapse:collapse;font-size:var(--fs-13)}th,td{padding:12px 14px;border-bottom:1px solid var(--c-border);text-align:left;white-space:nowrap}th{background:var(--c-surface-2);color:var(--c-text-3);font-size:var(--fs-12);font-weight:var(--fw-medium)}tbody tr:last-child td{border-bottom:0}.import-score{font-size:var(--fs-16);font-weight:var(--fw-semibold);color:var(--c-primary)}@media(max-width:600px){.import-meta{grid-template-columns:1fr}.import-review-head{align-items:start;flex-direction:column}}
</style>
