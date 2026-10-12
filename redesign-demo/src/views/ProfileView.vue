<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import { GUIDES, partialCopy } from '../data/copy'
import { COLLECT_ITEMS, PROFILE_FIELDS } from '../data/student'
import GuideNote from '../components/GuideNote.vue'
import type { ProfileField } from '../data/types'

/**
 * 学生档案 —— **档案页**（2026-10-11 重做）。
 *
 * 上一版把 12 条字段排成一张"标签一列、值一列"的两列表格铺满整页，右栏再挂一块"还差 3 条"。
 * 两个问题：
 *   1. 键值元数据本来就该是 `<dl>`，不是两列表格（Geist Table 的明文禁令）；
 *   2. **元数据抢占了主体** —— 记录页的主体该是"条目"，属性只是少量元数据
 *      （Linear 的客户页就是这个比例：几个属性 + 一大串关联条目）。
 *
 * 这一版换语法：页顶一条 `<dl>` 属性条（只放学校系统里的事实），
 * 主体是按来源分节的**证据流**（你说的 / 你的行为记录），
 * 缺口与已知**在同一张清单的两半** —— 不再另开一栏。
 *
 * 一条内容只出现在一处：学校那层进属性条，就不进证据流。
 */

const progress = computed(() => demo.use.profileProgress.value)
const scenario = computed(() => demo.use.scenario.value)

/**
 * 年级这一条跟着切换器走。
 * 不跟的话，切到大一，"年级"那一栏还写着大三 —— 一条自相矛盾的画像，
 * 正好毁掉这一页要证明的东西（每条都经得起盘问）。
 */
function fieldValue(f: ProfileField) {
  return f.key === 'grade' ? `${scenario.value.grade}（在读）` : f.value
}

const layers = [
  { key: 'talk', title: '你自己说的', note: '从对话里来 —— 你说了什么，就记什么', sources: ['对话'] },
  {
    key: 'school',
    title: '学校系统里的客观档案',
    note: '学信网与教务系统里有的事实 —— 不是我们猜的',
    sources: ['学信网', '教务系统', '学校'],
  },
  {
    key: 'behavior',
    title: '你的行为记录',
    note: '你实际做了什么。完成记录只由这一层驱动',
    sources: ['行为记录'],
  },
]

const known = computed(() => PROFILE_FIELDS.slice(0, progress.value.known))
const missing = computed(() => PROFILE_FIELDS.slice(progress.value.known))

function inLayer(f: ProfileField, sources: string[]) {
  return sources.includes(f.source)
}

const fetchable = computed(() => COLLECT_ITEMS.filter((c) => c.fetchable))
const blocked = computed(() => COLLECT_ITEMS.filter((c) => !c.fetchable))

/**
 * 属性条＝学校系统里的事实（客观、稳定、不需要用户再填）。
 * 证据流＝「你自己说的」与「你的行为记录」两层。
 */
const schoolLayer = layers.find((l) => l.key === 'school')!
const schoolFacts = computed(() => known.value.filter((f) => inLayer(f, schoolLayer.sources)))
const evidenceLayers = layers.filter((l) => l.key !== 'school')

function inLayerKnown(l: (typeof layers)[number]) {
  return known.value.filter((f) => inLayer(f, l.sources))
}
</script>

