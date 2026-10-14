<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo } from '../store'
import { SCENARIOS } from '../data/scenarios'
import { JOURNEY_STEPS } from '../data/copy'
import SourceChip from '../components/SourceChip.vue'

/**
 * 大一到大四：场景化设计。
 *
 * 评审原话：「按一年级到四年级的不同使用场景设计内容，每个操作步骤配对应界面截图，
 * 直观展示产品使用路径」。
 *
 * 所以这一页做两件事：
 *   1. 四个年级各自的处境、要解决的事、任务卡、里程碑 —— 整套内容跟着换
 *   2. 一条七步操作路径，每一步配本轮实际浏览器截图
 */

const active = computed(() => SCENARIOS.find((s) => s.id === demo.state.grade) ?? SCENARIOS[2])

/** 七步操作路径：每一步落在哪个界面、用户在这里做什么 */
const PATH = [
  {
    step: '门户 · 开始咨询',
    view: '门户',
    shot: 'v7-portal.jpg',
    what: '门户展示服务说明、咨询示例和主要入口。',
    where: '点击主要入口或登录后直接进入咨询对话。',
  },
  {
    step: '对话 · 选择主题并补充信息',
    view: '对话',
    shot: 'v7-chat.jpg',
    what: '选择咨询主题或输入问题；材料、个人画像和成果按需查看。',
    where: '顾问交接显示接手人、原因与依据；长对话可返回最新消息。',
  },
  {
    step: '个人画像 · 查看信息来源与待补充项',
    view: '个人画像',
    shot: 'v7-profile.jpg',
    what: '按主题查看个人信息，用来源筛选和展开条目核对依据。',
    where: '待补充项与资料获取限制分别说明，已有信息支持更正。',
  },
  {
    step: '诊断报告 · 查看结果与支持依据',
    view: '诊断报告',
    shot: 'v7-report.jpg',
    what: '先看诊断结果与关键依据，再按章节核对分析和分值。',
    where: '版本选择进入历史记录，方向方案通过二级菜单独立访问。',
  },
  {
    step: '方向方案 · 比较并选择',
    view: '方向方案',
    shot: 'v7-directions.jpg',
    what: '逐项比较三个方向的依据与风险，选定候选后统一确认。',
    where: '改选后当场列出关联内容。本演示展示影响范围，尚未接入真实自动重算。',
  },
  {
    step: '计划与行动 · 执行当前任务',
    view: '行动计划',
    shot: 'v7-home.jpg',
    what: '优先任务突出当前行动，状态分组与执行概览同步更新。',
    where: '任务支持完成、恢复与拆分，保留来源和执行依据。',
  },
  {
    step: '复盘记录 · 分析执行与调整',
    view: '复盘记录',
    shot: 'v7-review.jpg',
    what: '结合执行时间线分析任务负担、方法和方向问题。',
    where: '依据归因查看调整建议，可添加任务或重新比较方向。',
  },
]

/** 截图缺失时不要裂图：退回一个说明块 */
const broken = ref<Record<string, boolean>>({})

/**
 * 七张截图的**拍摄日**（落点③溯源）。
 * 为什么是一个常量而不是逐条写：这一批就是同一天截的（见下方路径区标题下的那句话），
 * 逐条写七个一样的日期只会制造"它们可能不一样"的错觉。将来分批补截时，
 * 这里要改成按 step 记录 —— 那一天图注自然会跟着变。
 */
const SHOT_AT = '2026-10-13'

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

    <!-- =====================================================================
         落点③溯源 —— 文档页的每类说法都要能回到它的出处
         ---------------------------------------------------------------------
         这一页的"出处"不是用户数据，而是三样可以当场核对的东西：评审原话、
         预置示例文件、真实截图。三者性质不同（引用 / 外部文本 / 转录），
         所以用 SourceChip 的三支不同**形态**（不靠颜色）分开 —— 灰度打印下也要分得清。
         ② 组织权在这一页不适用，理由见交付说明（不硬塞一个假的分组控件）。
         ===================================================================== -->
    <section class="path-prov" aria-labelledby="path-prov-title">
      <h2 id="path-prov-title" class="t-h2">这一页的每条说法从哪来</h2>
      <ul class="path-prov__list">
        <li>
          <SourceChip label="评审要求原文" kind="citation" />
          <span>四个年级的内容按评审原话组织：「按一年级到四年级的不同使用场景设计内容，每个操作步骤配对应界面截图，直观展示产品使用路径」。</span>
        </li>
        <li>
          <SourceChip label="预置演示文案" kind="external" />
          <span>处境、要解决的事、任务卡与里程碑来自预置示例文件 <code class="code">src/data/scenarios.ts</code>，不是任何一位学生的真实数据。</span>
        </li>
        <li>
          <SourceChip label="实际浏览器预览" kind="transcript" :at="'2026-10-13'" />
          <span>下面七张截图是 2026-10-13 在本地跑起来之后截的，文件在 <code class="code">public/shots/</code>；每一步的图注写了它属于哪一步。</span>
        </li>
      </ul>
    </section>

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
          截图来自 2026-10-13 改造后的实际浏览器预览。门户进入对话，
          桌面通过二级侧栏切换功能，历史会话位于菜单下方；移动端保留底部导航。
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
                本轮截图文件为 <code class="code">public/shots/{{ p.shot }}</code>，
                可以直接进入对应页面查看。
              </p>
            </div>
            <figcaption class="pstep__cap">{{ p.view }} · <time :datetime="SHOT_AT">{{ SHOT_AT }} 截图</time></figcaption>
          </figure>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
/* ============================================================================
 * 落点③溯源 · "这一页的每条说法从哪来"
 * ---------------------------------------------------------------------------
 * 徽标占第一列、它解释的那句话占第二列：三行徽标的左边缘严格对齐，
 * 扫读时"看来源"是一条竖线，不用在行里找。
 * 列宽用 max-content 而不是固定值 —— 三枚徽标的宽度不同（「评审要求原文」最长），
 * 写死一个宽度会在窄屏把它裁掉。
 * ==========================================================================*/
.path-prov { margin-top: var(--sp-6); }

.path-prov__list {
  display: grid;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}

.path-prov__list li {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: baseline;
  gap: var(--sp-3);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-2);
}

@media (max-width: 640px) {
  .path-prov__list li {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-1);
  }
}

/* 图注里的拍摄日：与"界面落在哪一页"同一行，但比它安静一档 */
.pstep__cap time {
  color: var(--c-text-3);
}

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
