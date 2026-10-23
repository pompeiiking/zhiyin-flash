<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { backendClient } from '../api/backend-client'
import type { ChsiPdfPreview, ChsiPdfReceipt } from '../api/backend-types'
import { backendDemo } from '../lib/backend-demo'
import StatusBanner from './StatusBanner.vue'

const emit = defineEmits<{ changed: [] }>()
const file = ref<File | null>(null), busy = ref(false), error = ref('')
const preview = ref<ChsiPdfPreview | null>(null), receipt = ref<ChsiPdfReceipt | null>(null)
const selected = ref<string[]>([]), ownership = ref(false), refreshing = ref(false), refreshError = ref('')
const expired = ref(false)
let expiryTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(expiryTimer))
const canConfirm = computed(() => preview.value?.can_import && selected.value.length > 0 && !expired.value &&
  (!preview.value.requires_ownership_confirmation || ownership.value))

function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  preview.value = null; receipt.value = null; error.value = ''; ownership.value = false
  selected.value = []; clearTimeout(expiryTimer)
}
async function parse() {
  if (!file.value || busy.value) return
  error.value = ''; preview.value = null; receipt.value = null
  if (file.value.size > 2_000_000) { error.value = '报告超过 2MB，请上传单份原版 PDF。'; return }
  busy.value = true
  try {
    const form = new FormData(); form.append('file', file.value)
    preview.value = await backendClient.chsiPdfPreview(form)
    selected.value = preview.value.fields.filter(f => f.selected && f.selectable).map(f => f.key)
    expired.value = Date.parse(preview.value.expires_at) <= Date.now()
    clearTimeout(expiryTimer)
    expiryTimer = setTimeout(() => { expired.value = true }, Math.max(0, Date.parse(preview.value.expires_at) - Date.now()))
    ownership.value = false
  } catch (e) { error.value = e instanceof Error ? e.message : '报告没有读取成功，请重试。' }
  finally { busy.value = false }
}
async function refresh() {
  refreshing.value = true; refreshError.value = ''
  try { backendDemo.setWorkspace(await backendClient.workspace()); emit('changed') }
  catch { refreshError.value = '导入已完成，但最新画像没有读到。请重试读取，不需要再次导入。' }
  finally { refreshing.value = false }
}
async function confirm() {
  if (!preview.value || !canConfirm.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    receipt.value = await backendClient.chsiPdfConfirm({ preview_id: preview.value.preview_id,
      selected_keys: selected.value, ownership_confirmed: ownership.value })
    receipt.value.imported.forEach(key => backendDemo.markProfileChange(key))
    preview.value = null; file.value = null; clearTimeout(expiryTimer)
    await refresh()
  } catch (e) { error.value = e instanceof Error ? e.message : '导入没有完成，请重试。' }
  finally { busy.value = false }
}
function text(value: unknown) { return value == null ? '暂无' : String(value) }
function previewValueLabel(key: string) { return key === 'study_year' ? '按入学日期推算' : '报告' }
function previewValue(key: string, value: unknown) {
  return key === 'study_year' && value == null ? '无法推算，请核对当前年级' : text(value)
}
</script>

<template>
  <section class="pdf-import" aria-labelledby="chsi-pdf-heading">
    <h3 id="chsi-pdf-heading">上传学籍报告 PDF</h3>
    <p class="ws-muted">在学信档案下载中文版《教育部学籍在线验证报告》，再上传到这里。支持原版文字 PDF，最多 2MB、3 页。</p>
    <p class="ws-muted">导入后作为资料记录，待在线核验；原 PDF 不长期保存。</p>
    <a class="ws-text-link" href="https://my.chsi.com.cn/archive/index.jsp" target="_blank" rel="noopener noreferrer">去学信档案下载报告</a>
    <label class="ws-field ws-section">选择报告
      <input type="file" accept=".pdf,application/pdf" :disabled="busy" @change="choose" />
    </label>
    <button class="btn" :disabled="!file || busy" @click="parse">{{ busy ? '正在处理…' : '解析并预览' }}</button>
    <p v-if="error" class="ws-field-error" role="alert">{{ error }}</p>
    <div v-if="preview" class="ws-section" aria-live="polite">
      <p>报告日期：{{ preview.report_date || '未识别' }} · 有效期至：{{ preview.valid_until || '无法判断' }}</p>
      <ul v-if="preview.warnings?.length" class="ws-mini-list"><li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li></ul>
      <p class="ws-muted">缺失项默认选中。已有不同值请逐项选择；已核验字段保留原记录。</p>
      <ul class="pdf-import__fields">
        <li v-for="field in preview.fields" :key="field.key">
          <label class="pdf-import__choice">
            <input v-model="selected" type="checkbox" :value="field.key" :disabled="!field.selectable || busy || expired" />
            <span><strong>{{ field.label }}</strong><span class="pdf-import__value">{{ previewValueLabel(field.key) }}：{{ previewValue(field.key, field.value) }}</span><span class="pdf-import__value ws-muted">当前：{{ text(field.current_value) }}</span><small v-if="field.reason">{{ field.reason }}</small></span>
          </label>
        </li>
      </ul>
      <label v-if="preview.requires_ownership_confirmation" class="pdf-import__choice ws-section">
        <input v-model="ownership" type="checkbox" :disabled="busy" /><span>我确认这是本人的学籍报告。</span>
      </label>
      <p v-if="expired" role="alert" class="ws-field-error">预览已过期，请重新解析报告。</p>
      <button class="btn btn--primary ws-section" :disabled="!canConfirm || busy" @click="confirm">{{ busy ? '正在导入…' : `确认导入 ${selected.length} 项` }}</button>
    </div>
    <template v-if="receipt">
      <StatusBanner tone="success" size="sm" class="ws-section" :message="receipt.message || '报告材料已导入，待在线核验。'" :retryable="false" />
      <p class="ws-muted">导入 {{ receipt.imported.length }} 项，保留 {{ receipt.retained.length }} 项，跳过 {{ receipt.skipped.length }} 项。</p>
      <p v-if="refreshError" class="ws-field-error" role="alert">{{ refreshError }}</p>
      <button v-if="refreshError" class="btn" :disabled="refreshing" @click="refresh">{{ refreshing ? '正在读取…' : '重新读取画像' }}</button>
    </template>
  </section>
</template>

<style scoped>
.pdf-import{margin-top:var(--space-6,24px);padding-top:var(--space-5,20px);border-top:1px solid var(--c-border)}
.pdf-import h3{margin:0 0 8px;font-size:1rem}
.pdf-import__fields{list-style:none;padding:0;margin:16px 0;display:grid;gap:12px}
.pdf-import__fields li{padding:12px;border:1px solid var(--c-border);border-radius:var(--radius-md,8px);min-width:0}
.pdf-import__choice{display:flex;gap:10px;align-items:flex-start;line-height:1.6;overflow-wrap:anywhere}
.pdf-import__choice input{flex:0 0 auto;margin-top:5px}
.pdf-import__value{display:block}
.pdf-import input[type=file]{max-width:100%;min-width:0}
</style>
