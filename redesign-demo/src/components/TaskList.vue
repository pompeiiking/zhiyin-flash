<script setup lang="ts">
import { demo } from '../store'
import UiIcon from './UiIcon.vue'
import type { TaskItem } from '../data/types'
defineProps<{ items: TaskItem[]; mode?: string }>()
</script>
<template>
  <ul v-if="items.length" class="ws-tasks">
    <li v-for="t in items" :key="t.id" class="ws-task" :class="{ 'ws-task--done': t.bucket === 'done' }">
      <button v-if="t.bucket !== 'waiting'" class="ws-task__check" :aria-label="(t.bucket === 'done' ? '恢复任务：' : '完成任务：') + t.title" @click="t.bucket === 'done' ? demo.reopenTask(t.id) : demo.completeTask(t.id)">
        <UiIcon v-if="t.bucket === 'done'" name="check" :size="16" />
      </button>
      <span v-else class="ws-task__waiting" aria-label="等待中" />
      <div class="ws-task__content">
        <p class="ws-task__title">{{ t.title }}</p>
        <p class="ws-task__meta"><span>{{ t.minutes ? '约 ' + t.minutes + ' 分钟' : '暂时不用行动' }}</span><span>{{ t.origin }}</span><span v-if="t.due" class="ws-attention">{{ t.due }}</span><span v-if="t.doneAt">{{ t.doneAt }}完成</span></p>
        <details class="ws-task__details">
          <summary>为什么安排这件事<UiIcon name="chevron" :size="14" /></summary>
          <p>{{ t.why }}</p>
          <div class="ws-inline-actions">
            <template v-if="t.origin === '建议的'"><button class="btn btn--sm" @click="demo.acceptSuggestion(t.id)">采纳建议</button><button class="ws-text-button" @click="demo.rejectSuggestion(t.id)">不适合我</button></template>
            <button v-if="t.bucket === 'now' && t.minutes > 5" class="ws-text-button" @click="demo.shrinkTask(t.id)">拆成 5 分钟</button>
            <button v-if="t.bucket === 'waiting' && t.minutes > 0" class="ws-text-button" @click="demo.planToday(t.id)">排进今天</button>
          </div>
        </details>
      </div>
    </li>
  </ul>
  <div v-else class="ws-empty"><h3>{{ mode === 'done' ? '完成一件事，就会留在这里' : mode === 'waiting' ? '目前没有需要等待的事' : '先聊两句，找出今天的一小步' }}</h3><p>{{ mode === 'done' ? '完成记录来自你做过的事。' : '不用急着排满日程，每次推进一件事就好。' }}</p><RouterLink v-if="mode !== 'done' && mode !== 'waiting'" class="ws-text-link" to="/chat">去对话<UiIcon name="arrow" :size="16" /></RouterLink></div>
</template>
