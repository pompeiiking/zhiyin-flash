<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {backendClient,BackendError} from '../api/backend-client'
import {backendDemo} from '../lib/backend-demo'
import type {AssetVersionView} from '../api/backend-types'
import PageHeading from '../components/PageHeading.vue'
import DirectionDetails from '../components/LiveDirectionCompare.vue'
import ReportHistory from '../components/ReportHistory.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StatusBanner from '../components/StatusBanner.vue'
const route=useRoute(),router=useRouter(),busy=ref(false),saving=ref(false),error=ref(''),selectionChanged=ref(false)
const plans=computed(()=>backendDemo.state.liveDirections)
const history=computed(()=>route.query.view==='versions'||route.query.focus==='versions')
const impact=ref({report:false,plan:false,checked:false})
async function loadImpact(){
 const settled=await Promise.allSettled([backendClient.versions('report'),backendClient.versions('action_plan')])
 const latest=(result:PromiseSettledResult<AssetVersionView[]>)=>result.status==='fulfilled'?[...result.value].sort((a,b)=>b.version-a.version)[0]:undefined
 impact.value={report:latest(settled[0])?.needs_recompute===true,plan:latest(settled[1])?.needs_recompute===true,checked:settled.every(result=>result.status==='fulfilled')}
}
async function load(){if(busy.value)return;busy.value=true;error.value='';try{
 backendDemo.setLiveDirections(await backendClient.directions());await loadImpact()
}catch(e){if(!(e instanceof BackendError&&e.code===1002))error.value=(e as Error).message}finally{busy.value=false}}
async function select(id:string){if(saving.value)return;saving.value=true;error.value='';try{backendDemo.setLiveDirections(await backendClient.selectDirection(id));backendDemo.markDirectionChange();selectionChanged.value=true;await loadImpact()}catch(e){error.value=(e as Error).message}finally{saving.value=false}}
function printReport(){window.print()}
function setHistory(open:boolean){const query={...route.query};delete query.focus;if(open)query.view='versions';else delete query.view;void router.replace({query})}
onMounted(load)
</script>
<template><div class="ws-page report-page">
<PageHeading title="方向方案" description="把不同方向的可能性看清楚，用一次真实尝试替代仓促决定。"><button class="btn" :disabled="busy" @click="load">{{busy?'正在读取…':'刷新方向'}}</button><button class="ws-text-button" @click="setHistory(!history)">{{history?'返回方案':'版本记录'}}</button><button class="ws-text-button" :disabled="busy||!plans" @click="printReport">打印方案</button></PageHeading>
<StatusBanner v-if="error" tone="error" :message="error" retry-label="重新读取" @retry="load"/><SkeletonBlock v-if="busy" variant="list" :lines="4"/>
<DirectionDetails v-if="plans && !history" :plans="plans" :saving="saving" :impact="impact" :selection-changed="selectionChanged" @select="select"/>
<ReportHistory v-else-if="history" asset-type="direction_plan"/>
<EmptyState v-else-if="!busy&&!error" kind="report" title="尚未形成方向方案" description="先通过咨询补充资料，生成后会保存在这里。"><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink></EmptyState>
</div></template>
<style scoped>
.report-page .c2-report-layout > .report-next-rail { grid-column:2; grid-row:1; display:grid; gap:24px; position:sticky; top:20px; padding-top:0; }
@media(max-width:1279px){.report-page .c2-report-layout{grid-template-columns:minmax(0,1fr)}.report-page .c2-report-layout > .report-next-rail{grid-column:1;grid-row:auto;position:static}}

