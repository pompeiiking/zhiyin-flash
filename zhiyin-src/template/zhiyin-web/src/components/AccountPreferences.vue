<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {studentApi} from '../api/student-capabilities'
import type {Preferences} from '../api/backend-types'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
const loading=ref(false)
const values=ref<Preferences|null>(null),busy=ref(false),error=ref(''),status=ref('')
async function load(){if(loading.value)return;loading.value=true;error.value='';try{values.value=await studentApi.preferences()}catch(e){error.value=(e as Error).message}finally{loading.value=false}}
async function save(){if(!values.value||busy.value)return;busy.value=true;error.value='';status.value='';try{values.value=await studentApi.savePreferences({...values.value,quiet_start:values.value.quiet_start||null,quiet_end:values.value.quiet_end||null});status.value='偏好已保存，后续提醒与分析请求将按此设置执行。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
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
            <div><strong>暂停提醒</strong><DetailPopover title="安静时间规则" side="right"><template #trigger><UiIcon name="info" :size="16" /></template><p>按 {{values.timezone}} 执行。清空两个时间可取消安静时段，也可以设置跨午夜的时间段。</p></DetailPopover></div>
            <label>从<input v-model="values.quiet_start" type="time" aria-label="安静时间开始"/></label>
            <span aria-hidden="true">至</span>
            <label><input v-model="values.quiet_end" type="time" aria-label="安静时间结束"/></label>
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

        <footer class="preference-actions">
          <p v-if="error" role="alert">{{error}}</p>
          <p v-else-if="status" role="status">{{status}}</p>
          <button class="btn btn--primary" :disabled="busy">{{busy?'正在保存…':'保存设置'}}</button>
        </footer>
      </fieldset>
    </form>
    <div v-if="!values&&error" class="preference-panel__error"><p role="alert">{{error}}</p><button class="btn" :disabled="loading" @click="load">重新读取</button></div>
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
.toggle{position:relative;display:inline-flex;flex:none;width:48px;height:28px;cursor:pointer}.toggle input{position:absolute;opacity:0;pointer-events:none}.toggle>span{width:100%;height:100%;border:1px solid var(--c-border-strong);border-radius:999px;background:var(--c-surface-3);transition:.18s ease}.toggle>span::after{content:'';display:block;width:20px;height:20px;margin:3px;border-radius:50%;background:var(--c-surface);box-shadow:0 2px 6px rgb(20 32 46 / 22%);transition:.18s ease}.toggle input:checked+span{border-color:var(--c-primary);background:var(--c-primary)}.toggle input:checked+span::after{transform:translateX(20px)}.toggle input:focus-visible+span{outline:3px solid var(--c-focus);outline-offset:2px}
.quiet-time{display:grid;grid-template-columns:minmax(120px,1fr) auto 18px auto;align-items:center;gap:8px;margin:0 0 14px 54px;padding:12px 14px;border-radius:13px;background:var(--c-surface-2)}
.quiet-time>div{display:flex;align-items:center;gap:5px}.quiet-time strong{font-size:13px}.quiet-time>span{color:var(--c-text-3);font-size:12px;text-align:center}.quiet-time label{display:flex;align-items:center;gap:7px;color:var(--c-text-2);font-size:12px}.quiet-time input{width:116px;min-height:40px}
.preference-actions{display:flex;align-items:center;justify-content:space-between;gap:18px;min-height:72px;padding:12px 22px}.preference-actions p{margin:0;color:var(--c-text-2);font-size:12px;line-height:1.5}.preference-actions [role=alert]{color:var(--c-danger)}.preference-actions [role=status]{color:var(--c-primary)}.preference-actions .btn{margin-left:auto}
@media(max-width:600px){.preference-panel__head,.preference-group,.preference-actions{padding-left:16px;padding-right:16px}.quiet-time{grid-template-columns:1fr 18px 1fr;margin-left:0}.quiet-time>div{grid-column:1/-1}.quiet-time label{display:block}.quiet-time label:first-of-type{font-size:0}.quiet-time input{width:100%}.preference-actions{align-items:stretch;flex-direction:column}.preference-actions .btn{width:100%}}
</style>
