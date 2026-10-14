<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import PanelTabs from '../components/PanelTabs.vue'
import EmptyState from '../components/EmptyState.vue'
import TodoSuggestions from '../components/TodoSuggestions.vue'
import InfoSheet from '../components/InfoSheet.vue'
import Foldable from '../components/Foldable.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StatusBanner from '../components/StatusBanner.vue'
import SourceChip from '../components/SourceChip.vue'
import SegMeter from '../components/SegMeter.vue'
import { backendClient } from '../api/backend-client'
import { REVIEW_CONCLUSION, REVIEW_ITEMS } from '../data/student'
import { attributionLabel } from '../lib/presentation'
import type { NoteView } from '../api/backend-types'
const tab = ref<'todo'|'goal'>('todo'), drafts = ref({todo:'',goal:''}), error=ref(''), status=ref('')
const deleting=ref<NoteView|null>(null),busy=ref(false),deleteError=ref('')
/* 读取态与"忙"分开：busy 也覆盖添加/删除，用它画骨架会把"正在保存"错认成"还没读到" */
const loading=ref(false)
async function loadNotes(){if(busy.value)return;busy.value=true;loading.value=true;error.value='';try{const notes=await backendClient.notes();if(!Array.isArray(notes))throw new Error('Incomplete notes');backendDemo.setNotes(notes);status.value='已读取最新个人记录。'}catch{error.value='最新记录没有取得，请重试。现有条目和输入仍保留。'}finally{busy.value=false;loading.value=false}}
async function setDone(item: NoteView,done:boolean){if(busy.value)return;if(!backendDemo.state.liveNoteIds.includes(item.id)){backendDemo.setNoteDone(item.id,done);return}busy.value=true;error.value='';try{const result=await backendClient.noteDone(item.id,done);backendDemo.upsertNote(result);status.value='记录状态已保存。'}catch{error.value='记录状态没有保存成功，请重试。原状态仍保留。'}finally{busy.value=false}}
const text=computed({get:()=>drafts.value[tab.value],set:v=>drafts.value[tab.value]=v})
const items=computed(()=>backendDemo.state.notes.filter(n=>n.kind===tab.value))
const pending=computed(()=>items.value.filter(n=>!n.done)), completed=computed(()=>items.value.filter(n=>n.done))
async function add(){if(busy.value)return;try{if(!text.value.trim()||text.value.trim().length>200)throw new Error('请写下1–200个字。');if(items.value.some(n=>n.text===text.value.trim())){status.value='这条记录已存在，已保留原记录。';return}if(backendDemo.state.notesOrigin==='live'){busy.value=true;const note=await backendClient.addNote({kind:tab.value,text:text.value.trim()});backendDemo.upsertNote(note);status.value='已保存到个人记录。'}else{backendDemo.addNote(text.value,tab.value);status.value='已添加到当前演示。'}text.value='';error.value=''}catch{error.value='这条记录没有保存成功，请核对内容后重试。输入仍保留。'}finally{busy.value=false}}
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
const firstPending = computed(() => pending.value[0] ?? null)
const nextPending = computed(() => pending.value[1] ?? null)
/** 勾掉第一条之后浮上来的那一条（没有第二条时退回第一条，"只剩这一条"由文案交代） */
const nextUp = computed(() => nextPending.value ?? firstPending.value)
const tabLabel = computed(() => (tab.value === 'todo' ? '我的待办' : '个人目标'))
const attributed = computed(() => REVIEW_ITEMS.filter((r) => r.attribution))
</script>
<template>
<div class="ws-page notes-page journey-page"><PageHeading title="待办与目标" description="写下你自己的安排，与方向方案生成的任务分别保留。"><button class="btn" :disabled="busy" @click="loadNotes">{{ busy?'正在处理…':'读取最新记录' }}</button><RouterLink class="btn" to="/home">去行动计划<UiIcon name="arrow" :size="16"/></RouterLink></PageHeading>
<!-- G-04：主列 + 右栏。两列与粘性**不在这里重写**：根上的 `journey-page` 让本页加入
     journey.css 里那套形状（`.journey-page .journey-action-grid` 是 `minmax(0,1fr) 312px`、
     `.journey-page .journey-action-aside` 是 `position:sticky`），与 /home、/plan 逐值同构。

     【靶子"多视角"（`.lens` 三种看法）这一项没有动】理由是数据与信息架构两件事都不成立：
     真实 note 模型只有 text / kind / done / created_at（api/backend-types.ts:3-9），靶子的
     "按它怎么来的"（自己写的 / 计划里带出来的 / 行为留下的）**在这份模型里没有那个字段**，
     硬做只能编字段；而"按做没做完"这一轴，页面已经用「已完成」那一段表达了，再包一个 tab
     就是反例表点名的"多视角做成 tab 换个列表"。要真做得先给 note 模型加来源轴 ——
     那是信息架构改动，留给 Lead 拍板；这一轮先把右栏做到位。 -->
