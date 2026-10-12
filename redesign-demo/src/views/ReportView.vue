<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { FALLBACK_COPY, GUIDES } from '../data/copy'
import {
  DIRECTION_PLANS,
  REPORT_SECTIONS,
  REPORT_SUMMARY,
  REPORT_VERSIONS,
  SELF_RADAR,
  THRESHOLD_COMPARE,
} from '../data/student'
import GuideNote from '../components/GuideNote.vue'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'
import RadarChart from '../components/charts/RadarChart.vue'
import MeterRow from '../components/charts/MeterRow.vue'
import QuadrantChart from '../components/charts/QuadrantChart.vue'
import TrendLine from '../components/charts/TrendLine.vue'

/**
 * 你的报告。
 *
 * 三条不能破的口径：
 *   1. 三个分区用用户语言，不用维度名（7.4）
 *   2. L1 只给"结论一句 + 有多大把握 + 一句门槛解释"；分值、走势、来源全在 L2（7.4）
 *   3. citations 必填 —— 不带依据的产出过不了契约（第 6 幕）
 */

const sections = REPORT_SECTIONS
const versions = REPORT_VERSIONS
const currentVersion = computed(
  () => versions.find((v) => v.id === demo.state.reportVersion) ?? versions[0],
)

/** L2 展开：哪一条被点开了 */
const openDim = ref<string | null>(null)

const quadItems = computed(() =>
  DIRECTION_PLANS.map((d, i) => ({
    id: d.id,
    label: d.title,
    role: d.role,
    // 横轴 = 机会大小，纵轴 = 够得着的程度
    x: [72, 84, 40][i] ?? 50,
    y: [58, 44, 76][i] ?? 50,
  })),
)

const trendPoints = computed(() =>
  versions
    .slice()
    .reverse()
    .map((v) => ({ label: v.label.replace('（当前）', ''), value: v.fit })),
)

/** 打印 / 存成 PDF：导出功能开关关掉时按钮不出现，不灰着放一个点不动的按钮 */
function printReport() {
  window.print()
}

/** 变更说明：改选之后"还有几处跟着改"（第 7 幕） */
const selected = computed(() => demo.use.selectedDirection.value)
const previous = computed(() => demo.use.previousDirection.value)

/**
 * 这一页现在是一篇文章：结论 → 画像 → 三个分区 → 门槛 → 取舍 → 影响面。
 * 不再有索引栏，因此也没有"点一条只看那一块"的焦点状态 ——
 * 报告本来就是一份要通读的文件；藏起来的那部分，等于没写。
 * （顺带修掉一个真 bug：GuideNote 在这页原本渲染了两次。）
 */
</script>

