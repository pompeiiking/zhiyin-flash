<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import type { IntelItemView } from '../api/backend-types'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import IntelArticle from '../components/IntelArticle.vue'
import CareerMatchPanel from '../components/CareerMatchPanel.vue'
import StatusBanner from '../components/StatusBanner.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import DetailPopover from '../components/DetailPopover.vue'

type CareerMatchHandle = { run: () => void }

const query = ref('')
const error = ref('')
const busy = ref(false)
const loaded = ref(false)
const refreshing = ref(false)
const lastRefresh = ref(false)
const status = ref('')
const matchOpen = ref(false)
const reading = ref<IntelItemView | null>(null)
const selectedId = ref('')
const matchPanel = ref<CareerMatchHandle | null>(null)

const allItems = computed(() => backendDemo.state.intel)
const majorItems = computed(() => allItems.value.filter((item) => item.kind === 'speciality'))
const major = computed(() => majorItems.value[0] ?? null)
const explorableItems = computed(() => allItems.value.filter((item) => item.kind !== 'speciality'))

const filteredItems = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase('zh-CN')
  if (!keyword) return explorableItems.value
  return explorableItems.value.filter((item) => {
    const fields = [item.title, displayKind(item)]
    return fields.filter(Boolean).join(' ').toLocaleLowerCase('zh-CN').includes(keyword)
  })
})

const careerItems = computed(() => filteredItems.value.filter((item) => item.kind === 'occupation'))
const caseItems = computed(() => filteredItems.value.filter((item) => item.kind === 'career_case'))
const otherItems = computed(() => filteredItems.value.filter((item) => !['occupation', 'career_case'].includes(item.kind ?? '')))
const selected = computed(() => {
  const visible = [...careerItems.value, ...caseItems.value, ...otherItems.value]
  const current = allItems.value.find((item) => item.id === selectedId.value)
  if (!query.value.trim() && current?.kind === 'speciality') return current
  return visible.find((item) => item.id === selectedId.value) ?? visible[0] ?? current ?? major.value
})
const initialLoading = computed(() => busy.value && !loaded.value && !allItems.value.length)

function displayKind(item: IntelItemView) {
  const labels: Record<string, string> = {
    speciality: '专业信息',
    occupation: '职业方向',
    career_case: '校友去向',
    job_requirement: '岗位要求',
    industry: '行业情况',
  }
  return labels[item.kind ?? ''] ?? item.kind_label ?? '参考资料'
}

function majorExcerpt(item: IntelItemView | null) {
  if (!item?.text) return '查看培养方向、毕业去向和对口职业。'
  const intro = item.text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.startsWith('简介：'))
    ?.replace(/^简介：/, '')
  const text = intro || item.text.replace(/^专业：[^\r\n]+/, '').trim()
  return text.length > 112 ? `${text.slice(0, 112)}…` : text
}

function selectItem(item: IntelItemView) {
  selectedId.value = item.id
  if (window.matchMedia('(max-width: 900px)').matches) reading.value = { ...item }
}

async function startMatch() {
  matchOpen.value = true
  await nextTick()
  matchPanel.value?.run()
}

async function load(refresh = false) {
  if (busy.value) return
  busy.value = true
  refreshing.value = refresh
  lastRefresh.value = refresh
  error.value = ''
  status.value = ''
  try {
    const result = await (refresh ? backendClient.refreshIntel('') : backendClient.intel(''))
    if (!result || !Array.isArray(result.items)) throw new Error('Incomplete intel')
    backendDemo.setIntel(result.items)
    if (refresh) status.value = result.items.length ? `已重新获取 ${result.items.length} 条职业资料。` : '本次未获取到职业资料，可稍后重试或使用画像匹配。'
    if (!result.items.some((item) => item.id === selectedId.value)) {
      selectedId.value = result.items.find((item) => item.kind === 'occupation')?.id ?? result.items[0]?.id ?? ''
    }
  } catch {
    error.value = refresh ? '职业资料更新失败，已读取的内容仍保留，请稍后重试。' : '职业资料没有读取成功。可以稍后重试，画像匹配仍可单独发起。'
  } finally {
    busy.value = false
    refreshing.value = false
    loaded.value = true
  }
}

onMounted(() => { void load() })
</script>

