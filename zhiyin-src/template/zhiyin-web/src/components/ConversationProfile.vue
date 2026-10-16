<script setup lang="ts">
import { computed } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { profileLabel } from '../lib/server-copy'
import { PROFILE_TOPICS, profilePriority } from '../lib/profile-organization'
import DetailPopover from './DetailPopover.vue'
import UiIcon from './UiIcon.vue'
defineProps<{ loading?: boolean; error?: string; embedded?: boolean }>()
defineEmits<{ refresh: []; close: []; supplement: [text: string] }>()
const profile = computed(() => backendDemo.state.liveWorkspace?.profile_panel)
const fields = computed(() => [...(profile.value?.fields ?? [])].sort((a,b) => profilePriority(a.key) - profilePriority(b.key)))
const groups = computed(() => {
  const grouped = new Set<string>()
  const sections = PROFILE_TOPICS.map(topic => {
    const items = fields.value.filter(field => topic.keys.includes(field.key))
    items.forEach(field => grouped.add(field.key))
    return { key:topic.key, title:topic.title, items }
  }).filter(section => section.items.length)
  const other = fields.value.filter(field => !grouped.has(field.key))
  return other.length ? [...sections, { key:'other', title:'其他信息', items:other }] : sections
})
const sources: Record<string,string> = { conversation:'咨询对话',resume:'简历材料',assessment:'测评',behavior_inference:'行为分析',mentor:'导师记录',record:'导入资料',user_edit:'本人填写' }
function valueText(value: unknown): string {
  if (value == null || value === '') return '尚未填写'
  if (Array.isArray(value)) return value.map(valueText).join('、')
  if (typeof value === 'object') return Object.entries(value).map(([k,v]) => `${k}：${valueText(v)}`).join('；')
  return String(value)
}
</script>
<template>
  <section class="consult-profile" aria-label="当前个人画像">
    <header v-if="!embedded"><div><h2>对你的了解</h2><p>{{ fields.length ? `已记录 ${fields.length} 项信息` : '随咨询逐步完善' }}</p></div><button class="consult-icon" aria-label="收起个人画像" @click="$emit('close')"><UiIcon name="sidebar" :size="19" /></button></header>
    <div class="consult-profile__scroll">
      <p v-if="embedded && fields.length" class="consult-profile__summary">已记录 {{ fields.length }} 项信息，按用途归在下面几组。</p>
      <p v-if="loading" role="status" class="consult-muted">正在更新资料…</p>
      <p v-if="error" role="alert" class="consult-error">{{ error }} <button @click="$emit('refresh')">重新读取</button></p>
      <p v-if="!fields.length && !loading" class="consult-empty">尚未收集到个人信息。可以从兴趣、经历或当前目标开始交流。</p>
      <section v-for="group in groups" :key="group.key" class="consult-profile__group">
        <h3>{{ group.title }}<small>{{ group.items.length }}</small></h3>
        <dl><div v-for="field in group.items" :key="field.key" class="consult-profile__field">
          <dt>{{ profileLabel(field.key, field.label || field.key) }}<DetailPopover :title="profileLabel(field.key, field.label || field.key) + ' · 信息来源'" side="left"><template #trigger><UiIcon name="info" :size="15" /></template><p>来源：{{ sources[field.source] || field.source }}</p><p v-for="(e,i) in field.evidence" :key="i">{{ e }}</p><p v-if="!field.evidence?.length">暂无详细依据。</p><RouterLink to="/profile" @click="$emit('close')">查看或更正资料</RouterLink></DetailPopover></dt>
          <dd>{{ valueText(field.value) }}</dd>
        </div></dl>
      </section>
      <section v-if="profile?.gaps?.length" class="consult-profile__gaps"><h3>还可以补充</h3><button v-for="gap in profile.gaps" :key="gap.key" @click="$emit('supplement', '我想补充' + (gap.label || profileLabel(gap.key, gap.key)) + '：')"><span>{{ gap.label || profileLabel(gap.key, gap.key) }}</span><UiIcon name="plus" :size="15" /></button></section>
    </div>
    <footer><RouterLink to="/profile" @click="$emit('close')">查看完整画像<UiIcon name="arrow" :size="16" /></RouterLink><small>仅展示系统已记录的信息</small></footer>
  </section>
</template>