<div class="journey-action-grid">
<div class="journey-action-main">
 <section class="c2-profile-stats" aria-label="待办与目标概览"><article class="c2-profile-stat"><strong>{{ goalPending }}</strong><small>条</small><h2>目标在走</h2><p>你自己写下的个人目标</p></article><article class="c2-profile-stat"><strong>{{ todoPending }}</strong><small>条</small><h2>待办没做</h2><p>下一步可以动手的具体事项</p></article><article class="c2-profile-stat"><strong>{{ doneAll }}</strong><small>条</small><h2>已经完成</h2><p>完成后可恢复，也会保留记录</p></article><article class="c2-profile-stat"><strong>{{ allNotes.length }}</strong><small>条</small><h2>自己写下的</h2><p>个人记录独立保留，不与计划任务混算</p></article></section>
<PanelTabs :model-value="tab" @update:model-value="tab=$event as 'todo'|'goal';status='';error=''" label="待办与目标视图" :items="[{key:'todo',label:'我的待办',count:backendDemo.state.notes.filter(n=>n.kind==='todo').length},{key:'goal',label:'个人目标',count:backendDemo.state.notes.filter(n=>n.kind==='goal').length}]">
<form class="desk-note-form" @submit.prevent="add"><label class="sr-only" for="desk-note-text">{{ tab==='todo'?'写下一件事':'写下一个目标' }}</label><input id="desk-note-text" v-model="text" maxlength="200" :placeholder="tab==='todo'?'下一件想做的事…':'你想达成什么…'"/><button class="btn btn--primary" type="submit"><UiIcon name="plus" :size="16"/>添加</button></form><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p>
<!-- 成功反馈换成 StatusBanner：旧写法是 `v-if="status"` 常驻不消失（审计 D9 点名的病灶），
     success 由组件在 4s 后自动收起，也可以手动关。 -->
<StatusBanner class="notes-page__status" tone="success" :message="status" :open="!!status" @dismiss="status=''"/>
<!-- 加载态与"真的没有待办"分开（MIGRATION §4.1 K2：v-if="pending.length" 让两者长得一样）。
     有内容时用 overlay 盖在仍在 DOM 的记录上：刷新不该让已有记录先消失再重建。 -->
<div class="notes-page__records" :aria-busy="loading">
<SkeletonBlock v-if="loading" :overlay="items.length > 0" variant="list" :lines="4"/>
<ul v-if="pending.length"><li v-for="item in pending" :key="item.id" class="desk-record"><button class="desk-record__toggle" :aria-label="'完成：'+item.text" :aria-pressed="false" @click="setDone(item,true)" :disabled="busy"><UiIcon name="check" :size="16"/></button><div><p>{{ item.text }}</p><!-- 来源与时间原来是 12px 灰字；换成 SourceChip（来源默认可见，DESIGN-LANGUAGE §4.3） --><span class="desk-record__source"><SourceChip source="user_edit" :at="item.created_at"/></span></div><button class="ws-icon-button" :aria-label="'删除：'+item.text" @click="deleting={...item}"><UiIcon name="trash" :size="17"/></button></li></ul><EmptyState v-else kind="notes" :title="completed.length?'当前记录都已完成':tab==='todo'?'暂无个人待办':'暂无个人目标'" description="在上方写下新的安排，已经完成的记录仍可恢复。"/>
<!-- 已完成：`.ws-context` → Foldable。计数由组件内建徽标承载，且默认展开 ——
     这是全页唯一能"看到完成时"的地方，不该藏在一次点击后面（MIGRATION §1.3 A1 / §1.4）。 -->
<Foldable v-if="completed.length" variant="section" :count="completed.length" :default-open="true" title="已完成"><ul><li v-for="item in completed" :key="item.id" class="desk-record desk-record--done"><button class="desk-record__toggle" :aria-label="'恢复：'+item.text" :aria-pressed="true" @click="setDone(item,false)" :disabled="busy"><UiIcon name="check" :size="16"/></button><div><p>{{ item.text }}</p><span class="desk-record__source"><SourceChip source="user_edit" :at="item.created_at"/></span></div><button class="ws-icon-button" :aria-label="'删除：'+item.text" @click="deleting={...item}"><UiIcon name="trash" :size="17"/></button></li></ul></Foldable></div></PanelTabs>
<TodoSuggestions/>
</div>

<!-- ============================ 右栏（G-04） ============================
     靶子这一页的 `.pg-doc__side` 实测 312×604、9 条叶子文本；真实页原来是 0 条。
     下面三段一一对上靶子的三块（下一件会浮上来 / 复盘里会留下什么 / 这一区会跟着勾选更新），
     每一句都取自真实字段：state.notes（backend-demo）、REVIEW_ITEMS、attributionLabel。 -->
<aside class="journey-action-aside">

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
    <p class="hm-side__warn">这一栏和「今日行动」里的任务不是同一本账：那边是从阶段计划拆下来的任务，这里是你自己写下的记录。<template v-if="backendDemo.state.notesOrigin === 'live'">现在读的是服务回包里的记录。</template><template v-else>现在读的是本次演示里的记录。</template></p>
  </section>
</aside>
</div>
<nav class="ws-related"><RouterLink to="/chat">和顾问讨论这些安排<UiIcon name="chat" :size="16"/></RouterLink></nav><p class="ws-demo-note">每条最多200字，同类内容会去重。{{ backendDemo.state.notesOrigin==='live'?'读取的记录按服务回包保存。':'演示记录只保留在本次会话；正式建议采纳的条目按服务回包保存。' }}</p>
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
