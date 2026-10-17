<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { dateKey } from '../lib/action-insights.mjs'
import DetailPopover from '../components/DetailPopover.vue'
import ResultPager from '../components/ResultPager.vue'
import { usePagedItems } from '../lib/paged-items'
import { backendDemo } from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import TodoSuggestions from '../components/TodoSuggestions.vue'
import InfoSheet from '../components/InfoSheet.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusBanner from '../components/StatusBanner.vue'
import SourceChip from '../components/SourceChip.vue'
import { backendClient } from '../api/backend-client'
import type { NoteView } from '../api/backend-types'

type NoteKind = 'todo' | 'goal'

const scope = ref<NoteKind>('todo')
const drafts = ref<Record<NoteKind, string>>({ todo: '', goal: '' })
const noteQuery = ref('')
const loading = ref(false)
const adding = ref(false)
const changingId = ref('')
const deleting = ref<NoteView | null>(null)
const deletingBusy = ref(false)
const loadError = ref('')
const actionError = ref('')
const deleteError = ref('')
const status = ref('')

const displayNote = (text: string) => text.replace(/^【任务复盘:[^】]+】/, '任务复盘 · ')
const allNotes = computed(() => backendDemo.state.notes)
const todoNotes = computed(() => allNotes.value.filter((note) => note.kind === 'todo'))
const goalNotes = computed(() => allNotes.value.filter((note) => note.kind === 'goal'))
const todoPending = computed(() => todoNotes.value.filter((note) => !note.done).length)
const goalPending = computed(() => goalNotes.value.filter((note) => !note.done).length)
const scopeLabel = computed(() => scope.value === 'todo' ? '待办' : '目标')
const items = computed(() => scope.value === 'todo' ? todoNotes.value : goalNotes.value)
const pending = computed(() => items.value.filter((note) => !note.done))
const completed = computed(() => items.value.filter((note) => note.done))
const otherKind = computed<NoteKind>(() => scope.value === 'todo' ? 'goal' : 'todo')
const otherLabel = computed(() => otherKind.value === 'todo' ? '待办' : '目标')
const otherItems = computed(() => otherKind.value === 'todo' ? todoNotes.value : goalNotes.value)
const otherPending = computed(() => otherItems.value.filter((note) => !note.done))
const contextItems = computed(() => otherPending.value.slice(0, 4))
const text = computed({
  get: () => drafts.value[scope.value],
  set: (value: string) => { drafts.value[scope.value] = value },
})
const visibleNotes = computed(() => {
  const query = noteQuery.value.trim().toLocaleLowerCase()
  const ordered = [...pending.value, ...completed.value]
  return query ? ordered.filter((note) => note.text.toLocaleLowerCase().includes(query)) : ordered
})
const { page: notesPage, paged: pagedNotes } = usePagedItems(visibleNotes, 6, () => [scope.value, noteQuery.value])
const noteGroups = computed(() => [
  { key: 'pending', title: '待完成', items: pagedNotes.value.filter((note) => !note.done) },
  { key: 'done', title: '已完成', items: pagedNotes.value.filter((note) => note.done) },
])

function selectScope(kind: NoteKind) {
  scope.value = kind
  noteQuery.value = ''
  actionError.value = ''
  status.value = ''
}

async function loadNotes() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    const notes = await backendClient.notes()
    if (!Array.isArray(notes)) throw new Error('Incomplete notes')
    backendDemo.setNotes(notes)
  } catch {
    loadError.value = '最新记录没有取得。现有条目和输入仍保留。'
  } finally {
    loading.value = false
  }
}

async function add() {
  if (adding.value) return
  actionError.value = ''
  status.value = ''
  const cleaned = text.value.trim()
  if (!cleaned || cleaned.length > 200) {
    actionError.value = '请写下 1–200 个字。'
    return
  }
  if (items.value.some((note) => note.text === cleaned)) {
    status.value = `这条${scopeLabel.value}已经存在，原记录没有改变。`
    return
  }
  adding.value = true
  try {
    const note = await backendClient.addNote({ kind: scope.value, text: cleaned })
    backendDemo.upsertNote(note)
    text.value = ''
    status.value = `${scopeLabel.value}已保存到个人记录。`
  } catch {
    actionError.value = `这条${scopeLabel.value}没有保存成功，请核对内容后重试。输入仍保留。`
  } finally {
    adding.value = false
  }
}

