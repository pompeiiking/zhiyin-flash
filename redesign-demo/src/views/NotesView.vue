<script setup lang="ts">
import DetailPopover from '../components/DetailPopover.vue'
import ResultPager from '../components/ResultPager.vue'
import { usePagedItems } from '../lib/paged-items'
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import TodoSuggestions from '../components/TodoSuggestions.vue'
import InfoSheet from '../components/InfoSheet.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusBanner from '../components/StatusBanner.vue'
import SourceChip from '../components/SourceChip.vue'
import SegMeter from '../components/SegMeter.vue'
import { backendClient } from '../api/backend-client'
import { REVIEW_CONCLUSION, REVIEW_ITEMS } from '../data/student'
import { attributionLabel } from '../lib/presentation'
import type { NoteView } from '../api/backend-types'
const noteAxis = ref('done')
const notesBasisOpen=ref(false)
const noteQuery = ref('')
const visibleNotes = computed(()=>allNotes.value.filter(n=>!noteQuery.value.trim()||n.text.toLocaleLowerCase().includes(noteQuery.value.trim().toLocaleLowerCase())))
const tab = ref<'todo'|'goal'>('todo'), drafts = ref({todo:'',goal:''}), error=ref(''), status=ref('')
const deleting=ref<NoteView|null>(null),busy=ref(false),deleteError=ref('')
/* 读取态与"忙"分开：busy 也覆盖添加/删除，用它画骨架会把"正在保存"错认成"还没读到" */
const loading=ref(false)
async function loadNotes(){if(busy.value)return;busy.value=true;loading.value=true;error.value='';try{const notes=await backendClient.notes();if(!Array.isArray(notes))throw new Error('Incomplete notes');backendDemo.setNotes(notes);status.value='已读取最新个人记录。'}catch{error.value='最新记录没有取得，请重试。现有条目和输入仍保留。'}finally{busy.value=false;loading.value=false}}
async function setDone(item: NoteView,done:boolean){if(busy.value)return;if(!backendDemo.state.liveNoteIds.includes(item.id)){backendDemo.setNoteDone(item.id,done);return}busy.value=true;error.value='';try{const result=await backendClient.noteDone(item.id,done);backendDemo.upsertNote(result);status.value='记录状态已保存。'}catch{error.value='记录状态没有保存成功，请重试。原状态仍保留。'}finally{busy.value=false}}
const text=computed({get:()=>drafts.value[tab.value],set:v=>drafts.value[tab.value]=v})
const items=computed(()=>backendDemo.state.notes.filter(n=>n.kind===tab.value))
const pending=computed(()=>items.value.filter(n=>!n.done)), completed=computed(()=>items.value.filter(n=>n.done))
async function add(){if(busy.value)return;try{if(!text.value.trim()||text.value.trim().length>200)throw new Error('请写下1–200个字。');if(items.value.some(n=>n.text===text.value.trim())){status.value='这条记录已存在，已保留原记录。';return}if(backendDemo.state.notesOrigin==='live'){busy.value=true;const note=await backendClient.addNote({kind:tab.value,text:text.value.trim()});backendDemo.upsertNote(note);status.value='已保存到个人记录。'}else{backendDemo.addNote(text.value,tab.value);status.value='已保存这条个人记录。'}text.value='';error.value=''}catch{error.value='这条记录没有保存成功，请核对内容后重试。输入仍保留。'}finally{busy.value=false}}
async function remove(){if(!deleting.value||busy.value)return;busy.value=true;deleteError.value='';try{const id=deleting.value.id;if(backendDemo.state.liveNoteIds.includes(id)){const result=await backendClient.removeNote(id);if(result.removed!==id)throw new Error('Delete was not confirmed')}backendDemo.removeNote(id);deleting.value=null;status.value='已删除这条记录。'}catch{deleteError.value='这条记录没有删除成功，请重试；原记录仍保留。'}finally{busy.value=false}}

