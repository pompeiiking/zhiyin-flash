<script lang="ts">
/**
 * 工具目录 · 类型出口
 *
 * 【2026-10-14 · wave2 第二批】目录的**渲染**搬去了 /tools（ToolsView）：
 * 那一页要把"服务端已发布的工具"与"本演示预置的入口"放进**同一个目录**，
 * 并且给出能改变分组方式的控件（落点②组织权）。分组要跨两个来源，
 * 所以目录的列表必须在外层手里；本组件从此只管"读目录 + 跑工具 + 报状态"。
 *
 * 三态口径（ToolsView 的首屏状态轨就是用这三个字面值画的）：
 *   idle    还没取     —— 打开页面会自动读一次；读失败也停在这一格（错误条另有提示）
 *   loading 正在取
 *   empty   取了但没有 —— 服务返回了空清单
 *   ready   有内容
 *   error   这一次没取到
 */
export type ToolStage = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

/** 目录里的一条（已发布工具）。ToolsView 用它和预置入口拼成同一个目录。 */
export interface ToolEntry {
  /** 前缀 p: 区分来源，避免与服务端的 id 撞上 */
  key: string
  id: string
  name: string
  description: string
  version: string
  kind: string
  /** 有可执行动作 = 打开它就能真的做事，而不是只读一段数据 */
  runnable: boolean
}
</script>

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
import { ref, computed, onMounted, watch } from 'vue'
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

/* ============================================================================
 * 【2026-10-14 · wave2 第二批】三件事，都是"这一页首屏不该是空壳 + 一个按钮"的修法
 * ---------------------------------------------------------------------------
 * 1. **挂载即读**：原来目录、空态、骨架屏、状态条全都要点一下「读取工具目录」才出现，
 *    门禁在"加载完成、未做任何点击"的状态下量到的是 1/2 落点、orgKinds 全 0 ——
 *    也就是说那一屏上除了一句话和一个按钮什么结构都没有。
 *    改成 onMounted 自动读一次：三态从"点了才知道"变成"进来就是其中之一"。
 *    手动重读的按钮没有删，它现在在 /tools 的页头（重读是用户的正当权利）。
 * 2. **状态外传**：目录列表与三态都交给 ToolsView（它要把两个来源放进同一个目录，
 *    还要给"换分组轴"的控件）。这里只回传**事实**：阶段 + 条目。
 * 3. **空态换成 tools 档**：原来借 `search-empty`（"条件太窄，换个关键词"），
 *    而这里是"服务没返回"，让用户去改条件是指错方向。EmptyState 已经在 wave2
 *    补了 `tools` 档（EmptyState.vue:40 / :118），现在真的用上它。
 * ==========================================================================*/
const emit = defineEmits<{
  'update:stage': [stage: ToolStage]
  'update:entries': [entries: ToolEntry[]]
}>()

const entries = computed<ToolEntry[]>(() =>
  (modules.value ?? []).map((m) => ({
    key: 'p:' + m.manifest.id,
    id: m.manifest.id,
    name: m.manifest.name,
    description: m.manifest.description,
    version: m.manifest.version,
    kind: m.manifest.kind,
    runnable: (m.manifest.actions?.length ?? 0) > 0,
  })),
)

/* 阶段是**从既有状态推出来的**，不是另加一个 ref 去同步 —— 两份状态一定会漂。
   判据的优先级：正在读 > 这次没读到 > 读到了但没有 > 有内容 > 还没取。
   注意 `error` 只压过 `empty`：读失败时若手里还有上一批内容，那批内容仍然可用，
   阶段报 ready 才诚实（错误条会同时说明"现有内容仍保留"）。 */
const stage = computed<ToolStage>(() => {
  if (busy.value && loading.value) return 'loading'
  if (error.value && !modules.value) return 'error'
  if (modules.value && modules.value.length === 0) return 'empty'
  if (modules.value && modules.value.length > 0) return 'ready'
  return 'idle'
})

watch(stage, (v) => emit('update:stage', v), { immediate: true })
watch(entries, (v) => emit('update:entries', v), { immediate: true })

/**
 * 目录渲染在 ToolsView，所以"打开哪一条 / 什么时候重读"这两件事必须由外层发起。
 * 两者都用**属性**而不是 ref + defineExpose：属性是可类型检查的，
 * 而且不需要外层去猜这个组件实例上有什么方法。
 *   · openId       —— 要打开的那条工具（服务端的 manifest.id）
 *   · reloadToken  —— 每次自增 = 重读一次目录（初值 0 不会触发，首次由 onMounted 负责）
 */
