<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
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

type CareerMatchHandle = { run: () => void }

const query = ref('')
const error = ref('')
const busy = ref(false)
const loaded = ref(false)
const refreshing = ref(false)
const lastRefresh = ref(false)
const status = ref('')
const basis = ref('')
const basisKind = ref('')
const matchOpen = ref(false)
const reading = ref<IntelItemView | null>(null)
const selectedId = ref('')
const matchPanel = ref<CareerMatchHandle | null>(null)
/**
 * 从提醒页「看看是什么」跳进来时，把职业资料区滚进视野并在顶部说明来意。
 * 路由在 onMounted 里读（组件挂载时一定在路由上下文内），避免在模块/setup 顶层
 * 直接取 route：单测会把 IntelView 的 setup 跑在没有路由的 vm 里。
 */
const fromReminders = ref(false)
const bannerDismissed = ref(false)

/*
 * 【#12】展示层清洗：后端抓回来的原文是"标签堆叠 + 整段无分段 + 中英标点混排"，
 * 直接渲染时用户会看到「基本信息：职业定义：职业定义：……」这样一堵字。
 * 这里只做展示转换，不改数据请求、不改后端：
 *   ① 合并相邻的重复标签（职业定义：职业定义： → 职业定义：）；
 *   ② 统一中文标点（把 , : ; ( ) 在中文语境里换成全角）；
 *   ③ 按「职业定义 / 基本信息 / 知识技能 / 职业发展」等小标题分段；
 *   ④ 把 1. / 2、/ 3) 这类编号拆成独立条目，长段落按句子切成不超过约 110 字的行。
 * IntelArticle 的文章正文是 `white-space: pre-line`，所以插入的换行会真实显示成分段。
 */
const majorSectionLabels = ['职业定义', '基本信息', '知识技能', '职业发展', '职业前景', '工作内容', '任职要求', '主要职责', '发展路径', '职业介绍']
const inlineLabels = ['个性定义', '常用工具', '职业道德', '职业其他名称', '职业别名', '所属行业', '学科门类', '摘要', '案例', '职业']