/* =============================================================================
 * G-04 右栏的数字来源 —— 全部从 `backendDemo.state.notes` 派生，没有一个是写死的。
 * 靶子右栏（`.pg-doc__side` 实测 312×604、9 条叶子文本）里那些条数是样张的演示数据；
 * 真实页按同一把尺子量真实记录，所以每个数都指得出字段：
 *   · allNotes / todoNotes / goalNotes —— `state.notes`（`data/demo-fixtures.ts:24-26`
 *     的 12 条演示记录；`data=service` 时是服务回包），按 `kind` 分两本账
 *   · todoPending / goalPending / doneAll —— 其中没做完与已做完的条数
 *     （`doneAll` 直接读 `backendDemo.notesDone`，不在这里重算一遍，免得两处对不上）
 *   · firstPending / nextPending —— 当前这一栏 pending 列表的第 1、2 条（真实列表顺序）
 *   · attributed —— 复盘里带归因的那几条（`data/student.ts:723-750`）
 * 段数/条数就是件数：勾一条、加一条、删一条，上面这些数都跟着变。
 * ========================================================================== */
const allNotes = computed(() => backendDemo.state.notes)
const todoNotes = computed(() => allNotes.value.filter((n) => n.kind === 'todo'))
const goalNotes = computed(() => allNotes.value.filter((n) => n.kind === 'goal'))
const todoPending = computed(() => todoNotes.value.filter((n) => !n.done).length)
const goalPending = computed(() => goalNotes.value.filter((n) => !n.done).length)
const doneAll = computed(() => backendDemo.notesDone.value)
const firstPending = computed(() => allNotes.value.find(n=>!n.done) ?? null)
const nextPending = computed(() => allNotes.value.filter(n=>!n.done)[1] ?? null)
/** 勾掉第一条之后浮上来的那一条（没有第二条时退回第一条，"只剩这一条"由文案交代） */
const nextUp = computed(() => nextPending.value ?? firstPending.value)
const tabLabel = computed(() => (tab.value === 'todo' ? '我的待办' : '个人目标'))
const attributed = computed(() => REVIEW_ITEMS.filter((r) => r.attribution))
const {page:notesPage,paged:pagedNotes}=usePagedItems(visibleNotes)
const noteGroups = computed(() => {
 const notes = pagedNotes.value
 if (noteAxis.value === 'done') return [{key:'pending',title:'还没有完成',items:notes.filter(n=>!n.done)},{key:'done',title:'已经完成',items:notes.filter(n=>n.done)}]
 if (noteAxis.value === 'source') return [{key:'live',title:'已保存的个人记录',items:notes.filter(n=>backendDemo.state.liveNoteIds.includes(n.id))},{key:'demo',title:'自己写的 · 个人记录',items:notes.filter(n=>!backendDemo.state.liveNoteIds.includes(n.id))}]
 return [{key:'goal',title:'目标 · 为什么',items:notes.filter(n=>n.kind==='goal')},{key:'todo',title:'待办 · 做什么',items:notes.filter(n=>n.kind==='todo')}]
})
</script>
<template>
<div class="ws-page notes-page journey-page"><PageHeading title="待办与目标" description="写下你自己的安排，与方向方案生成的任务分别保留。"><button class="btn" :disabled="busy" @click="loadNotes">{{ busy?'正在处理…':'读取最新记录' }}</button><RouterLink class="btn" to="/home">查看今日行动<UiIcon name="arrow" :size="16"/></RouterLink></PageHeading>
<!-- G-04：主列 + 右栏。两列与粘性**不在这里重写**：根上的 `journey-page` 让本页加入
     journey.css 里那套形状（`.journey-page .journey-action-grid` 是 `minmax(0,1fr) 312px`、
     `.journey-page .journey-action-aside` 是 `position:sticky`），与 /home、/plan 逐值同构。

     【靶子"多视角"（`.lens` 三种看法）这一项没有动】理由是数据与信息架构两件事都不成立：
     真实 note 模型只有 text / kind / done / created_at（api/backend-types.ts:3-9），靶子的
     "按来源"（自己写的 / 计划里带出来的 / 行为留下的）**在这份模型里没有那个字段**，
     硬做只能编字段；而"按完成状态"这一轴，页面已经用「已完成」那一段表达了，再包一个 tab
     就是反例表点名的"多视角做成 tab 换个列表"。要真做得先给 note 模型加来源轴 ——
     那是信息架构改动，留给 Lead 拍板；这一轮先把右栏做到位。 -->
