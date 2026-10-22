<script setup lang="ts">
import WorkflowRunner from '../components/WorkflowRunner.vue'
import DetailPopover from '../components/DetailPopover.vue'
import { computed, ref, onMounted } from 'vue'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import PublishedTools from '../components/PublishedTools.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { backendDemo } from '../lib/backend-demo'
import { demo } from '../store'
import { backendClient } from '../api/backend-client'
const busy=ref(false), error=ref(''), status=ref(''), axis=ref('step')
const profileCount=computed(()=>backendDemo.state.liveWorkspace?.profile_panel?.fields?.length??0)
const directionCount=computed(()=>backendDemo.state.liveDirections?.plans?.length??0)
const taskCount=computed(()=>backendDemo.state.liveAction?.phases?.reduce((n,p)=>n+(p.tasks?.length??0),0)??0)
const destinations:Record<string,string>={verify:'学籍信息',import:'我的成绩',profile:'个人画像',directions:'方向方案',tasks:'今日行动',schedule:'日历与课表'}
const tools = computed(() => [
 {id:'verify',name:'学籍核验',step:1,reads:'学信网在线验证码（需你本人授权获取）',writes:'专业、年级与在读状态，保留核验时间',when:'第一次使用，或学籍变化之后',to:'/profile?section=enrollment',state:backendDemo.chsiVerified.value?'已有核验资料':'还没核验'},
 {id:'import',name:'成绩导入',step:1,reads:'本人提供的成绩单',writes:(backendDemo.state.academic?.grades?.length??0)+' 条成绩，按学期核对导入记录',when:'资料更新时，重新核对导入快照',to:'/grades',state:backendDemo.state.academic?.grades?.length?'已有资料':'还没导入资料'},
 {id:'profile',name:'画像分析',step:2,reads:'已核对的学校资料、对话与本人更正',writes:'已有信息、缺口与判断的依赖关系',when:'先补资料，再核对每条判断',to:'/profile',state:profileCount.value?'已有画像':'还没导入资料'},
 {id:'directions',name:'方向对比',step:2,reads:'个人画像和岗位要求笔记',writes:directionCount.value+' 条方向方案，可逐项核对目标、依据与风险',when:'需要比较方向、调整看重程度时',to:'/directions',state:directionCount.value?'可比较':'还没有方案'},
 {id:'tasks',name:'任务建议',step:3,reads:'已选方向与报告中的差距',writes:demo.use.now.value.length+' 件未完成任务',when:'把判断拆成今天做得完的小事',to:'/home',state:demo.use.now.value.length?'待处理':taskCount.value?'已全部完成':'暂未形成'},
 {id:'schedule',name:'课表导入与日历',step:3,reads:'课程占用、任务时长与截止节点',writes:'任务、课程与空档，放在同一时间刻度上',when:'课表或计划变化后重新看一周',to:'/schedule',state:backendDemo.state.academic?'可查看':'还没导入课表'},
])
const groups=computed(()=>axis.value==='state' ? [true,false].map(ready=>({key:String(ready),title:ready?'可以使用':'需要先补充资料',items:tools.value.filter(t=>/等待|暂未|还没/.test(t.state)!==ready)})) : [1,2,3].map(step=>({key:String(step),title:['','资料管理','分析与比较','行动安排'][step],items:tools.value.filter(t=>t.step===step)})))
const steps=computed(()=>[
 {title:'把学校那边的记录接进来',name:'第一步 · 取资料',detail:'学籍核验、成绩与课表导入。先做这一步，判断才有得可用。',output:(backendDemo.state.academic?.grades?.length??0)+' 条成绩与 '+(backendDemo.state.academic?.courses?.length??0)+' 门课程',next:'被第 2 步读'},
 {title:'从资料里得出判断，并标上把握度',name:'第二步 · 看出东西',detail:'画像分析给出结论、缺口与下一步；方向对比用同一把尺子比较三个方向。',output:profileCount.value+' 项画像字段 · '+directionCount.value+' 条方向',next:'被第 3 步读'},
 {title:'把判断拆成今天做得完的小事',name:'第三步 · 变成动作',detail:'任务建议写进计划，周时间表把课程与任务放进具体时段。选择与完成由你确认。',output:demo.use.now.value.length+' 件未完成 · '+demo.use.done.value.length+' 件已完成',next:'等你确认'},
 {title:'用完一轮，资料池该长一条',name:'第四步 · 回到资料',detail:'完成记录与复盘保留实际发生的事，下一次判断还能追到这些依据。',output:demo.use.done.value.length+' 件完成记录',next:'回到画像与复盘'},
])
async function reload(user=true){ if(busy.value)return;busy.value=true;error.value='';try {const [workspace,report,directions,action]=await Promise.all([backendClient.workspace(),backendClient.report(),backendClient.directions(),backendClient.action()]);backendDemo.setWorkspace(workspace);backendDemo.setReport(report);backendDemo.setLiveDirections(directions);backendDemo.setAction(action);if(user)status.value='已重新读取画像、报告与方向。学籍核验、资料导入和任务确认仍需你操作。'}catch{error.value='部分资料没有重新读到。原资料仍保留，请重试。'}finally{busy.value=false}}
onMounted(()=>{void reload(false)})
</script>
<template><div class="ws-page tools-page c2-tools-page"><PageHeading title="工具" description="六个工具，分三组，沿四步衔接：先把资料取回来，再从资料里看出东西，最后把它变成今天能做的一件事。每个工具都写着它读什么、给你什么、什么时候该用它。"><button class="btn" :disabled="busy" @click="reload()">{{ busy?'正在读取…':'刷新已有资料' }}</button><RouterLink class="btn" to="/guide">去看使用指南<UiIcon name="arrow" :size="16"/></RouterLink></PageHeading><p class="c2-page-meta"><span>{{ tools.length }} 个工具 · 3 组</span><span>{{ tools.filter(t=>!/等待|暂未|还没/.test(t.state)).length }} 个已有资料</span><span>{{ tools.filter(t=>/等待|暂未|还没/.test(t.state)).length }} 个还没就绪</span></p><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="reload()"/><StatusBanner :open="!!status" tone="success" :message="status" @dismiss="status=''"/>