<template>
  <div class="page">
    <header class="page__head">
      <div class="hstack hstack-3 between wrap">
        <div>
          <h1 class="page__title">评估报告</h1>
          <p class="page__sub">
            每条结论都写清楚它是怎么来的。分值、走势、来源默认收起来 —— 点开才出现。
          </p>
        </div>
        <div class="hstack hstack-2">
          <label class="version">
            <span class="t-label">版本</span>
            <select
              class="version__select"
              :value="demo.state.reportVersion"
              @change="demo.setReportVersion(($event.target as HTMLSelectElement).value)"
            >
              <option v-for="v in versions" :key="v.id" :value="v.id">{{ v.label }}</option>
            </select>
          </label>
          <button class="btn" @click="printReport">打印 / 存成 PDF</button>
        </div>
      </div>
    </header>

    <GuideNote gkey="report" :text="GUIDES.report" to="/path" to-label="看要做的取舍" />

    <article class="article">
      <!-- ① 结论：全页只出现一次，用引文语法（一条细竖线 + 大字），全宽。
             原来它被塞进 8 栏的方块里，比右侧矮一截 —— 下半截全是死白。 -->
      <section class="sec">
        <h2 class="sec__title">这一版的结论</h2>
        <p class="sec__note">
          {{ currentVersion.label }} · {{ currentVersion.at }} —— 结论段读的是那一版资产，不会每次重新生成。
        </p>
        <blockquote class="quote sec__body">{{ REPORT_SUMMARY }}</blockquote>
        <p class="quote__src">这一版补上了：{{ currentVersion.change }}</p>
      </section>

      <!-- ② 你是什么样的人：图与它的注解并排，两边都窄，图不再挤在 4 栏里 -->
      <section class="sec">
        <h2 class="sec__title">你是什么样的人</h2>
        <p class="sec__note">六条，分值是 L2，默认不显示数字以外的判断。</p>
        <div class="split2 sec__body">
          <div>
            <RadarChart :axes="SELF_RADAR" :size="300" :baseline="50" />
            <p class="sec__note" style="margin-top: var(--sp-3)">
              虚线是两条主攻方向的要求线（50 分）。落在虚线里面的，就是拖后腿的那一项。
            </p>
            <p class="sec__note">
              数据来源：学生档案的 {{ SELF_RADAR.length }} 项自评，对照两条主攻方向的要求线。
            </p>
          </div>
          <div>
            <h3 class="sub">第 1 版 → 这一版</h3>
            <p class="t-note" style="margin-top: var(--sp-2)">
              匹配度从 0.61 提到 {{ (currentVersion.fit / 100).toFixed(2) }}，
              靠的是补上画像与学籍核验，不是重新生成一遍。
            </p>
            <TrendLine :points="trendPoints" :highlight-index="trendPoints.length - 1" />
            <p class="sec__note" style="margin-top: var(--sp-2)">
              数据来源：报告第 1–3 版的匹配度快照（每次核验后重算）。
            </p>
            <ul class="versions">
              <li v-for="v in versions" :key="v.id" class="versions__item">
                <span class="versions__label">{{ v.label }}</span>
                <span class="t-note">{{ v.change }}</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- ③ 三个分区：分区标题是用户语言；每条维度＝结论一句 + 门槛一句 + 收起的 L2 -->
      <section class="sec">
        <h2 class="sec__title">你是什么样的人 / 外面是什么情况 / 你要做哪些取舍</h2>
        <p class="sec__note">分区标题是用户语言，不是维度名。每条结论都能点开看依据。</p>
        <div class="stack stack-5 sec__body">
          <div v-for="s in sections" :key="s.key" class="section">
            <h3 class="sub">{{ s.title }}</h3>

            <div v-for="d in s.dimensions" :key="d.key" class="dim">
              <div class="dim__head">
                <span class="dim__label">{{ d.label }}</span>
                <ConfidenceBadge :value="d.confidence" />
              </div>

              <!-- L1：结论一句 -->
              <p class="dim__conclusion">{{ d.conclusion }}</p>

              <!-- L1：门槛解释 —— 这份报告最值钱的一句话 -->
              <p v-if="d.threshold" class="dim__threshold">{{ d.threshold }}</p>

              <button
                class="dim__more"
                :aria-expanded="openDim === d.key"
                @click="openDim = openDim === d.key ? null : d.key"
              >
                {{ openDim === d.key ? '收起分值、走势与来源' : '看分值、走势与来源' }}
              </button>

              <!-- L2 -->
              <div v-if="openDim === d.key" class="dim__l2">
                <div v-if="d.score != null" class="dim__meter">
                  <MeterRow
                    :label="d.label"
                    :score="d.score"
                    :requirement="d.label === '呈现能力' ? 50 : undefined"
                  />
                </div>
                <div class="dim__evidence">
                  <p class="t-label">依据（点开任何一条结论，都能看到它依据的是什么）</p>
                  <ul class="evidence">
                    <li v-for="e in d.evidence" :key="e">{{ e }}</li>
                  </ul>
                  <p class="t-note" style="margin-top: var(--sp-2)">
                    用法与理论引用：{{ '生涯建构理论 · 岗位门槛比对' }} —— 点开可查。
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ④ 门槛：一个数字列，不写成"建议提升" -->
      <section class="sec">
        <h2 class="sec__title">离门槛差几分</h2>
        <p class="sec__note">
          主攻方向给你定的三条硬要求 —— 差 4 分和差 20 分，不是一回事。
        </p>
        <div class="stack stack-4 sec__body">
          <MeterRow
            v-for="t in THRESHOLD_COMPARE"
            :key="t.label"
            :label="t.label"
            :score="t.mine"
            :requirement="t.requirement"
          />
          <p class="t-note">
            门槛解释不写"建议提升"这种话 —— 写"差 4 分，是补起来最快的一个"，用户才知道先做哪件。
          </p>
        </div>
      </section>

      <!-- ⑤ 取舍：图与三条并排 -->
      <section class="sec">
        <h2 class="sec__title">三条方向的取舍</h2>
        <p class="sec__note">系统只比差别，不替你选 —— 产出契约里根本没有"选择"字段。</p>
        <div class="two-col sec__body">
          <QuadrantChart
            :items="quadItems"
            :selected-id="demo.state.selectedDirectionId"
            @pick="demo.chooseDirection"
          />
          <div class="stack stack-3">
            <article
              v-for="d in DIRECTION_PLANS"
              :key="d.id"
              class="plan"
              :class="{ 'plan--on': demo.state.selectedDirectionId === d.id }"
            >
              <div class="hstack hstack-2 between">
                <span class="chip" :class="d.role === '主攻' ? 'chip--primary' : 'chip--outline'">
                  {{ d.role }}
                </span>
                <ConfidenceBadge :value="d.fit" />
              </div>
              <h3 class="plan__title">{{ d.title }}</h3>
              <ul class="plan__evidence">
                <li v-for="e in d.evidence" :key="e">{{ e }}</li>
              </ul>
              <p class="plan__risk">风险：{{ d.risk }}</p>
              <button
                class="btn btn--sm"
                :class="demo.state.selectedDirectionId === d.id ? '' : 'btn--primary'"
                :disabled="demo.state.selectedDirectionId === d.id"
                @click="demo.chooseDirection(d.id)"
              >
                {{ demo.state.selectedDirectionId === d.id ? '已选为' + d.role : '选它作为' + d.role }}
              </button>
            </article>
            <p class="t-note">
              产出契约里根本没有"选择"字段 —— 选不选、选哪个，始终在你手上。
            </p>
          </div>
        </div>
      </section>

      <!-- ⑥ 影响面：标题本身就是结论（几处 / 还没选） -->
      <section class="sec">
        <h2 class="sec__title">
          {{ selected ? `改选会牵动 ${selected.ripple} 处，其余原样` : '还没选方向' }}
        </h2>
        <p class="sec__note">
          {{ selected ? '"先放着"也是一个选项 —— 推迟也是决定。' : '报告不会预填内容：没生成的部分会写清原因，而不是摆一个空盒子。' }}
        </p>

        <div class="sec__body">
          <template v-if="selected">
            <p v-if="previous" class="change">
              从「{{ previous.title }}」改选为「{{ selected.title }}」。只重算了受影响的片段，其余原样。
            </p>
            <p v-else class="change">已选定「{{ selected.title }}」。改选零成本 —— 随时可以换。</p>
            <ul class="ripple">
              <li v-for="r in selected.ripplePoints" :key="r">{{ r }}</li>
            </ul>
          </template>
          <p v-else class="callout callout--attention">{{ FALLBACK_COPY.mock }}</p>
        </div>
      </section>
    </article>
  </div>
