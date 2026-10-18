<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {studentApi} from '../api/student-capabilities'
import FormConflict from './FormConflict.vue'
import {rebaseForm,conflictRows} from '../lib/form-conflict'
import type {Preferences} from '../api/backend-types'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const loading=ref(false)
const original=ref<Preferences|null>(null),latest=ref<Preferences|null>(null)
const rows=computed(()=>values.value&&original.value&&latest.value?conflictRows(values.value,original.value,latest.value,{proactive_reminders:'主动提醒',quiet_start:'安静时间开始',quiet_end:'安静时间结束',timezone:'时区',academic_analysis:'学校资料参与分析',material_analysis:'上传材料参与分析'}):[])
async function confirmConflict(){if(!values.value||!original.value||!latest.value)return;values.value=rebaseForm(values.value,original.value,latest.value);original.value=latest.value;latest.value=null;await save()}
const values=ref<Preferences|null>(null),busy=ref(false),error=ref(''),status=ref('')
/**
 * 【#23】设置页原来没有时区选项，但接口 Preferences 已经支持 timezone，
 * 安静时间也写着"按某个时区执行"，用户没法改。这里给一组常用时区；
 * 已保存的值如果不在列表里（比如其它时区），保留并显示原值，不会把用户设置改掉。
 */
const timezoneOptions=[
  {id:'Asia/Shanghai',label:'中国标准时间（北京，UTC+8）'},
  {id:'Asia/Hong_Kong',label:'香港时间（UTC+8）'},
  {id:'Asia/Taipei',label:'台北时间（UTC+8）'},
  {id:'Asia/Tokyo',label:'东京时间（UTC+9）'},
  {id:'Asia/Singapore',label:'新加坡时间（UTC+8）'},
  {id:'UTC',label:'协调世界时（UTC）'},
  {id:'Europe/London',label:'伦敦时间'},
  {id:'Europe/Paris',label:'巴黎时间'},
  {id:'America/New_York',label:'纽约时间'},
  {id:'America/Los_Angeles',label:'洛杉矶时间'},
  {id:'Australia/Sydney',label:'悉尼时间'},
]
const timezoneChoices=computed(()=>{
  const current=values.value?.timezone
  if(current&&!timezoneOptions.some(option=>option.id===current))return [...timezoneOptions,{id:current,label:`${current}（当前设置）`}]
  return timezoneOptions
})
const timezoneLabel=computed(()=>timezoneChoices.value.find(option=>option.id===values.value?.timezone)?.label||values.value?.timezone||'Asia/Shanghai')
async function load(){if(loading.value)return;loading.value=true;error.value='';try{values.value=await studentApi.preferences();original.value={...values.value}}catch(e){error.value=(e as Error).message}finally{loading.value=false}}
/** 技术报文 → 学生能照着做的一句话（#10：安静时间只填一端时的后端报错兜底）。 */
function friendlyPreferenceError(message: unknown) {
  const text = String(message ?? '')
  if (/(安静时段|quiet)/i.test(text) || (/Value error/i.test(text) && /(开始|结束|start|end)/i.test(text))) {
    return '安静时段需要同时填写开始和结束时间，或两处都清空。'
  }
  if (/Value error|请求参数不合法|body[：:]/i.test(text)) {
    return '保存内容没有通过校验，请检查填写的时间与选项后重试。'
  }
  return text || '偏好没有保存成功，请稍后重试。'
}
let savingLock=false
async function save(){
  if(!values.value||!original.value||busy.value||savingLock)return
  // 页面内先拦住"只填一端"，不让它走到后端再回一段技术报文。
  const quietStart=values.value.quiet_start||'', quietEnd=values.value.quiet_end||''
  if(!quietStart !== !quietEnd){error.value='安静时段需要同时填写开始和结束时间，或两处都清空。';return}
  savingLock=true;busy.value=true;error.value='';status.value=''
  try{values.value=await studentApi.savePreferences({...values.value,expected:original.value,quiet_start:quietStart||null,quiet_end:quietEnd||null});original.value={...values.value};latest.value=null;status.value='偏好已保存，后续提醒与分析请求将按此设置执行。'}catch(e){error.value=friendlyPreferenceError((e as Error).message);if((e as {code?:number}).code===1003){try{latest.value=await studentApi.preferences()}catch{error.value+=' 最新记录暂未取得，请稍后重试。'}}}finally{savingLock=false;busy.value=false}
}
onMounted(load)
</script>
<template>
  <section class="preference-panel">
    <header class="preference-panel__head">
      <div><span>使用偏好</span><h2>提醒与资料范围</h2></div>
      <DetailPopover title="这些设置会影响什么" side="right" label="查看偏好说明">
        <p>提醒设置控制系统主动联系你的时段；资料范围决定下一次分析可以读取哪些已保存内容。</p>
      </DetailPopover>
    </header>

    <p v-if="loading" class="preference-panel__loading" role="status">正在读取已保存的偏好…</p>
    <form v-if="values" class="account-preferences" @submit.prevent="save">
      <fieldset :disabled="busy">
        <section class="preference-group">
          <div class="preference-row">
            <span class="preference-row__icon"><UiIcon name="bell" :size="20" /></span>
            <div><h3>主动提醒</h3><p>{{ values.proactive_reminders ? '在合适的时间提醒未完成事项' : '仅在你打开职引时查看事项' }}</p></div>
            <label class="toggle"><input v-model="values.proactive_reminders" type="checkbox" role="switch" aria-label="主动提醒"/><span aria-hidden="true" /></label>
          </div>
          <div v-if="values.proactive_reminders" class="quiet-time">
            <div><strong>暂停提醒</strong><DetailPopover title="安静时间规则" side="right"><template #trigger><UiIcon name="info" :size="16" /></template><p>按{{ timezoneLabel }}执行。清空两个时间可取消安静时段，也可以设置跨午夜的时间段。</p></DetailPopover></div>
            <label>从<input v-model="values.quiet_start" type="time" aria-label="安静时间开始"/></label>
            <span aria-hidden="true">至</span>
            <label><input v-model="values.quiet_end" type="time" aria-label="安静时间结束"/></label>
          </div>
          <div class="preference-row preference-row--timezone">
            <span class="preference-row__icon"><UiIcon name="calendar" :size="20" /></span>
            <div><h3>时区</h3><p>提醒时间与「暂停提醒」时段都按这个时区计算，保存后刷新仍会保持。</p></div>
            <select v-model="values.timezone" class="preference-row__select" aria-label="时区">
              <option v-for="option in timezoneChoices" :key="option.id" :value="option.id">{{ option.label }}</option>
            </select>
          </div>
        </section>

        <section class="preference-group">
          <header><strong>参与分析的资料</strong><DetailPopover title="资料参与分析的规则" side="right"><template #trigger><UiIcon name="info" :size="16" /></template><p>关闭某一来源后，AI 继续使用本轮对话、本人填写内容和仍被允许的资料。已保存资料仍可查看、编辑和导出。</p><p>关闭上传材料时，请先移除附件再发送。</p></DetailPopover></header>
          <label class="preference-row preference-row--choice">
            <span class="preference-row__icon"><UiIcon name="academic" :size="20" /></span>
            <div><h3>学校资料</h3><p>成绩、课程和已核对的学籍信息</p></div>
            <span class="toggle"><input v-model="values.academic_analysis" type="checkbox" role="switch" aria-label="学校资料参与分析"/><span aria-hidden="true" /></span>
          </label>
          <label class="preference-row preference-row--choice">
            <span class="preference-row__icon"><UiIcon name="attachment" :size="20" /></span>
            <div><h3>上传材料</h3><p>你在咨询中主动添加的文件</p></div>
            <span class="toggle"><input v-model="values.material_analysis" type="checkbox" role="switch" aria-label="上传材料参与分析"/><span aria-hidden="true" /></span>
          </label>
        </section>

        <FormConflict v-if="latest" :rows="rows" :busy="busy" @confirm="confirmConflict" />
        <footer class="preference-actions">
          <p v-if="error" role="alert">{{error}}</p>
          <p v-else-if="status" role="status">{{status}}</p>
          <button class="btn btn--primary" :disabled="busy || latest !== null">{{busy?'正在保存…':'保存设置'}}</button>
        </footer>
      </fieldset>
    </form>
    <div v-if="!values&&error" class="preference-panel__error"><p role="alert">{{error}}</p><button class="btn" :disabled="loading" @click="load">重试</button></div>
  </section>
