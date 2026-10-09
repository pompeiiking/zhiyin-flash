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

/**
 * 时间线是**给人读的**，所以这里有一层防御：后端历史上把事件码当标题、
 * 把 payload 的 Python 字典 repr 当说明写进了记录（`function.py` 已修，
 * 但已经在库里的旧记录还在）。判据很朴素 —— 标题长得像事件码、说明里带花括号，
 * 就不是给用户看的东西，退到一句中性话，而不是把它摆在用户面前。
 * 这一层不替代后端修复：它只是让"漏网的历史数据"不变成界面上的一串英文下划线。
 */
const looksLikeCode = (text: string) => /^[a-z][a-z0-9_]{2,}$/.test(text)

function humanTitle(event: TrackEvent): string {
  const title = (event.title || '').trim()
  if (!title) return '一条记录'
  return looksLikeCode(title) ? '一条操作记录' : title
}

function humanDetail(event: TrackEvent): string {
  const detail = (event.detail || '').trim()
  return detail.includes('{') || detail.includes('}') ? '' : detail
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

function show(event: TrackEvent, times = 1) {
  session.openDrawer(
    humanTitle(event),
    humanDetail(event) || '这一条只记了"那一下你做过了"，没有更多说明。',
    [
      { source: '类型', detail: TONE[event.type] ?? event.type, confidence: 1, at: at(event.occurred_at) ?? '—' },
      { source: '时间', detail: event.due_at ? `截止 ${event.due_at.slice(0, 10)}` : (at(event.occurred_at) ?? '—'), confidence: 1, at: '记录' },
      // 合并过的那几行：把次数说清楚，别让用户以为只有一次
      ...(times > 1
        ? [{ source: '次数', detail: `${times} 次`, confidence: 1, at: '最近一次' }]
        : []),
    ],
  )
}

const at = (value?: string | null) => (value ? value.slice(0, 16).replace('T', ' ') : '—')

/**
 * 时间线按**同一条记录**合并成一行，次数写在后面。
 *
 * 为什么必须合并：后端每上报一次埋点就落一条，而"进了工作台、开口聊了一句"这类
 * 动作一天会重复几十次 —— 实测一次核验跑完，这一屏就是 50 行一模一样的文本，
 * 用户读到的不是"这段时间发生过什么"，而是"这软件在刷屏"。
 *
 * 判据用**身份**（类型 + 人话标题 + 说明）而不是只看相邻：同一天里分散发生的同一件事
 * 本来就该算一件。次数照样如实写出来（不隐藏事实），时间取最近的那一次。
 */
const rows = computed(() => {
  const grouped = new Map<string, { event: TrackEvent; n: number }>()
  for (const event of events.value) {
    const key = `${event.type}|${humanTitle(event)}|${humanDetail(event)}`
    const hit = grouped.get(key)
    if (hit) hit.n += 1
    else grouped.set(key, { event, n: 1 })
  }
  return [...grouped.values()]
})
</script>

<template>
  <Overlay
    title="上周复盘"
    :subtitle="
      events.length
        ? rows.length < events.length
          ? `${events.length} 条记录 · 归成 ${rows.length} 类`
          : `${events.length} 条记录 · 都是已经发生的事`
        : '这段时间做了什么'
    "
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
      <li v-for="row in rows" :key="row.event.id">
        <button class="row" type="button" @click="show(row.event, row.n)">
          <span class="mono row__at">{{ at(row.event.occurred_at) }}</span>
          <span class="label row__type" :data-type="row.event.type">{{ TONE[row.event.type] ?? row.event.type }}</span>
          <span class="row__title">
            {{ humanTitle(row.event) }}
            <span v-if="row.n > 1" class="label row__n">{{ row.n }} 次</span>
          </span>
          <span class="row__detail">{{ humanDetail(row.event) }}</span>
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
@media (hover: hover) and (pointer: fine) {
.row:hover { background: var(--fill-subtle); } }
.row__at { color: var(--ink-3); }
.row__type { color: var(--ink-2); }
.row__type[data-type='warning'] { color: var(--warn); }
.row__type[data-type='milestone_done'] { color: var(--mk-green); }
.row__title { font-size: var(--fs-small); color: var(--ink-1); }
.row__n { color: var(--ink-3); margin-left: 6px; }
.row__detail { font-size: var(--fs-small); color: var(--ink-2); }

@media (max-width: 900px) {
  .row { grid-template-columns: 104px minmax(0, 1fr); }
  .row__detail { grid-column: 2; }
}
</style>
