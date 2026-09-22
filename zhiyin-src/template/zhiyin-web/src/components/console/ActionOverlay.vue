<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import {
  getActionPlan,
  getCalendarNodes,
  setActionTaskDone,
  type ActionPhase,
  type ActionPlan,
  type ActionTask,
  type CalendarNode,
} from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { failureText } from '@/lib/failure'

/**
 * ④ 行动 —— 行动计划。
 *
 * 这一屏回答的是"接下来怎么做"，口径是**今天/本周勾得掉**：
 *   · 阶段（时间范围 + 标签）与阶段下的任务，全部来自 ④ 环节产出的资产；
 *   · 每一条都能勾掉，勾错了能撤回（后端支持 done=false）；
 *   · 顶部只放"现在这一件"——同时给十件事等于没给；
 *   · 关键节点走日历（规划师写入、教练读取），这里如实说它有没有写进去。
 *
 * 数据来源是资产不是模型：打开这一屏**不会再算一次**，读的是那一版计划。
 */
const session = useSessionStore()

const data = ref<ActionPlan | null>(null)
const nodes = ref<CalendarNode[]>([])
const loading = ref(true)
const error = ref('')
const busy = ref('')

const phases = computed<ActionPhase[]>(() => data.value?.phases ?? [])
const nextTask = computed<ActionTask | null>(() => data.value?.next_task ?? null)
const doneCount = computed(() =>
  phases.value.reduce((n, p) => n + (p.tasks ?? []).filter((t) => t.done).length, 0),
)
const totalCount = computed(() =>
  phases.value.reduce((n, p) => n + (p.tasks ?? []).length, 0),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [plan, calendar] = await Promise.all([
      getActionPlan(),
      getCalendarNodes().catch(() => [] as CalendarNode[]),
    ])
    data.value = plan
    nodes.value = calendar
  } catch (cause) {
    error.value = failureText(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)

/** 关键节点是谁写的。取值由内核契约限定为 planner / coach / manual，界面只把它翻成人话。 */
const NODE_SOURCE: Record<string, string> = {
  planner: '路径规划师写进日历',
  coach: '教练提醒写进日历',
  manual: '你自己加进日历',
}

function showNode(node: CalendarNode) {
  session.openDrawer(
    node.title,
    node.due_at ? `截止 ${node.due_at.slice(0, 10)}` : '没有写截止时间',
    [
      { source: '来自', detail: NODE_SOURCE[node.source ?? ''] ?? '写进了你的日历', confidence: 1, at: '日历' },
      ...(node.related_task_text
        ? [{ source: '对应的事', detail: node.related_task_text, confidence: 1, at: '生成时' }]
        : []),
    ],
  )
}

async function toggle(task: ActionTask) {
  busy.value = task.task_id
  try {
    data.value = await setActionTaskDone(task.task_id, !task.done)
  } catch (cause) {
    /*
     * 勾选失败最常见的原因不是"点错了"，而是**这一版计划已经过期**：
     * 另一边（对话里的 AI）刚重算出一版新计划，任务 id 换了，你手上这一条
     * 在新版里根本不存在。这时该做的是把最新那版取回来，而不是让用户对着一句
     * 报错怀疑自己。
     */
    error.value = failureText(cause)
    try {
      const latest = await getActionPlan()
      if (latest) {
        data.value = latest
        error.value = '计划刚更新过，已经帮你刷新到最新的一版。'
      }
    } catch {
      /* 刷新也失败：保留原来那句错误，不把它吞掉 */
    }
  } finally {
    busy.value = ''
  }
}

function showTask(task: ActionTask) {
  session.openDrawer(task.text, `${task.phase} · ${task.due_date ? `截止 ${task.due_date.slice(0, 10)}` : '没有写截止时间'}`, [
    { source: '来自', detail: `行动这一步的「${task.phase}」阶段`, confidence: 1, at: '生成时' },
    { source: '状态', detail: task.done ? '已经勾掉了' : '还没勾掉', confidence: 1, at: task.done_at?.slice(0, 16) ?? '—' },
  ])
}
</script>

<template>
  <Overlay
    title="行动计划"
    :subtitle="totalCount ? `已完成 ${doneCount} / ${totalCount}` : '阶段 · 任务 · 关键节点'"
    from="action"
    size="wide"
    @close="session.closeOverlay()"
  >
    <p v-if="loading" class="label hint">正在读你的行动计划…</p>
    <p v-else-if="error" class="warn" role="alert">{{ error }}</p>

    <div v-else-if="!data?.has_plan" class="empty sheet">
      <h3 class="empty__t editorial">还没有行动计划。</h3>
      <p class="empty__d">
        计划来自「行动」这一步：方向定下来之后，跟主理说一句"接下来怎么做"，
        它会把任务拆到"今天 / 本周勾得掉"的粒度，写进这里与关键节点日历。
      </p>
      <button class="btn" type="button" @click="session.callTalk()">去要一份计划</button>
    </div>

    <template v-else>
      <!-- 现在这一件：一屏只推一件 -->
      <section v-if="nextTask" class="now sheet">
        <span class="label now__k">现在这一件</span>
        <h3 class="now__t">{{ nextTask.text }}</h3>
        <p class="now__meta label">
          {{ nextTask.phase }}
          <template v-if="nextTask.due_date"> · 截止 {{ nextTask.due_date.slice(0, 10) }}</template>
        </p>
        <div class="now__acts">
          <button class="btn primary" type="button" :disabled="busy === nextTask.task_id" @click="toggle(nextTask)">
            {{ busy === nextTask.task_id ? '正在记下…' : '勾掉它' }}
          </button>
          <button class="btn ghost" type="button" @click="showTask(nextTask)">看依据</button>
        </div>
      </section>
      <section v-else class="now sheet done">
        <span class="label now__k">现在这一件</span>
        <h3 class="now__t">这一版计划里的任务都勾完了。</h3>
        <p class="now__meta label">跟主理说一句，它会按你的新情况重排下一段。</p>
      </section>

      <!-- 阶段与任务 -->
      <section v-for="phase in phases" :key="phase.name" class="phase sheet">
        <header class="phase__head">
          <h3 class="phase__name">{{ phase.name }}</h3>
          <span class="label phase__range">{{ phase.date_range }}</span>
          <span v-if="phase.tag" class="label phase__tag">{{ phase.tag }}</span>
        </header>

        <ul class="tasks">
          <li v-for="task in phase.tasks ?? []" :key="task.task_id" :class="{ done: task.done }">
            <button
              class="tick"
              type="button"
              :aria-pressed="task.done"
              :aria-label="task.done ? `取消勾选：${task.text}` : `勾掉：${task.text}`"
              :disabled="busy === task.task_id"
              @click="toggle(task)"
            >
              <svg viewBox="0 0 14 14" aria-hidden="true">
                <path d="M2.6 7.4 5.6 10.4 11.4 3.8" fill="none" stroke="currentColor"
                      stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
            <span class="tasks__text">{{ task.text }}</span>
            <span v-if="task.due_date" class="label tasks__due">{{ task.due_date.slice(0, 10) }}</span>
            <button class="label tasks__why" type="button" @click="showTask(task)">依据</button>
          </li>
        </ul>
      </section>

      <p class="label foot">
        {{ data.reminders_synced ? '关键节点已经写进日历（规划师写入、教练读取）。' : '关键节点还没写进日历 —— 计划里只有任务清单。' }}
      </p>

      <!-- 关键节点日历：与任务清单分开摆 —— 一条是"什么时候"，
           一条是"做什么"。混在一起会让人按时间顺序去理解任务。 -->
      <section v-if="nodes.length" class="cal sheet">
        <header class="cal__head">
          <h3 class="cal__t">关键节点</h3>
          <span class="label cal__n">{{ nodes.length }} 条 · 来自日历</span>
        </header>
        <ul class="cal__list">
          <li v-for="node in nodes" :key="node.node_id">
            <button class="node" type="button" @click="showNode(node)">
              <span class="mono node__at">{{ node.due_at ? node.due_at.slice(0, 10) : '—' }}</span>
              <span class="node__title">{{ node.title }}</span>
              <span v-if="node.related_task_text" class="label node__task">{{ node.related_task_text }}</span>
            </button>
          </li>
        </ul>
      </section>
    </template>
  </Overlay>
</template>

<style scoped>
.hint { color: var(--ink-3); }
.warn { color: var(--warn); font-size: var(--fs-small); }

.now { padding: var(--s5); display: flex; flex-direction: column; gap: var(--s2); border-left: 4px solid var(--accent); }
.now.done { border-left-color: var(--mk-green); }
.now__k { color: var(--accent); }
.now__t { font-size: var(--fs-lg); color: var(--ink-1); line-height: 1.5; }
.now__meta { color: var(--ink-3); }
.now__acts { display: flex; gap: var(--s2); margin-top: var(--s2); }

.phase { padding: var(--s4) var(--s5); display: flex; flex-direction: column; gap: var(--s2); }
.phase__head { display: flex; align-items: baseline; gap: var(--s3); }
.phase__name { font-size: var(--fs-body); color: var(--ink-1); }
.phase__range, .phase__tag { color: var(--ink-3); }
.phase__tag { margin-left: auto; }

.tasks { list-style: none; margin: 0; padding: 0; display: grid; }
.tasks li {
  display: grid; grid-template-columns: 26px minmax(0, 1fr) 90px 52px;
  align-items: center; gap: var(--s2);
  padding: 7px 0; border-top: 1px solid var(--line-1);
}
.tasks li:first-child { border-top: 0; }
.tasks__text { font-size: var(--fs-small); color: var(--ink-1); }
.tasks li.done .tasks__text { color: var(--ink-faint); text-decoration: line-through; }
.tasks__due { color: var(--ink-3); text-align: right; }
.tasks__why { color: var(--ink-3); }
.tasks__why:hover { color: var(--accent); }

.tick {
  width: 20px; height: 20px; border-radius: 6px;
  border: 1.5px solid var(--line-3); color: transparent;
  display: inline-flex; align-items: center; justify-content: center;
  transition: border-color var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.tick svg { width: 12px; height: 12px; }
.tick:hover { border-color: var(--accent); }
.tasks li.done .tick { border-color: var(--mk-green); color: var(--mk-green); background: var(--accent-soft); }
.tick:disabled { opacity: 0.5; }

.empty { padding: var(--s6); display: flex; flex-direction: column; gap: var(--s3); align-items: flex-start; }
.empty__t { font-size: var(--fs-lg); color: var(--ink-1); }
.empty__d { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.8; max-width: 60ch; }
/*
 * 这一句原来直接铺在浮层底板上。底板拿掉（见 Overlay.vue）之后，
 * 它得自己有一张纸 —— 否则是浮层里唯一一段压在遮罩上的字。
 */
.foot {
  margin-top: var(--s4);
  padding: var(--s3) var(--s4);
  background: var(--n-1);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-md);
  color: var(--ink-3);
  line-height: 1.7;
}

.cal { padding: var(--s4) var(--s5); display: flex; flex-direction: column; gap: var(--s2); }
.cal__head { display: flex; align-items: baseline; gap: var(--s3); }
.cal__t { font-size: var(--fs-body); color: var(--ink-1); }
.cal__n { margin-left: auto; color: var(--ink-3); }
.cal__list { list-style: none; margin: 0; padding: 0; display: grid; }
.node {
  width: 100%; display: grid; grid-template-columns: 92px minmax(0, 1fr);
  gap: 4px var(--s3); align-items: baseline; text-align: left;
  padding: 7px 0; border-top: 1px solid var(--line-1);
  transition: color var(--mo-fast) var(--mo-out);
}
.cal__list li:first-child .node { border-top: 0; }
.node:hover .node__title { color: var(--accent); }
.node__at { color: var(--ink-3); }
.node__title { font-size: var(--fs-small); color: var(--ink-1); }
.node__task { grid-column: 2; color: var(--ink-3); }
</style>
