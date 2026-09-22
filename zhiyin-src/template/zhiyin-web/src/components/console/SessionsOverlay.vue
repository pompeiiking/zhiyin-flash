<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import {
  listSessions,
  listSessionTurns,
  type SessionItem,
  type SessionList,
  type TurnHistoryItem,
} from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { failureText } from '@/lib/failure'

/**
 * 我的任务会话。
 *
 * 会话是"可拆可续"的载体（`TaskSession`）：换一件事、换一个环节，都可以新开一条，
 * 中间停几天再回来接着走。这一屏回答两件事：
 *
 *   1. **都开过哪些会话**：任务名、当前环节、主理、进度、最近活动 —— 全来自后端；
 *   2. **这条会话发生过什么**：逐轮原文（他说的话 + 主理的回答）。
 *
 * 第 2 条以前是空的：库里只有累积摘要，用户自己说的话一个字都没落库。
 * 所以这里不是"补了个界面"，是补了那条数据链路。
 */
const session = useSessionStore()

const data = ref<SessionList | null>(null)
const loading = ref(true)
const error = ref('')
const active = ref<string | null>(null)
const turns = ref<TurnHistoryItem[]>([])
const turnsLoading = ref(false)

const sessions = computed<SessionItem[]>(() => data.value?.sessions ?? [])
const currentTaskId = computed(() => data.value?.current_task_id ?? null)

const STATUS_LABEL: Record<string, string> = {
  active: '进行中',
  paused: '暂停',
  done: '已完成',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await listSessions()
    if (!active.value && sessions.value.length) {
      await open(sessions.value[0])
    }
  } catch (cause) {
    error.value = failureText(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function open(item: SessionItem) {
  active.value = item.task_id
  turnsLoading.value = true
  turns.value = []
  try {
    turns.value = await listSessionTurns(item.task_id)
  } catch (cause) {
    error.value = failureText(cause)
  } finally {
    turnsLoading.value = false
  }
}

/** 接着这条会话往下聊：把它设成当前会话，然后打开对话层 */
function resume(item: SessionItem) {
  session.switchSession(item.task_id, turns.value.map((t) => ({
    role: t.role === 'user' ? 'me' : 'ai',
    text: t.text,
    actor: t.agent_name ?? undefined,
  })))
  session.callTalk()
}

const at = (value?: string | null) => (value ? value.slice(0, 16).replace('T', ' ') : '—')
</script>

<template>
  <Overlay
    title="我的任务会话"
    :subtitle="sessions.length ? `${sessions.length} 条 · 可以回到任意一条接着聊` : '还没开过会话'"
    from="sessions"
    size="wide"
    @close="session.closeOverlay()"
  >
    <p v-if="loading" class="label hint">正在读会话清单…</p>
    <p v-else-if="error" class="warn" role="alert">{{ error }}</p>

    <div v-else-if="!sessions.length" class="empty sheet">
      <h3 class="empty__t editorial">还没有会话。</h3>
      <p class="empty__d">从画布上的「和主理聊聊」说一句话，就会开出一条会话。</p>
    </div>

    <div v-else class="wrap">
      <nav class="list sheet sheet--quiet" aria-label="会话清单">
        <ul>
          <li v-for="item in sessions" :key="item.task_id">
            <button
              class="row"
              type="button"
              :class="{ on: item.task_id === active }"
              @click="open(item)"
            >
              <span class="row__name">{{ item.task_name || item.task_id }}</span>
              <span class="label row__stage">{{ item.stage_label }}</span>
              <span class="label row__lead">{{ item.lead_agent_name || '—' }}</span>
              <span class="mono row__at">{{ at(item.last_active_at) }}</span>
              <span class="mono row__bar" aria-hidden="true">
                <i :style="{ width: `${Math.round((item.progress ?? 0) * 100)}%` }" />
              </span>
              <span class="label row__status">{{ STATUS_LABEL[item.status ?? ''] ?? item.status }}</span>
              <span v-if="item.task_id === currentTaskId" class="label row__cur">当前</span>
            </button>
          </li>
        </ul>
      </nav>

      <section class="thread sheet">
        <header class="thread__head">
          <span class="label">这条会话发生过什么</span>
          <button
            v-if="active"
            class="btn primary"
            type="button"
            @click="resume(sessions.find((s) => s.task_id === active)!)"
          >
            接着这条聊
          </button>
        </header>

        <p v-if="turnsLoading" class="label hint">正在读这一条的历史…</p>
        <p v-else-if="!turns.length" class="label hint">
          这一条还没有逐轮原文 —— 从这条会话往下聊，说过的话就会一条条留在这里。
        </p>
        <ol v-else class="turns">
          <li v-for="(turn, i) in turns" :key="i" :class="turn.role">
            <span class="label turn__who">{{ turn.role === 'user' ? '你' : (turn.agent_name || '主理') }}</span>
            <span class="turn__text">{{ turn.text }}</span>
            <span class="mono turn__at">{{ at(turn.created_at) }}</span>
          </li>
        </ol>
      </section>
    </div>
  </Overlay>
</template>

<style scoped>
.hint { color: var(--ink-3); }
.warn { color: var(--warn); font-size: var(--fs-small); }
.wrap { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: var(--s4); align-items: start; }

.list { padding: var(--s2); }
.list ul { list-style: none; margin: 0; padding: 0; display: grid; }
.row {
  width: 100%; display: grid;
  grid-template-columns: minmax(0, 1fr) 64px 88px 108px 60px 64px;
  align-items: center; gap: var(--s2);
  padding: 8px var(--s2); border-radius: var(--r-sm); text-align: left;
  transition: background var(--mo-fast) var(--mo-out);
}
.row:hover { background: var(--fill-subtle); }
.row.on { background: var(--accent-soft); }
.row__name { font-size: var(--fs-small); color: var(--ink-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row__stage, .row__lead, .row__at, .row__status, .row__cur { color: var(--ink-3); }
.row__cur { color: var(--accent); }
.row__bar { height: 4px; border-radius: 2px; background: var(--fill-hover); overflow: hidden; }
.row__bar i { display: block; height: 100%; background: var(--mk-green); }

.thread { padding: var(--s4) var(--s5); display: flex; flex-direction: column; gap: var(--s3); }
.thread__head { display: flex; align-items: center; gap: var(--s3); }
.thread__head .btn { margin-left: auto; }
.turns { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.turns li { display: grid; grid-template-columns: 62px minmax(0, 1fr) 104px; gap: var(--s2); align-items: baseline; }
.turns li.user .turn__who { color: var(--accent); }
.turn__who { color: var(--mk-purple); }
.turn__text { font-size: var(--fs-small); color: var(--ink-1); line-height: 1.7; white-space: pre-wrap; }
.turn__at { color: var(--ink-faint); }

.empty { padding: var(--s6); display: flex; flex-direction: column; gap: var(--s2); }
.empty__t { font-size: var(--fs-lg); color: var(--ink-1); }
.empty__d { font-size: var(--fs-small); color: var(--ink-2); }

@media (max-width: 900px) {
  .wrap { grid-template-columns: minmax(0, 1fr); }
}
</style>