function normalizeChinesePunctuation(text: string) {
  return text
    .replace(/,\s*(?=[\u4e00-\u9fa5])/g, '，')
    .replace(/([\u4e00-\u9fa5])\s*,\s*/g, '$1，')
    .replace(/:\s*(?=[\u4e00-\u9fa5（(])/g, '：')
    .replace(/([\u4e00-\u9fa5])\s*:\s*/g, '$1：')
    .replace(/;\s*(?=[\u4e00-\u9fa5])/g, '；')
    .replace(/([\u4e00-\u9fa5])\s*;\s*/g, '$1；')
    .replace(/\(/g, '（')
    .replace(/\)/g, '）')
    .replace(/([\u4e00-\u9fa5，。；：！？、（）])[ \t\u3000]+(?=[\u4e00-\u9fa5])/g, '$1')
    .replace(/[ \t\u3000]+([，。；：！？、）])/g, '$1')
}

/** 长句按句号切成不超过约 110 字的行，避免整段一大块压在一起。 */
function breakSentences(text: string, limit = 110): string[] {
  const sentences = text.split(/(?<=[。！？])/).map((part) => part.trim()).filter(Boolean)
  const lines: string[] = []
  for (const sentence of sentences) {
    const last = lines.length - 1
    if (last >= 0 && (lines[last]!.length + sentence.length) <= limit) lines[last] += sentence
    else lines.push(sentence)
  }
  return lines.length ? lines : [text.trim()]
}

function cleanIntelText(input?: string): string {
  if (!input?.trim()) return ''
  let text = input.replace(/\r\n?/g, '\n')
  // ① 重复标签：连续两次以上同一个「xx：」只留一个
  for (let pass = 0; pass < 3; pass += 1) {
    const before = text
    text = text.replace(/([\u4e00-\u9fa5]{2,8}[：:])\s*\1/g, '$1')
    if (before === text) break
  }
  // ② 统一标点
  text = normalizeChinesePunctuation(text)
  // ③ 小标题前强制分段（原文常见「……。基本信息：……」这种挤在一行里的情况）
  text = text.replace(new RegExp('\\s*(' + majorSectionLabels.join('|') + ')[：:]', 'g'), '\n\n$1：')
  const blocks: string[] = []
  const seen = new Set<string>()
  const pushLine = (line: string) => {
    const key = line.replace(/\s/g, '')
    if (!key || seen.has(key)) return
    seen.add(key)
    blocks.push(line)
  }
  for (const raw of text.split(/\n+/).map((part) => part.trim()).filter(Boolean)) {
    // ④ 编号条目独立成行：1. / 1、 / （1）
    const withItems = raw
      .replace(/(?<=[\s：。；])(\d{1,2})[.、]/g, '\n$1.')
      .replace(/^(\d{1,2})[.、]\s*/, '$1. ')
      .replace(/\s*[（(](\d{1,2})[)）]\s*/g, '\n（$1）')
    for (const chunk of withItems.split(/\n/).map((part) => part.trim()).filter(Boolean)) {
      const label = [...majorSectionLabels, ...inlineLabels].find((name) => chunk.startsWith(name + '：') || chunk.startsWith(name + ':'))
      const headingOnly = label && chunk.replace(/[：:\s]/g, '') === label
      if (label && headingOnly) { blocks.push(label); continue }
      if (label && majorSectionLabels.includes(label)) {
        const content = chunk.slice(label.length + 1).trim()
        if (!content) { blocks.push(label); continue }
        blocks.push(`${label}\n${breakSentences(content).join('\n')}`)
        continue
      }
      pushLine(breakSentences(chunk).join('\n'))
    }
  }
  return blocks.join('\n\n').replace(/\n{3,}/g, '\n\n').trim()
}

/** 传给 IntelArticle 的副本：只换 text，其余字段保持后端原值。 */
function cleanArticle(item: IntelItemView): IntelItemView {
  return { ...item, text: cleanIntelText(item.text) || item.text }
}

const allItems = computed(() => backendDemo.state.intel)
/** 画像里已记录的专业（只用于说明「专业已记录、资料待获取」，不改后端数据）。 */
const profileMajor = ref('')
async function loadProfileMajor() {
  try {
    const workspace = await backendClient.workspace()
    const fields = workspace.profile_panel?.fields ?? []
    profileMajor.value = String(fields.find((field) => field.key === 'major')?.value ?? '').trim()
  } catch { /* 读不到画像就退回通用文案 */ }
}
const majorItems = computed(() => allItems.value.filter((item) => item.kind === 'speciality'))
const major = computed(() => majorItems.value[0] ?? null)
const basisLabel = computed(() => {
  if (!basis.value) return ''
  return basisKind.value === 'direction'
    ? `你的方向方案「${basis.value}」`
    : `画像专业「${basis.value}」`
})
const explorableItems = computed(() => allItems.value.filter((item) => item.kind !== 'speciality'))

const filteredItems = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase('zh-CN')
  if (!keyword) return explorableItems.value
  return explorableItems.value.filter((item) => {
    const fields = [item.title, displayKind(item)]
    return fields.filter(Boolean).join(' ').toLocaleLowerCase('zh-CN').includes(keyword)
  })
})

const directionBasis = computed(() => basisKind.value === 'direction')
// 有方向方案时，只有 relation=direction 的条目才算“方向相关”；
// 按专业取回的职业/案例只能作为参考，不能混在“相关职业方向”里冒充方向结果。
const primaryItems = computed(() =>
  directionBasis.value
    ? filteredItems.value.filter((item) => item.relation === 'direction')
    : filteredItems.value,
)
const referenceItems = computed(() =>
  directionBasis.value
    ? filteredItems.value.filter((item) => item.relation !== 'direction')
    : [],
)
const careerItems = computed(() => primaryItems.value.filter((item) => item.kind === 'occupation'))
const caseItems = computed(() => primaryItems.value.filter((item) => item.kind === 'career_case'))
const otherItems = computed(() => primaryItems.value.filter((item) => !['occupation', 'career_case'].includes(item.kind ?? '')))
const selected = computed(() => {
  const visible = [...careerItems.value, ...caseItems.value, ...otherItems.value, ...referenceItems.value]
  const current = allItems.value.find((item) => item.id === selectedId.value)
  if (!query.value.trim() && current?.kind === 'speciality') return current
  return visible.find((item) => item.id === selectedId.value) ?? visible[0] ?? current ?? major.value
})
/** 详情区与移动端抽屉都用清洗后的正文（#12）。 */
const selectedArticle = computed(() => (selected.value ? cleanArticle(selected.value) : null))
const initialLoading = computed(() => busy.value && !loaded.value && !allItems.value.length)