<template>
  <div class="ws-page intel-page">
    <section class="intel-command" aria-labelledby="intel-page-title">
      <div class="intel-command__title">
        <div><h1 id="intel-page-title">职业探索</h1><DetailPopover title="职业探索 · 页面说明" label="查看职业探索说明"><p>从所学专业出发，了解相关职业，再用真实去向帮助自己做选择。</p></DetailPopover></div>
      </div>
      <div class="intel-command__actions">
        <label v-if="allItems.length" class="intel-search">
          <UiIcon name="search" :size="17" />
          <input v-model="query" name="intel-search" autocomplete="off" aria-label="搜索职业方向或校友去向" placeholder="搜索职业方向或校友去向…" />
          <button v-if="query" type="button" aria-label="清空搜索" @click="query = ''">清空</button>
        </label>
        <button v-if="allItems.length" class="btn" type="button" :disabled="busy" @click="load(true)">{{ refreshing ? '正在更新资料…' : '更新职业资料' }}</button>
      </div>
    </section>
    <StatusBanner v-if="error" tone="error" :message="error" :retry-label="lastRefresh ? '重试更新' : '重新读取'" :retrying="busy" @retry="load(lastRefresh)" @dismiss="error = ''" />

    <StatusBanner v-if="status" tone="info" :message="status" @dismiss="status = ''" />
    <div v-if="initialLoading" class="intel-loading" role="status" aria-label="正在读取职业资料">
      <SkeletonBlock variant="list" :lines="6" />
    </div>

    <template v-else-if="allItems.length">
      <section class="intel-route" aria-label="从专业到职业的探索路径">
        <article v-if="major" class="intel-origin">
          <div class="intel-origin__mark" aria-hidden="true"><UiIcon name="profile" :size="20" /></div>
          <div class="intel-origin__copy">
            <span>你的专业起点</span>
            <h2>{{ major.title }}</h2>
            <p>{{ majorExcerpt(major) }}</p>
            <button type="button" @click="selectItem(major)">查看专业信息</button>
          </div>
        </article>

        <div class="intel-route__steps" aria-label="探索关系">
          <span><strong>{{ major ? 1 : 0 }}</strong> 个专业起点</span>
          <i aria-hidden="true"></i>
          <span><strong>{{ allItems.filter((item) => item.kind === 'occupation').length }}</strong> 个相关职业</span>
          <i aria-hidden="true"></i>
          <span><strong>{{ allItems.filter((item) => item.kind === 'career_case').length }}</strong> 个校友去向</span>
        </div>

        <aside class="intel-match-prompt" aria-labelledby="intel-match-title">
          <div>
            <h2 id="intel-match-title">哪些方向更适合你？</h2>
            <p>使用当前画像比较职业要求和已有能力。</p>
          </div>
          <button class="btn btn--primary" type="button" data-sheet-trigger @click="startMatch">用画像比较</button>
          <small><UiIcon name="info" :size="13" />仅在点击后运行</small>
        </aside>
      </section>

      <div class="intel-workbench">
        <section class="intel-list-pane" :aria-busy="busy" aria-labelledby="intel-results-title">
          <header class="intel-list-pane__head">
            <div>
              <h2 id="intel-results-title">{{ query ? '搜索结果' : '相关职业方向' }}</h2>
              <p>{{ query ? `找到 ${filteredItems.length} 条相关资料` : '先了解工作本身，再决定是否深入' }}</p>
            </div>
            <span v-if="!query">{{ careerItems.length }} 个方向</span>
          </header>

          <div v-if="filteredItems.length" class="intel-result-groups">
            <section v-if="careerItems.length" class="intel-result-group" aria-labelledby="career-direction-title">
              <h3 v-if="query" id="career-direction-title">职业方向</h3>
              <div class="intel-result-list">
                <button
                  v-for="(item, index) in careerItems"
                  :key="item.id"
                  class="intel-result-card"
                  :class="{ 'is-selected': selected?.id === item.id }"
                  type="button"
                  :aria-pressed="selected?.id === item.id"
                  @click="selectItem(item)"
                >
                  <span class="intel-result-card__index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
                  <span class="intel-result-card__copy">
                    <strong>{{ item.title || '未命名职业方向' }}</strong>
                    <small>{{ item.source_name || '来源待补充' }}</small>
                  </span>
                  <UiIcon name="arrow" :size="16" />
                </button>
              </div>
            </section>

            <section v-if="caseItems.length" class="intel-result-group intel-result-group--cases" aria-labelledby="career-case-title">
              <header>
                <h3 id="career-case-title">校友怎么走</h3>
                <span>{{ caseItems.length }} 个参考</span>
              </header>
              <p>看见真实路径，但不把个例当作唯一答案。</p>
              <div class="intel-case-list">
                <button
                  v-for="item in caseItems"
                  :key="item.id"
                  class="intel-case-row"
                  :class="{ 'is-selected': selected?.id === item.id }"
                  type="button"
                  :aria-pressed="selected?.id === item.id"
                  @click="selectItem(item)"
                >
                  <UiIcon name="profile" :size="16" />
                  <span><strong>{{ item.title || '未命名校友去向' }}</strong><small>{{ item.source_name || '来源待补充' }}</small></span>
                  <UiIcon name="arrow" :size="15" />
                </button>
              </div>
            </section>

            <section v-if="otherItems.length" class="intel-result-group intel-result-group--cases" aria-labelledby="other-reference-title">
              <header><h3 id="other-reference-title">其他参考</h3><span>{{ otherItems.length }} 条</span></header>
              <div class="intel-case-list">
                <button v-for="item in otherItems" :key="item.id" class="intel-case-row" :class="{ 'is-selected': selected?.id === item.id }" type="button" :aria-pressed="selected?.id === item.id" @click="selectItem(item)">
                  <UiIcon name="document" :size="16" />
                  <span><strong>{{ item.title || '未命名参考资料' }}</strong><small>{{ displayKind(item) }}</small></span>
                  <UiIcon name="arrow" :size="15" />
                </button>
              </div>
            </section>
          </div>

          <EmptyState v-else kind="search-empty" size="sm" title="没有找到相关方向" description="换一个职业名称或清空搜索。" :next="false">
            <button class="btn" type="button" @click="query = ''">清空搜索</button>
          </EmptyState>
        </section>

        <section v-if="selected" class="intel-detail-card" aria-label="职业探索详情">
          <IntelArticle :item="selected" />
        </section>
      </div>
    </template>

    <EmptyState v-else kind="intel" title="从真实资料开始职业探索" description="先读取职业资料了解可探索范围；也可以直接用当前画像发起一次匹配。" :next="false">
      <div class="intel-empty-actions" aria-label="职业探索起步操作">
        <button class="intel-empty-action is-primary" type="button" :disabled="busy" @click="load(true)"><span>01</span><strong>{{ refreshing ? '正在更新资料…' : '更新职业资料' }}</strong><small>读取专业相关职业与真实去向</small></button>
        <button class="intel-empty-action" type="button" data-sheet-trigger @click="startMatch"><span>02</span><strong>用画像匹配</strong><small>根据当前资料生成匹配建议</small></button>
      </div>
    </EmptyState>

    <InfoSheet :open="reading !== null" shape="sheet" :title="reading ? displayKind(reading) : '职业详情'" @close="reading = null">
      <IntelArticle v-if="reading" :item="reading" />
    </InfoSheet>

    <InfoSheet :open="matchOpen" shape="panel" title="画像岗位匹配" description="本次匹配由你主动发起，不会自动重复运行。" @close="matchOpen = false">
      <CareerMatchPanel ref="matchPanel" />
    </InfoSheet>
  </div>