<section class="tools-directory"><section v-for="group in groups" :key="group.key" class="c2-tool-group"><header class="ws-section-head"><h2>{{ group.title }}</h2><span>{{ group.items.length }} 个</span></header><div class="c2-tool-grid"><article v-for="tool in group.items" :key="tool.id"><header><h3>{{ tool.name }}</h3><span>{{ tool.state }}</span></header><p class="tool-purpose">{{ tool.writes }}</p><DetailPopover :title="tool.name + ' · 使用说明'" :label="'查看' + tool.name + '使用说明'"><template #trigger>使用说明<UiIcon name="info" :size="16"/></template><p><strong>所需资料</strong><br/>{{ tool.reads }}</p><p><strong>适用时机</strong><br/>{{ tool.when }}</p></DetailPopover><RouterLink class="btn" :to="tool.to">前往{{ destinations[tool.id] || tool.name }}<UiIcon name="arrow" :size="16"/></RouterLink></article></div></section></section><DetailPopover title="工具的使用顺序" label="查看工具使用顺序"><template #trigger>查看工具使用顺序<UiIcon name="info" :size="16"/></template><section class="tools-chain"><div class="ws-section-head"><div><h2>这六个工具怎么接在一起</h2><p>后一步读前一步的产物。画像分析没形成之前，方向与任务就缺少依据——这是顺序。</p></div><span>4 步</span></div><ol class="c2-tool-chain"><li v-for="step in steps" :key="step.name"><span>{{ step.name }}</span><h3>{{ step.title }}</h3><p>{{ step.detail }}</p><div class="c2-tool-output"><span>产出 {{ step.output }}</span><span>{{ step.next }}</span></div></li></ol></section></DetailPopover><details class="c2-published-tools"><summary>平台提供的工具与执行记录</summary><WorkflowRunner/><PublishedTools/></details></div></template>
