import { computed } from 'vue'
import registry from '../data/backend-registry.json'
import { backendDemo } from './backend-demo'
const labels: Record<string,string> = {first_answer:'认真回答过一次',first_gap_claim:'认领过一条差距',decision_made:'做出过一次选择',first_task_done:'完成过一件任务',first_review:'回头复盘过一次'}
const topics: Record<string,string> = {first_answer:'了解自己',first_gap_claim:'补齐证据',decision_made:'做决定',first_task_done:'去做',first_review:'回头看'}
const eventLabels: Record<string,string> = {answer:'回答过咨询问题',gap_claim:'认领过具体差距',decision_made:'确认过方向选择',task_done:'完成过一件任务',review:'保存过复盘记录'}
/** Same event evidence as the existing achievement rules; no synthetic unlocks. */
export const growthRecords = computed(() => [
 ...registry.badgeRules.map(rule => {
  const events=rule.trigger_events.filter(event=>!!backendDemo.state.eventTimes[event])
  const at=events.map(event=>backendDemo.state.eventTimes[event]!).sort()[0]??null
  return {id:rule.code,title:labels[rule.code]??rule.code,source:'行为记录',topic:topics[rule.code]??'回头看',method:'由行为日志确认',at,done:!!at,evidence:events.length?events.map(event=>`${eventLabels[event]??'相关行为已发生'} · ${new Date(backendDemo.state.eventTimes[event]!).toLocaleString('zh-CN')}`):['还没有满足这一条规则的行为记录'],next:rule.trigger_events.map(event=>eventLabels[event]??'相关行为记录').join(' / ')}
 }),
 {id:'academic-verification',title:'核对过学校资料',source:'本人授权与学籍资料',topic:'了解自己',method:'由核验结果确认',at:backendDemo.state.chsiChecked?backendDemo.state.academic?.imported_at??null:null,done:backendDemo.state.chsiChecked,evidence:[backendDemo.state.chsiChecked?'本次演示核验已完成；结果仍为演示样例':'需要本人授权的在线验证码，导入课程不等于核验通过'],next:'在学籍与资料中核验'},
])