async function setDone(item: NoteView, done: boolean) {
  if (changingId.value) return
  changingId.value = item.id
  actionError.value = ''
  status.value = ''
  try {
    const result = await backendClient.noteDone(item.id, done)
    backendDemo.upsertNote(result)
    status.value = done ? `已完成“${displayNote(item.text)}”。` : `“${displayNote(item.text)}”已恢复为待完成。`
  } catch {
    actionError.value = '记录状态没有保存成功。原状态仍保留，可以再次操作。'
  } finally {
    changingId.value = ''
  }
}

async function remove() {
  if (!deleting.value || deletingBusy.value) return
  deletingBusy.value = true
  deleteError.value = ''
  try {
    const id = deleting.value.id
    const result = await backendClient.removeNote(id)
    if (result.removed !== id) throw new Error('Delete was not confirmed')
    const removedText = displayNote(deleting.value.text)
    backendDemo.removeNote(id)
    deleting.value = null
    status.value = `已删除“${removedText}”。`
  } catch {
    deleteError.value = '这条记录没有删除成功，请重试；原记录仍保留。'
  } finally {
    deletingBusy.value = false
  }
}

onMounted(() => { void loadNotes() })
</script>

<template>
  <div class="ws-page notes-page">
    <PageHeading title="待办与目标" description="先把方向和下一步记下来，再决定哪些值得排进今天。">
      <DetailPopover title="这三层有什么不同" label="查看目标、待办与今日行动的区别" side="bottom">
        <template #trigger>怎么区分</template>
        <p>目标描述你想达到的结果；待办是可以开始的一步；今日行动来自阶段计划，包含日期与用时。</p>
        <p>三类记录不会自动互相改写，你可以按自己的节奏整理。</p>
      </DetailPopover>
    </PageHeading>

    <ol class="notes-flow" aria-label="从方向到行动的三层记录">
      <li>
        <span class="notes-flow__mark"><UiIcon name="trophy" :size="18" /></span>
        <span><strong>目标</strong><small>想达到的结果</small></span>
      </li>
      <li aria-hidden="true" class="notes-flow__arrow"><UiIcon name="arrow" :size="16" /></li>
      <li>
        <span class="notes-flow__mark"><UiIcon name="notes" :size="18" /></span>
        <span><strong>待办</strong><small>可以开始的一步</small></span>
      </li>
      <li aria-hidden="true" class="notes-flow__arrow"><UiIcon name="arrow" :size="16" /></li>
      <li>
        <RouterLink to="/home">
          <span class="notes-flow__mark"><UiIcon name="calendar" :size="18" /></span>
          <span><strong>今日行动</strong><small>安排日期与用时</small></span>
        </RouterLink>
      </li>
    </ol>

    <section class="notes-capture" aria-labelledby="notesCaptureTitle">
      <div class="notes-capture__head">
        <div class="notes-capture__title">
          <h2 id="notesCaptureTitle">记下一件事</h2>
          <DetailPopover title="记录提示" label="查看记录提示" side="bottom">
            <template #trigger>记录提示</template>
            <p>{{ scope === 'todo' ? '待办适合用动词写成一个可以开始的动作。' : '目标适合写成想达到的结果，不必急着拆分步骤。' }}</p>
            <p>每条最多 200 字；同一类型下的相同内容只保留一条。</p>
          </DetailPopover>
        </div>
        <div class="notes-scope" role="group" aria-label="选择记录类型并查看相应清单">
          <button type="button" :aria-pressed="scope === 'todo'" @click="selectScope('todo')">
            待办 <strong>{{ todoPending }}</strong><span>未完成</span>
          </button>
          <button type="button" :aria-pressed="scope === 'goal'" @click="selectScope('goal')">
            目标 <strong>{{ goalPending }}</strong><span>未完成</span>
          </button>
        </div>
      </div>

      <form class="notes-composer" @submit.prevent="add">
        <label class="sr-only" :for="`note-${scope}`">新增{{ scopeLabel }}</label>
        <input
          :id="`note-${scope}`"
          v-model="text"
          maxlength="200"
          :placeholder="scope === 'todo' ? '例如：整理一版项目经历' : '例如：明确下学期的实习方向'"
        />
        <button class="btn btn--primary notes-composer__submit" type="submit" :disabled="adding || !text.trim()">
          <UiIcon name="plus" :size="17" />{{ adding ? '正在保存…' : `添加${scopeLabel}` }}
        </button>
      </form>
      <StatusBanner :open="!!status" tone="success" :message="status" @dismiss="status = ''" />
      <StatusBanner v-if="actionError" tone="warning" :message="actionError" @dismiss="actionError = ''" />
      <StatusBanner
        v-if="loadError"
        tone="error"
        :message="loadError"
        retry-label="重新读取"
        :retrying="loading"
        @retry="loadNotes"
        @dismiss="loadError = ''"
      />
    </section>

    <div class="notes-workspace">
      <main class="notes-main">
        <section class="notes-ledger" aria-labelledby="notesLedgerTitle">
          <header class="notes-ledger__head">
            <div>
              <p class="notes-ledger__kicker">{{ scope === 'todo' ? '下一步' : '方向' }}</p>
              <h2 id="notesLedgerTitle">我的{{ scopeLabel }}</h2>
              <p>{{ pending.length }} 条待完成，{{ completed.length }} 条已完成</p>
            </div>
            <strong>{{ items.length }}</strong>
          </header>

          <label class="notes-search" for="notes-search-input">
            <UiIcon name="search" :size="17" />
            <span class="sr-only">查找{{ scopeLabel }}</span>
            <input id="notes-search-input" v-model="noteQuery" type="search" :placeholder="`查找${scopeLabel}…`" />
          </label>
          <p v-if="noteQuery" class="notes-search-result" role="status">
            找到 {{ visibleNotes.length }} 条，共 {{ items.length }} 条。
            <button class="ws-text-button" type="button" @click="noteQuery = ''">清空关键词</button>
          </p>

          <div class="notes-ledger__records" :aria-busy="loading">
            <SkeletonBlock v-if="loading" :overlay="allNotes.length > 0" variant="list" :lines="4" />
            <EmptyState
              v-else-if="!visibleNotes.length"
              :kind="noteQuery ? 'search-empty' : 'notes'"
              :title="noteQuery ? `没有找到这条${scopeLabel}` : `还没有${scopeLabel}`"
              :description="noteQuery ? '换一个关键词，或清空关键词查看全部记录。' : `在上方写下第一条${scopeLabel}，保存后会出现在这里。`"
              :next="false"
            >
              <button v-if="noteQuery" class="btn" type="button" @click="noteQuery = ''">查看全部{{ scopeLabel }}</button>
            </EmptyState>

            <section v-for="group in noteGroups.filter((item) => item.items.length)" :key="group.key" class="notes-group">
              <h3>{{ group.title }}<span>本页 {{ group.items.length }} 条</span></h3>
              <ul>
                <li v-for="item in group.items" :key="item.id" class="notes-record" :class="{ 'notes-record--done': item.done }">
                  <button
                    class="notes-record__toggle"
                    type="button"
                    :aria-label="(item.done ? '恢复：' : '完成：') + displayNote(item.text)"
                    :aria-pressed="item.done"
                    :disabled="changingId === item.id"
                    @click="setDone(item, !item.done)"
                  >
                    <span><UiIcon v-if="item.done" name="check" :size="15" /></span>
                  </button>
                  <div class="notes-record__body">
                    <p>{{ displayNote(item.text) }}</p>
                    <DetailPopover title="记录信息" :label="'查看记录信息：' + displayNote(item.text)" side="bottom">
                      <template #trigger><time>{{ dateKey(item.created_at) || '日期未提供' }}</time></template>
                      <SourceChip source="user_edit" :at="item.created_at" />
                      <p>{{ item.done ? '已完成，可恢复为待完成。' : '完成后仍会保留，可随时恢复。' }}</p>
                    </DetailPopover>
                  </div>
                  <button class="ws-icon-button notes-record__delete" type="button" :aria-label="'删除：' + displayNote(item.text)" @click="deleting = { ...item }">
                    <UiIcon name="trash" :size="17" />
                  </button>
                </li>
              </ul>
            </section>
          </div>
          <ResultPager v-model:page="notesPage" :total="visibleNotes.length" :label="scopeLabel" />
        </section>

        <TodoSuggestions v-if="scope === 'todo'" />
      </main>

      <aside class="notes-aside" aria-label="行动上下文">
        <section class="notes-context">
          <header>
            <span class="notes-context__icon"><UiIcon :name="otherKind === 'goal' ? 'trophy' : 'notes'" :size="18" /></span>
            <div>
              <h2>{{ otherKind === 'goal' ? '别忘了方向' : '把目标落到下一步' }}</h2>
              <p>还有 {{ otherPending.length }} 条{{ otherLabel }}待完成</p>
            </div>
          </header>
          <ul v-if="contextItems.length">
            <li v-for="item in contextItems" :key="item.id">{{ displayNote(item.text) }}</li>
          </ul>
          <p v-else class="notes-context__empty">目前没有待完成的{{ otherLabel }}。</p>
          <button class="ws-text-button" type="button" @click="selectScope(otherKind)">
            查看全部{{ otherLabel }}<UiIcon name="arrow" :size="15" />
          </button>
        </section>

        <section class="notes-plan">
          <span class="notes-plan__icon"><UiIcon name="calendar" :size="19" /></span>
          <h2>准备今天做？</h2>
          <p>这里是个人记录，不包含日期与用时。选好要做的事后，再去今日行动排进日程。</p>
          <RouterLink class="ws-text-link" to="/home">打开今日行动<UiIcon name="arrow" :size="16" /></RouterLink>
        </section>
      </aside>
    </div>

    <nav class="ws-related"><RouterLink  :to="{ path: '/chat', query: { question: '我想讨论当前' + scopeLabel + '的安排：' + pending.slice(0, 5).map(item => item.text).join('；') } }">和顾问讨论这些安排<UiIcon name="chat" :size="16" /></RouterLink></nav>

    <InfoSheet :open="deleting !== null" shape="dialog" title="删除这条记录？" @close="!deletingBusy && (deleting = null)">
      <p>{{ deleting?.text }}</p>
      <p class="ws-muted ws-section">删除后无法恢复；如果只是暂时不做，可以保留记录或标记为已完成。</p>
      <p v-if="deleteError" class="ws-field-error" role="alert">{{ deleteError }}</p>
      <div class="ws-inline-actions">
        <button class="btn btn--danger" type="button" :disabled="deletingBusy" @click="remove">{{ deletingBusy ? '正在删除…' : '确认删除' }}</button>
        <button class="btn" type="button" :disabled="deletingBusy" @click="deleting = null">保留记录</button>
      </div>
    </InfoSheet>
  </div>