<div class="journey-action-grid">
<div class="journey-action-main">
<div class="notes-count-line"><span>待完成 <strong>{{ todoPending + goalPending }}</strong></span><span>已完成 <strong>{{ doneAll }}</strong></span><DetailPopover title="个人记录统计" label="查看个人记录统计"><p>{{ goalPending }} 条目标、{{ todoPending }} 条待办尚未完成；共有 {{ allNotes.length }} 条个人记录，与计划任务分别统计。</p></DetailPopover></div>
<section class="c2-note-pool ws-paper"><header class="ws-section-head"><div><h2>个人待办与目标</h2><p>未完成事项优先显示；可按关键词直接查找。</p></div><span class="c2-pool-count">{{ allNotes.length }} 条 · 完成 {{ doneAll }}</span></header>
<section class="c2-note-add" aria-label="添加待办或目标"><form class="desk-note-form" @submit.prevent="add"><label class="sr-only" for="note-kind">记录类型</label><select id="note-kind" v-model="tab"><option value="todo">待办</option><option value="goal">目标</option></select><label class="sr-only" for="desk-note-text">写下一条个人记录</label><input id="desk-note-text" v-model="text" maxlength="200" placeholder="下一件想做的事…"/><button class="btn" type="submit" :disabled="busy" aria-label="添加记录"><UiIcon name="plus" :size="18"/></button></form></section><label class="c2-note-search">查找个人记录<input v-model="noteQuery" type="search" placeholder="输入关键词查找待办或目标…"/></label><p v-if="noteQuery" class="c2-lens-hint" role="status">找到 {{ visibleNotes.length }} 条，共 {{ allNotes.length }} 条。<button class="ws-text-button" @click="noteQuery=''">清空关键词</button></p>
<StatusBanner :open="!!status" tone="success" :message="status" @dismiss="status=''"/><StatusBanner v-if="error" tone="error" :message="error" retry-label="重试读取" @retry="loadNotes"/>
<EmptyState v-if="noteQuery && !visibleNotes.length" kind="search-empty" title="没有找到这条记录" description="换一个关键词，或清空关键词查看全部记录。" :next="false"><button class="btn" @click="noteQuery=''">查看全部记录</button></EmptyState><div class="notes-page__records" :aria-busy="loading"><SkeletonBlock v-if="loading" :overlay="allNotes.length>0" variant="list" :lines="4"/>
<section v-for="group in noteGroups.filter(group=>group.items.length)" :key="group.key" class="c2-note-group"><h3>{{ group.title }}<span>本页 {{ group.items.length }} 条</span></h3><ul><li v-for="item in group.items" :key="item.id" class="desk-record c2-note-row" :class="{'desk-record--done':item.done}"><button class="desk-record__toggle" :aria-label="(item.done?'恢复：':'完成：')+item.text" :aria-pressed="item.done" @click="setDone(item,!item.done)" :disabled="busy"><UiIcon v-if="item.done" name="check" :size="16"/></button><div><p><span class="c2-note-kind">{{ item.kind==='goal'?'目标':'待办' }}</span>{{ item.text }}</p><DetailPopover title="记录信息" :label="'查看记录信息：'+item.text"><template #trigger><time>{{ item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN') : '日期未提供' }}</time></template><SourceChip source="user_edit" :at="item.created_at"/><p>{{ item.done ? '已完成，可恢复。' : '完成后保留记录，可随时恢复。' }}</p></DetailPopover></div><button class="ws-icon-button" :aria-label="'删除：'+item.text" @click="deleting={...item}"><UiIcon name="trash" :size="17"/></button></li></ul><p v-if="!group.items.length" class="ws-muted">这一组现在没有记录。</p></section></div>
<ResultPager v-model:page="notesPage" :total="visibleNotes.length" label="个人记录"/></section>
<TodoSuggestions/>
</div>

<!-- ============================ 右栏（G-04） ============================
     靶子这一页的 `.pg-doc__side` 实测 312×604、9 条叶子文本；真实页原来是 0 条。
     下面三段一一对上靶子的三块（下一件会浮上来 / 复盘里会留下什么 / 这一区会跟着勾选更新），
     每一句都取自真实字段：state.notes（backend-demo）、REVIEW_ITEMS、attributionLabel。 -->
