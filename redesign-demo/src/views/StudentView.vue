<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { COLLECT_ITEMS, PROFILE_FIELDS, STUDENT } from '../data/student'
import type { ProfileField } from '../data/types'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
const progress = computed(() => demo.use.profileProgress.value)
const known = computed(() => PROFILE_FIELDS.slice(0, progress.value.known))
const missing = computed(() => PROFILE_FIELDS.slice(progress.value.known))
const filter = ref('all')
const filters = [
  { key: 'all', label: '全部信息', sources: [] },
  { key: 'school', label: '学校档案', sources: ['学信网', '教务系统', '学校'] },
  { key: 'talk', label: '你说过的', sources: ['对话'] },
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
  if (!value.value.trim()) { correctionError.value = '请写下更正后的信息。'; return }
  if (value.value.trim().length > 40) { correctionError.value = '最多 40 个字，请把这条信息写得简短一点。'; return }
  if (correction.value) demo.updateProfileField(correction.value.key, value.value)
  correction.value = null
}
function fieldSource(f: ProfileField) { return demo.state.profileEdits[f.key] ? '本人填写' : f.source }
</script>
<template>
  <div class="ws-page">
    <PageHeading title="个人画像" description="已经了解的情况、还缺的依据，都放在这里。"><RouterLink class="btn btn--primary" to="/chat">{{ progress.gap ? '继续聊，补充了解' : '聊聊新的变化' }}<UiIcon name="arrow" :size="16" /></RouterLink></PageHeading>
    <nav class="desk-section-nav" aria-label="个人画像视图"><RouterLink to="/profile" aria-current="page">已有信息与缺口</RouterLink><RouterLink to="/academic">学籍与资料</RouterLink></nav>
    <div class="ws-two-columns">
      <section class="ws-paper">
        <div class="ws-profile-head"><div><h2>{{ STUDENT.name }}</h2><p>{{ demo.state.profileEdits.school ?? STUDENT.school }} · {{ demo.state.profileEdits.grade ?? demo.use.scenario.value.grade }}</p></div><div class="ws-profile-progress"><strong>{{ progress.known }} / {{ progress.total }} 条</strong><p>{{ progress.gap ? '还有 ' + progress.gap + ' 条会在后面聊到' : '这份示例的了解已补齐' }}</p></div></div>
        <dl class="ws-facts"><div><dt>专业</dt><dd>{{ demo.state.profileEdits.major ?? STUDENT.major }}</dd></div><div><dt>年级</dt><dd>{{ demo.state.profileEdits.grade ?? demo.use.scenario.value.grade }}</dd></div><div><dt>已有信息来源</dt><dd>{{ known.length ? '对话 · 学校 · 行为' : '等待对话了解' }}</dd></div></dl>
        <section class="ws-section">
          <div class="ws-section-head"><h2>已经了解到的</h2><span class="ws-muted">点开一条，看看出处</span></div>
          <div class="ws-tabs" aria-label="档案信息来源"><button v-for="f in filters" :key="f.key" :aria-pressed="filter === f.key" @click="filter = f.key">{{ f.label }}</button></div>
          <div v-if="visible.length" class="ws-evidence"><details v-for="f in visible" :key="f.key" class="ws-evidence__row"><summary><span class="ws-evidence__label">{{ f.label }}</span><span class="ws-evidence__value">{{ fieldValue(f) }}</span><UiIcon name="chevron" :size="18" /></summary><div class="ws-evidence__explain"><p>来源：{{ fieldSource(f) }}<span v-if="demo.state.profileEdits[f.key]"> · 你刚刚更正过</span></p><p>把握：{{ demo.state.profileEdits[f.key] ? '本人确认' : f.confidence.label }}</p><p>记于：{{ f.noted }}</p><button class="ws-text-button" @click="edit(f)">这条需要更正<UiIcon name="arrow" :size="14" /></button></div></details></div>
          <div v-else class="ws-empty"><h3>{{ known.length ? '这一类还没有记录' : '还不太了解你' }}</h3><p>先聊几个容易回答的问题，信息会逐条出现在这里。</p><RouterLink class="ws-text-link" to="/chat">开始第一个问题<UiIcon name="arrow" :size="16" /></RouterLink></div>
        </section>
      </section>
      <aside class="ws-aside">
        <section><h2>{{ missing.length ? '慢慢补齐这几条' : '发现变化，随时更正' }}</h2><p>不用一次答完，也不用把不确定的事说成结论。</p><ul class="ws-mini-list"><li v-for="f in missing" :key="f.key">{{ f.label }}</li></ul><RouterLink class="ws-text-link" to="/chat">回到对话补充<UiIcon name="arrow" :size="16" /></RouterLink></section>
        <section><h2>少问你重复的问题</h2><p>学校系统里的事实可以直接取到；取不到的，会说明原因。</p><details class="ws-fold"><summary>哪些信息可以取得<UiIcon name="chevron" :size="16" /></summary><ul class="ws-mini-list"><li v-for="c in COLLECT_ITEMS" :key="c.label"><strong>{{ c.label }}</strong><p>{{ c.fetchable ? '来自' + c.from : c.blockedBy }}</p></li></ul></details></section>
        <section><details class="ws-fold"><summary>学籍核验怎么进行<UiIcon name="chevron" :size="16" /></summary><div class="ws-fold__body"><p>去学信网获取在线验证码，在这里提供验证码即可。全程不需要账号密码。</p><p style="margin-top: var(--sp-4)">课表空档来自教务课表，学信网不提供课表。</p><p class="ws-demo-note">当前为核验流程说明，尚未接入真实核验服务。</p></div></details></section>
      </aside>
    </div>
    <div v-if="!demo.state.guidesClosed.profile" class="ws-guide"><UiIcon name="info" :size="18" /><p>档案是可以更正的。点开已有信息查看来源，发现不对时直接告诉我们。</p><button @click="demo.closeGuide('profile')">收起</button></div>
    <p class="ws-demo-note">陈亦然的预置示例，不代表你的真实档案；学校数据来源用于说明产品流程。</p>
    <InfoSheet :open="correction !== null" :title="'更正' + (correction?.label ?? '信息')" @close="correction = null"><form @submit.prevent="save"><label class="ws-field">你现在的情况<textarea v-model="value" maxlength="300" /></label><p v-if="correctionError" class="ws-field-error" role="alert">{{ correctionError }}</p><p class="ws-muted" style="margin-top: var(--sp-4)">更正会记在当前演示里。需要解释原因时，可以继续在对话里补充。</p><div class="ws-inline-actions"><button class="btn btn--primary" type="submit">保存更正</button><button class="ws-text-button" type="button" @click="correction = null">取消</button></div></form></InfoSheet>
  </div>
</template>
