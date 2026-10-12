<script setup lang="ts">
import { computed } from 'vue'
import registry from '../data/backend-registry.json'
import { backendDemo } from '../lib/backend-demo'
import type { AchievementListView } from '../api/backend-types'
import UiIcon from './UiIcon.vue'
const labels: Record<string, string> = { first_answer: '认真回答过一次', first_gap_claim: '认领过一条差距', decision_made: '做出过一次选择', first_task_done: '完成过一件任务', first_review: '回头复盘过一次' }
const records = computed<AchievementListView>(() => {
  const items = registry.badgeRules.map(rule => {
    const date = rule.trigger_events.map(event => backendDemo.state.eventTimes[event]).filter(Boolean).sort()[0]
    return { key: rule.code, unlocked: !!date, unlocked_at: date ?? null }
  })
  return { items, total: items.length, unlocked: items.filter(i => i.unlocked).length }
})
</script>
<template>
  <section class="ws-paper"><div class="ws-section-head"><div><h2>你做过的事，会留下来</h2><p>已有 {{ records.unlocked }} 项记录。它们来自行为，不靠签到或打开次数。</p></div></div><div class="desk-achievements"><article v-for="item in records.items" :key="item.key" class="desk-achievement" :class="{ 'desk-achievement--unlocked': item.unlocked }"><div class="desk-achievement__icon"><UiIcon :name="item.unlocked ? 'check' : 'review'" :size="22" /></div><div><h3>{{ labels[item.key] ?? item.key }}</h3><p>{{ item.unlocked ? '已经做到过' : '还没有可以确认的行为记录' }}</p><small>{{ item.unlocked_at ? new Date(item.unlocked_at).toLocaleDateString('zh-CN') : '不需要赶着完成它' }}</small></div></article></div></section><p class="ws-demo-note">预置行为与本次演示操作用于展示记录规则；正式记录由后端行为日志推导，不提供手动解锁入口。</p>
</template>