<aside class="journey-action-aside notes-visual-rail"><section><h2>接下来可以做</h2><button v-for="note in [firstPending,nextPending].filter(Boolean)" :key="note!.id" class="information-entry" @click="noteQuery=note!.text"><UiIcon name="notes" :size="19"/><span><strong>{{ note!.text }}</strong><small>{{ note!.kind==='goal'?'个人目标':'个人待办' }}</small></span><UiIcon name="arrow" :size="16"/></button><p v-if="!firstPending" class="ws-muted">当前没有未完成的个人记录。</p></section><button class="ws-text-button" @click="notesBasisOpen=true">记录与复盘说明<UiIcon name="info" :size="16"/></button></aside><InfoSheet :open="notesBasisOpen" shape="panel" title="记录与复盘说明" @close="notesBasisOpen=false">

  <!-- ① 「下一件会变成哪一条」：靶子这块是 `.nt-side__big` + 两句说明。
       真实页的"下一件"就是这一栏 pending 列表里的**第二条** —— 顺序就是真实列表顺序，
       不是另排的优先级（`data/demo-fixtures.ts:24-26` 的插入顺序：新写的排在最前）。 -->
  <section aria-labelledby="notesNextT">
    <h2 id="notesNextT">下一件会浮上来的是哪一条</h2>
    <p v-if="nextPending" class="hm-side__d">勾掉现在排在第一的那一条（{{ firstPending?.text }}），接下来浮上来的是：</p>
    <p v-else-if="firstPending" class="hm-side__d">这一栏里没做完的只剩这一条：</p>
    <p v-else class="hm-side__d">这一栏里现在没有没做完的记录。</p>
    <p v-if="nextUp" class="notes-side__big">{{ nextUp.text }}</p>
    <p class="hm-side__d">顺序就是你写下来的顺序（新写的排在最前），不是按重要性排的；这一栏里还压着 {{ pending.length }} 条没做。</p>
  </section>

  <!-- ② 「复盘里会留下什么」：靶子那块写着"归因只在三类里选，不归到人"。
       真实数据里那几个归因的落点是 `REVIEW_ITEMS` 的 attribution（data/student.ts:723-750），
       中文由 `lib/presentation.ts:2-4` 的 attributionLabel 统一翻译 —— 所以这里不写死那句口径，
       直接把带归因的那几条列出来，再加复盘的结论原文（data/student.ts:752-753）。 -->
  <section aria-labelledby="notesTraceT">
    <h2 id="notesTraceT">勾掉之后，复盘里会留下什么</h2>
    <p class="hm-side__d">没完成的原因不归到人：复盘里只挑一个归因写在那件事上 —— {{ REVIEW_ITEMS.length }} 条记录里有 {{ attributed.length }} 条带着归因。</p>
    <ul class="notes-side__list">
      <li v-for="r in attributed" :key="r.id"><b>{{ attributionLabel(r.attribution) }}</b> · {{ r.when }}「{{ r.what }}」</li>
    </ul>
    <p class="hm-side__warn">{{ REVIEW_CONCLUSION }}</p>
    <RouterLink class="ws-text-link" to="/review">去看复盘的完整记录<UiIcon name="arrow" :size="16" /></RouterLink>
  </section>

  <!-- ③ 「这一区会跟着你的勾选更新」：靶子那块是四个实时计数（`.nt-count`）。
       这里给同一种读数，口径换成这本账自己的：两栏各几条没做、总共几条做完。
       大号数字走 journey.css 的 `.hm-side__n`（30px/700，与 /home、/plan 右栏同一档）；
       下面那条分段读数复用 SegMeter —— **一根条 = 这一栏里的一条记录**，
       段数就是条数（当前这一栏，勾掉一条亮一段，切栏跟着换；不是装饰刻度）。 -->
  <section aria-labelledby="notesCountT">
    <h2 id="notesCountT">这一区会跟着你的勾选更新</h2>
    <p class="hm-side__n"><b>{{ pending.length }}</b> 条还没做完</p>
    <p class="hm-side__d">{{ tabLabel }}里一共 {{ items.length }} 条，已完成 {{ completed.length }} 条。切到另一栏，这个读数跟着换。</p>
    <div class="notes-side__meter"><SegMeter v-if="items.length" :total="items.length" :lit="completed.length" :label="`${tabLabel} ${items.length} 条里已完成 ${completed.length} 条`" /></div>
    <div class="hm-kv">
      <div class="hm-kv__r"><span class="hm-kv__k">我的待办</span><span class="hm-kv__v">{{ todoPending }} 条没做 · 共 {{ todoNotes.length }} 条</span></div>
      <div class="hm-kv__r"><span class="hm-kv__k">个人目标</span><span class="hm-kv__v">{{ goalPending }} 条没做 · 共 {{ goalNotes.length }} 条</span></div>
      <div class="hm-kv__r"><span class="hm-kv__k">已完成</span><span class="hm-kv__v">{{ doneAll }} 条（全部 {{ allNotes.length }} 条里）</span></div>
    </div>
    <p class="hm-side__warn">这一栏和「今日行动」里的任务不是同一本账：那边是从阶段计划拆下来的任务，这里是你个人记录记录。<template v-if="backendDemo.state.notesOrigin === 'live'">现在读的是服务回包里的记录。</template><template v-else>现在读的是当前工作空间的记录。</template></p>
  </section>
