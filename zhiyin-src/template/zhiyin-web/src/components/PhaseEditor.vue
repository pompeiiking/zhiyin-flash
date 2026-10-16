<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {dateKey} from '../lib/action-insights.mjs'
import {studentApi} from '../api/student-capabilities'
import {backendDemo} from '../lib/backend-demo'
import type {PhaseEdit} from '../api/backend-types'
import InfoSheet from './InfoSheet.vue'
const props=defineProps<{phaseId?:string}>()
const savedId=ref('')
const open=ref(false),name=ref(''),dependencies=ref<string[]>([]),start=ref(''),end=ref(''),blocks=ref(''),handoff=ref(''),busy=ref(false),error=ref(''),status=ref('')
const dateRange=ref(''),datesTouched=ref(false)
const phases=computed(()=>backendDemo.state.liveAction?.phases??[])
const hasRules=computed(()=>!!blocks.value.trim()||!!handoff.value.trim())
function revealRules(event:Event){
  const details=event.currentTarget as HTMLDetailsElement
  if(!details.open)return
  requestAnimationFrame(()=>details.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}))
}
watch(open,v=>{if(!v)return;savedId.value='';const p=phases.value.find(p=>p.id===props.phaseId);name.value=p?.name??'';dependencies.value=[...(p?.depends_on??[])];start.value=dateKey(p?.starts_at);end.value=dateKey(p?.ends_at);dateRange.value=p?.date_range??'';datesTouched.value=false;blocks.value=p?.blocking_conditions?.join('\n')??'';handoff.value=p?.handoff_requirements?.join('\n')??'';status.value='';error.value=''})
async function save(){if(busy.value)return;error.value='';status.value='';if(start.value&&end.value&&end.value<start.value){error.value='结束日期不能早于开始日期。';return}busy.value=true;try{const oldIds=new Set(phases.value.map(p=>p.id));const payload:PhaseEdit={name:name.value,depends_on:dependencies.value,starts_at:start.value?new Date(start.value+'T00:00').toISOString():null,ends_at:end.value?new Date(end.value+'T23:59').toISOString():null,blocking_conditions:blocks.value.split('\n').filter(Boolean),handoff_requirements:handoff.value.split('\n').filter(Boolean)};const plan=await studentApi.savePhase(payload,savedId.value||props.phaseId);savedId.value=savedId.value||props.phaseId||(plan.phases??[]).find(p=>!oldIds.has(p.id))?.id||'';backendDemo.setAction(plan);dateRange.value=(plan.phases??[]).find(p=>p.id===(savedId.value||props.phaseId))?.date_range??dateRange.value;datesTouched.value=false;status.value='阶段安排已保存。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template>
  <button class="ws-text-button" type="button" @click="open=true">{{phaseId?'编辑阶段':'新增阶段'}}</button>
  <Teleport to="body">
    <InfoSheet :open="open" shape="panel" :title="phaseId?'编辑阶段与交接':'新增阶段'" @close="open=false">
      <form class="phase-editor" @submit.prevent="save">
        <fieldset :disabled="busy">
          <section class="phase-editor__section phase-editor__name">
            <label class="ws-field">阶段名称<input v-model="name" type="text" autofocus required maxlength="100" placeholder="例如：完成第一个可演示作品"/></label>
            <p>写清这一阶段要推进的结果，后续任务会围绕它展开。</p>
          </section>

          <section class="phase-editor__section" aria-labelledby="phase-editor-time-title">
            <div class="phase-editor__heading"><div><h3 id="phase-editor-time-title">时间范围</h3><p>先给自己一个大致区间，之后仍可调整。</p></div><span>可选</span></div>
            <div class="phase-editor__dates">
              <label class="ws-field">开始日期<input v-model="start" type="date" @input="datesTouched=true"/></label>
              <span aria-hidden="true">至</span>
              <label class="ws-field">计划完成<input v-model="end" type="date" :min="start||undefined" @input="datesTouched=true"/></label>
            </div>
            <p v-if="dateRange&&!start&&!end&&!datesTouched" class="phase-editor__legacy-date">当前安排：{{dateRange}}。不修改日期会保留原时间。</p>
          </section>

          <fieldset class="phase-editor__section phase-editor__dependencies">
            <legend>前置阶段 <span>可选</span></legend>
            <p>只有确实需要先完成的阶段才勾选；没有依赖就直接跳过。</p>
            <div class="phase-editor__dependency-grid">
              <label v-for="p in phases.filter(p=>p.id!==(savedId||phaseId))" :key="p.id" :class="{'is-selected':!!p.id&&dependencies.includes(p.id)}"><input v-model="dependencies" type="checkbox" :value="p.id"/><span><strong>{{p.name}}</strong><small>完成后再开始本阶段</small></span></label>
            </div>
            <p v-if="!phases.some(p=>p.id!==(savedId||phaseId))" class="phase-editor__empty">暂无其他阶段，本阶段可以直接开始。</p>
          </fieldset>

          <details class="phase-editor__advanced" @toggle="revealRules">
            <summary><span><strong>补充开始条件和完成标准</strong><small>{{hasRules?'已填写，可展开修改':'需要明确验收方式时再填写'}}</small></span><i aria-hidden="true"/></summary>
            <div class="phase-editor__rules">
              <label class="ws-field">开始前要满足什么 <span>可选</span><textarea v-model="blocks" rows="3" placeholder="例如：先完成 Python 基础练习&#10;每行写一项"/></label>
              <label class="ws-field">做到什么算完成 <span>可选</span><textarea v-model="handoff" rows="3" placeholder="例如：做出一个可以演示的小工具&#10;例如：邀请 2 位同学试用并记录反馈"/></label>
            </div>
          </details>
        </fieldset>
        <footer class="phase-editor__footer">
          <p v-if="error" role="alert">{{error}}</p><p v-if="status" role="status">{{status}}</p>
          <div><button type="button" class="btn" @click="open=false">{{status?'完成':'取消'}}</button><button class="btn btn--primary" :disabled="busy">{{busy?'正在保存…':'保存阶段'}}</button></div>
        </footer>
      </form>
    </InfoSheet>
  </Teleport>
</template>
<style scoped>
.phase-editor{display:grid;max-width:760px;margin:0 auto}.phase-editor>fieldset{display:grid;border:0;padding:0;min-width:0}.phase-editor .ws-field{margin:0}.phase-editor input[type=text],.phase-editor input[type=date]{min-height:48px}.phase-editor__section{min-width:0;padding:20px 0;border-bottom:1px solid var(--c-border)}.phase-editor__name{padding-top:0}.phase-editor__name>p,.phase-editor__heading p,.phase-editor__dependencies>p,.phase-editor__legacy-date{margin:7px 0 0;color:var(--c-text-3);font-size:var(--fs-12);line-height:1.6}.phase-editor__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:14px}.phase-editor__heading h3{margin:0;font-size:var(--fs-14);font-weight:var(--fw-medium)}.phase-editor__heading p{margin-top:4px}.phase-editor__heading>span,.phase-editor__dependencies legend span,.phase-editor__rules .ws-field>span{color:var(--c-text-3);font-size:11px;font-weight:var(--fw-regular)}.phase-editor__dates{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:12px;align-items:end}.phase-editor__dates>span{display:grid;place-items:center;min-height:48px;color:var(--c-text-3);font-size:var(--fs-12)}.phase-editor .phase-editor__dependencies{display:block;min-width:0;margin:0;padding:20px 0;border:0}.phase-editor__dependencies legend{padding:0;font-size:var(--fs-14);font-weight:var(--fw-medium)}.phase-editor__dependency-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin-top:14px}.phase-editor__dependency-grid label{display:flex;align-items:center;gap:11px;min-height:60px;padding:9px 11px;border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-surface);cursor:pointer}.phase-editor__dependency-grid label:hover,.phase-editor__dependency-grid label:focus-within{border-color:var(--c-primary-border);background:var(--c-primary-weak)}.phase-editor__dependency-grid label.is-selected{border-color:var(--c-primary);background:var(--c-primary-weak)}.phase-editor__dependency-grid input{flex:none;width:18px;height:18px;accent-color:var(--c-primary)}.phase-editor__dependency-grid label>span{display:grid;gap:2px;min-width:0}.phase-editor__dependency-grid strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--fs-14);font-weight:var(--fw-medium)}.phase-editor__dependency-grid small{color:var(--c-text-3);font-size:11px;line-height:1.35}.phase-editor__empty{padding:12px 14px;background:var(--c-bg)}.phase-editor__advanced{border-bottom:1px solid var(--c-border)}.phase-editor__advanced>summary{display:flex;align-items:center;justify-content:space-between;gap:20px;min-height:76px;cursor:pointer;list-style:none}.phase-editor__advanced>summary::-webkit-details-marker{display:none}.phase-editor__advanced>summary>span{display:grid;gap:4px}.phase-editor__advanced>summary strong{font-size:var(--fs-14);font-weight:var(--fw-medium)}.phase-editor__advanced>summary small{color:var(--c-text-3);font-size:var(--fs-12)}.phase-editor__advanced>summary i::before{content:"展开";color:var(--c-primary);font-size:var(--fs-12);font-style:normal}.phase-editor__advanced[open]>summary i::before{content:"收起"}.phase-editor__rules{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding:0 0 20px}.phase-editor__rules textarea{min-height:108px;margin-top:7px;resize:vertical}.phase-editor__footer{position:sticky;bottom:-32px;z-index:1;display:flex;align-items:center;justify-content:flex-end;min-height:76px;background:var(--c-surface);border-top:0}.phase-editor__footer>div{display:flex;justify-content:flex-end;gap:12px}.phase-editor__footer p{margin:0 auto 0 0}.phase-editor textarea{resize:vertical}@media(max-width:600px){.phase-editor__section{padding:18px 0}.phase-editor__dates{grid-template-columns:1fr;gap:10px}.phase-editor__dates>span{display:none}.phase-editor__dependency-grid,.phase-editor__rules{grid-template-columns:1fr}.phase-editor__advanced>summary{min-height:80px}.phase-editor__footer{bottom:-24px;min-height:72px}}
</style>
