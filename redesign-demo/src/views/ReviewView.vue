<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'
import { GUIDES } from '../data/copy'
import { REVIEW_CONCLUSION, REVIEW_ITEMS, INTERVENTION } from '../data/student'
import GuideNote from '../components/GuideNote.vue'
import { useCountUp } from '../lib/motion'

/**
 * 复盘记录 —— **文章页 · blameless 变体**（2026-10-11 重做）。
 *
 * 上一版是"左索引栏 + 主块时间线 + 次块归因 + 两块并排"。它的问题是**读起来像问责**：
 * 一上来就是"没做成的那件归到哪儿"和时间线，没有任何"你做到了什么"。
 * 而 Google SRE 的 blameless postmortem 把顺序定得很清楚：
 * **先看做到了什么，再看归因，最后才是行动** —— 因为
 * "you can't fix people, but you can fix systems and processes"。
 *
 * 所以这一页换了语法：不再是"方块 + 索引栏"，而是**一节一节往下读的文章**，
 * 而且每节的标题写成一句**判断**（"这一周你动过 46% 的手"），不是名词（"概览"）
 * —— 这是"报告"与"报表"的分界。基元在 base.css 的 `.article` / `.sec` 里。
 *
 * 归因仍然只归到三处：任务太大 / 方法不对 / 方向要重估 —— **不归到人**。
 * 这是这个产品与"打卡 App"的分界：没完成不等于你不自律。
 */

const scenario = computed(() => demo.use.scenario.value)

const ATTRIBUTIONS = ['任务太大', '方法不对', '方向要重估'] as const

const resultLabel: Record<string, string> = {
  done: '做完了',
  partial: '做了一半',
  missed: '没做成',
}

/** "你做到了什么"直接取自 REVIEW_ITEMS，不新造内容 */
const didDone = computed(() => REVIEW_ITEMS.filter((r) => r.result === 'done'))

/** 没做成的那件（归因的对象）。没有就是没有 —— 页面不假装有。 */
const missed = computed(() => REVIEW_ITEMS.find((r) => r.result === 'missed') ?? null)
const currentAttr = computed(() => missed.value?.attribution ?? null)

const rate = computed(() => Math.round((didDone.value.length / REVIEW_ITEMS.length) * 100))

/** 百分比滚动：这一周"动了多少手"是这一屏最该被看见的一个数 */
const { shown: rateShown } = useCountUp(rate)
</script>

<template>
  <div class="page">
    <header class="page__head">
      <h1 class="page__title">复盘记录</h1>
      <p class="page__sub">
        {{ scenario.grade }}这一轮要看的重点：{{ scenario.reviewFocus }}。
        归因归到任务、方法或方向，不归到人。
      </p>
      <RouterLink class="btn" to="/plan" style="margin-top: var(--sp-4)">回到计划</RouterLink>
    </header>

    <article class="article">
      <!-- ① 先看做到的。复盘不是问责 —— 这一节原来整页都没有。 -->
      <section class="sec">
        <h2 class="sec__title">这一周你动过 {{ Math.round(rateShown) }}% 的手</h2>
        <p class="sec__note">先看做完的，再看没做的。复盘是为了下一周好过，不是为了追责。</p>
        <ul class="did sec__body">
          <li v-for="r in didDone" :key="r.id" class="did__row">
            <span class="did__what">{{ r.what }}</span>
            <span class="t-note t-num-nowrap">{{ r.when }}</span>
          </li>
        </ul>
      </section>

      <!-- ② 归因：这一屏唯一要求用户表态的地方 -->
      <section class="sec">
        <h2 class="sec__title">没做成的那件，归到哪儿</h2>
        <p class="sec__note">
          三选一，界面不让你归到"我不行"。归因归事不归人 ——
          归到事上，下一步才有得改。
        </p>
        <div class="sec__body">
          <div class="attrs">
            <button
              v-for="a in ATTRIBUTIONS"
              :key="a"
              class="attr"
              :class="{ 'attr--on': currentAttr === a }"
            >
              <span class="attr__name">{{ a }}</span>
              <span class="attr__note">
                {{
                  a === '任务太大'
                    ? '一次要 40 分钟以上 —— 拆小就能做'
                    : a === '方法不对'
                      ? '做法本身不奏效 —— 换一种试'
                      : '方向要重估 —— 交回给判断方向的人'
                }}
              </span>
            </button>
          </div>
          <p class="conclusion">{{ REVIEW_CONCLUSION }}</p>
        </div>
      </section>

      <!-- ③ 事实：一行一个时间点，节点用加粗短语分节（SRE postmortem 的 timeline 语法） -->
      <section class="sec">
        <h2 class="sec__title">这一周发生了什么</h2>
        <p class="sec__note">只记事实与时间，不记评价。</p>
        <ol class="timeline stagger sec__body">
          <li v-for="r in REVIEW_ITEMS" :key="r.id" class="tl">
            <span class="tl__dot" :class="`tl__dot--${r.result}`" />
            <div class="tl__main">
              <div class="hstack hstack-2 between">
                <span class="tl__what">{{ r.what }}</span>
                <span class="t-note t-num-nowrap">{{ r.when }}</span>
              </div>
              <div class="hstack hstack-2" style="margin-top: 6px; flex-wrap: wrap">
                <span
                  class="chip"
                  :class="r.result === 'done' ? 'chip--done' : 'chip--attention'"
                >
                  {{ resultLabel[r.result] }}
                </span>
                <template v-if="r.attribution">
                  <span class="t-note">归到：</span>
                  <span class="chip chip--outline">{{ r.attribution }}</span>
                </template>
              </div>
            </div>
          </li>
        </ol>
      </section>

      <!-- ④ 话术对照：成对两行，中间一条竖线。不做左右两个盒子。 -->
      <section class="sec">
        <h2 class="sec__title">同一件事，两种说法</h2>
        <p class="sec__note">停滞归到任务、方法或方向；不追究，也不假装没发生。</p>
        <div class="say sec__body">
          <div class="say__col say__col--no">
            <span class="say__tag">不这么说</span>
            <p>你已经三天没完成任务了，请注意自律。</p>
          </div>
          <div class="say__col say__col--yes">
            <span class="say__tag">这么说</span>
            <p>看你好几天没动，来问一句 —— 上次那条确实太大了，先做 5 分钟？</p>
          </div>
        </div>
      </section>

      <!-- ⑤ 干预参数：不是每次都要看，收起来（原生 details，键盘可达） -->
      <section class="sec">
        <details class="fold">
          <summary class="fold__sum">
            {{ INTERVENTION.host }} —— 能主动开口的只有这一个，受 {{ INTERVENTION.rules.length }} 条参数约束
          </summary>
          <div class="fold__body">
            <ul class="rules-list">
              <li v-for="r in INTERVENTION.rules" :key="r">{{ r }}</li>
            </ul>
            <button class="btn btn--sm" style="margin-top: var(--sp-4)" @click="demo.openIntervention()">
              看一次主动干预长什么样
            </button>
          </div>
        </details>
      </section>
    </article>

    <GuideNote gkey="review" :text="GUIDES.review" to="/home" to-label="回任务与计划" />
  </div>