<template>
  <div class="page">
    <header class="page__head">
      <h1 class="page__title">学生档案</h1>
      <p class="page__sub">
        {{ partialCopy(progress.known, progress.gap) }}。每一条都标了来源与把握程度 —— 点开看依据。
      </p>
    </header>

    <article class="article">
      <!-- ① 属性条：学校系统里的客观事实。是 <dl>，不是两列表格。 -->
      <section v-if="schoolFacts.length" class="sec">
        <h2 class="sec__title">这几条是学校系统里的事实，不用你重复填</h2>
        <p class="sec__note">来自学信网与教务系统 —— 不是我们猜的，也不是你填的。</p>
        <dl class="facts sec__body">
          <div v-for="f in schoolFacts" :key="f.key" class="facts__row">
            <dt class="facts__key">{{ f.label }}</dt>
            <dd class="facts__val">
              {{ fieldValue(f) }}<span class="t-note"> · {{ f.source }}</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- ② 证据流：按来源分节。每行左内容、右把握度；点开看依据。 -->
      <section v-for="l in evidenceLayers" :key="l.key" class="sec">
        <h2 class="sec__title">{{ l.title }}</h2>
        <p class="sec__note">{{ l.note }}</p>
        <ul class="ev sec__body">
          <li v-for="f in inLayerKnown(l)" :key="f.key" class="ev__row">
            <button
              class="ev__head"
              :aria-expanded="demo.state.openField === f.key"
              @click="demo.toggleField(f.key)"
            >
              <span class="ev__label">{{ f.label }}</span>
              <span class="ev__value">{{ fieldValue(f) }}</span>
              <span class="ev__conf">{{ f.confidence.label }}</span>
            </button>

            <div v-if="demo.state.openField === f.key" class="ev__detail">
              <dl class="ev__dl">
                <div class="ev__dlrow">
                  <dt>什么时候记的</dt>
                  <dd>{{ f.noted }}</dd>
                </div>
                <div class="ev__dlrow">
                  <dt>从哪来</dt>
                  <dd>{{ f.source }}</dd>
                </div>
                <div class="ev__dlrow">
                  <dt>有多大把握</dt>
                  <dd>
                    {{ f.confidence.label }}
                    <span class="t-note">（{{ f.confidence.bars }}/3 —— 把握不到就直说，不写成结论）</span>
                  </dd>
                </div>
              </dl>
              <p class="ev__foot">
                这条要是记错了，直接说一句就能改 —— 改了会影响报告和计划里跟着它的那几处。
              </p>
            </div>
          </li>
          <li v-if="!inLayerKnown(l).length" class="ev__empty">这一层还没有记录。</li>
        </ul>
      </section>

      <!-- ③ 待补：缺口与已知在同一张清单的两半 -->
      <section v-if="missing.length" class="sec">
        <h2 class="sec__title">还差 {{ missing.length }} 条，补完方向就定得下来</h2>
        <p class="sec__note">缺口和已知在同一张清单上 —— 不藏起来，也不写成结论。</p>
        <ul class="ev sec__body">
          <li v-for="f in missing" :key="f.key" class="ev__row">
            <div class="ev__head ev__head--todo">
              <span class="ev__label">{{ f.label }}</span>
              <span class="ev__value t-note">从「{{ f.source }}」就能补上</span>
              <RouterLink class="btn btn--sm" to="/chat">现在就问</RouterLink>
            </div>
          </li>
        </ul>
      </section>

      <!-- ④ 采集动线 -->
      <section class="sec">
        <h2 class="sec__title">还有 {{ fetchable.length }} 条现在就能取</h2>
        <p class="sec__note">取不到的也会直接说 —— 不装作没有。</p>
        <ul class="rows sec__body">
          <li v-for="c in fetchable" :key="c.label" class="row">
            <div class="row__main">
              <p class="row__title">{{ c.label }}</p>
              <p class="row__sub">{{ c.from }}</p>
            </div>
            <span class="chip chip--done">能取</span>
          </li>
        </ul>

        <div v-if="blocked.length" class="blocked" style="margin-top: var(--sp-5)">
          <p class="t-label">取不到的，会直接说</p>
          <div v-for="c in blocked" :key="c.label" class="blocked__item">
            <p class="blocked__title">{{ c.label }}</p>
            <p class="blocked__why">{{ c.blockedBy }}</p>
          </div>
        </div>
      </section>

      <!-- ⑤ 核验学籍 -->
      <section class="sec">
        <h2 class="sec__title">核验学籍，是为了少问你几次</h2>
        <p class="sec__note">全程不要账号密码 —— 只要一个在线验证码。</p>
        <ol class="verify sec__body">
          <li class="verify__step">
            <span class="steps__index">1</span>
            <span>去学信网拿一个<strong>在线验证码</strong></span>
          </li>
          <li class="verify__step">
            <span class="steps__index">2</span>
            <span>把验证码填进来 —— <strong>全程不要账号密码</strong></span>
          </li>
          <li class="verify__step">
            <span class="steps__index">3</span>
            <span>核验完，看"跟着改的地方"有哪几处</span>
          </li>
        </ol>
        <div class="callout callout--plain" style="margin-top: var(--sp-4)">
          <span>
            课表不在学信网 —— 空档是从教务系统的课表<strong>算出来的事实</strong>，
            模型只能改措辞，不能改时间。
          </span>
        </div>
      </section>
    </article>

    <GuideNote gkey="profile" :text="GUIDES.profile" to="/chat" to-label="去聊两句" />
  </div>
</template>

<style scoped>
/* 属性条：`<dl>` 键值对，键窄值宽，零边框 —— 靠一列留白分列 */
.facts {
  display: flex;
  flex-direction: column;
  max-width: 46em;
}

.facts__row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
}

.facts__row:first-child {
  padding-top: 0;
}

.facts__row:last-child {
  padding-bottom: 0;
}

.facts__key {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.facts__val {
  margin: 0;
  font-size: var(--fs-14);
}

/* 证据流：一行一个条目。左 = 内容，右 = 把握度。点开看依据。 */
.ev {
  display: flex;
  flex-direction: column;
}

.ev__row {
  padding: var(--sp-3) 0;
}

.ev__row:first-child {
  padding-top: 0;
}

.ev__row:last-child {
  padding-bottom: 0;
}

.ev__head {
  width: 100%;
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr) auto;
  align-items: baseline;
  gap: var(--sp-3);
  text-align: left;
}

.ev__head--todo {
  align-items: center;
}

.ev__label {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.ev__value {
  font-size: var(--fs-14);
  min-width: 0;
}

.ev__conf {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  white-space: nowrap;
}

.ev__detail {
  margin-top: var(--sp-3);
  margin-left: calc(88px + var(--sp-3));
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
}

.ev__dl {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ev__dlrow {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: var(--sp-3);
  font-size: var(--fs-12);
}

.ev__dlrow dt {
  color: var(--c-text-3);
}

.ev__dlrow dd {
  margin: 0;
  color: var(--c-text-2);
}

.ev__foot {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.ev__empty {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  padding: var(--sp-2) 0;
}

/* 取不到的：用浅底，不用彩色竖条（竖条是"用装饰表达层级"） */
.blocked__item {
  margin-top: var(--sp-2);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-attention-weak);
}

.blocked__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

.blocked__why {
  margin-top: 2px;
  font-size: var(--fs-12);
  color: var(--c-text-2);
  line-height: var(--lh-snug);
}

/* 核验三步 */
.verify {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.verify__step {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-snug);
}
</style>
