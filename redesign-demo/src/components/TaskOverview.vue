<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
const total = computed(() => demo.state.tasks.length)
const done = computed(() => demo.use.done.value.length)
const ratio = computed(() => total.value ? done.value / total.value : 0)
const circumference = 2 * Math.PI * 30
</script>
<template><section class="exp-overview"><div class="exp-overview__head"><h2>执行概览</h2><span>当前演示任务</span></div><div class="exp-overview__body"><div class="exp-overview__ring"><svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="30" stroke="var(--c-border)" /><circle cx="40" cy="40" r="30" stroke="var(--c-primary)" :stroke-dasharray="circumference" :stroke-dashoffset="circumference * (1 - ratio)" /></svg><strong>{{ done }}<small>/ {{ total }}</small></strong></div><dl><div><dt>待执行</dt><dd>{{ demo.use.now.value.length }}</dd></div><div><dt>等待中</dt><dd>{{ demo.use.waiting.value.length }}</dd></div><div><dt>已完成</dt><dd>{{ done }}</dd></div></dl></div><RouterLink to="/review" class="ws-text-link">查看执行记录 →</RouterLink></section></template>
