<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { COLLECT_ITEMS, PROFILE_FIELDS, STUDENT } from '../data/student'
import type { ProfileField } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'

import EmptyState from '../components/EmptyState.vue'
import ProfileInsights from '../components/ProfileInsights.vue'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import type { ProfileFieldView } from '../api/backend-types'
const loading = ref(false), serviceError = ref('')
const live = computed(() => backendDemo.state.liveWorkspace?.profile_panel)
const originalLive = computed(() => backendDemo.state.profileOriginals)
const sourceNames: Record<string, ProfileField['source']> = {resume:'简历材料',conversation:'对话',assessment:'综合分析',behavior_inference:'行为记录',mentor:'导师记录',record:'学校',user_edit:'本人填写'}
function human(value: unknown): string { if (value == null) return '尚待补充'; if (Array.isArray(value)) return value.map(human).join('、'); if(typeof value==='object')return Object.values(value).map(human).join('；');return String(value) }
async function loadWorkspace(){ if(loading.value)return; loading.value=true;serviceError.value='';try{const data=await backendClient.workspace();if(!data?.profile_panel)throw new Error('Incomplete profile');backendDemo.setWorkspace(data)}catch{serviceError.value='最新档案暂时没有取得，请重试。现有内容仍保留。'}finally{loading.value=false} }
const insights = ref<InstanceType<typeof ProfileInsights> | null>(null)
const progress = computed(() => live.value ? {known:live.value.fields?.length??0,total:(live.value.fields?.length??0)+(live.value.gaps?.length??0),gap:live.value.gaps?.length??0} : demo.use.profileProgress.value)
const known = computed<ProfileField[]>(() => live.value ? (live.value.fields??[]).map(f=>({key:f.key,label:f.label??f.key,value:human(f.value),source:sourceNames[f.source]??'学校',noted:new Date(f.updated_at).toLocaleString('zh-CN'),confidence:{label:f.confidence===undefined?'待确认':f.confidence>=.8?'比较确定':f.confidence>=.5?'还要核对':'待确认',level:f.confidence!==undefined&&f.confidence>=.8?'high':'mid',bars:f.confidence===undefined?0:Math.round(f.confidence*3)}})) : PROFILE_FIELDS.slice(0, progress.value.known))
const missing = computed(() => live.value ? (live.value.gaps??[]).map(g=>({key:g.key,label:g.label??g.key})) : PROFILE_FIELDS.slice(progress.value.known))
const filter = ref('all')
const filters = [
  { key: 'all', label: '全部信息', sources: [] },
  { key: 'school', label: '学校档案', sources: ['学信网', '教务系统', '学校'] },
  { key: 'talk', label: '咨询记录', sources: ['对话'] },
  { key: 'material', label: '材料与分析', sources: ['简历材料','综合分析','导师记录'] },
  { key: 'behavior', label: '行为记录', sources: ['行为记录'] },
  { key: 'user', label: '本人填写', sources: ['本人填写'] },
]
const visible = computed(() => {
  const f = filters.find((item) => item.key === filter.value)!
  return filter.value === 'all' ? known.value : known.value.filter((item) => f.sources.includes(fieldSource(item)))
})
const correction = ref<ProfileField | null>(null)
const value = ref('')
const correctionError = ref('')
function fieldValue(f: ProfileField) {
  if(live.value)return f.value
  return demo.state.profileEdits[f.key] ?? (f.key === 'grade' ? demo.use.scenario.value.grade + '（在读）' : f.value)
}
function edit(f: ProfileField) {
  correction.value = f; value.value = fieldValue(f); correctionError.value = ''
}
async function save() {
  if (!value.value.trim()) { correctionError.value = '请填写更正后的信息。'; return }
  if (value.value.trim().length > 40) { correctionError.value = '更正内容最多 40 个字。'; return }
  if (correction.value && live.value) {
    const field=correction.value;const previous=backendDemo.state.liveWorkspace?.profile_panel?.fields?.find(f=>f.key===field.key)
    serviceError.value='';try{const updated=await backendClient.correct(field.key,value.value.trim());if(previous&&!originalLive.value[field.key])backendDemo.rememberProfileOriginal(field.key);const workspace=JSON.parse(JSON.stringify(backendDemo.state.liveWorkspace));workspace.profile_panel.fields=workspace.profile_panel.fields.map((f:ProfileFieldView)=>f.key===updated.key?updated:f);backendDemo.setWorkspace(workspace)}catch{correctionError.value='更正没有保存成功，输入仍保留，请重试。';return}
  }
  if (correction.value) demo.updateProfileField(correction.value.key, value.value)
  correction.value = null
}
function originalSource(f: ProfileField) { return sourceNames[originalLive.value[f.key]?.source ?? ''] ?? f.source }
function edited(f: ProfileField) { return live.value ? f.source==='本人填写' : !!demo.state.profileEdits[f.key] }
function fieldSource(f: ProfileField) { return !live.value&&demo.state.profileEdits[f.key] ? '本人填写' : f.source }
const topics = [
  { title: '学习与经历', keys: ['major', 'grade', 'rank', 'award', 'internship'] },
  { title: '兴趣与能力', keys: ['interest', 'style', 'weakness'] },
  { title: '条件与期待', keys: ['family', 'city', 'jobtype', 'salary'] },
  { title: '行动与时间', keys: ['pipeline', 'time', 'schedule'] },
]
const allTopics = computed(() => [...topics, { title:'其他已记录信息', keys:known.value.filter(f=>!topics.some(t=>t.keys.includes(f.key))).map(f=>f.key).concat(missing.value.filter(f=>!topics.some(t=>t.keys.includes(f.key))).map(f=>f.key)) }])
const groups = computed(() => allTopics.value.map(t => ({ ...t, fields: visible.value.filter(f => t.keys.includes(f.key)), missing: missing.value.filter(f => t.keys.includes(f.key)) })).filter(t => t.fields.length || (filter.value === 'all' && t.missing.length)))
</script>
<template>
  <div class="ws-page profile-page">
    <PageHeading title="个人画像" description="按主题整理你的信息，判断和来源都可以核对。"><button class="btn" :disabled="loading" @click="loadWorkspace">{{ loading ? '正在读取…' : '读取最新档案' }}</button><RouterLink class="btn btn--primary" to="/chat">{{ progress.gap ? '补充信息' : '更新信息' }}<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <p v-if="serviceError" class="ws-field-error" role="alert">{{ serviceError }}</p><section class="profile-summary"><div><h2>{{ live ? known.find(f=>f.key==='name')?.value || '个人档案' : demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</h2><p>{{ live ? [known.find(f=>f.key==='school')?.value,known.find(f=>f.key==='grade')?.value].filter(Boolean).join(' · ') || '学校与年级待补充' : demo.state.account === 'fresh' ? '学校与年级待补充' : (demo.state.profileEdits.school ?? STUDENT.school) + ' · ' + (demo.state.profileEdits.grade ?? demo.use.scenario.value.grade) }}</p></div><p class="profile-summary__status">已有 {{ progress.known }} / {{ progress.total }} 条信息<span v-if="progress.gap"> · {{ progress.gap }} 条待补充</span></p></section>
    <ProfileInsights ref="insights"/><div class="profile-toolbar"><h2>主题档案</h2><label>信息来源<select v-model="filter" aria-label="信息来源"><option v-for="f in filters" :key="f.key" :value="f.key">{{ f.label }}</option></select></label></div>
    <div class="profile-topics" v-if="groups.length"><section v-for="g in groups" :key="g.title" class="profile-topic"><h3>{{ g.title }}</h3><div class="ws-evidence"><details v-for="f in g.fields" :key="f.key" class="ws-evidence__row"><summary><span class="ws-evidence__label">{{ f.label }}</span><span class="ws-evidence__value">{{ fieldValue(f) }}</span><UiIcon name="chevron" :size="18" /></summary><div class="ws-evidence__explain"><p>当前来源：{{ fieldSource(f) }} · {{ edited(f) ? '本人确认' : f.confidence.label }}</p><p>原始依据：{{ originalSource(f) }} · {{ originalLive[f.key]?.updated_at ?? f.noted }}</p><ul v-if="live" class="ws-mini-list"><li v-for="e in (originalLive[f.key]?.evidence ?? live.fields?.find(item=>item.key===f.key)?.evidence ?? [])" :key="e">{{ e }}</li></ul><p v-if="edited(f)">本人更正于 {{ live ? f.noted : demo.state.profileEditTimes[f.key] }}</p><button class="ws-text-button" @click="insights?.inspect(f.key,f.label)">深入了解这项信息</button><button class="ws-text-button" @click="edit(f)">更正信息<UiIcon name="arrow" :size="14" /></button></div></details></div><ul v-if="filter === 'all' && g.missing.length" class="profile-gaps"><li v-for="f in g.missing" :key="f.key"><span>{{ f.label }}<small>待补充</small></span><button class="ws-text-button" @click="insights?.inspect(f.key,f.label,true)">看看需要补充什么</button><RouterLink class="ws-text-link" :to="'/chat?gap=' + f.key">补充{{ f.label }}<UiIcon name="arrow" :size="14" /></RouterLink></li></ul></section></div>
    <EmptyState v-else :title="known.length ? '暂无此类记录' : '暂无个人信息'" description="可以从一次咨询开始，也可以导入已有的学校资料。"><RouterLink class="btn" to="/chat">开始咨询</RouterLink></EmptyState>
    <details class="ws-context"><summary>资料来源与核验说明<UiIcon name="chevron" :size="16" /></summary><div class="ws-context__body"><section><h3>可获取的信息</h3><ul class="ws-mini-list"><li v-for="c in COLLECT_ITEMS" :key="c.label"><strong>{{ c.label }}</strong><p>{{ c.fetchable ? '来自' + c.from : c.blockedBy }}</p></li></ul></section><section><h3>学校资料</h3><p>学籍核验只需在线验证码，不需要账号密码。课表来自教务资料，空课时段不直接代表可用时间。</p><RouterLink class="ws-text-link" to="/academic">管理学籍与资料<UiIcon name="arrow" :size="16" /></RouterLink></section></div></details>
    <p class="ws-demo-note">{{ live ? '字段与缺口来自本次读取的档案；更正按服务回包保存。' : '预置人物与来源仅作演示；更正保留在本次演示会话。' }}</p>
    <InfoSheet :open="correction !== null" :title="'更正' + (correction?.label ?? '信息')" @close="correction = null"><form @submit.prevent="save"><label class="ws-field">更正内容<textarea v-model="value" maxlength="40" /></label><p v-if="correctionError" class="ws-field-error" role="alert">{{ correctionError }}</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">保存更正</button><button class="btn" type="button" @click="correction = null">取消</button></div></form></InfoSheet>
  </div>
</template>