</template>

<style scoped>
.intel-page { width: 100%; min-width: 0; padding-bottom: 48px; }
.intel-loading { padding: 20px; border: 1px solid var(--c-border); border-radius: 16px; background: var(--c-surface); }
.intel-empty-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; width:min(560px,100%); margin-top:4px; text-align:left; }
.intel-empty-action { display:grid; grid-template-columns:30px minmax(0,1fr); gap:2px 10px; align-items:center; min-height:72px; padding:12px 14px; border:1px solid var(--c-border-strong); border-radius:12px; background:var(--c-surface); color:var(--c-text); text-align:left; }
.intel-empty-action:hover { border-color:var(--c-primary-border); background:var(--c-primary-weak-2); }
.intel-empty-action>span { grid-row:1 / 3; color:var(--c-primary); font-size: 12px; font-variant-numeric:tabular-nums; }
.intel-empty-action strong { font-size:14px; }
.intel-empty-action small { color:var(--c-text-3); font-size: 12px; }
.intel-empty-action.is-primary { border-color:var(--c-primary-border); background:var(--c-primary-weak); }

.intel-command { display: flex; align-items: end; justify-content: space-between; gap: 28px; margin-bottom: 14px; padding: 8px 2px 12px; }
.intel-command__title h1 { font-size: 24px; font-weight: 720; line-height: 1.35; }
.intel-command__title>div { display:flex; align-items:center; gap:8px; }
.intel-command__actions { display:flex; flex:0 1 520px; align-items:center; justify-content:flex-end; gap:10px; }
.intel-search { display: flex; flex: 0 1 360px; align-items: center; gap: 8px; min-width: 260px; min-height: 44px; padding: 0 11px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-surface); color: var(--c-text-3); box-shadow: var(--e-1); }
.intel-search:focus-within { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-weak); }
.intel-search input { width: 100%; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--c-text); font-size: 12px; }
.intel-search button { flex: none; color: var(--c-primary); font-size: 12px; }

