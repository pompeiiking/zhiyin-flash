<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { PhFilePdf, PhArrowRight } from '@phosphor-icons/vue'
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
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
  // 读到文件后立刻重置原生控件：不清的话，导入成功（或解析失败）后再选
  // **同一个**文件不触发 change，界面停在"选择学籍报告"、解析按钮一直禁用。
  input.value = ''
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
    <div class="pdf-import__upload">
      <div class="pdf-import__toolbar">
        <label class="pdf-import__picker" :class="{ 'is-busy': busy }">
          <input class="pdf-import__input" type="file" accept=".pdf,application/pdf" aria-label="选择学籍报告 PDF" :disabled="busy" @change="choose" />
          <span class="pdf-import__file-icon" aria-hidden="true"><PhFilePdf :size="26" weight="duotone" /></span>
          <span class="pdf-import__file-info">
            <span class="pdf-import__filename" :title="file?.name">{{ file ? file.name : '选择学籍报告' }}</span>
            <span class="pdf-import__file-hint">{{ file ? '已选择文件，可点击更换' : '原版文字 PDF，最大 2MB' }}</span>
          </span>
          <span class="pdf-import__browse" aria-hidden="true">{{ file ? '更换文件' : '选择文件' }}</span>
        </label>
        <button class="btn btn--primary pdf-import__parse" :disabled="!file || busy" @click="parse">
          {{ busy ? '正在处理…' : '解析并预览' }}<PhArrowRight v-if="!busy" :size="16" aria-hidden="true" />
        </button>
      </div>
    </div>
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
.pdf-import__upload{container-type:inline-size;margin-top:18px}
.pdf-import__toolbar{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center;padding:14px;background:var(--c-surface-2);border:1px solid var(--c-border);border-radius:var(--radius-md,8px)}
.pdf-import__picker{position:relative;display:flex;align-items:center;gap:12px;min-width:0;min-height:48px;border-radius:6px;cursor:pointer}
.pdf-import__picker:has(input:focus-visible){outline:2px solid var(--c-focus);outline-offset:5px}
.pdf-import__picker.is-busy{cursor:wait;opacity:.6}
.pdf-import__picker .pdf-import__input{position:absolute;inset:0;width:100%;height:100%;min-width:0;max-width:100%;padding:0;margin:0;border:0;opacity:0;cursor:inherit}
.pdf-import__file-icon{display:grid;place-items:center;flex:0 0 44px;height:48px;border:1px solid var(--c-primary-border);border-radius:8px;background:var(--c-surface);color:var(--c-primary)}
.pdf-import__file-info{display:grid;gap:3px;flex:1;min-width:0}
.pdf-import__filename{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--c-text);font-size:14px;font-weight:600;line-height:1.5}
.pdf-import__file-hint{font-size:12px;color:var(--c-text-2);line-height:1.5}
.pdf-import__browse{flex-shrink:0;padding:7px 10px;border:1px solid var(--c-border-control);border-radius:6px;background:var(--c-surface);color:var(--c-text);font-size:12px;font-weight:500;line-height:1.5}
.pdf-import__picker:hover:not(.is-busy) .pdf-import__browse{border-color:var(--c-primary);color:var(--c-primary);background:var(--c-primary-weak)}
.pdf-import__parse{gap:8px;min-height:40px;white-space:nowrap}
@container (max-width:480px){
  .pdf-import__toolbar{grid-template-columns:minmax(0,1fr);gap:14px;padding:14px}
  .pdf-import__parse{width:100%}
  .pdf-import__picker{gap:10px}
  .pdf-import__file-icon{flex-basis:36px;height:42px}
  .pdf-import__browse{padding:7px 8px}
}
</style>