</template>

<style scoped>
:global(.app.app--workspace .notes-page.ws-page) { max-width: 1220px; }

.notes-flow { display: grid; grid-template-columns: minmax(0,1fr) 28px minmax(0,1fr) 28px minmax(0,1fr); align-items: center; margin: 0 0 18px; padding: 13px 18px; border-block: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-surface) 86%, var(--c-primary-weak)); list-style: none; }
.notes-flow li:not(.notes-flow__arrow), .notes-flow a { display: flex; align-items: center; gap: 11px; min-width: 0; color: var(--c-text); text-decoration: none; }
.notes-flow li:last-child { min-width: 0; }
.notes-flow__mark { display: grid; flex: none; place-items: center; width: 34px; height: 34px; border: 1px solid var(--c-primary-border); border-radius: 50%; color: var(--c-primary); background: var(--c-surface); }
.notes-flow strong, .notes-flow small { display: block; }
.notes-flow strong { font-size: var(--fs-13); font-weight: var(--fw-semibold); }
.notes-flow small { margin-top: 2px; color: var(--c-text-3); font-size: var(--fs-11); }
.notes-flow__arrow { display: grid; place-items: center; color: var(--c-border-strong); }
.notes-flow a:hover strong { color: var(--c-primary); }
.notes-flow a:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 4px; border-radius: 4px; }