</template>

<style scoped>
/* 结论：引文语法 —— 一条细竖线 + 更大的字。**一页只用一次**
   （GOV.UK Inset text：用多了就不灵了）。1px 是线，不是装饰性色条。 */
.quote {
  margin: 0;
  padding-left: var(--sp-5);
  border-left: var(--bw-1) solid var(--c-border-strong);
  font-size: var(--fs-20);
  line-height: var(--lh-snug);
  letter-spacing: -0.008em;
  max-width: 34em;
}

.quote__src {
  margin-top: var(--sp-4);
  padding-left: var(--sp-5);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* 图与注解并排：两边都窄。原来雷达图被挤在 4 栏（≈250px）里，读不出来。 */
.split2 {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-7);
  align-items: start;
}

.sub {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
}

@media (max-width: 1080px) {
  .split2 {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* 明细块的标题行：块自己已经有内距，标题不再缩进第二次 */
.detail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 0 0 var(--sp-3);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.version {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.version__select {
  height: var(--btn-h-md);
  padding: 0 var(--sp-3);
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: var(--r-md);
  background: var(--c-surface);
  font-size: var(--fs-14);
}

.summary {
  border-left: 3px solid var(--c-primary);
}

.summary__text {
  margin-top: var(--sp-4);
  font-size: var(--fs-14);
  line-height: var(--lh-relaxed);
  color: var(--c-text);
}

.summary__foot {
  margin-top: var(--sp-4);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
  font-size: var(--fs-12);
  color: var(--c-text-2);
}

/* 分区与维度 */
.section__title {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  padding-bottom: var(--sp-2);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.dim {
  padding: var(--sp-4) 0;
  border-bottom: var(--bw-1) solid var(--c-border);
}

.dim:last-child {
  border-bottom: none;
}

.dim__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}

.dim__label {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  letter-spacing: 0.02em;
}

.dim__conclusion {
  margin-top: var(--sp-2);
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  line-height: var(--lh-snug);
}

.dim__threshold {
  margin-top: var(--sp-2);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-attention-weak);
  border-left: 3px solid var(--c-attention);
  font-size: var(--fs-14);
  color: var(--c-text);
  line-height: var(--lh-normal);
}

.dim__more {
  margin-top: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--c-primary);
}

.dim__more:hover {
  text-decoration: underline;
}

.dim__l2 {
  margin-top: var(--sp-3);
  padding: var(--sp-4);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
}

.dim__meter {
  max-width: 360px;
}

.dim__evidence {
  margin-top: var(--sp-4);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
}

.evidence {
  margin-top: var(--sp-2);
}

.evidence li {
  position: relative;
  padding-left: var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  line-height: 1.65;
}

.evidence li::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 9px;
  width: 4px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--c-primary);
}

