<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import PanelTabs from '../components/PanelTabs.vue'
import EmptyState from '../components/EmptyState.vue'
import TodoSuggestions from '../components/TodoSuggestions.vue'
import InfoSheet from '../components/InfoSheet.vue'
import { backendClient } from '../api/backend-client'
import type { NoteView } from '../api/backend-types'
const tab = ref<'todo'|'goal'>('todo'), drafts = ref({todo:'',goal:''}), error=ref(''), status=ref('')
const deleting=ref<NoteView|null>(null),busy=ref(false),deleteError=ref('')
async function loadNotes(){if(busy.value)return;busy.value=true;error.value='';try{const notes=await backendClient.notes();if(!Array.isArray(notes))throw new Error('Incomplete notes');backendDemo.setNotes(notes);status.value='已读取最新个人记录。'}catch{error.value='最新记录没有取得，请重试。现有条目和输入仍保留。'}finally{busy.value=false}}
async function setDone(item: NoteView,done:boolean){if(busy.value)return;if(!backendDemo.state.liveNoteIds.includes(item.id)){backendDemo.setNoteDone(item.id,done);return}busy.value=true;error.value='';try{const result=await backendClient.noteDone(item.id,done);backendDemo.upsertNote(result);status.value='记录状态已保存。'}catch{error.value='记录状态没有保存成功，请重试。原状态仍保留。'}finally{busy.value=false}}
const text=computed({get:()=>drafts.value[tab.value],set:v=>drafts.value[tab.value]=v})
const items=computed(()=>backendDemo.state.notes.filter(n=>n.kind===tab.value))
const pending=computed(()=>items.value.filter(n=>!n.done)), completed=computed(()=>items.value.filter(n=>n.done))
async function add(){if(busy.value)return;try{if(!text.value.trim()||text.value.trim().length>200)throw new Error('请写下1–200个字。');if(items.value.some(n=>n.text===text.value.trim())){status.value='这条记录已存在，已保留原记录。';return}if(backendDemo.state.notesOrigin==='live'){busy.value=true;const note=await backendClient.addNote({kind:tab.value,text:text.value.trim()});backendDemo.upsertNote(note);status.value='已保存到个人记录。'}else{backendDemo.addNote(text.value,tab.value);status.value='已添加到当前演示。'}text.value='';error.value=''}catch{error.value='这条记录没有保存成功，请核对内容后重试。输入仍保留。'}finally{busy.value=false}}
async function remove(){if(!deleting.value||busy.value)return;busy.value=true;deleteError.value='';try{const id=deleting.value.id;if(backendDemo.state.liveNoteIds.includes(id)){const result=await backendClient.removeNote(id);if(result.removed!==id)throw new Error('Delete was not confirmed')}backendDemo.removeNote(id);deleting.value=null;status.value='已删除这条记录。'}catch{deleteError.value='这条记录没有删除成功，请重试；原记录仍保留。'}finally{busy.value=false}}
</script>
<template>
<div class="ws-page notes-page"><PageHeading title="待办与目标" description="写下你自己的安排，与方向方案生成的任务分别保留。"><button class="btn" :disabled="busy" @click="loadNotes">{{ busy?'正在处理…':'读取最新记录' }}</button><RouterLink class="btn" to="/home">去行动计划<UiIcon name="arrow" :size="16"/></RouterLink></PageHeading>
<PanelTabs :model-value="tab" @update:model-value="tab=$event as 'todo'|'goal';status='';error=''" label="待办与目标视图" :items="[{key:'todo',label:'我的待办',count:backendDemo.state.notes.filter(n=>n.kind==='todo').length},{key:'goal',label:'个人目标',count:backendDemo.state.notes.filter(n=>n.kind==='goal').length}]">
<form class="desk-note-form" @submit.prevent="add"><label class="sr-only" for="desk-note-text">{{ tab==='todo'?'写下一件事':'写下一个目标' }}</label><input id="desk-note-text" v-model="text" maxlength="200" :placeholder="tab==='todo'?'下一件想做的事…':'你想达成什么…'"/><button class="btn btn--primary" type="submit"><UiIcon name="plus" :size="16"/>添加</button></form><p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><p v-if="status" class="desk-status" role="status">{{ status }}</p>
<ul v-if="pending.length"><li v-for="item in pending" :key="item.id" class="desk-record"><button class="desk-record__toggle" :aria-label="'完成：'+item.text" :aria-pressed="false" @click="setDone(item,true)" :disabled="busy"><UiIcon name="check" :size="16"/></button><div><p>{{ item.text }}</p><small>个人创建 · {{ new Date(item.created_at).toLocaleDateString('zh-CN') }}</small></div><button class="ws-icon-button" :aria-label="'删除：'+item.text" @click="deleting={...item}"><UiIcon name="trash" :size="17"/></button></li></ul><EmptyState v-else kind="notes" :title="completed.length?'当前记录都已完成':tab==='todo'?'暂无个人待办':'暂无个人目标'" description="在上方写下新的安排，已经完成的记录仍可恢复。"/>
<details v-if="completed.length" class="ws-context"><summary>已完成 · {{ completed.length }} 条<UiIcon name="chevron" :size="16"/></summary><ul><li v-for="item in completed" :key="item.id" class="desk-record desk-record--done"><button class="desk-record__toggle" :aria-label="'恢复：'+item.text" :aria-pressed="true" @click="setDone(item,false)" :disabled="busy"><UiIcon name="check" :size="16"/></button><div><p>{{ item.text }}</p><small>已完成，可以恢复</small></div><button class="ws-icon-button" :aria-label="'删除：'+item.text" @click="deleting={...item}"><UiIcon name="trash" :size="17"/></button></li></ul></details></PanelTabs>
<TodoSuggestions/><nav class="ws-related"><RouterLink to="/chat">和顾问讨论这些安排<UiIcon name="chat" :size="16"/></RouterLink></nav><p class="ws-demo-note">每条最多200字，同类内容会去重。{{ backendDemo.state.notesOrigin==='live'?'读取的记录按服务回包保存。':'演示记录只保留在本次会话；正式建议采纳的条目按服务回包保存。' }}</p>
<InfoSheet :open="deleting!==null" title="删除这条记录？" @close="deleting=null"><p>{{ deleting?.text }}</p><p class="ws-muted ws-section">删除后无法恢复，完成的记录可以选择恢复到待执行。</p><p v-if="deleteError" class="ws-field-error" role="alert">{{ deleteError }}</p><div class="ws-inline-actions"><button class="btn btn--danger" @click="remove" :disabled="busy">{{ busy?'正在删除…':'确认删除' }}</button><button class="btn" @click="deleting=null">保留记录</button></div></InfoSheet></div>
</template>