.intel-route { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(250px, .75fr); gap: 0 14px; margin-bottom: 14px; }
.intel-origin { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 13px; padding: 17px 18px; border: 1px solid var(--c-primary-border); border-radius: 13px 13px 0 0; background: linear-gradient(120deg, var(--c-primary-weak-2), var(--c-surface) 70%); }
.intel-origin__mark { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 11px; background: var(--c-primary); color: white; }
.intel-origin__copy > span { color: var(--c-primary); font-size: 12px; font-weight: 650; }
.intel-origin__copy h2 { margin-top: 3px; font-size: 18px; font-weight: 720; }
.intel-origin__copy p { display: -webkit-box; overflow: hidden; max-width: 64em; margin-top: 7px; color: var(--c-text-2); font-size: 12px; line-height: 1.7; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.intel-origin__copy button { margin-top: 9px; color: var(--c-primary); font-size: 12px; font-weight: 650; }
.intel-route__steps { display: flex; grid-column: 1; align-items: center; justify-content: center; gap: 12px; min-height: 42px; padding: 0 14px; border: 1px solid var(--c-primary-border); border-top: 0; border-radius: 0 0 13px 13px; background: var(--c-surface); color: var(--c-text-3); font-size: 12px; }
.intel-route__steps span { white-space: nowrap; }
.intel-route__steps strong { color: var(--c-primary); font-size: 13px; }
.intel-route__steps i { width: 30px; height: 1px; background: var(--c-primary-border); }
.intel-match-prompt { display: grid; grid-row: 1 / span 2; grid-column: 2; align-content: center; justify-items: start; padding: 18px; border: 1px solid var(--c-border); border-radius: 13px; background: var(--c-surface); box-shadow: var(--e-1); }
.intel-match-prompt h2 { font-size: 15px; font-weight: 720; }
.intel-match-prompt p { margin-top: 5px; color: var(--c-text-3); font-size: 12px; line-height: 1.6; }
.intel-match-prompt .btn { min-height: 36px; margin-top: 15px; }
.intel-match-prompt small { display: flex; align-items: center; gap: 4px; margin-top: 9px; color: var(--c-text-3); font-size: 12px; }

.intel-workbench { display: grid; grid-template-columns: minmax(290px, 340px) minmax(0, 1fr); align-items: start; gap: 14px; }
.intel-list-pane { overflow: hidden; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); box-shadow: var(--e-1); }
.intel-list-pane__head { display: flex; align-items: center; justify-content: space-between; min-height: 66px; padding: 0 14px; border-bottom: 1px solid var(--c-border); }
.intel-list-pane__head h2 { font-size: 15px; font-weight: 720; }
.intel-list-pane__head p { margin-top: 3px; color: var(--c-text-3); font-size: 12px; }
.intel-list-pane__head > span { flex: none; color: var(--c-primary); font-size: 12px; }
.intel-result-groups { padding: 8px; }
.intel-result-group > h3 { padding: 5px 4px 8px; color: var(--c-text-2); font-size: 12px; font-weight: 650; }
.intel-result-list { display: grid; gap: 6px; }
.intel-result-card { display: grid; grid-template-columns: 28px minmax(0, 1fr) 18px; align-items: center; gap: 8px; width: 100%; height: 64px; padding: 9px 10px; border: 1px solid transparent; border-radius: 9px; background: var(--c-surface); color: var(--c-text-3); text-align: left; transition: border-color 150ms ease, background-color 150ms ease; }
.intel-result-card:hover { background: var(--c-surface-2); }
.intel-result-card.is-selected { border-color: var(--c-primary-border); background: var(--c-primary-weak-2); color: var(--c-primary); }
.intel-result-card__index { color: var(--c-text-3); font-size: 12px; font-variant-numeric: tabular-nums; }
.intel-result-card__copy { display: grid; min-width: 0; }
.intel-result-card__copy strong { overflow: hidden; color: var(--c-text); font-size: 13px; font-weight: 680; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.intel-result-card__copy small { overflow: hidden; margin-top: 3px; color: var(--c-text-3); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.intel-result-group--cases { margin-top: 14px; padding-top: 13px; border-top: 1px solid var(--c-border); }
.intel-result-group--cases > header { display: flex; align-items: center; justify-content: space-between; padding: 0 4px; }
.intel-result-group--cases h3 { font-size: 12px; font-weight: 700; }
.intel-result-group--cases header span, .intel-result-group--cases > p { color: var(--c-text-3); font-size: 12px; }
.intel-result-group--cases > p { margin: 4px 4px 8px; line-height: 1.5; }
.intel-case-list { display: grid; gap: 4px; }
.intel-case-row { display: grid; grid-template-columns: 20px minmax(0, 1fr) 16px; align-items: center; gap: 7px; width: 100%; height: 52px; padding: 7px 8px; border: 1px solid transparent; border-radius: 8px; color: var(--c-text-3); text-align: left; }
.intel-case-row:hover { background: var(--c-surface-2); }
.intel-case-row.is-selected { border-color: var(--c-primary-border); background: var(--c-primary-weak-2); color: var(--c-primary); }
.intel-case-row > span { display: grid; min-width: 0; }
.intel-case-row strong { overflow: hidden; color: var(--c-text); font-size: 12px; font-weight: 650; line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.intel-case-row small { margin-top: 2px; color: var(--c-text-3); font-size: 12px; }

.intel-detail-card { min-width: 0; min-height: 680px; padding: 24px 20px 32px; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); box-shadow: var(--e-1); }

@media (max-width: 1040px) {
  .intel-route { grid-template-columns: 1fr; gap: 10px; }
  .intel-match-prompt { grid-row: auto; grid-column: 1; grid-template-columns: 1fr auto; align-items: center; }
  .intel-match-prompt .btn { grid-row: 1 / span 2; grid-column: 2; margin: 0 0 0 18px; }
  .intel-match-prompt small { margin-top: 5px; }
}

@media (max-width: 900px) {
  .intel-command { align-items: stretch; flex-direction: column; gap: 13px; }
  .intel-search { flex-basis: auto; width: 100%; }
  .intel-command__actions { width:100%; flex-basis:auto; align-items:stretch; }
  .intel-workbench { display: block; }
  .intel-detail-card { display: none; }
}

@media (max-width: 640px) {
  .intel-page { padding-bottom: 92px; }
  .intel-command { padding-inline: 2px; }
  .intel-command__title h1 { font-size: 22px; }
  .intel-search { min-width: 0; }
  .intel-command__actions { flex-direction:column; }
  .intel-command__actions>.btn { width:100%; }
  .intel-empty-actions { grid-template-columns:minmax(0,1fr); }
  .intel-route { margin-inline: -4px; }
  .intel-origin { grid-template-columns: 36px minmax(0, 1fr); padding: 15px 14px; }
  .intel-origin__mark { width: 36px; height: 36px; }
  .intel-route__steps { justify-content: flex-start; gap: 7px; overflow-x: auto; }
  .intel-route__steps i { width: 14px; }
  .intel-match-prompt { display: flex; align-items: flex-start; flex-direction: column; }
  .intel-match-prompt .btn { width: 100%; margin: 13px 0 0; }
  .intel-list-pane { margin-inline: -4px; }
}
</style>