.notes-capture { margin-bottom: 22px; padding: 18px 20px 16px; border: 1px solid var(--c-border); border-top: 3px solid var(--c-primary); border-radius: 0 0 12px 12px; background: var(--c-surface); }
.notes-capture__head { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.notes-capture__head h2 { font-size: var(--fs-16); font-weight: var(--fw-semibold); }
.notes-capture__title { display: flex; align-items: center; gap: var(--sp-2); }
.notes-capture__title :deep(.detail-trigger) { min-height: 32px; padding-inline: var(--sp-2); color: var(--c-text-2); font-size: var(--fs-12); }
.notes-scope { display: flex; flex: none; gap: 4px; padding: 3px; border-radius: 9px; background: var(--c-surface-2); }
.notes-scope button { display: flex; align-items: baseline; gap: 5px; min-height: 38px; padding: 7px 11px; border: 1px solid transparent; border-radius: 7px; color: var(--c-text-2); font-size: var(--fs-12); }
.notes-scope button[aria-pressed='true'] { border-color: var(--c-primary-border); background: var(--c-surface); color: var(--c-primary); box-shadow: var(--e-1); }
.notes-scope strong { font-size: var(--fs-16); font-variant-numeric: tabular-nums; }
.notes-scope span { color: var(--c-text-3); font-size: var(--fs-11); }
.notes-composer { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 8px; margin-top: 14px; }
.notes-composer input { width: 100%; min-width: 0; min-height: 46px; padding: 10px 13px; border: 1px solid var(--c-border-control); border-radius: 8px; background: var(--c-surface); color: var(--c-text); font: inherit; }
.notes-composer input:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.notes-composer__submit { min-height: 46px; gap: 7px; white-space: nowrap; }
.notes-capture :deep(.status-banner) { margin-top: 12px; }

.notes-workspace { display: grid; grid-template-columns: minmax(0,1fr) 282px; align-items: start; gap: 26px; }
.notes-main { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.notes-ledger { padding: 0 24px 12px; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); }
.notes-ledger__head { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 21px 0 16px; border-bottom: 1px solid var(--c-border); }
.notes-ledger__kicker { margin-bottom: 2px; color: var(--c-primary) !important; font-size: var(--fs-11) !important; font-weight: var(--fw-semibold); }
.notes-ledger__head h2 { font-size: var(--fs-20); font-weight: var(--fw-semibold); }
.notes-ledger__head p { margin-top: 3px; color: var(--c-text-3); font-size: var(--fs-12); }
.notes-ledger__head > strong { flex: none; color: var(--c-text); font-size: 42px; font-weight: var(--fw-regular); line-height: 1; font-variant-numeric: tabular-nums; }
.notes-search { display: grid; grid-template-columns: 18px minmax(0,1fr); align-items: center; gap: 8px; margin: 13px 0 8px; color: var(--c-text-3); }
.notes-search input { min-width: 0; min-height: 40px; padding: 8px 10px; border: 0; border-bottom: 1px solid var(--c-border-control); border-radius: 0; background: transparent; color: var(--c-text); font: inherit; font-size: var(--fs-13); }
.notes-search input:focus-visible { outline: 0; border-bottom-color: var(--c-primary); box-shadow: 0 1px 0 var(--c-primary); }
.notes-search-result { margin-bottom: 10px; color: var(--c-text-3); font-size: var(--fs-12); }
.notes-ledger__records { position: relative; min-height: 80px; }
.notes-group + .notes-group { margin-top: 18px; }
.notes-group h3 { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; padding: 9px 0 6px; color: var(--c-text-2); font-size: var(--fs-12); font-weight: var(--fw-semibold); }
.notes-group h3 span { color: var(--c-text-3); font-size: var(--fs-11); font-weight: var(--fw-regular); }
.notes-group ul { padding: 0; border-top: 1px solid var(--c-border); list-style: none; }
.notes-record { display: grid; grid-template-columns: 44px minmax(0,1fr) 44px; align-items: center; gap: 10px; min-height: 66px; padding: 8px 0; border-bottom: 1px solid var(--c-border); }
.notes-record__toggle { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 8px; }
.notes-record__toggle > span { display: grid; place-items: center; width: 21px; height: 21px; border: 1px solid var(--c-border-strong); border-radius: 6px; background: var(--c-surface); color: #fff; }
.notes-record__toggle[aria-pressed='true'] > span { border-color: var(--c-primary); background: var(--c-primary); }
.notes-record__toggle:focus-visible, .notes-record__delete:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 1px; }
.notes-record__body { min-width: 0; }
.notes-record__body > p { color: var(--c-text); font-size: var(--fs-14); font-weight: var(--fw-medium); line-height: 1.65; overflow-wrap: anywhere; }
.notes-record--done .notes-record__body > p { color: var(--c-text-3); text-decoration: line-through; text-decoration-color: var(--c-border-strong); }
.notes-record__body :deep(.detail-trigger) { min-height: 28px; margin-top: 1px; padding: 0; color: var(--c-text-3); font-size: var(--fs-11); }
.notes-record__delete { color: var(--c-text-3); }
.notes-record__delete:hover { color: var(--c-attention); }

.notes-aside { position: sticky; top: 76px; display: flex; flex-direction: column; gap: 16px; }
.notes-aside > section { padding: 18px; }
.notes-context { border-left: 3px solid var(--c-primary); background: var(--c-primary-weak); }
.notes-context header { display: flex; align-items: flex-start; gap: 10px; }
.notes-context__icon, .notes-plan__icon { display: grid; flex: none; place-items: center; width: 34px; height: 34px; border-radius: 50%; color: var(--c-primary); background: var(--c-surface); }
.notes-context h2, .notes-plan h2 { font-size: var(--fs-14); font-weight: var(--fw-semibold); }
.notes-context header p { margin-top: 3px; color: var(--c-text-3); font-size: var(--fs-11); }
.notes-context ul { margin: 14px 0 12px; padding: 0; border-top: 1px solid var(--c-primary-border); list-style: none; }
.notes-context li { position: relative; padding: 9px 2px 9px 15px; border-bottom: 1px solid var(--c-primary-border); color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.55; overflow-wrap: anywhere; }
.notes-context li::before { position: absolute; top: 16px; left: 2px; width: 5px; height: 5px; border-radius: 50%; background: var(--c-primary); content: ''; }
.notes-context__empty { margin: 14px 0; color: var(--c-text-3); font-size: var(--fs-12); }
.notes-context .ws-text-button { display: inline-flex; align-items: center; gap: 5px; min-height: 40px; color: var(--c-primary); }
.notes-plan { border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); }
.notes-plan__icon { margin-bottom: 12px; background: var(--c-surface-2); }
.notes-plan p { margin: 9px 0 13px; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.7; }

