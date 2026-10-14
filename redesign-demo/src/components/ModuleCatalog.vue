<script setup lang="ts">
/*
 * ModuleCatalog —— 已发布工具目录。
 *
 * 逐条对应 MIGRATION：
 *   · §4.3 B5：`<p v-if="status" class="desk-status" role="status">` 是"成功反馈常驻不消失"
 *     （`status` 由 `load` / `fetchData` / `setDone` 写入，**没有一处清空**）
 *     → `StatusBanner tone="success"`（4s 自动消失 + 可关）。
 *   · §4.3 B10 的形状：错误原来只是一个 `<p class="ws-field-error">`，没有动作位
 *     → `StatusBanner tone="error"`，自带「重试」。
 *   · §4.1 K9 / K15 / P2：`<template v-if="modules">` 缺加载态（"还没取"与"取了但没有"
 *     同形），`<p v-else class="ws-muted ws-section">按服务返回…` 是**兜底说明句当首屏正文**。
 *     现在三件事分开：① 还没取 → `SkeletonBlock variant="list"`；② 取了但没有 → `EmptyState`；
 *     ③ 口径说明 → 进空态的 `description`，不再单独占正文首屏。
 *   · §4.2 E16：工具目录为空**没有对应的 `kind`**（枚举里没有 `tools`，见 U2）。
 *     借用最近的 `search-empty`（"这里没有符合条件的内容"），并在交付说明里点名缺口。
 *   · §4.2 E17：`result.empty` 用 `search-empty` 语义准确（"这次运行没结果"）。
 *   · §4.2 的三条收尾之一：整块内容被空态顶掉时**显式传 `headingLevel="2"`**（H5）。
 *   · §3.3：`N / M 件已完成` 的"只有分母文案" → `StatTile`（value + denominator 自动画进度）。
 *   · §1.3 A10：`result.sources` 的 `<details class="ws-context">` → `Foldable variant="inline"`。
 *   · §1.3 E2 同因：`<details>` 里是"原始数据来源"，属允许折叠的那一类，保留一层。
 */
import { ref, computed } from 'vue'
import { backendRequest, backendClient } from '../api/backend-client'
import { backendDemo } from '../lib/backend-demo'
import EmptyState from './EmptyState.vue'
import Foldable from './Foldable.vue'
import SkeletonBlock from './SkeletonBlock.vue'
import StatTile from './StatTile.vue'
import StatusBanner from './StatusBanner.vue'
import StructuredFacts from './StructuredFacts.vue'
type Schema={type?:string;title?:string;enum?:unknown[];default?:unknown;properties?:Record<string,Schema>;required?:string[]}
type Module={manifest:{id:string;name:string;version:string;description:string;kind:string;tool?:string;actions:string[];input_schema?:Schema};policy:{enabled:boolean;actions?:string[]}}
type Result={data:Record<string,unknown>;sources?:string[];empty?:boolean;module_version?:string}
const modules=ref<Module[]|null>(null),active=ref<Module|null>(null),result=ref<Result|null>(null),busy=ref(false),error=ref(''),status=ref(''),inputs=ref<Record<string,string|number|boolean>>({})
/* 只给"读目录 / 读工具数据"这两条真正的取数路径开骨架屏；
   运行工具（invoke）与改任务状态（setDone）是**动作**，让位会打断用户手里的表单。 */
