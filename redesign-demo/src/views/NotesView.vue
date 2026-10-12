<script setup lang="ts">
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
const tab = ref<'todo' | 'goal'>('todo')
const text = ref('')
const error = ref('')
const status = ref('')
const items = computed(() => backendDemo.state.notes.filter(n => n.kind === tab.value))
function add() {
  try { backendDemo.addNote(text.value, tab.value); text.value = ''; error.value = ''; status.value = '已添加到当前演示。' }
  catch (e) { error.value = (e as Error).message }
}
</script>
<template>
  <div class="ws-page">
    <PageHeading title="待办与目标" description="管理个人待办与目标，与方案生成的任务分别保存。"><RouterLink class="btn" to="/home">去行动计划<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-tabs" aria-label="待办与目标视图"><button :aria-pressed="tab === 'todo'" @click="tab = 'todo'; status = ''">我的待办</button><button :aria-pressed="tab === 'goal'" @click="tab = 'goal'; status = ''">个人目标</button></div>
        <form class="desk-note-form" @submit.prevent="add"><label class="sr-only" for="desk-note-text">{{ tab === 'todo' ? '写下一件事' : '写下一个目标' }}</label><input id="desk-note-text" v-model="text" maxlength="200" :placeholder="tab === 'todo' ? '输入个人待办…' : '输入个人目标…'" /><button class="btn btn--primary" type="submit"><UiIcon name="plus" :size="16" />添加</button></form>
        <p v-if="error" class="ws-field-error" role="alert">{{ error }}</p><p v-if="status" class="ws-muted" role="status">{{ status }}</p>
        <ul v-if="items.length"><li v-for="item in items" :key="item.id" class="desk-record" :class="{ 'desk-record--done': item.done }"><button class="desk-record__toggle" :aria-label="(item.done ? '恢复：' : '完成：') + item.text" :aria-pressed="!!item.done" @click="backendDemo.setNoteDone(item.id, !item.done)"><UiIcon v-if="item.done" name="check" :size="16" /></button><div><p>{{ item.text }}</p><small>{{ item.done ? '已完成，可恢复' : '个人创建' }} · {{ new Date(item.created_at).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' }) }}</small></div><button class="ws-icon-button desk-record__delete" :aria-label="'删除：' + item.text" @click="backendDemo.removeNote(item.id); status = '已从当前演示中移除。'"><UiIcon name="trash" :size="17" /></button></li></ul>
        <div v-else class="ws-empty"><UiIcon name="notes" :size="40" /><h2 class="ws-section-title" style="margin-top: var(--sp-4)">{{ tab === 'todo' ? '暂无个人待办' : '暂无个人目标' }}</h2><p>通过上方输入框添加内容，可在咨询中进一步讨论。</p></div>
      </section>
      <aside class="ws-aside"><section><h2>个人记录</h2><p>保留个人原始表述，为咨询提供补充依据。</p><RouterLink class="ws-text-link" to="/chat">讨论待办与目标<UiIcon name="arrow" :size="16" /></RouterLink></section><section><h2>与行动计划的区别</h2><p>行动计划来自已经形成的方案；待办与目标保留个人原始记录。</p></section><section><p>最多 200 个字。同一类内容重复提交时，会保留已有的一条。</p></section></aside>
    </div>
    <p class="ws-demo-note">演示中的记录保留在当前页面会话；正式数据使用后端的待办与目标接口。</p>
  </div>
</template>