@media (max-width: 1100px) {
  .notes-workspace { grid-template-columns: minmax(0,1fr); }
  .notes-aside { position: static; display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); }
}

@media (max-width: 767px) {
  :global(.app.app--workspace .notes-page .ws-heading) { flex-wrap: nowrap; align-items: center; }
  :global(.app.app--workspace .notes-page .ws-heading__actions) { width: auto; margin-left: auto; }
  :global(.app.app--workspace .notes-page .ws-heading__actions .detail-trigger) { min-height: 44px; white-space: nowrap; }
  .notes-flow { grid-template-columns: minmax(0,1fr) 18px minmax(0,1fr) 18px minmax(0,1fr); padding: 10px 6px; }
  .notes-flow li:not(.notes-flow__arrow), .notes-flow a { justify-content: center; gap: 6px; }
  .notes-flow__mark { width: 30px; height: 30px; }
  .notes-flow small { display: none; }
  .notes-flow strong { font-size: var(--fs-12); white-space: nowrap; }
  .notes-capture { margin-bottom: 16px; padding: 15px 14px 13px; }
  .notes-capture__head { align-items: flex-start; gap: 12px; }
  .notes-scope button { min-height: 44px; padding-inline: 9px; }
  .notes-composer { margin-top: 12px; }
  .notes-composer input, .notes-composer__submit { min-height: 44px; }
  .notes-workspace { gap: 16px; }
  .notes-main { gap: 16px; }
  .notes-ledger { padding: 0 14px 8px; }
  .notes-ledger__head { padding: 17px 0 13px; }
  .notes-ledger__head h2 { font-size: var(--fs-18); }
  .notes-ledger__head > strong { font-size: 34px; }
  .notes-search input { min-height: 44px; }
  .notes-record { grid-template-columns: 44px minmax(0,1fr) 44px; gap: 7px; }
  .notes-aside { grid-template-columns: minmax(0,1fr); }
}

@media (max-width: 560px) {
  .notes-capture__head { flex-direction: column; }
  .notes-scope { width: 100%; }
  .notes-scope button { flex: 1; justify-content: center; }
  .notes-composer { grid-template-columns: minmax(0,1fr); }
  .notes-composer__submit { width: 100%; }
}

@media (max-width: 350px) {
  .notes-flow__mark { display: none; }
  .notes-scope span { display: none; }
}
</style>