</template>

<style scoped>
.preference-panel{overflow:hidden;border:1px solid var(--c-border);border-radius:20px;background:var(--c-surface);box-shadow:0 18px 44px -42px color-mix(in srgb,var(--c-text) 50%,transparent)}
.preference-panel__head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 22px 17px;border-bottom:1px solid var(--c-border)}
.preference-panel__head span{color:var(--c-primary);font-size:12px;font-weight:650}.preference-panel__head h2{margin-top:3px;font-size:20px}
.preference-panel__loading,.preference-panel__error{padding:28px 22px;color:var(--c-text-2)}
.preference-panel__error{display:flex;align-items:center;justify-content:space-between;gap:16px}
.account-preferences fieldset{display:grid;border:0;padding:0;margin:0;min-width:0}
.preference-group{display:grid;padding:4px 22px;border-bottom:1px solid var(--c-border)}
.preference-group>header{display:flex;align-items:center;justify-content:space-between;min-height:48px;color:var(--c-text-2);font-size:13px}
.preference-row{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:12px;min-height:76px;padding:10px 0}
.preference-row--choice{cursor:pointer}.preference-row--choice+.preference-row--choice{border-top:1px solid var(--c-border)}
.preference-row__icon{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:var(--c-primary-weak);color:var(--c-primary)}
.preference-row h3{font-size:14px;font-weight:650}.preference-row p{margin-top:4px;color:var(--c-text-2);font-size:13px;line-height:1.45}
.preference-row--timezone{min-height:64px;border-top:1px solid var(--c-border)}
.preference-row__select{min-width:220px;max-width:100%;min-height:40px;padding:0 10px;border:1px solid var(--c-border);border-radius:10px;background:var(--c-surface);color:var(--c-text);font-size:13px}
.toggle{position:relative;display:inline-flex;flex:none;width:48px;height:28px;cursor:pointer}.toggle input{position:absolute;opacity:0;pointer-events:none}.toggle>span{width:100%;height:100%;border:1px solid var(--c-border-strong);border-radius:999px;background:var(--c-surface-3);transition:.18s ease}.toggle>span::after{content:'';display:block;width:20px;height:20px;margin:3px;border-radius:50%;background:var(--c-surface);box-shadow:0 2px 6px rgb(20 32 46 / 22%);transition:.18s ease}.toggle input:checked+span{border-color:var(--c-primary);background:var(--c-primary)}.toggle input:checked+span::after{transform:translateX(20px)}.toggle input:focus-visible+span{outline:3px solid var(--c-focus);outline-offset:2px}
.quiet-time{display:grid;grid-template-columns:minmax(120px,1fr) auto 18px auto;align-items:center;gap:8px;margin:0 0 14px 54px;padding:12px 14px;border-radius:13px;background:var(--c-surface-2)}
.quiet-time>div{display:flex;align-items:center;gap:5px}.quiet-time strong{font-size:13px}.quiet-time>span{color:var(--c-text-3);font-size:12px;text-align:center}.quiet-time label{display:flex;align-items:center;gap:7px;color:var(--c-text-2);font-size:12px}.quiet-time input{width:116px;min-height:40px}
.preference-actions{display:flex;align-items:center;justify-content:space-between;gap:18px;min-height:72px;padding:12px 22px}.preference-actions p{margin:0;color:var(--c-text-2);font-size:12px;line-height:1.5}.preference-actions [role=alert]{color:var(--c-danger)}.preference-actions [role=status]{color:var(--c-primary)}.preference-actions .btn{margin-left:auto}
@media(max-width:600px){.preference-panel__head,.preference-group,.preference-actions{padding-left:16px;padding-right:16px}.quiet-time{grid-template-columns:1fr 18px 1fr;margin-left:0}.quiet-time>div{grid-column:1/-1}.quiet-time label{display:block}.quiet-time label:first-of-type{font-size:0}.quiet-time input{width:100%}.preference-actions{align-items:stretch;flex-direction:column}.preference-actions .btn{width:100%}.preference-row--timezone{grid-template-columns:42px minmax(0,1fr)}.preference-row__select{grid-column:1/-1;width:100%;min-width:0}}
</style>