function displayKind(item: IntelItemView) {
  const labels: Record<string, string> = {
    speciality: '专业信息',
    occupation: '职业方向',
    career_case: '公开职业案例',
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

/**
 * 从提醒页跳进来时定位到"职业资料"工作台（#11 的"跳转带定位"）。
 * 只滚到有内容的区块，不改选中项，也不额外发请求。
 */
async function focusFromReminders() {
  if (!fromReminders.value) return
  await nextTick()
  requestAnimationFrame(() => {
    document.getElementById('intel-related')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}
function clearFromReminders() {
  bannerDismissed.value = true
}

async function load(refresh = false) {
  if (busy.value) return
  busy.value = true
  refreshing.value = refresh
  lastRefresh.value = refresh
  error.value = ''
  status.value = ''
  // 更新是"有过程"的动作：请求可能很快，先把状态条立起来，避免看起来没反应。
  if (refresh) status.value = '正在更新职业资料…'
  try {
    const result = await (refresh ? backendClient.refreshIntel('') : backendClient.intel(''))
    if (!result || !Array.isArray(result.items)) throw new Error('Incomplete intel')
    backendDemo.setIntel(result.items)
    basis.value = String(result.basis || '').trim()
    basisKind.value = String(result.basis_kind || '').trim()
    // 后端现在会给出取数状态（ok/empty/failed）与画像专业：把"确实没有"
    // 和"这次没取到、可以重试"分开说，不再一律当 0 条。
    if (result.major) profileMajor.value = String(result.major).trim()
    else void loadProfileMajor()
    if (result.status === 'failed') {
      error.value = String(result.message || '这次没有取到职业资料（不是"没有相关内容"）。可以稍后重试。')
    } else if (result.status === 'empty') {
      // 没有搜索词时的"0 条"交给页面空态解释；搜索后再显示"没找到匹配"。
      status.value = query.value.trim() ? String(result.message || '没有找到匹配的职业资料，可以换一个关键词或稍后重试。') : ''
    }
    if (refresh) status.value = result.items.length
      ? `已重新获取 ${result.items.length} 条职业资料。`
      : (result.status === 'empty' ? status.value : '本次未获取到职业资料，可稍后重试或使用画像匹配。')
    if (!result.items.some((item) => item.id === selectedId.value)) {
      selectedId.value = result.items.find((item) => item.kind === 'occupation')?.id ?? result.items[0]?.id ?? ''
    }
    await focusFromReminders()
  } catch {
    if (refresh) status.value = ''
    error.value = refresh ? '职业资料更新失败，已读取的内容仍保留，请稍后重试。' : '职业资料没有读取成功。可以稍后重试，画像匹配仍可单独发起。'
  } finally {
    busy.value = false
    refreshing.value = false
    loaded.value = true
  }
}

onMounted(() => {
  const route = useRoute()
  fromReminders.value = route.query.from === 'reminders'
  void load()
})
</script>

<template>
  <div class="ws-page intel-page">
    <section class="intel-command" aria-labelledby="intel-page-title">
      <div class="intel-command__title">
        <h1 id="intel-page-title">职业探索</h1>
        <p>从所学专业出发，了解相关职业，再用真实去向帮助自己做选择。</p>
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
    <StatusBanner v-if="fromReminders && !bannerDismissed" tone="info" message="你从提醒里的「看看是什么」进来：下面是与你方向相关的职业资料，可以逐条点开核对来源。提醒已同时标为已读。" @dismiss="clearFromReminders" />
    <div v-if="initialLoading" class="intel-loading" role="status" aria-label="正在读取职业资料">
      <SkeletonBlock variant="list" :lines="6" />
    </div>

    <template v-else-if="allItems.length">
      <section class="intel-route" aria-label="从专业到职业的探索路径">
        <article class="intel-origin">
          <div class="intel-origin__mark" aria-hidden="true"><UiIcon name="profile" :size="20" /></div>
          <div class="intel-origin__copy">
            <span>你的专业起点</span>
            <template v-if="major">
              <h2>{{ major.title }}</h2>
              <p>{{ majorExcerpt(major) }}</p>
              <button type="button" @click="selectItem(major)">查看专业信息</button>
            </template>
            <template v-else>
              <template v-if="profileMajor">
                <h2>专业已记录，相关职业资料待获取</h2>
                <p>画像里已记录专业：{{ profileMajor }}。这次没有取到对应的职业资料，可以点「更新职业资料」重试，不用回画像重复填写。</p>
                <button type="button" :disabled="busy" @click="load(true)">{{ refreshing ? '正在更新资料…' : '更新职业资料' }}</button>
              </template>
              <template v-else>
                <h2>专业信息待补充</h2>
                <p>补充专业信息后，可进一步了解相关职业方向。</p>
                <RouterLink to="/profile">前往个人画像</RouterLink>
              </template>
            </template>
          </div>
        </article>

        <div class="intel-route__steps" aria-label="探索关系">
          <span><strong>{{ major || profileMajor ? 1 : 0 }}</strong> 个专业起点</span>
          <i aria-hidden="true"></i>
          <span><strong>{{ allItems.filter((item) => item.kind === 'occupation').length }}</strong> 个相关职业</span>
          <i aria-hidden="true"></i>
          <span><strong>{{ allItems.filter((item) => item.kind === 'career_case').length }}</strong> 个公开职业案例</span>
        </div>
        <p v-if="basisLabel" class="intel-basis" role="status">
          本次探索依据：{{ basisLabel }}。平台职业库按职业大类收录；未收录当前方向时，方向相关内容以公开案例呈现，专业对口职业只作背景参考。
          <RouterLink v-if="basisKind === 'direction'" to="/directions">查看方向方案</RouterLink>
          <RouterLink v-else to="/profile">查看个人画像</RouterLink>
        </p>

        <aside class="intel-match-prompt" aria-labelledby="intel-match-title">
          <div>
            <h2 id="intel-match-title">哪些方向更适合你？</h2>
            <p>使用当前画像比较职业要求和已有能力。</p>
          </div>
          <button class="btn btn--primary" type="button" data-sheet-trigger @click="startMatch">用画像比较</button>
          <small><UiIcon name="info" :size="13" />仅在点击后运行</small>
        </aside>
      </section>

      <div id="intel-related" class="intel-workbench">
        <section class="intel-list-pane" :aria-busy="busy" aria-labelledby="intel-results-title">
          <header class="intel-list-pane__head">
            <div>
              <h2 id="intel-results-title">{{ query ? '搜索结果' : careerItems.length ? '相关职业方向' : caseItems.length ? '与方向相关的公开案例' : '职业参考资料' }}</h2>
              <p>{{ query ? `找到 ${primaryItems.length} 条方向相关资料` : careerItems.length ? '先了解工作本身，再决定是否深入' : caseItems.length ? '平台职业库未单列该方向，先看真实案例' : '暂未获取方向直接对应的职业资料，可先浏览下方专业参考' }}</p>
            </div>
            <span v-if="!query">{{ careerItems.length ? `${careerItems.length} 个方向` : caseItems.length ? `${caseItems.length} 个案例` : '' }}</span>
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
                <h3 id="career-case-title">公开职业案例</h3>
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

            <section v-if="referenceItems.length" class="intel-result-group intel-result-group--cases" aria-labelledby="major-reference-title">
              <header><h3 id="major-reference-title">专业对口参考</h3><span>{{ referenceItems.length }} 条</span></header>
              <p>以下按画像专业{{ profileMajor ? `「${profileMajor}」` : '' }}取回，不等于你当前方向{{ basis ? `「${basis}」` : '' }}；只作背景参考，不要把这里的职业当成方向结论。</p>
              <div class="intel-case-list">
                <button v-for="item in referenceItems" :key="item.id" class="intel-case-row" :class="{ 'is-selected': selected?.id === item.id }" type="button" :aria-pressed="selected?.id === item.id" @click="selectItem(item)">
                  <UiIcon name="document" :size="16" />
                  <span><strong>{{ item.title || '未命名参考资料' }}</strong><small>{{ displayKind(item) }} · 专业对口</small></span>
                  <UiIcon name="arrow" :size="15" />
                </button>
              </div>
            </section>
          </div>

          <EmptyState v-else-if="query.trim()" kind="search-empty" size="sm" title="没有找到相关方向" description="换一个职业名称或清空搜索。" :next="false">
            <button class="btn" type="button" @click="query = ''">清空搜索</button>
          </EmptyState>
          <p v-else class="ws-muted">暂无可展示的职业资料，可点「更新职业资料」获取；也可以先用画像发起匹配。</p>
        </section>

        <section v-if="selectedArticle" class="intel-detail-card" aria-label="职业探索详情">
          <IntelArticle :item="selectedArticle" />
        </section>
      </div>
    </template>

    <EmptyState v-else kind="intel" :heading-level="2" title="从真实资料开始职业探索" description="先读取职业资料了解可探索范围；也可以直接用当前画像发起一次匹配。" :next="false">
      <div class="intel-empty-actions" aria-label="职业探索起步操作">
        <button class="intel-empty-action is-primary" type="button" :disabled="busy" @click="load(true)"><span aria-hidden="true"><UiIcon name="search" :size="18" /></span><strong>{{ refreshing ? '正在更新资料…' : '更新职业资料' }}</strong><small>读取专业相关职业与真实去向</small></button>
        <button class="ws-text-link" type="button" data-sheet-trigger @click="startMatch">已有方向，直接用画像匹配</button>
      </div>
    </EmptyState>

    <InfoSheet :open="reading !== null" shape="sheet" :title="reading ? displayKind(reading) : '职业详情'" @close="reading = null">
      <IntelArticle v-if="reading" :item="cleanArticle(reading)" />
    </InfoSheet>

    <InfoSheet :open="matchOpen" shape="panel" title="画像岗位匹配" description="本次匹配由你主动发起，不会自动重复运行。" @close="matchOpen = false">
      <CareerMatchPanel ref="matchPanel" />
    </InfoSheet>
  </div>
</template>

<style scoped>
.intel-page { width: 100%; min-width: 0; padding-bottom: 48px; }
.intel-loading { padding: 20px; border: 1px solid var(--c-border); border-radius: 16px; background: var(--c-surface); }
.intel-empty-actions { display:flex; flex-wrap:wrap; align-items:center; gap:12px 18px; width:min(620px,100%); margin-top:4px; text-align:left; }
.intel-empty-action { display:grid; grid-template-columns:30px minmax(0,1fr); gap:2px 10px; align-items:center; width:min(360px,100%); min-height:72px; padding:12px 14px; border:1px solid var(--c-border-strong); border-radius:12px; background:var(--c-surface); color:var(--c-text); text-align:left; }
.intel-empty-action:hover { border-color:var(--c-primary-border); background:var(--c-primary-weak-2); }
.intel-empty-action>span { grid-row:1 / 3; color:var(--c-primary); font-size: 12px; font-variant-numeric:tabular-nums; }
.intel-empty-action strong { font-size:14px; }
.intel-empty-action small { color:var(--c-text-3); font-size: 12px; }
.intel-empty-action.is-primary { border-color:var(--c-primary-border); background:var(--c-primary-weak); }

.intel-command { display: flex; align-items: end; justify-content: space-between; gap: 28px; margin-bottom: 14px; padding: 8px 2px 12px; }
.intel-command__title h1 { font-size: 24px; font-weight: 720; line-height: 1.35; }
.intel-command__title p { max-width: 52em; margin-top: 5px; color: var(--c-text-3); font-size: 12px; line-height: 1.6; }
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
.intel-origin__copy button, .intel-origin__copy a { display: inline-block; margin-top: 9px; color: var(--c-primary); font-size: 12px; font-weight: 650; }
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

.intel-basis { margin: 10px 0 0; color: var(--c-text-2); font-size: 13px; line-height: 1.7; }
.intel-basis a { margin-left: 6px; color: var(--c-primary); }

@media (max-width: 640px) {
  .intel-page { padding-bottom: 92px; }
  .intel-command { padding-inline: 2px; }
  .intel-command__title h1 { font-size: 22px; }
  .intel-search { min-width: 0; }
  .intel-command__actions { flex-direction:column; }
  .intel-command__actions>.btn { width:100%; }
  .intel-empty-actions { flex-direction:column; align-items:stretch; }
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
