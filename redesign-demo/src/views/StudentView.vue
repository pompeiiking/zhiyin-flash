<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { COLLECT_ITEMS, PROFILE_FIELDS, STUDENT } from '../data/student'
import type { ProfileField } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import PanelTabs from '../components/PanelTabs.vue'
import EmptyState from '../components/EmptyState.vue'
const progress = computed(() => demo.use.profileProgress.value)
const known = computed(() => PROFILE_FIELDS.slice(0, progress.value.known))
const missing = computed(() => PROFILE_FIELDS.slice(progress.value.known))
const filter = ref('all')
const filters = [
  { key: 'all', label: '全部信息', sources: [] },
  { key: 'school', label: '学校档案', sources: ['学信网', '教务系统', '学校'] },
  { key: 'talk', label: '咨询记录', sources: ['对话'] },
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
  return demo.state.profileEdits[f.key] ?? (f.key === 'grade' ? demo.use.scenario.value.grade + '（在读）' : f.value)
}
function edit(f: ProfileField) {
  correction.value = f; value.value = fieldValue(f); correctionError.value = ''
}
function save() {
  if (!value.value.trim()) { correctionError.value = '请填写更正后的信息。'; return }
  if (value.value.trim().length > 40) { correctionError.value = '更正内容最多 40 个字。'; return }
  if (correction.value) demo.updateProfileField(correction.value.key, value.value)
  correction.value = null
}
function fieldSource(f: ProfileField) { return demo.state.profileEdits[f.key] ? '本人填写' : f.source }
</script>
<template>
  <div class="ws-page">
    <PageHeading title="个人画像" description="管理个人信息，查看来源、依据与待补充项。"><RouterLink class="btn btn--primary" to="/chat">{{ progress.gap ? '补充信息' : '更新信息' }}<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-profile-head"><div><h2>{{ demo.state.account === 'fresh' ? '新用户' : STUDENT.name }}</h2><p>{{ demo.state.account === 'fresh' ? '学校与年级待补充' : (demo.state.profileEdits.school ?? STUDENT.school) + ' · ' + (demo.state.profileEdits.grade ?? demo.use.scenario.value.grade) }}</p></div><div class="ws-profile-progress"><strong>{{ progress.known }} / {{ progress.total }} 条</strong><p>{{ progress.gap ? '待补充 ' + progress.gap + ' 条信息' : '示例信息已完整' }}</p></div></div>
        <dl v-if="demo.state.account !== 'fresh'" class="ws-facts"><div><dt>专业</dt><dd>{{ demo.state.profileEdits.major ?? STUDENT.major }}</dd></div><div><dt>年级</dt><dd>{{ demo.state.profileEdits.grade ?? demo.use.scenario.value.grade }}</dd></div><div><dt>已有信息来源</dt><dd>{{ known.length ? '对话 · 学校 · 行为' : '待采集' }}</dd></div></dl>
        <section class="ws-section">
          <div class="ws-section-head"><h2>个人信息</h2><span class="ws-muted">展开查看来源与依据</span></div>
          <PanelTabs v-model="filter" label="档案信息来源" :items="filters.map(f => ({ key: f.key, label: f.label }))">
          <div v-if="visible.length" class="ws-evidence"><details v-for="f in visible" :key="f.key" class="ws-evidence__row"><summary><span class="ws-evidence__label">{{ f.label }}</span><span class="ws-evidence__value">{{ fieldValue(f) }}</span><UiIcon name="chevron" :size="18" /></summary><div class="ws-evidence__explain"><p>来源：{{ fieldSource(f) }}<span v-if="demo.state.profileEdits[f.key]"> · 已由本人更正</span></p><p>把握：{{ demo.state.profileEdits[f.key] ? '本人确认' : f.confidence.label }}</p><p>记于：{{ f.noted }}</p><button class="ws-text-button" @click="edit(f)">更正信息<UiIcon name="arrow" :size="14" /></button></div></details></div>
          <EmptyState v-else :title="known.length ? '暂无此类记录' : '暂无个人信息'" description="完成咨询后，已采集的信息将在此展示。"><RouterLink class="ws-text-link" to="/chat">开始咨询<UiIcon name="arrow" :size="16" /></RouterLink></EmptyState>
          </PanelTabs>
        </section>
      </section>
      <aside class="ws-aside">
        <section><h2>{{ missing.length ? '待补充信息' : '信息维护' }}</h2><p>可通过咨询逐项补充，不确定的信息可暂时保留。</p><ul class="ws-mini-list"><li v-for="f in missing" :key="f.key">{{ f.label }}</li></ul><RouterLink class="ws-text-link" to="/chat">补充个人信息<UiIcon name="arrow" :size="16" /></RouterLink></section>
        <section><h2>资料来源</h2><p>学校资料可通过导入与核验补充。当前演示展示可取得的信息及限制。</p><details class="ws-fold"><summary>哪些信息可以取得<UiIcon name="chevron" :size="16" /></summary><ul class="ws-mini-list"><li v-for="c in COLLECT_ITEMS" :key="c.label"><strong>{{ c.label }}</strong><p>{{ c.fetchable ? '来自' + c.from : c.blockedBy }}</p></li></ul></details></section>
        <section><details class="ws-fold"><summary>学籍核验说明<UiIcon name="chevron" :size="16" /></summary><div class="ws-fold__body"><p>去学信网获取在线验证码，在这里提供验证码即可。全程不需要账号密码。</p><p style="margin-top: var(--sp-4)">课表空档来自教务课表，学信网不提供课表。</p><p class="ws-demo-note">当前为核验流程说明，尚未接入真实核验服务。</p></div></details></section>
      </aside>
    </div>
    <div v-if="!demo.state.guidesClosed.profile" class="ws-guide"><UiIcon name="info" :size="18" /><p>个人信息支持更正。展开条目可查看来源与可信度。</p><button @click="demo.closeGuide('profile')">收起</button></div>
    <p class="ws-demo-note">陈亦然的预置示例，不代表你的真实档案；学校数据来源用于说明产品流程。</p>
    <InfoSheet :open="correction !== null" :title="'更正' + (correction?.label ?? '信息')" @close="correction = null"><form @submit.prevent="save"><label class="ws-field">更正内容<textarea v-model="value" maxlength="40" /></label><p v-if="correctionError" class="ws-field-error" role="alert">{{ correctionError }}</p><p class="ws-muted" style="margin-top: var(--sp-4)">更正仅保存于当前演示。可通过咨询补充说明。</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">保存更正</button><button class="ws-text-button" type="button" @click="correction = null">取消</button></div></form></InfoSheet>
  </div>
</template>
