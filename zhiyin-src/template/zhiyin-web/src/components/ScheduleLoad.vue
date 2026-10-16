<script setup lang="ts">
import {computed} from 'vue'
import {backendDemo} from '../lib/backend-demo'
import {actionRows,dateKey} from '../lib/action-insights.mjs'
import DetailPopover from './DetailPopover.vue'
import CapabilityGap from './CapabilityGap.vue'
const props=defineProps<{date:string}>()
defineEmits<{select:[date:Date]}>()
const tasks=computed(()=>actionRows(backendDemo.state.liveAction))
const weeks=computed(()=>{
 const anchor=new Date(props.date+'T12:00:00');anchor.setDate(anchor.getDate()-(anchor.getDay()+6)%7)
 return [-1,0,1].map((offset,index)=>{
  const start=new Date(anchor);start.setDate(start.getDate()+offset*7);const end=new Date(start);end.setDate(end.getDate()+6)
  const from=dateKey(start.toISOString()),to=dateKey(end.toISOString())
  const inWeek=(date?:string|null)=>!!dateKey(date)&&dateKey(date)>=from&&dateKey(date)<=to
  return {label:['前一周','所选周','后一周'][index],start,from,to,tasks:tasks.value.filter(t=>inWeek(t.due_date)),nodes:(backendDemo.state.liveCalendar??[]).filter(n=>inWeek(n.due_at))}
 })
})
const max=computed(()=>Math.max(1,...weeks.value.map(w=>w.tasks.length)))
const undated=computed(()=>tasks.value.filter(t=>!dateKey(t.due_date)).length)
const courseDays=computed(()=>Array.from({length:7},(_,i)=>({day:i+1,label:'周'+['一','二','三','四','五','六','日'][i],courses:backendDemo.state.academic?.courses?.filter(c=>c.weekday===i+1)??[]})))
</script>
<template><section class="restored-load"><div class="ws-section-head"><h2>三周安排对照</h2><DetailPopover title="时间统计依据" label="查看三周安排的统计依据" side="right"><template #trigger>统计依据</template><p>任务按截止日期归周；节点按日程日期归周。两者可能关联，分别展示，不相加。</p><p>另有 {{undated}} 项任务没有可识别的截止日期，未计入三周分布。</p><p>课程缺少学期首日，不能把“第几周”换算为这三周的真实课量。</p></DetailPopover></div>
<div class="load-weeks"><article v-for="week in weeks" :key="week.from"><button class="week-title" @click="$emit('select',week.start)"><strong>{{week.label}}</strong><span>{{week.from.slice(5)}} — {{week.to.slice(5)}}</span></button><div class="week-task-count"><strong>{{week.tasks.length}}<small> 项到期任务</small></strong><span>{{week.tasks.filter(t=>t.done).length}} 已完成</span></div><div class="load-bar" :aria-label="week.label+'到期任务 '+week.tasks.length+' 项'"><i :style="{width:week.tasks.length/max*100+'%'}"/></div><div class="ws-section-head"><span class="ws-muted">{{week.nodes.length}} 个日程节点</span><DetailPopover :title="week.label+' · 安排明细'" :label="'查看'+week.label+'安排明细'" side="right"><template #trigger>展开明细</template><ul class="ws-mini-list"><li v-for="t in week.tasks" :key="t.task_id">{{dateKey(t.due_date)}} · {{t.text}}<small>{{t.done?' 已完成':' 待执行'}}</small></li><li v-for="n in week.nodes" :key="n.node_id">{{dateKey(n.due_at)}} · {{n.title}}<small> 日程节点</small></li></ul><p v-if="!week.tasks.length&&!week.nodes.length">没有已记录的任务或节点。</p><button class="btn" @click="$emit('select',week.start)">在日历中查看这一周</button></DetailPopover></div></article></div>
<div class="course-load-strip"><span>课程分布</span><DetailPopover v-for="d in courseDays" :key="d.day" :title="d.label+' · 导入课程'" :label="'查看'+d.label+'课程分布'" side="right"><template #trigger>{{d.label}} · {{d.courses.length}} 门</template><ul class="ws-mini-list"><li v-for="(c,i) in d.courses" :key="i"><strong>{{c.name}}</strong><p>{{c.start_period&&c.end_period?'第 '+c.start_period+'–'+c.end_period+' 节':'节次未提供'}} · {{c.weeks?'第 '+c.weeks+' 周':'教学周未提供'}}</p></li></ul><p v-if="!d.courses.length">尚未导入这一天的课程。</p><p class="ws-muted">按已导入课表列出，未确认所选自然周是否开课。</p></DetailPopover></div>
<CapabilityGap title="课程与任务小时对比、剩余时间及冲突" reason="尚缺学期首日、节次起止时间和任务预计用时。已恢复三周任务分布与课程核对入口，但不能据此计算剩余小时或判定冲突。"/>
</section></template>
<style scoped>.restored-load{margin:24px 0 32px}.load-weeks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;margin:18px 0}.load-weeks article{padding:18px;border:1px solid var(--c-border);border-radius:var(--r-sm);min-width:0}.week-title{display:flex;justify-content:space-between;align-items:center;gap:10px;background:transparent;color:var(--c-text);width:100%;min-height:40px;text-align:left}.week-title span{color:var(--c-text-3);font-size:var(--fs-12)}.week-task-count{display:flex;justify-content:space-between;align-items:baseline;margin:12px 0}.week-task-count strong{font-size:26px;color:var(--c-primary)}.week-task-count small,.week-task-count>span{font-size:var(--fs-12);font-weight:400;color:var(--c-text-3)}.load-bar{height:5px;background:var(--c-border);margin:12px 0 20px}.load-bar i{display:block;height:100%;background:var(--c-primary)}.course-load-strip{display:flex;flex-wrap:wrap;gap:16px;font-size:var(--fs-12);margin:20px 0}.load-weeks :deep(.detail-trigger){font-size:var(--fs-12)}@media(max-width:800px){.load-weeks{grid-template-columns:1fr;gap:12px}.load-weeks article{padding:14px}}</style>
