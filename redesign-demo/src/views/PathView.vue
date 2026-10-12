<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { SCENARIOS } from '../data/scenarios'
import { JOURNEY_STEPS } from '../data/copy'

/**
 * 大一到大四：场景化设计。
 *
 * 评审原话：「按一年级到四年级的不同使用场景设计内容，每个操作步骤配对应界面截图，
 * 直观展示产品使用路径」。
 *
 * 所以这一页做两件事：
 *   1. 四个年级各自的处境、要解决的事、任务卡、里程碑 —— 整套内容跟着换
 *   2. 一条七步操作路径，每一步配一张真实界面截图（截图由 scripts/shots.mjs 生成）
 */

const active = computed(() => SCENARIOS.find((s) => s.id === demo.state.grade) ?? SCENARIOS[2])

/** 七步操作路径：每一步落在哪个界面、用户在这里做什么 */
const PATH = [
  {
    step: '门户 · 选一件你现在最想解决的事',
    view: '门户',
    shot: 'portal.png',
    what: '不注册也能看：主张、成本（5 分钟 / 0 张表 / 随时停）、隐私说明都在首屏。',
    where: '说的和做的同一处：主张下面就放任务卡组，选一张直接进对话。',
  },
  {
    step: '对话 · 一次只问一个问题',
    view: '对话',
    shot: 'chat.png',
    what: '能用点选项就不让人打字；答不上来可以跳过。',
    where: '换主理时有交接卡：谁接手、凭什么、为什么，三件事齐全。',
  },
  {
    step: '学生档案 · 每条都能看到依据与把握程度',
    view: '学生档案',
    shot: 'profile.png',
    what: '每一条都标了来源（你说的 / 学校档案 / 行为记录）与把握度。',
    where: '还差几条、去哪取、取不到为什么，全写在明面上。',
  },
  {
    step: '评估报告 · 结论带门槛解释',
    view: '评估报告',
    shot: 'report.png',
    what: 'L1 只给结论一句 + 把握 + 门槛解释，分值依据点开才出现。',
    where: '"差 4 分，是补起来最快的一个" —— 报告最值钱的就是这一句人话。',
  },
  {
    step: '选一个方向 · 系统不替你选',
    view: '评估报告',
    shot: 'report-directions.png',
    what: '主攻 / 平行 / 保底，各带契合依据与主要风险。',
    where: '改选零成本：只重算受影响的那几处，"还有几处跟着改"当场列出来。',
  },
  {
    step: '计划与行动 · 今天勾掉一件',
    view: '计划与行动',
    shot: 'plan.png',
    what: '每条任务三样齐全：什么 + 多久 + 为什么是现在。',
    where: '做不动可以点"改小"，当场拆到 5 分钟 —— 回退是设计好的。',
  },
  {
    step: '复盘记录 · 归因不归到人',
    view: '复盘记录',
    shot: 'review.png',
    what: '时间线 + 归因三选一：任务太大 / 方法不对 / 方向要重估。',
    where: '主动消息全产品只有"陪你推进的人"能发，且受三个参数约束。',
  },
]

/** 截图缺失时不要裂图：退回一个说明块 */
const broken = ref<Record<string, boolean>>({})

function onError(shot: string) {
  broken.value = { ...broken.value, [shot]: true }
}
</script>

