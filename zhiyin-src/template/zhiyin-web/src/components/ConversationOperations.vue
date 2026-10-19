<script setup lang="ts">
import { computed } from 'vue'
import type { ConversationAction } from '../api/backend-client'
const props = defineProps<{ actions: ConversationAction[]; busy: boolean }>()
const emit = defineEmits<{ decide: [id: string, accept: boolean] }>()
const pending = computed(() => props.actions.filter(a => a.state === 'proposed' && Date.parse(a.expires_at) > Date.now()))
const records = computed(() => props.actions.filter(a => a.state !== 'proposed').slice(-5).reverse())
const states: Record<string, string> = { succeeded: '已完成', reverted: '已撤回', outcome_unknown: '结果待核对，请查看当前数据', failed: '未完成', superseded: '旧提案已失效', rejected: '未执行', expired: '已过期', executing: '正在执行，请稍后核对结果' }
const titles: Record<string, string> = { 'plan.activate': '启用这份计划', 'plan.save': '保存计划', 'profile.update': '更新画像', 'task.set_done': '更新任务状态', 'report.save': '保存报告', 'directions.save': '保存方向方案', 'direction.select': '选择方向', 'memory.forget': '删除这项记忆' }
Object.assign(titles, { 'action.undo': '撤销上次修改', 'plan.patch': '调整计划任务', 'report.activate': '启用这份报告', 'directions.activate': '启用方向方案' })
Object.assign(titles, { 'calendar.write': '保存日历提醒', 'calendar.delete': '删除日历提醒' })
function preview(a: ConversationAction): string[] {
 const p = a.payload.content || a.payload
 if (a.operation.startsWith('calendar.')) return [p.title, p.due_at ? new Date(p.due_at).toLocaleString(undefined, { timeZoneName: 'short' }) : '无指定时间', a.operation === 'calendar.delete' ? '确认后删除这一条提醒。' : '确认后保存这一条提醒。']
 if (a.operation === 'direction.select') return [`${p.name}：${p.target_desc}`]
 if (a.operation === 'memory.forget') return [`${p.label}：${p.value}`, '删除这项画像，并重置此前的对话上下文；其他已保存画像保留。历史聊天需另行删除会话。']
 if (a.operation === 'action.undo') {
  if (p.draft_only) return ['撤回这份尚未启用的草稿；当前使用的内容保持原样。']
  const old = p.before
  if (p.operation === 'profile.update') {
   const field = old?.fields?.find((f: any) => f.key === p.original_payload.key)
   return [`${p.original_payload.label || p.original_payload.key}：${p.original_payload.value} → ${field ? field.value : '删除本次新增内容'}`]
  }
  if (p.operation === 'task.set_done') {
   const task = old?.phases?.flatMap((v: any) => v.tasks || []).find((t: any) => t.id === p.original_payload.task_id)
   return [`${task?.text || '任务'} → ${task?.done ? '已完成' : '未完成'}`]
  }
  if (old?.phases) return old.phases.flatMap((phase: any) => [phase.name, ...phase.tasks.map((t: any) => t.text)])
  if (old?.verdict) return [old.verdict.title, old.verdict.summary]
  if (Array.isArray(old)) return old.map((v: any) => `${v.name}：${v.target_desc}`)
 }
 if (a.operation === 'profile.update') return [`${p.label || '个人信息'}：${p.value}`]
 if (a.operation === 'task.set_done') return [`${p.task} → ${p.done ? '已完成' : '未完成'}`]
 const plan = ['plan.activate', 'plan.save'].includes(a.operation) ? p : null
 if (plan) return (plan.phases || []).flatMap((phase: any) => [phase.name, ...(phase.tasks || []).map((t: any) => `${t.text}${t.due_date ? ' · ' + new Date(t.due_date).toLocaleDateString() : ''}`)])
 if (p.updates) return p.updates.map((c: any) => `${c.before.text} → ${c.after.text}${c.after.due_date ? ' · ' + new Date(c.after.due_date).toLocaleDateString() : ''}${c.after.estimated_minutes ? ' · ' + c.after.estimated_minutes + '分钟' : ''}`)
 if (p.verdict) return [p.verdict.title, p.verdict.summary]
 if (p.plans) return p.plans.map((v: any) => `${v.name}：${v.target_desc}`)
 return [a.operation === 'memory.forget' ? '删除后不再将这项画像作为咨询依据，相关内容将标记待复核。' : '执行你刚才讨论的具体变更。']
}
</script>
<template>
 <section v-if="pending.length" class="conversation-operations" aria-label="待确认的变更">
  <article v-for="a in pending" :key="a.id" class="conversation-operation">
   <h3>{{ titles[a.operation] || '确认变更' }}</h3>
   <p>确认后执行以下内容。你也可以继续输入调整要求。</p>
   <ul><li v-for="(line, index) in preview(a)" :key="index">{{ line }}</li></ul>
   <div><button type="button" class="btn btn--primary btn--sm" :disabled="busy" @click="emit('decide', a.id, true)">确认执行</button><button type="button" class="btn btn--sm" :disabled="busy" @click="emit('decide', a.id, false)">暂不执行</button></div>
  </article>
 </section>
 <details v-if="records.length" class="conversation-receipts"><summary>操作记录</summary><ul><li v-for="a in records" :key="a.id">{{ titles[a.operation] || '操作' }} · {{ states[a.state] || '状态待核对' }}</li></ul></details>
</template>
<style scoped>
.conversation-operations { display: grid; gap: 12px; margin: 16px 0; }
.conversation-operation { border: 1px solid var(--c-border); background: var(--c-surface); border-radius: 14px; padding: 18px; }
.conversation-operation h3 { margin: 0 0 8px; font-size: 16px; }
.conversation-operation p { color: var(--c-text-2); font-size: 14px; }
.conversation-operation ul { max-height: 240px; overflow: auto; padding-left: 22px; line-height: 1.7; }
.conversation-operation > div { display: flex; gap: 10px; flex-wrap: wrap; }
.conversation-operation > div button { min-height: 44px; min-width: 88px; }
.conversation-receipts { margin: 12px 0; font-size: 14px; color: var(--c-text-2); }
.conversation-receipts summary { cursor: pointer; }
.conversation-receipts li { line-height: 1.8; }
</style>
