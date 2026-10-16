<script setup lang="ts">
import { ref } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import type { TodoSuggestion } from '../api/ai-types'
import { backendClient } from '../api/backend-client'
import { backendDemo } from '../lib/backend-demo'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
const task=useAiTask<TodoSuggestion[]>(), decisions=ref<Record<string,string>>({}),saving=ref(''),error=ref('')
async function accept(item: TodoSuggestion){if(saving.value)return;saving.value=item.id;error.value='';try{const note=await backendClient.addNote({kind:'todo',text:item.label});backendDemo.upsertNote(note);decisions.value[item.id]='已添加为个人待办'}catch{error.value='这条建议没有保存成功，请重试；原记录仍保留。'}finally{saving.value=''}}
</script>
<template>
  <section class="notes-suggestions" aria-labelledby="notesSuggestionsTitle">
    <header>
      <div>
        <h2 id="notesSuggestionsTitle">需要补充思路时</h2>
        <p>根据现有资料生成待办建议；只有采纳后，建议才会写入个人待办。</p>
      </div>
      <button class="btn" type="button" :disabled="task.busy.value || !!saving" @click="task.run('noteSuggestions')">
        {{ task.result.value ? '更新建议' : '生成建议' }}
      </button>
    </header>
    <AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="task.run('noteSuggestions')" />
    <p v-if="error" class="ws-field-error" role="alert">{{ error }}</p>
    <div v-if="task.result.value" class="notes-suggestions__list">
      <article v-for="item in task.result.value.data" :key="item.id" class="notes-suggestion">
        <div>
          <h3>{{ item.label }}</h3>
          <p>{{ item.why }}</p>
          <small>{{ item.from }} · {{ item.when }}</small>
        </div>
        <p v-if="decisions[item.id]" class="notes-suggestion__status" role="status">{{ decisions[item.id] }}</p>
        <div v-else class="notes-suggestion__actions">
          <button class="btn" type="button" :disabled="!!saving" @click="accept(item)">{{ saving === item.id ? '正在保存…' : '采纳为待办' }}</button>
          <button class="ws-text-button" type="button" :disabled="!!saving" @click="decisions[item.id] = '本次不采用，个人记录没有改变'">暂不采用</button>
        </div>
      </article>
      <p v-if="!task.result.value.data.length" class="ws-empty">当前没有待办建议。</p>
      <AiResultMeta :result="task.result.value" />
    </div>
  </section>
</template>

<style scoped>
.notes-suggestions { padding: 18px 20px; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); }
.notes-suggestions > header { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.notes-suggestions h2 { font-size: var(--fs-14); font-weight: var(--fw-semibold); }
.notes-suggestions header p { margin-top: 4px; color: var(--c-text-3); font-size: var(--fs-12); line-height: 1.7; }
.notes-suggestions > header .btn { min-height: 40px; flex: none; }
.notes-suggestions :deep(.ai-status) { margin-top: 14px; }
.notes-suggestions__list { margin-top: 14px; border-top: 1px solid var(--c-border); }
.notes-suggestion { display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: center; gap: 10px 18px; padding: 14px 0; border-bottom: 1px solid var(--c-border); }
.notes-suggestion h3 { color: var(--c-text); font-size: var(--fs-14); font-weight: var(--fw-semibold); }
.notes-suggestion p { margin-top: 4px; color: var(--c-text-2); font-size: var(--fs-12); line-height: 1.7; }
.notes-suggestion small { display: block; margin-top: 5px; color: var(--c-text-3); font-size: var(--fs-11); }
.notes-suggestion__actions { display: flex; align-items: center; gap: 10px; }
.notes-suggestion__status { color: var(--c-primary) !important; }

@media (max-width: 767px) {
  .notes-suggestions { padding: 16px 14px; }
  .notes-suggestions > header { align-items: flex-start; }
  .notes-suggestions > header .btn { min-height: 44px; }
  .notes-suggestion { grid-template-columns: minmax(0,1fr); }
  .notes-suggestion__actions { justify-content: flex-start; }
}
</style>