/* 四象限与方案 */
.two-col {
  display: grid;
  grid-template-columns: minmax(0, 340px) minmax(0, 1fr);
  gap: var(--sp-5);
  align-items: start;
}

.plan {
  padding: var(--sp-3);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
}

.plan--on {
  border-color: var(--c-primary);
  background: var(--c-primary-weak);
}

.plan__title {
  margin-top: var(--sp-2);
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
}

.plan__evidence {
  margin-top: var(--sp-2);
}

.plan__evidence li {
  position: relative;
  padding-left: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  line-height: 1.6;
}

.plan__evidence li::before {
  content: '·';
  position: absolute;
  left: 2px;
}

.plan__risk {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-attention);
}

.plan .btn {
  margin-top: var(--sp-3);
}

/* 侧栏 */
.radar {
  display: flex;
  justify-content: center;
  margin: var(--sp-3) 0;
}

.versions {
  margin-top: var(--sp-4);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
}

.versions__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--sp-2) 0;
  border-bottom: var(--bw-1) solid var(--c-border);
}

.versions__item:last-child {
  border-bottom: none;
}

.versions__label {
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
}

.change {
  margin-top: var(--sp-3);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-snug);
}

.ripple {
  margin-top: var(--sp-3);
}

.ripple li {
  position: relative;
  padding: var(--sp-2) 0 var(--sp-2) var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  border-bottom: var(--bw-1) dashed var(--c-border);
}

.ripple li:last-child {
  border-bottom: none;
}

.ripple li::before {
  content: '↻';
  position: absolute;
  left: 0;
  color: var(--c-primary);
}

@media (max-width: 1080px) {
  .two-col {
    grid-template-columns: minmax(0, 1fr);
  }
}

</style>
