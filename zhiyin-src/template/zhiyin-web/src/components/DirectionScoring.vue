<script setup lang="ts">
import {computed,onMounted,ref,useId} from 'vue'
import {studentApi,type Comparison} from '../api/student-capabilities'
import type {DirectionWeights} from '../api/backend-types'
import DetailPopover from './DetailPopover.vue'
import MeasurementPanel from './MeasurementPanel.vue'
const data=ref<Comparison|null>(null),error=ref(''),loading=ref(false),busy=ref(false),status=ref(''),expanded=ref('')
const defaults=()=>({major:1,jobs:1,salary:1,stability:1,location:1})
const draft=ref<DirectionWeights>(defaults()),id=useId()
const dimensions=[{key:'major',label:'专业对口'},{key:'jobs',label:'岗位数量'},{key:'salary',label:'起薪水平'},{key:'stability',label:'稳定性'},{key:'location',label:'通勤与地点'}] as const
const allDimensions=[...dimensions,{key:'opportunity',label:'机会坐标'},{key:'feasibility',label:'可达性坐标'}]
const points=computed(()=>data.value?.plans.filter(p=>p.opportunity!=null&&p.feasibility!=null)??[])
async function load(){
  loading.value=true;error.value=''
  try{data.value=await studentApi.compare();draft.value={...defaults(),...data.value.weights}}
  catch(e){error.value=(e as Error).message}
  finally{loading.value=false}
}
async function save(){
  if(busy.value||loading.value)return
  status.value='';error.value=''
  if(!dimensions.some(d=>(draft.value[d.key]??0)>0)){error.value='请至少保留一项大于 0 的权重。';return}
  busy.value=true
  try{await studentApi.saveWeights({...draft.value});await load();status.value=error.value?'偏好已保存，比较结果暂未更新，请重新读取。':'偏好已保存，比较结果已更新。'}
  catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
onMounted(load)
</script>
<template>
  <section class="direction-scoring" :aria-busy="loading||busy">
    <div class="ws-section-head">
      <div><h2>按我的偏好比较</h2><p>加权评分与方案匹配分分别保留，选择仍由你确认。</p></div>
      <DetailPopover title="选择偏好" label="调整比较权重">
        <template #trigger>调整权重</template>
        <form class="weight-form" @submit.prevent="save">
          <fieldset :disabled="busy||loading||!data">
            <label v-for="d in dimensions" :key="d.key" class="ws-field">{{d.label}}
              <span class="weight-control"><input v-model.number="draft[d.key]" type="range" min="0" max="5" step="1"/><output>{{draft[d.key]}}</output></span>
            </label>
          </fieldset>
          <p class="ws-muted">0 表示不计入，至少保留一项；缺少依据的维度不会自动补分。</p>
          <p v-if="error" class="ws-field-error" role="alert">{{error}}</p>
          <p v-if="status" role="status">{{status}}</p>
          <div class="ws-inline-actions"><button type="button" class="btn" :disabled="busy||loading||!data" @click="draft=defaults();status=''">同等权重</button><button class="btn btn--primary" :disabled="busy||loading||!data">{{busy?'正在保存…':'保存并重算'}}</button></div>
        </form>
      </DetailPopover>
    </div>
    <p v-if="loading" class="ws-muted" role="status">正在读取偏好与量化依据…</p>
    <p v-if="error" class="ws-field-error" role="alert">{{error}} <button class="ws-text-button" :disabled="loading||busy" @click="load">重新读取</button></p>
    <p v-if="status" role="status">{{status}}</p>
    <template v-if="data">
      <DetailPopover v-if="data.method" title="加权评分依据" label="了解加权评分依据"><template #trigger>评分如何计算</template><p>{{data.method}}</p></DetailPopover>
      <div v-if="points.length" class="direction-quadrant" aria-label="方向机会与可达性">
        <span class="quadrant-y">机会 ↑</span><span class="quadrant-x">可达性 →</span>
        <button v-for="p in points" :key="p.id" type="button" class="quadrant-point" :style="{left:(10+p.feasibility!*75)+'%',bottom:(10+p.opportunity!*75)+'%'}" :aria-label="p.name+'：查看量化依据'" :aria-expanded="expanded===p.id" :aria-controls="expanded===p.id?id+p.id:undefined" @click="expanded=expanded===p.id?'':p.id">{{p.name}}</button>
      </div>
      <p v-else class="ws-muted scoring-hint">已有记录会显示在下方；补齐机会与可达性后可查看象限。</p>
      <article v-for="p in data.plans" :key="p.id" class="scoring-row">
        <div class="scoring-row__summary">
          <h3>{{p.name}}</h3><strong>{{p.score==null?'依据待补充':Math.round(p.score*100)+' / 100'}}</strong>
          <button type="button" class="ws-text-button" :aria-expanded="expanded===p.id" :aria-controls="expanded===p.id?id+p.id:undefined" @click="expanded=expanded===p.id?'':p.id">{{expanded===p.id?'收起依据':'核对量化依据'}}</button>
        </div>
        <p v-if="p.missing.length" class="ws-muted">缺少：{{p.missing.map(k=>dimensions.find(d=>d.key===k)?.label??k).join('、')}}</p>
        <div v-if="expanded===p.id" :id="id+p.id" class="scoring-evidence">
          <MeasurementPanel v-if="data.version!=null" asset-type="direction_plan" :version="data.version" :subject-id="p.id" :dimensions="allDimensions" @saved="load"/>
          <p v-else class="ws-muted">当前方案尚无可记录量表的版本。</p>
        </div>
      </article>
      <p v-if="!data.plans.length" class="ws-muted">当前尚无可比较的方向方案。</p>
    </template>
  </section>
</template>
<style scoped>
.direction-scoring{margin:24px 0}.direction-scoring>.ws-section-head{flex-wrap:wrap;gap:12px}.scoring-hint{margin:12px 0}
.scoring-row{padding:16px 0;border-bottom:1px solid var(--c-border)}.scoring-row__summary{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:12px 20px}.scoring-row h3{font-size:var(--fs-14);overflow-wrap:anywhere}.scoring-row strong{color:var(--c-primary);font-size:var(--fs-14);font-variant-numeric:tabular-nums}.scoring-row>p{margin-top:6px;font-size:var(--fs-12)}.scoring-evidence{margin-top:12px;padding-left:16px;border-left:2px solid var(--c-border)}
.weight-form,.weight-form fieldset{display:grid;gap:14px}.weight-form fieldset{border:0;padding:0;margin:0;min-width:0}.weight-control{display:flex;align-items:center;gap:16px}.weight-control output{min-width:2ch;font-variant-numeric:tabular-nums;color:var(--c-primary)}
.direction-quadrant{position:relative;height:240px;margin:20px 0;border-left:1px solid var(--c-border);border-bottom:1px solid var(--c-border);background:linear-gradient(90deg,transparent 49.8%,var(--c-border) 50%,transparent 50.2%),linear-gradient(transparent 49.8%,var(--c-border) 50%,transparent 50.2%)}.quadrant-point{position:absolute;max-width:38%;overflow-wrap:anywhere;transform:translateX(-50%);background:var(--c-primary-weak);color:var(--c-primary);padding:8px 10px;border-radius:8px;font-size:12px;border:1px solid var(--c-border);cursor:pointer}.quadrant-point:hover,.quadrant-point[aria-expanded=true]{border-color:var(--c-primary)}.quadrant-y{position:absolute;top:0;left:4px}.quadrant-x{position:absolute;bottom:0;right:0}
@media(max-width:600px){.scoring-row__summary{grid-template-columns:minmax(0,1fr) auto}.scoring-row__summary>button{grid-column:1/-1;justify-self:start}.scoring-evidence{padding-left:10px}}
</style>