</template>

<style scoped>
/* 做到了什么：一行一件事，靠留白分组，不逐行画线 */
.did {
  display: flex;
  flex-direction: column;
}

.did__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-3) 0;
}

.did__row:first-child {
  padding-top: 0;
}

.did__row:last-child {
  padding-bottom: 0;
}

.did__what {
  font-size: var(--fs-14);
}

/* 时间线：竖线与节点都只表达"有没有动过手" */
.timeline {
  position: relative;
  padding-left: var(--sp-5);
}

.timeline::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 6px;
  bottom: 6px;
  width: 1px;
  background: var(--c-border);
}

.tl {
  position: relative;
  padding: var(--sp-3) 0;
}

.tl__dot {
  position: absolute;
  left: calc(-1 * var(--sp-5) + 1px);
  top: 18px;
  width: 9px;
  height: 9px;
  border-radius: var(--r-pill);
  background: var(--c-text-4);
  box-shadow: 0 0 0 3px var(--c-surface);
}

.tl__dot--done {
  background: var(--c-done);
}

.tl__dot--partial {
  background: var(--c-attention);
}

.tl__dot--missed {
  background: var(--c-attention-strong);
}

.tl__what {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

/* 归因：三选一 */
.attrs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
}

.attr {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--sp-3);
  text-align: left;
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
  transition: border-color var(--mo-fast) var(--mo-ease);
}

.attr:hover {
  border-color: var(--c-border-strong);
}

.attr--on {
  border-color: var(--c-primary);
  background: var(--c-primary-weak);
}

.attr__name {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

.attr__note {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: 1.5;
}

.conclusion {
  margin-top: var(--sp-4);
  padding: var(--sp-4);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text);
  max-width: 34em;
}

/* 干预参数 */
.rules-list li {
  position: relative;
  padding: var(--sp-3) 0 var(--sp-3) var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-2);
}

.rules-list li:first-child {
  padding-top: 0;
}

.rules-list li:last-child {
  padding-bottom: 0;
}

.rules-list li::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 16px;
  width: 4px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--c-border-strong);
}

/* 话术对照：成对两行，中间一条 1px 竖线。左边降灰，右边正常字色。 */
.say {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}

.say__col {
  padding: 0 var(--sp-6);
  font-size: var(--fs-14);
  line-height: var(--lh-snug);
}

.say__col:first-child {
  padding-left: 0;
}

.say__col:last-child {
  padding-right: 0;
}

.say__col--no {
  color: var(--c-text-3);
  border-right: var(--bw-1) solid var(--c-border);
}

.say__tag {
  display: block;
  font-size: var(--fs-12);
  margin-bottom: var(--sp-2);
  color: var(--c-text-3);
}

@media (max-width: 1080px) {
  .attrs {
    grid-template-columns: minmax(0, 1fr);
  }

  .say {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-5);
  }

  .say__col {
    padding: 0;
  }

  .say__col--no {
    border-right: none;
    border-bottom: var(--bw-1) solid var(--c-border);
    padding-bottom: var(--sp-5);
  }
}
</style>
