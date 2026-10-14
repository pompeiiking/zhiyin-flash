<script setup lang="ts">
import { computed, ref } from 'vue'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import PublishedTools from '../components/PublishedTools.vue'
import SourceChip from '../components/SourceChip.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { backendDemo } from '../lib/backend-demo'
import { demo } from '../store'
import { PROFILE_FIELDS, DIRECTION_PLANS } from '../data/student'
import { backendClient } from '../api/backend-client'
const busy=ref(false), error=ref(''), status=ref(''), axis=ref('step')
const tools = computed(() => [
 {id:'verify',name:'学籍核验',step:1,reads:'本人授权的在线验证码',writes:'专业、年级与在读状态，保留核验时间',when:'第一次使用，或学籍变化之后',to:'/academic',state:backendDemo.state.chsiChecked?'已查看核验流程':'等待本人授权'},
 {id:'import',name:'成绩与课表导入',step:1,reads:'本人提供的成绩单与课表',writes:(backendDemo.state.academic?.grades?.length??0)+' 条成绩、'+(backendDemo.state.academic?.courses?.length??0)+' 门课程，保留冲突与缺失时间',when:'资料更新时，重新核对导入快照',to:'/academic',state:backendDemo.state.academic?'已有资料':'等待资料'},
 {id:'profile',name:'画像分析',step:2,reads:'已核对的学校资料、对话与本人更正',writes:'已有信息、缺口与判断的依赖关系',when:'先补资料，再核对每条判断',to:'/profile',state:demo.state.account==='fresh'?'等待资料':'已有画像'},
 {id:'directions',name:'方向对比',step:2,reads:'个人画像和岗位要求笔记',writes:DIRECTION_PLANS.length+' 条候选方向与五项同刻度比较',when:'需要比较方向、调整看重程度时',to:'/directions',state:backendDemo.state.directionsAvailable?'可比较':'等待画像'},
 {id:'tasks',name:'任务建议',step:3,reads:'已选方向与报告中的差距',writes:demo.use.now.value.length+' 件现在可以动手的任务',when:'把判断拆成今天做得完的小事',to:'/home',state:demo.use.now.value.length?'等待你确认':'暂未形成'},
 {id:'schedule',name:'周时间表',step:3,reads:'课程占用、任务时长与截止节点',writes:'任务、课程与空档，放在同一时间刻度上',when:'课表或计划变化后重新看一周',to:'/schedule',state:backendDemo.state.academic?'可查看':'等待课表'},
])
const groups=computed(()=>axis.value==='state' ? [true,false].map(ready=>({key:String(ready),title:ready?'已经有资料，可以接着用':'还在等前一步',items:tools.value.filter(t=>/等待|暂未/.test(t.state)!==ready)})) : [1,2,3].map(step=>({key:String(step),title:['','先把资料取回来','从资料里看出东西','变成今天能做的一件事'][step],items:tools.value.filter(t=>t.step===step)})))
const steps=computed(()=>[
 {title:'把学校那边的记录接进来',name:'第一步 · 取资料',detail:'学籍核验、成绩与课表导入。先做这一步，判断才有得可用。',output:(backendDemo.state.academic?.grades?.length??0)+' 条成绩与 '+(backendDemo.state.academic?.courses?.length??0)+' 门课程',next:'被第 2 步读'},
 {title:'从资料里得出判断，并标上把握度',name:'第二步 · 看出东西',detail:'画像分析给出结论、缺口与下一步；方向对比用同一把尺子比较三个方向。',output:PROFILE_FIELDS.length+' 项画像字段 · '+DIRECTION_PLANS.length+' 条方向',next:'被第 3 步读'},
 {title:'把判断拆成今天做得完的小事',name:'第三步 · 变成动作',detail:'任务建议写进计划，周时间表把课程与任务放进具体时段。选择与完成由你确认。',output:demo.use.now.value.length+' 件待执行 · '+demo.use.done.value.length+' 件已完成',next:'等你确认'},
 {title:'用完一轮，资料池该长一条',name:'第四步 · 回到资料',detail:'完成记录与复盘保留实际发生的事，下一次判断还能追到这些依据。',output:demo.use.done.value.length+' 件完成记录',next:'回到画像与复盘'},
])
async function reload(){ if(busy.value)return;busy.value=true;error.value='';try {const [workspace,report,directions]=await Promise.all([backendClient.workspace(),backendClient.report(),backendClient.directions()]);backendDemo.setWorkspace(workspace);backendDemo.setReport(report);backendDemo.setLiveDirections(directions);status.value='已重新读取画像、报告与方向。本人授权、资料导入和任务确认仍需你操作。'}catch{error.value='部分资料没有重新读到。原资料仍保留，请重试。'}finally{busy.value=false}}
</script>
<template><div class="ws-page tools-page c2-tools-page"><PageHeading title="工具" description="六个工具，分三组，沿四步衔接：先把资料取回来，再从资料里看出东西，最后把它变成今天能做的一件事。每个工具都写着它读什么、给你什么、什么时候该用它。"><button class="btn" :disabled="busy" @click="reload">{{ busy?'正在读取…':'重新读取分析资料' }}</button><RouterLink class="btn" to="/guide">去看使用指南<UiIcon name="arrow" :size="16"/></RouterLink></PageHeading><p class="c2-page-meta"><span>{{ tools.length }} 个工具 · 3 组</span><span>{{ tools.filter(t=>!/等待|暂未/.test(t.state)).length }} 个已有资料</span><span>{{ tools.filter(t=>/等待|暂未/.test(t.state)).length }} 个等前一步</span></p><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试" @retry="reload"/><StatusBanner :open="!!status" tone="success" :message="status" @dismiss="status=''"/>
<section class="tools-chain"><div class="ws-section-head"><div><h2>这六个工具怎么接在一起</h2><p>后一步读前一步的产物。画像分析没形成之前，方向与任务就缺少依据——这是顺序。</p></div><span>4 步</span></div><ol class="c2-tool-chain"><li v-for="step in steps" :key="step.name"><span>{{ step.name }}</span><h3>{{ step.title }}</h3><p>{{ step.detail }}</p><div class="c2-tool-output"><span>产出 {{ step.output }}</span><span>{{ step.next }}</span></div></li></ol></section>
<section class="tools-directory"><div class="c2-lensbar" role="group" aria-label="工具的组织方式"><button :aria-pressed="axis==='step'" @click="axis='step'">按使用步骤</button><button :aria-pressed="axis==='state'" @click="axis='state'">按当前状态</button></div><section v-for="group in groups" :key="group.key" class="c2-tool-group"><header class="ws-section-head"><h2>{{ group.title }}</h2><span>{{ group.items.length }} 个</span></header><div class="c2-tool-grid"><article v-for="tool in group.items" :key="tool.id"><header><h3>{{ tool.name }}</h3><span>{{ tool.state }}</span></header><dl><div><dt>读什么</dt><dd>{{ tool.reads }}</dd></div><div><dt>给你什么</dt><dd>{{ tool.writes }}</dd></div><div><dt>什么时候用</dt><dd>{{ tool.when }}</dd></div></dl><SourceChip label="工作空间内置工具" kind="external"/><RouterLink class="btn" :to="tool.to">打开{{ tool.name }}<UiIcon name="arrow" :size="16"/></RouterLink></article></div></section></section><details class="c2-published-tools"><summary>服务端发布的工具与执行记录</summary><PublishedTools/></details></div></template>