<template>
  <div class="page">
    <header class="page__head">
      <h1 class="page__title">大一到大四</h1>
      <p class="page__sub">
        同一条产品动线，四个年级要解决的事不一样。切一次年级，任务卡、画像进度、里程碑、
        报告重点与复盘关注点整套跟着换；下面这张路径图说明每一步落在哪个界面上。
      </p>
    </header>

    <!-- 年级选择 -->
    <div class="grades">
      <button
        v-for="g in SCENARIOS"
        :key="g.id"
        class="gcard"
        :class="{ 'gcard--on': demo.state.grade === g.id }"
        @click="demo.setGrade(g.id)"
      >
        <span class="gcard__grade">{{ g.grade }}</span>
        <span class="gcard__focus">{{ g.focus }}</span>
        <span class="gcard__sit">{{ g.situation }}</span>
      </button>
    </div>

    <!-- 当前年级 -->
    <section class="card card--pad detail" style="margin-top: var(--sp-5)">
      <div class="hstack hstack-3 between wrap">
        <div>
          <span class="chip chip--primary">{{ active.grade }}的使用场景</span>
          <h2 class="detail__title">{{ active.focus }}</h2>
          <p class="detail__sit">{{ active.situation }}</p>
        </div>
        <div class="detail__next">
          <span class="t-label">现在最好先做</span>
          <p>{{ active.nextStep }}</p>
        </div>
      </div>

      <div class="detail__grid">
        <div class="detail__block">
          <p class="t-label">首页会出现的任务卡</p>
          <div class="hstack hstack-2 wrap" style="margin-top: 8px">
            <span v-for="t in active.taskCards" :key="t" class="chip chip--outline">{{ t }}</span>
          </div>
        </div>
        <div class="detail__block">
          <p class="t-label">这一年要达成的里程碑</p>
          <ul class="ms">
            <li v-for="m in active.milestones" :key="m.id" class="ms__item">
              <span class="ms__title">{{ m.title }}</span>
              <span class="ms__window">{{ m.window }}</span>
            </li>
          </ul>
        </div>
        <div class="detail__block">
          <p class="t-label">报告与复盘的重点</p>
          <p class="detail__line">报告先看：{{ active.reportFocus }}</p>
          <p class="detail__line">复盘重点：{{ active.reviewFocus }}</p>
          <p class="detail__line">这一年最常被问的一句：{{ active.probe }}</p>
        </div>
      </div>
    </section>

    <!-- 七步操作路径 + 界面截图 -->
    <section class="section">
      <div class="section__head">
        <h2 class="t-h2">操作路径：每一步落在哪个界面</h2>
        <p class="t-note">
          截图是这个演示工程自己的界面（在 {{ 'scripts/shots.mjs' }} 里用无头浏览器生成），
          不是设计稿 —— 你看到的和跑起来的完全一致。
        </p>
      </div>

      <ol class="steps-list">
        <li v-for="(p, i) in PATH" :key="p.step" class="pstep">
          <div class="pstep__info">
            <div class="pstep__no">{{ i + 1 }}</div>
            <h3 class="pstep__step">{{ p.step }}</h3>
            <p class="pstep__view">界面落点：{{ p.view }}</p>
            <p class="pstep__what">{{ p.what }}</p>
            <p class="pstep__where">设计要点：{{ p.where }}</p>
            <div v-if="i === 2" class="hstack hstack-2 wrap" style="margin-top: 10px">
              <span v-for="s in JOURNEY_STEPS" :key="s.key" class="chip chip--outline">{{ s.label }}</span>
            </div>
          </div>

          <figure class="pstep__shot">
            <img
              v-if="!broken[p.shot]"
              :src="`shots/${p.shot}`"
              :alt="`${p.step} 的界面截图`"
              loading="lazy"
              @error="onError(p.shot)"
            />
            <div v-else class="pstep__ph">
              <span class="chip chip--outline">截图待生成</span>
              <p class="t-note" style="margin-top: 8px">
                运行 <code class="code">node scripts/shots.mjs</code> 生成
                <code class="code">public/shots/{{ p.shot }}</code>
              </p>
            </div>
            <figcaption class="pstep__cap">{{ p.view }}</figcaption>
          </figure>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.grades {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-3);
}

.gcard {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-4);
  text-align: left;
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
  transition: border-color var(--mo-fast) var(--mo-ease);
}

.gcard:hover {
  border-color: var(--c-border-strong);
}

.gcard--on {
  border-color: var(--c-primary);
  background: var(--c-primary-weak);
}

.gcard__grade {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  color: var(--c-primary);
}

.gcard__focus {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

.gcard__sit {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: 1.5;
}

/* 详情 */
.detail__title {
  margin-top: var(--sp-3);
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
}

.detail__sit {
  margin-top: var(--sp-2);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  max-width: 30em;
}

.detail__next {
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
  max-width: 320px;
}

.detail__next p {
  margin-top: 4px;
  font-size: var(--fs-14);
  color: var(--c-text);
}

.detail__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-5);
  margin-top: var(--sp-5);
  padding-top: var(--sp-5);
  border-top: var(--bw-1) solid var(--c-border);
}

.detail__line {
  margin-top: var(--sp-2);
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.ms {
  margin-top: var(--sp-2);
}

.ms__item {
  display: flex;
  flex-direction: column;
  padding: var(--sp-2) 0;
  border-bottom: var(--bw-1) solid var(--c-border);
}

.ms__item:last-child {
  border-bottom: none;
}

.ms__title {
  font-size: var(--fs-14);
  color: var(--c-text);
}

.ms__window {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* 路径 */
.section {
  margin-top: var(--sp-8);
}

.section__head {
  margin-bottom: var(--sp-4);
}

.section__head .t-note {
  margin-top: var(--sp-2);
  max-width: 40em;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.pstep {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: var(--sp-5);
  padding: var(--sp-5);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
}

.pstep__no {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
}

.pstep__step {
  margin-top: var(--sp-3);
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
}

.pstep__view {
  margin-top: 4px;
  font-size: var(--fs-12);
  color: var(--c-primary);
}

.pstep__what {
  margin-top: var(--sp-3);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-normal);
}

.pstep__where {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

.pstep__shot {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.pstep__shot img {
  width: 100%;
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  display: block;
}

.pstep__ph {
  display: grid;
  place-items: center;
  align-content: center;
  min-height: 180px;
  border: var(--bw-1) dashed var(--c-border-strong);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  text-align: center;
  padding: var(--sp-4);
}

.code {
  font-family: var(--font-mono);
  font-size: var(--fs-12);
  padding: 1px 4px;
  border-radius: var(--r-sm);
  background: var(--c-surface-3);
  color: var(--c-text-2);
}

.pstep__cap {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

@media (max-width: 1080px) {
  .grades,
  .detail__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pstep {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .grades,
  .detail__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
