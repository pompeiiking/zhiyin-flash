<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import UiIcon from './UiIcon.vue'
import DetailPopover from './DetailPopover.vue'
import EmptyState from './EmptyState.vue'
import type { TaskItem } from '../data/types'
import { taskOriginLabel } from '../lib/presentation'
const props = defineProps<{ items: readonly TaskItem[]; mode?: string }>()
/*
 * 任务依据与操作：从 <details class="ws-task__details"> 里搬出来，改成**始终可见**
 * （MIGRATION §1.3 C1 / PLAN §4.4「主信息默认可见」）。
 * 旧行为是浏览器默认收起 —— 而这里装着"采纳建议 / 拒绝建议 / 拆成 5 分钟 / 安排执行"
 * 这四个唯一能推进任务的动作，收起来＝用户找不到动作（Foldable.vue:37-39 的原话）。
 *
 * 用 Foldable 的 `static` 形态而不是「删掉 <details> 就算完」：
 *   · static 是组件给的明路（Foldable.vue:12-15），它保留动作区的视觉落点
 *     （`.fold--actions` 左侧一条主色线），并明确表达"它不该被折叠"；
 *   · 读屏不会把它读成可展开控件（static 渲染 <section> 而不是 button）。
 * 本组件在任何页面区块里都不再产生折叠层 —— 这正是 /plan 从"嵌套 3 层"回到 1 层的前提。
 */
const emptyTitle = computed(() => props.mode === 'done' ? '暂无完成记录' : props.mode === 'waiting' ? '暂无等待任务' : '暂无待执行任务')
const emptyDesc = computed(() => props.mode === 'done' ? '完成记录来自你做过的事。' : '可通过咨询明确方向并生成行动任务。')
</script>
<template>
  <TransitionGroup v-if="items.length" name="task-list" tag="ul" class="ws-tasks">
    <li v-for="t in items" :key="t.id" class="ws-task" :class="{ 'ws-task--done': t.bucket === 'done' }">
      <button v-if="t.bucket !== 'waiting'" class="ws-task__check" :aria-pressed="t.bucket === 'done'" :aria-label="(t.bucket === 'done' ? '恢复任务：' : '完成任务：') + t.title" @click="t.bucket === 'done' ? demo.reopenTask(t.id) : demo.completeTask(t.id)">
        <UiIcon v-if="t.bucket === 'done'" name="check" :size="16" />
      </button>
      <span v-else class="ws-task__waiting" aria-label="等待中" />
      <div class="ws-task__content">
        <p class="ws-task__title">{{ t.title }}</p>
        <p class="ws-task__meta"><span>{{ t.minutes ? '约 ' + t.minutes + ' 分钟' : '等待后续安排' }}</span><span>{{ taskOriginLabel(t.origin) }}</span><span v-if="t.due" class="ws-attention">{{ t.due }}</span><span v-if="t.doneAt">{{ t.doneAt }}完成</span></p>
        <div class="task-row-actions">
          <DetailPopover v-if="t.why" :title="t.title+' · 任务依据'" :label="'查看'+t.title+'任务依据'"><template #trigger>任务依据<UiIcon name="info" :size="16"/></template><p>{{ t.why }}</p></DetailPopover>
          <div class="ws-inline-actions">
            <template v-if="t.origin === '建议的'"><button class="btn btn--sm" @click="demo.acceptSuggestion(t.id)">采纳建议</button><button class="ws-text-button" @click="demo.rejectSuggestion(t.id)">拒绝建议</button></template>
            <button v-if="t.bucket === 'now' && t.minutes > 5" class="ws-text-button" @click="demo.shrinkTask(t.id)">拆成 5 分钟</button>
            <button v-if="t.bucket === 'waiting' && t.minutes > 0" class="ws-text-button" @click="demo.planToday(t.id)">安排执行</button>
          </div>
        </div>
      </div>
    </li>
  </TransitionGroup>
  <EmptyState v-else kind="notes" :title="emptyTitle" :description="emptyDesc">
    <RouterLink v-if="mode !== 'done' && mode !== 'waiting'" class="ws-text-link" to="/chat">开始咨询<UiIcon name="arrow" :size="16" /></RouterLink>
  </EmptyState>
</template>
<style scoped>
.task-row-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 16px; margin-top: 6px; }
.task-row-actions .ws-inline-actions { margin: 0; gap: 12px; }
</style>
