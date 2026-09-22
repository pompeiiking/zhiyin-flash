<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import {
  listTrackEvents,
  type TrackEvent,
} from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { failureText } from '@/lib/failure'

/**
 * ⑤ 复盘 —— 这段时间发生过什么、起了什么作用。
 *
 * 两个来源，都是后端的事实：
 *   · **结论**：`workspace.review_panel.evaluation`（复盘环节给出的判断）；
 *   · **时间线**：`GET /app/track/events`（里程碑、提醒、警告、教练消息）。
 *
 * 复盘不是"再生成一份总结"：它读的是**已经发生的事**。所以这一屏没有 AI 生成，
 * 也没有把握度数字 —— 事实就是事实。
 */
const session = useSessionStore()

const events = ref<TrackEvent[]>([])
const loading = ref(true)
const error = ref('')

const conclusion = computed(() => session.wsPanels?.review || '')

const TONE: Record<string, string> = {
  milestone_done: '里程碑',
  reminder: '提醒',
  warning: '警告',
  semester_review: '学期复盘',
  coach_message: '教练消息',
}

onMounted(async () => {
  try {
    events.value = await listTrackEvents()
  } catch (cause) {
    error.value = failureText(cause)
  } finally {
    loading.value = false
  }
})

function show(event: TrackEvent) {
  session.openDrawer(
    event.title,
    event.detail || '这一条没有更多说明',
    [
      { source: '类型', detail: TONE[event.type] ?? event.type, confidence: 1, at: event.occurred_at?.slice(0, 16) ?? '—' },
      { source: '时间', detail: event.due_at ? `截止 ${event.due_at.slice(0, 10)}` : (event.occurred_at?.slice(0, 16) ?? '—'), confidence: 1, at: '记录' },
    ],
  )
}

const at = (value?: string | null) => (value ? value.slice(0, 16).replace('T', ' ') : '—')
</script>

<template>
  <Overlay
    title="上周复盘"
    :subtitle="events.length ? `${events.length} 条记录 · 都是已经发生的事` : '这段时间做了什么'"
    from="review"
    size="wide"
    @close="session.closeOverlay()"
  >
    <section class="conc sheet">
      <span class="label conc__k">这一段的效果</span>
      <p v-if="conclusion" class="conc__t">{{ conclusion }}</p>
      <p v-else class="conc__t muted">
        复盘环节还没给结论 —— 走完一轮行动之后再看，它才有东西可说。
      </p>
    </section>

    <p v-if="loading" class="label hint state">正在读这段时间的记录…</p>
    <p v-else-if="error" class="warn state" role="alert">{{ error }}</p>
    <p v-else-if="!events.length" class="label hint state">
      还没有跟踪记录。做过的事（勾掉任务、认领差距、做出选择）会一条条记在这里。
    </p>

    <ol v-else class="tl sheet">
      <li v-for="event in events" :key="event.id">
        <button class="row" type="button" @click="show(event)">
          <span class="mono row__at">{{ at(event.occurred_at) }}</span>
          <span class="label row__type" :data-type="event.type">{{ TONE[event.type] ?? event.type }}</span>
          <span class="row__title">{{ event.title }}</span>
          <span class="row__detail">{{ event.detail }}</span>
        </button>
      </li>
    </ol>
  </Overlay>
</template>

<style scoped>
.hint { color: var(--ink-3); line-height: 1.7; }
.warn { color: var(--warn); font-size: var(--fs-small); }
/*
 * 空态 / 加载 / 出错这三句话也是**内容**，得有一张纸接着 ——
 * 浮层底板拿掉之后，直接摆在遮罩上的字会看不清。
 */
.state {
  padding: var(--s4) var(--s5);
  background: var(--n-1);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-md);
}

.conc { padding: var(--s5); display: flex; flex-direction: column; gap: var(--s2); border-left: 4px solid var(--mk-green); }
.conc__k { color: var(--mk-green); }
.conc__t { font-size: var(--fs-body); color: var(--ink-1); line-height: 1.8; }
.conc__t.muted { color: var(--ink-3); }

.tl { list-style: none; margin: 0; padding: var(--s2) var(--s3); display: grid; }
.tl li { border-top: 1px solid var(--line-1); }
.tl li:first-child { border-top: 0; }
.row {
  width: 100%; display: grid;
  grid-template-columns: 116px 76px minmax(0, 1fr) minmax(0, 1.2fr);
  gap: var(--s3); align-items: baseline; text-align: left;
  padding: var(--s3) var(--s2);
  transition: background var(--mo-fast) var(--mo-out);
}
.row:hover { background: var(--fill-subtle); }
.row__at { color: var(--ink-3); }
.row__type { color: var(--ink-2); }
.row__type[data-type='warning'] { color: var(--warn); }
.row__type[data-type='milestone_done'] { color: var(--mk-green); }
.row__title { font-size: var(--fs-small); color: var(--ink-1); }
.row__detail { font-size: var(--fs-small); color: var(--ink-2); }

@media (max-width: 900px) {
  .row { grid-template-columns: 104px minmax(0, 1fr); }
  .row__detail { grid-column: 2; }
}
</style>
