<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import PageHeading from '../components/PageHeading.vue'
import TaskList from '../components/TaskList.vue'
import UiIcon from '../components/UiIcon.vue'
import { backendDemo } from '../lib/backend-demo'
import { taskOriginLabel } from '../lib/presentation'
const scenario = computed(() => demo.use.scenario.value)
const tab = ref('milestones')
const tabs = [{ key: 'milestones', label: '阶段里程碑' }, { key: 'week', label: '执行任务' }, { key: 'sources', label: '任务来源' }]
const books = computed(() => ['计划拆下来的', '建议的', '自己写的', '关键节点'].map((label) => ({ label, tasks: demo.state.tasks.filter((t) => t.origin === label) })))
</script>
<template>
  <div class="ws-page">
    <PageHeading title="行动计划" :description="scenario.grade + ' · 阶段目标、执行任务与来源说明'"><RouterLink class="btn btn--primary" to="/home">查看当前任务<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="ws-subnav" aria-label="行动计划视图"><RouterLink to="/home">今日行动</RouterLink><RouterLink to="/plan" aria-current="page">阶段计划</RouterLink></nav>
    <section v-if="!backendDemo.state.planAvailable" class="ws-paper"><div class="ws-empty"><h2 class="ws-section-title">阶段计划还没有形成</h2><p>先在对话里确定方向与下一步，计划才有依据。</p><RouterLink class="btn btn--primary" to="/chat">继续咨询</RouterLink><div><button class="ws-text-button" @click="backendDemo.loadPlanSample()">查看阶段计划示例</button></div></div></section>
    <div v-else class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-tabs" aria-label="计划内容"><button v-for="t in tabs" :key="t.key" :aria-pressed="tab === t.key" @click="tab = t.key">{{ t.label }}</button></div>
        <section v-if="tab === 'milestones'" class="ws-section"><div class="ws-section-head"><h2>{{ scenario.focus }}</h2></div><div class="ws-milestones"><article v-for="m in scenario.milestones" :key="m.id" class="ws-milestone"><div class="ws-milestone__head"><div><h3>{{ m.title }}</h3><p>{{ m.window }}</p></div><strong>{{ Math.round(m.progress * 100) }}%</strong></div><div class="ws-progress"><span :style="{ '--value': m.progress }" /></div><p>{{ m.note }}</p></article></div></section>
        <section v-else-if="tab === 'week'" class="ws-section"><div class="ws-section-head"><h2>当前待执行任务</h2></div><TaskList :items="[...demo.use.now.value, ...demo.use.waiting.value]" /><p class="ws-muted" style="margin-top: var(--sp-4)">已完成 {{ demo.use.done.value.length }} 件，完成记录在今日任务里。</p></section>
        <section v-else class="ws-section"><div class="ws-section-head"><div><h2>任务来源</h2><p>任务保留生成来源，系统建议支持采纳或拒绝。</p></div></div><details v-for="b in books" :key="b.label" class="ws-fold" :open="b.label === '计划拆下来的'"><summary>{{ taskOriginLabel(b.label) }} · {{ b.tasks.length }} 件<UiIcon name="chevron" :size="18" /></summary><TaskList :items="b.tasks" /></details></section>
      </section>
      <aside class="ws-aside"><section><h2>当前重点</h2><p>{{ scenario.nextStep }}</p><RouterLink class="ws-text-link" to="/home">回到今日任务<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>执行调整</h2><p>可通过复盘拆分任务、调整执行方法或重新评估方向。</p><RouterLink class="ws-text-link" to="/review">查看复盘建议<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>方向调整</h2><p>调整方向前，可比较匹配依据与主要风险。</p><RouterLink class="ws-text-link" to="/directions">比较三个方向<UiIcon name="arrow" :size="16" /></RouterLink></section></aside>
    </div>
    <div v-if="!demo.state.guidesClosed.plan" class="ws-guide"><UiIcon name="info" :size="18" /><p>阶段里程碑展示目标与进度，执行任务展示当前安排。关键日期请通过日历与课表查看。</p><button @click="demo.closeGuide('plan')">收起</button></div>
    <p class="ws-demo-note">阶段里程碑为预置示例，当前任务状态可交互操作。</p>
  </div>
</template>