@media print{.report-page :deep(button),.report-page :deep(.report-next-rail),.report-page :deep(.direction-radio),.report-page :deep(select){display:none!important}.report-page :deep(.c2-report-layout){display:block!important}.report-page :deep(.full-report){width:100%}}
/* ============================================================================
 * 落点②组织权 · 报告的"看角"
 * ---------------------------------------------------------------------------
 * 分组头带**条数**：换轴时条目被搬动、条数跟着变，这是"真的重组"唯一可核对的证据。
 * 计数徽标的形状沿用 Foldable 的 .fold__count（同一门编号语言），但类名不同 ——
 * 它是"分组有几条"，不是"折叠里有几条"，将来要分开改的时候不该互相牵制。
 * ==========================================================================*/
.report-views { margin-top: var(--sp-7); }
.report-views .ws-section-head p { margin-top: var(--sp-2); }

/* toc 里那一格条数。toc 常驻之后，三条轴的分组名不一样、条数也不一样 ——
   把条数摆在条目上是"点进去之后会看到什么"的预告（与分组头的徽标同一门编号语言，
   但类名不同：这条是"toc 条目上的计数"，将来分开改时不该互相牵制）。
   toc 本体（.report-toc）在 redesign.css，是全局零件，这里不重新声明它。 */
.report-toc__count {
  margin-left: var(--sp-2);
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
}

.report-chapter__count {
  margin-left: var(--sp-3);
  padding: 0 var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: var(--fw-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
  vertical-align: 2px;
}

.report-chapter__note {
  margin-bottom: var(--sp-4);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

/* 换轴之后，"它原本在哪个分区"必须还在 —— 否则用户会以为分区被删了 */
.report-dimension__from {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* ============================================================================
 * 「能力画像与门槛对照」那个 24px —— 实测出来的**真实机制**，不是猜的
 * ---------------------------------------------------------------------------
 * 结论：它 24px **不是任何 CSS 规则设的**，而是**一条规则都没有**给它字号，
 * 于是浏览器 UA 的 `h2 { font-size: 1.5em }` 生效：1.5 × 父元素 .fold__static-head
 * 的 16px = 24px。实测证据（Chromium 内遍历 document.styleSheets，
 * 列出所有"影响 font-size 且提到 fold"的规则）：
 *   `.fold--section .fold__body h2/h3 → var(--fs-16)`  hit=false
 *   `.fold__static-head → var(--fs-16)`               hit=false（它是**父元素**的规则，不是这个 h2 的）
 *   命中数 = 0；computed 24px；父元素 computed 16px。
 * 为什么 base.css / Foldable.vue 那条 16px 管不到它：那条是
 * `.fold--section .fold__body h2, .fold--section .fold__body h3`，
 * 而这个 h2 是调用方塞进 Foldable `#title` **插槽**的，落在 `.fold__static-head`
 * 里面，**不在 `.fold__body` 里面**（Foldable.vue:174 vs :191）——
 * 父类 .fold--section 是对的，子类不是。
 *
 * 修法不是给字号打一个补丁，而是把插槽收回去：改用 `title-level="2"`，
 * 让 Foldable 直接把标题渲染成 `<h2 class="fold__static-head">`。
 * 顺带消掉原来那条 `<h3 class="fold__static-head"><h2>…</h2></h3>`（标题套标题，
 * 读屏会念两级）—— 也就是说，这条 24px 的成因和那条非法嵌套是同一件事。
 *
 * 档位取 20：它与 `.report-chapter > h2`（20px）、`#report-full > h2`（20px）是同级，
 * 共用一套章节标题。16px 是眉标档（`.report-key-evidence h2`），这一段不是眉标。
 * 选择器写到 `h2.fold__static-head`（特异度 0,2,1）是为了稳赢组件侧那条
 * `.fold__static-head[data-v-*]`（0,2,0），不靠样式加载顺序。
 * ==========================================================================*/
.report-block :deep(h2.fold__static-head) {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  /* base.css 的 :where(.fold__static-head){letter-spacing:0} 特异度为 0，这里盖得住；
     20px 用 -0.01em 是 CRAFT-BRIEF 4.1 允许的那一档。 */
  letter-spacing: -0.01em;
}
</style>