const loading=ref(false)
const fields=computed(()=>Object.entries(active.value?.manifest.input_schema?.properties??{}).filter(([,s])=>['string','number','integer','boolean'].includes(s.type??'string')))
const tasks=computed(()=>Array.isArray(result.value?.data.tasks)?result.value!.data.tasks as {task_id:string;text:string;phase?:string;done:boolean}[]:[])
const doneCount=computed(()=>tasks.value.filter(t=>t.done).length)
/* 最近一次失败的是哪条路径 —— 决定 StatusBanner 的重试按钮重放哪个动作 */
const lastFailed=ref<'load'|'data'|'action'>('load')
async function load(){if(busy.value)return;busy.value=true;loading.value=true;error.value='';try{const data=await backendRequest<Module[]>('modules');if(!Array.isArray(data))throw new Error('Incomplete modules');modules.value=data.filter(m=>m.policy?.enabled&&m.manifest&&m.manifest.kind!=='tool')}catch{lastFailed.value='load';error.value='工具目录没有读取成功，请重试。现有内容仍保留。'}finally{busy.value=false;loading.value=false}}
async function open(module:Module){if(busy.value)return;active.value=module;result.value=null;status.value='';inputs.value={};fields.value.forEach(([key,s])=>{if(['string','number','boolean'].includes(typeof s.default))inputs.value[key]=s.default as string|number|boolean});await fetchData()}
async function fetchData(invoke=false){if(!active.value||busy.value)return;busy.value=true;if(!invoke)loading.value=true;error.value='';try{const m=active.value.manifest;if(invoke){for(const k of m.input_schema?.required??[])if(inputs.value[k]===undefined||inputs.value[k]==='')throw new Error('请填写所有必填项。')}const data=await backendRequest<Result>(invoke?'moduleInvoke':'moduleData',{params:{module_id:m.id},body:invoke?{input:inputs.value,expected_version:m.version,request_id:crypto.randomUUID()}:undefined});if(!data||typeof data.data!=='object')throw new Error('Incomplete module result');result.value=data;status.value=invoke?'工具调用已完成。':'工具数据已读取。'}catch(e){lastFailed.value='data';error.value=e instanceof Error&&e.message==='请填写所有必填项。'?e.message:'工具暂时没有返回结果，请重试。输入和原内容仍保留。'}finally{busy.value=false;loading.value=false}}
async function setDone(task:{task_id:string;done:boolean}){if(!active.value||busy.value)return;busy.value=true;error.value='';try{const data=await backendRequest<Result>('moduleAction',{params:{module_id:active.value.manifest.id},body:{action:'plan.task.set_done',payload:{task_id:task.task_id,done:!task.done},expected_version:active.value.manifest.version}});result.value=data;status.value='任务状态已保存。';const plan=await backendClient.action();backendDemo.setAction(plan)}catch{lastFailed.value='action';error.value='这次操作没有完整完成，请重新读取工具数据核对状态。'}finally{busy.value=false}}
function retry(){if(lastFailed.value==='load')void load();else if(lastFailed.value==='data')void fetchData();else void backendClient.action().then(plan=>backendDemo.setAction(plan)).catch(()=>{})}
const canComplete=computed(()=>active.value?.manifest.actions.includes('plan.task.set_done')&&active.value.policy.actions?.includes('plan.task.set_done'))
</script>
<template><section class="module-catalog"><div class="ws-section-head"><h2>已发布工具</h2><button class="btn" :disabled="busy" @click="load">{{ busy&&loading?'正在读取…':'读取工具目录' }}</button></div><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="retry"/><StatusBanner v-if="status" tone="success" :message="status" :open="!!status" @dismiss="status=''"/><template v-if="modules"><div class="ws-directory"><button class="module-entry" v-for="m in modules" :key="m.manifest.id" :disabled="busy" :aria-pressed="active?.manifest.id===m.manifest.id" @click="open(m)"><strong>{{ m.manifest.name }}</strong><span>{{ m.manifest.description }}</span></button></div><EmptyState v-if="!modules.length" kind="search-empty" title="当前没有已发布且启用的应用工具" description="按服务返回的发布和启用状态展示，不将未发布工具放入目录。" size="sm" :next="false"><button class="btn" @click="load">重新读取工具目录</button></EmptyState></template><SkeletonBlock v-else-if="loading" variant="list" :lines="3"/><section v-if="active" class="ws-section"><div class="ws-section-head"><h3>{{ active.manifest.name }}</h3><button class="btn" :disabled="busy" @click="fetchData()">刷新工具数据</button></div><p class="ws-muted">{{ active.manifest.description }}</p><form v-if="active.manifest.tool" class="ws-section" @submit.prevent="fetchData(true)"><label v-for="[key,s] in fields" :key="key" class="ws-field">{{ s.title || key }}<select v-if="s.enum" v-model="inputs[key]"><option v-for="v in s.enum" :key="String(v)" :value="v">{{ v }}</option></select><input v-else-if="s.type==='boolean'" v-model="inputs[key]" type="checkbox"/><input v-else-if="s.type==='number'||s.type==='integer'" v-model.number="inputs[key]" type="number" :required="active.manifest.input_schema?.required?.includes(key)"/><input v-else v-model="inputs[key]" maxlength="500" :required="active.manifest.input_schema?.required?.includes(key)"/></label><button class="btn btn--primary" :disabled="busy" type="submit">{{ busy?'正在运行…':'运行工具' }}</button></form><SkeletonBlock v-if="loading" class="ws-section" variant="list" :lines="3"/><template v-else-if="result"><EmptyState v-if="result.empty" kind="search-empty" title="工具当前没有可展示的结果" description="这次调用没有返回内容；输入与已有数据都保留。" size="sm" :next="false"><button class="btn" @click="fetchData()">重新读取工具数据</button></EmptyState><template v-else><ul v-if="tasks.length" class="ws-mini-list"><li v-for="t in tasks" :key="t.task_id" class="live-task"><div><strong>{{ t.text }}</strong><p class="ws-muted">{{ t.phase }} · {{ t.done?'已完成':'待执行' }}</p></div><button v-if="canComplete" class="btn" :disabled="busy" :aria-pressed="t.done" @click="setDone(t)">{{ t.done?'恢复任务':'完成任务' }}</button></li></ul><StructuredFacts v-else :value="result.data"/><StatTile v-if="tasks.length" class="ws-section" :value="doneCount" :denominator="tasks.length" unit="件" label="已完成"/></template><Foldable v-if="result.sources?.length" variant="inline" title="工具数据来源" :count="result.sources.length"><ul class="ws-mini-list"><li v-for="s in result.sources" :key="s">{{ s }}</li></ul></Foldable></template></section></section></template>