const props = defineProps<{ openId?: string | null; reloadToken?: number }>()

watch(
  () => props.openId,
  (id) => {
    if (!id) return
    if (active.value?.manifest.id === id) return
    const m = modules.value?.find((x) => x.manifest.id === id)
    if (m) void open(m)
  },
)
watch(() => props.reloadToken, () => { void load() })

onMounted(() => { void load() })
</script>
<template><section class="module-catalog"><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="retry"/><StatusBanner v-if="status" tone="success" :message="status" :open="!!status" @dismiss="status=''"/><p v-if="!active" class="ws-muted">在上面的目录里选一条工具，这里会显示它的数据与可执行动作。</p><section v-if="active" class="ws-section"><div class="ws-section-head"><h3 class="module-catalog__title">{{ active.manifest.name }}</h3><button class="btn" :disabled="busy" @click="fetchData()">刷新工具数据</button></div><p class="ws-muted">{{ active.manifest.description }}</p><form v-if="active.manifest.tool" class="ws-section" @submit.prevent="fetchData(true)"><label v-for="[key,s] in fields" :key="key" class="ws-field">{{ s.title || key }}<select v-if="s.enum" v-model="inputs[key]"><option v-for="v in s.enum" :key="String(v)" :value="v">{{ v }}</option></select><input v-else-if="s.type==='boolean'" v-model="inputs[key]" type="checkbox"/><input v-else-if="s.type==='number'||s.type==='integer'" v-model.number="inputs[key]" type="number" :required="active.manifest.input_schema?.required?.includes(key)"/><input v-else v-model="inputs[key]" maxlength="500" :required="active.manifest.input_schema?.required?.includes(key)"/></label><button class="btn btn--primary" :disabled="busy" type="submit">{{ busy?'正在运行…':'运行工具' }}</button></form><SkeletonBlock v-if="loading" class="ws-section" variant="list" :lines="3"/><template v-else-if="result"><EmptyState v-if="result.empty" kind="search-empty" title="工具当前没有可展示的结果" description="这次调用没有返回内容；输入与已有数据都保留。" size="sm" :next="false"><button class="btn" @click="fetchData()">重新读取工具数据</button></EmptyState><template v-else><ul v-if="tasks.length" class="ws-mini-list"><li v-for="t in tasks" :key="t.task_id" class="live-task"><div><strong>{{ t.text }}</strong><p class="ws-muted">{{ t.phase }} · {{ t.done?'已完成':'待执行' }}</p></div><button v-if="canComplete" class="btn" :disabled="busy" :aria-pressed="t.done" @click="setDone(t)">{{ t.done?'恢复任务':'完成任务' }}</button></li></ul><StructuredFacts v-else :value="result.data"/><StatTile v-if="tasks.length" class="ws-section" :value="doneCount" :denominator="tasks.length" unit="件" label="已完成"/></template><Foldable v-if="result.sources?.length" variant="inline" title="工具数据来源" :count="result.sources.length"><ul class="ws-mini-list"><li v-for="s in result.sources" :key="s">{{ s }}</li></ul></Foldable></template></section></section></template>

<style scoped>
/* ============================================================================
 * 选中工具的名字 —— 它是"二级标题"：整页 h2（/tools 的「运行区」）之下一级
 * ---------------------------------------------------------------------------
 * 改前它是一条**没有任何字号规则的裸 h3**：base.css 给 h1–h4 定了字重、行高、字距，
 * 但**没有定字号**，于是浏览器 UA 的 `h3 { font-size: 1.17em }` 生效，
 * 在 16px 的父级下算出 **18.72px** —— 落在登记档位（12/14/16/20/30）之外。
 * 与 /report 那个 24px 的 h2 是同一个机制（详注见 AssessmentView.vue 的 `.report-block` 段）：
 * "没有任何规则"本身就是原因，所以修法也必须是一条显式规则，不能靠父级继承
 * （font-size 会被 UA 的 em 规则截胡，不会继承下来）。
 * 门禁看不到它，只因为"点开一条工具才会渲染"，而门禁不做点击 —— 实测改前 18.72px。
 * ==========================================================================*/
.module-catalog__title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
}
</style>