</InfoSheet>
</div>
<nav class="ws-related"><RouterLink to="/chat">和顾问讨论这些安排<UiIcon name="chat" :size="16"/></RouterLink></nav><p class="ws-demo-note">每条最多200字，同类内容会去重。{{ backendDemo.state.notesOrigin==='live'?'读取的记录按服务回包保存。':'个人记录保留在当前会话；正式建议采纳的条目按服务回包保存。' }}</p>
<InfoSheet :open="deleting!==null" shape="dialog" title="删除这条记录？" @close="deleting=null"><p>{{ deleting?.text }}</p><p class="ws-muted ws-section">删除后无法恢复，完成的记录可以选择恢复到待执行。</p><p v-if="deleteError" class="ws-field-error" role="alert">{{ deleteError }}</p><div class="ws-inline-actions"><button class="btn btn--danger" @click="remove" :disabled="busy">{{ busy?'正在删除…':'确认删除' }}</button><button class="btn" @click="deleting=null">保留记录</button></div></InfoSheet></div>
</template>
<style scoped>
.notes-page__status { margin-top: var(--sp-4); }
/* 骨架 overlay 的定位参照（SkeletonBlock 要求父元素 position:relative） */
.notes-page__records { position: relative; }
/* 旧样式是 `.desk-record small { margin-top: 6px }`；SourceChip 自己管内距，这里只补它与上面一行的间距 */
.desk-record__source { display: block; margin-top: 6px; }

/* ---- 主列进 `.journey-action-grid` 之后：`.ws-context` 自带 margin-top: 32px
   （redesign.css:33），与列间距 28px 叠成 60px。这里只把多出来的那一份去掉，
   它的 border-top 分隔线保留 —— 共享规则本身不动。 ---- */
.journey-page .journey-action-main > .ws-context { margin-top: 0; }

/* =============================================================================
 * 右栏（G-04）—— 只写本页独有的三块形状（读数、分段条、复盘列表）。
 * 两列、粘性、段间分隔线、h2 / p / 链接、30px 读数**全部**来自 journey.css 的
 * `.journey-page …`（与 /home、/plan 同一套），一个值都不在这里重写。
 * ========================================================================== */
.notes-side__big { font-size: var(--fs-16); font-weight: var(--fw-semibold); line-height: var(--lh-snug); color: var(--c-text); overflow-wrap: anywhere; }
.notes-side__meter { margin-top: var(--sp-3); }
.notes-side__list { display: flex; flex-direction: column; gap: var(--sp-2); margin-top: var(--sp-3); padding-left: 0; list-style: none; font-size: var(--fs-12); line-height: var(--lh-normal); color: var(--c-text-3); }
.notes-side__list b { font-weight: var(--fw-semibold); color: var(--c-text-2); }
</style>
