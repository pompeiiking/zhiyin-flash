<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { demo } from '../store'
import { STUDENT } from '../data/student'

/**
 * 门户。
 *
 * 结构（自上而下）：
 *   两侧竖排四句口号 ｜ 品牌 → 主张 → 宣传词 → 定位 → 一个入口 → 成本 ｜ 四件事说明
 *
 * 关于那四句 —— 评审要求里本来就写着「核心口号参考"持续陪伴、专业牵引、行动落地、心想事成"」，
 * 上一轮我把它当成装饰删了，是错的：它是产品的四条承诺，属于内容。
 * 现在做成**两侧竖排**（左：持续陪伴 / 专业牵引；右：行动落地 / 心想事成）：
 *   · 竖排是中文原有的排法，放在一个中国高校的产品上不突兀；
 *   · 它正好用掉左右两条空白带（评审说"两侧还是有点空"）；
 *   · 不占正文的注意力 —— 它是"氛围里的承诺"，不是要你读的第一行。
 *
 * 背景**全部是静态图形，没有一处持续运动**（设计语言 §5 反例表 / §7.3）：
 *   1. 两片品牌色光晕（左上 / 右下），只负责"底不空"
 *   2. 一片居中的光晕，把中段托起来
 *   3. 版面竖线格，静态（透明度写死 0.3）
 *   4. 两条极淡的路线（SVG path），作为构图的一部分
 *   5. 颗粒纹理（压在文字底下，本来就是静止的）
 *
 * 上一版这里是"氛围海报"：光晕 22s/30s 无限漂移、网格 12s 呼吸、一道 12s 扫光、
 * 三个节点沿路径跑 SMIL animateMotion —— 全站最典型的"吵不是活"。
 * 现在只保留图形、撤掉运动：门户是宣传面，静图就是它的完整形态，
 * 动起来反而不承载任何信息（看的人答不出"这里发生了什么"）。
 * 唯一的例外是"删掉即没有意义"的扫光带，整层删除（见交付说明）。
 */

const router = useRouter()
const route = useRoute()

function start() {
  if (demo.state.authed) router.push('/chat')
  else router.push({ path: '/', query: { ...route.query, signin: '1' } })
}

/** 产品的四条承诺，一左一右 */
const LEFT_WORDS = ['持续陪伴', '专业牵引']
const RIGHT_WORDS = ['行动落地', '心想事成']

/**
 * 四件事：把产品真正的区别写出来。
 *
 * 用 4 字名词短语作标题（与两侧竖排的四字口号同一套语言），下面各配一句**书面语**。
 * 上一版这里全是口语（"答不上来可以跳过""少一样就不推给你""始终在你手上"）——
 * 产品内页该用生活化口吻（设计文档 7.4 是这么定的），但**门户是宣传面**，
 * 口语放在这里会显得不郑重。所以门户与内页用两套语气，这是有意的。
 */
const what = [
  {
    title: '一次一问',
    body: '每次只提出一个问题，答不上来可以跳过，无需提前准备简历。',
  },
  {
    title: '结论有据',
    body: '每条结论都注明依据：来自哪句话、哪条记录、哪份岗位要求，以及把握程度。',
  },
  {
    title: '每天一件',
    body: '每天只安排一件具体行动，并说明它需要多久、为什么是现在。',
  },
  {
    title: '选择自主',
    body: '只呈现各方向的差别与风险，不替你做选择；改选随时可行。',
  },
]
</script>

<template>
  <div class="portal">
    <div class="bg" aria-hidden="true">
      <div class="bg__glow bg__glow--a" />
      <div class="bg__glow bg__glow--c" />
      <div class="bg__glow bg__glow--b" />

      <!--
        两条路线：纯粹的静态构图，不再有沿路径移动的节点。
        上一版这里挂了三个 `<animateMotion>`（24s / 38s / 31s 无限循环），
        是整页最贵也最没信息量的动效 —— 节点在跑，但没人知道它在跑什么。
        现在只留两条曲线（`<use>`），它们撑住下部构图；节点连同心圆一起删掉：
        没有运动的圆点落在线上，读起来只是一个来路不明的斑点。
      -->
      <svg class="bg__paths" viewBox="0 0 1200 700" preserveAspectRatio="xMidYMid slice">
        <defs>
          <!--
            两条曲线必须**整条都在通栏之上**：上一版下面那条起点 y=692，
            越过了通栏顶边（约 643），于是它从通栏边缘冒出来 —— 看着就是"断掉的曲线"。
            现在两条的 y 都在 310–615 之间，通栏顶边之上留出余量。
            起点 x=-200、终点 x=1320 都在可视区之外（slice 居中裁切后可视约 90–1109），
            所以两端都是从屏幕外进来的，不会有突兀的断头。
          -->
          <path id="zp1" d="M-200,520 C 180,470 360,545 640,450 S 1000,345 1320,310" />
          <path id="zp2" d="M-200,600 C 200,575 420,615 740,520 S 1020,435 1320,420" />
        </defs>
        <use class="bg__curve" href="#zp1" />
        <use class="bg__curve bg__curve--dim" href="#zp2" />
      </svg>

      <div class="bg__grid" />
      <div class="bg__grain" />
    </div>

    <!-- 两侧竖排的四句承诺 -->
    <div class="sides" aria-hidden="true">
      <div class="side side--left">
        <p v-for="w in LEFT_WORDS" :key="w" class="side__word">{{ w }}</p>
      </div>
      <div class="side side--right">
        <p v-for="w in RIGHT_WORDS" :key="w" class="side__word">{{ w }}</p>
      </div>
    </div>

    <header class="top">
      <!-- 品牌回左上角：这是全页最先被扫到的位置，存在感靠位置拿，不靠字号 -->
      <div class="top__brand">
        <span class="top__mark" aria-hidden="true" />
        <span class="top__name">职引</span>
        <span class="top__divider" />
        <span class="top__context">{{ STUDENT.school }} · 生涯规划与就业指导</span>
      </div>
      <div class="pc-controls"><slot name="portal-switch" /><RouterLink v-if="demo.state.authed" class="top__account" to="/chat"><span class="pc-account-name">{{ STUDENT.name }} · </span>进入</RouterLink><button v-else class="top__login" @click="start">登录</button></div>
    </header>

    <main class="main">
      <section class="hero">
        <!--
          横排一行（评审要求）。两行改一行会让顶部重新变成"一道横条"，
          所以字号收到 74px —— 一行 666px 宽，明显窄于容器 1160px，
          读起来仍是"一簇字"而不是"一条线"；底部通栏那道横也继续压着页面最底边，
          不参与中部构图。
        -->
        <h1 class="hero__headline">问出方向，一路陪你</h1>

        <p class="hero__pitch">专业选择、岗位选择、行动计划，一件一件问清楚</p>

        <p class="hero__what">
          面向大学生的生涯规划与就业指导平台。以对话了解你，生成带依据的报告，
          据此每天安排一件具体的事。
        </p>

        <button class="hero__cta" @click="start">开始第一个问题</button>

        <p class="hero__cost">
          首次约 5 分钟 · 无需填表 · 可随时中止 · 回答仅用于生成你自己的报告
        </p>
      </section>
    </main>

    <!--
      四件事放在**贴边的通栏**里，而不是居中竖列底下的一个块。
      这是这一版避免"土"字的关键：居中的竖轴没办法不要（内容就是中轴对称的），
      所以只能让"别的东西"不构成第二道横 —— 通栏有底色、左右到边、贴着页面底部，
      它读作"页面的底边"，而不是读作版面上的一笔横。
    -->
    <section class="band" aria-label="它具体怎么帮你">
      <div class="band__inner">
        <ul class="band__list">
          <li v-for="w in what" :key="w.title" class="item">
            <p class="item__title">{{ w.title }}</p>
            <p class="item__body">{{ w.body }}</p>
          </li>
        </ul>
      </div>
    </section>

    <!--
      门户**只有一个入口**（评审要求）：这里不再放「设计规范」链接。
      规范页仍在 `#/spec`，评审直接敲 URL 就能打开（README 里也写了），
      但它不该在门户上多出第二个可点的东西 —— 门户只回答"从哪开始"。
    -->
    <footer class="foot">
      <span class="foot__note">演示环境 · 数据为预置内容，页面交互真实可用</span>
    </footer>
  </div>
</template>

<style scoped>
.portal {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--portal-bg);
  overflow: hidden;
}

/* ===========================================================================
 * 背景
 * ======================================================================== */
.bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.bg__glow {
  position: absolute;
  background: var(--hero-glow);
  /* 模糊掉边缘：加了模糊之后，它读起来才是"一片光"，而不是"一块浅蓝的斑"。
     模糊半径要比光斑本身小一个量级，否则会糊成一片灰。 */
  filter: blur(60px);
}

/* 两片光晕各有位置，没有动画 —— 它们曾经 22s / 30s 交替漂移（交替的周期是"一眼看出在放动画"），
   现在停在各自的静态位置上；构图（左上 / 右下 + 中间托底）原样保留。 */
.bg__glow--a {
  left: -14%;
  top: -14%;
  width: 1060px;
  height: 700px;
}

.bg__glow--b {
  right: -18%;
  bottom: -18%;
  width: 940px;
  height: 640px;
  opacity: 0.85;
}

/* 居中那片本来就不漂移：前两片在左上与右下，中间一条会是纯白，视觉上就成了"上下两块空" */
.bg__glow--c {
  left: 50%;
  top: 26%;
  width: 1240px;
  height: 640px;
  transform: translateX(-50%);
}

/* 路径：极淡，只做"这条路一直在"的暗示，不抢文字。现在整条线是静止的。
   沿路径跑的三个节点（.bg__node*）与它们的 animateMotion 已删除。 */
.bg__paths {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.bg__curve {
  fill: none;
  stroke: var(--c-border-strong);
  stroke-width: 1;
  opacity: 0.75;
}

.bg__curve--dim {
  opacity: 0.45;
}

/* 版面竖线格（思路取自 designeer 清单里 Fffuel 的 ooorganize）。
   上一版这里 12s 呼吸（opacity 0.2↔0.4）—— 背景"活着"最省的一种动法，但**它仍然不传达信息**，
   属于设计语言 §5 点名的"持续背景运动"。现在透明度固定在原区间的中值 0.3。 */
.bg__grid {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    to right,
    var(--c-border) 0 1px,
    transparent 1px 280px
  );
  -webkit-mask-image: radial-gradient(ellipse 74% 68% at 50% 44%, #000 26%, transparent 100%);
  mask-image: radial-gradient(ellipse 74% 68% at 50% 44%, #000 26%, transparent 100%);
  opacity: 0.3;
}

/* 这里原本是一道 12s 从左到右的扫光带（.bg__sweep + @keyframes sweep）。
   它的存在意义**完全依赖运动**：静止时它只是一块斜的白色蒙版，盖在文字上只会让人以为屏幕脏了，
   所以整层删除，而不是"留在原地不动"。 */

/* 颗粒（思路取自 Fffuel 的 nnnoise）。**本来就是静止的**，不属于禁令范围，原样保留：
   它压在文字底下，动起来字会发飘。 */
.bg__grain {
  position: absolute;
  inset: 0;
  opacity: 0.5;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.045'/%3E%3C/svg%3E");
}

/* ===========================================================================
 * 两侧竖排的四句承诺
 * ======================================================================== */
.sides {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.side {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}

.side--left {
  left: clamp(20px, 3vw, 56px);
}

.side--right {
  right: clamp(20px, 3vw, 56px);
  align-items: flex-end;
}

/* 竖排：中文原有的排法。放在一个高校的产品上不突兀，
   而且正好用掉左右两条空白带 —— 它是氛围里的承诺，不抢正文，但也不该轻到看不见。
   不加上下边框：加了每条都像一根被封口的短竖条，反而更像版面上的笔画。 */
.side__word {
  writing-mode: vertical-rl;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  letter-spacing: 0.45em;
  /* 用 --c-text-3 而不是 --c-text-4：后者在令牌注释里写着"仅图标/分隔符，不当文字用"，
     拿它排 14px 的中文是越界（虽然肉眼能看见，但白底对比度只有 2.5:1）。
     text-3 对纸面 5.36:1，过 AA。 */
  color: var(--c-text-3);
}

/* 横向空间不够时收起 —— 竖排挤内容比留白更糟。断点见文件末尾（统一为 1120px）。 */

/* ===========================================================================
 * 顶栏
 * ======================================================================== */
.top {
  position: relative;
  /* 3 而不是 2：`.main` 与 `.band` 都是 `z-index: 2`，DOM 里排在 `.top` 之后，
     于是同层里后来的赢 —— 顶栏里 slot 的「演示设置」下拉（PortalView 给的 z-index:10，
     但它在 `.top` 这个层叠上下文里）会被 `.main` 盖住，按钮点不动。抬一层即可。 */
  z-index: 3;
  height: var(--w-topbar);
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: 0 var(--sp-6);
}

.top__brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.pc-controls { display: flex; align-items: center; gap: 24px; flex: none; }

.top__mark {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--brand-stripe);
}

.top__name {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.22em;
}

.top__divider {
  width: 1px;
  height: 12px;
  margin: 0 var(--sp-2);
  background: var(--c-border-strong);
}

.top__context {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.top__account,
.top__login {
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.top__login {
  padding: 0 var(--sp-3);
  height: var(--btn-h-sm);
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: var(--btn-radius);
  transition:
    border-color var(--dur-1) ease,
    color var(--dur-1) ease;
}

@media (hover: hover) and (pointer: fine) {
  .top__login:hover {
    border-color: var(--c-primary);
    color: var(--c-primary);
  }
}

/* ===========================================================================
 * 主区
 * ======================================================================== */
.main {
  position: relative;
  z-index: 2;
  flex: 1;
  width: 100%;
  max-width: 1160px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: var(--sp-4) var(--sp-6) var(--sp-5);
}

.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.hero__headline {
  /* 一行排下"问出方向，一路陪你"（9 个字符位）：4.6vw 在 1600 屏上约 74px，
     净宽 666px，容器 1160px —— 留得住两边的余量，不会顶到边。 */
  font-size: clamp(28px, 4.6vw, 74px);
  font-weight: var(--fw-semibold);
  line-height: 1.15;
  letter-spacing: -0.02em;
}

/* 宣传词：解决"这件事对我意味着什么" */
.hero__pitch {
  margin-top: var(--sp-4);
  font-size: clamp(16px, 1.5vw, 21px);
  font-weight: var(--fw-medium);
  color: var(--c-text);
  letter-spacing: 0.01em;
}

/* 定位：解决"这是什么、给谁用" */
.hero__what {
  margin-top: var(--sp-5);
  max-width: 34em;
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: 1.85;
}

.hero__cta {
  margin-top: var(--sp-6);
  height: 52px;
  padding: 0 var(--sp-9);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  box-shadow: var(--e-2);
  transition:
    background-color var(--dur-1) ease,
    transform var(--dur-1) var(--ease-out),
    box-shadow var(--dur-1) ease;
}

.hero__cta:active {
  transform: scale(var(--btn-press));
}

@media (hover: hover) and (pointer: fine) {
  .hero__cta:hover {
    background: var(--c-primary-hover);
    box-shadow: var(--e-3);
  }
}

.hero__cost {
  margin-top: var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* ===========================================================================
 * 四件事 · 贴边通栏
 * ---------------------------------------------------------------------------
 * 它不是版面上的一笔横，而是"页面的底边"：有底色、左右到边、贴着底部。
 * 居中的竖轴没法不要（内容就是中轴对称的），所以只能让第二道横**不像横**。
 * ======================================================================== */
.band {
  /* 必须有定位：.bg 是绝对定位元素，会盖在所有未定位的块级元素上面 ——
     少了这两行，背景的两条路线会画在通栏之上，横穿"一次一问"那一段。 */
  position: relative;
  z-index: 2;
  flex: none;
  background: var(--c-surface-2);
  border-top: var(--bw-1) solid var(--c-border);
}

.band__inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: var(--sp-5) var(--sp-6);
}

.band__list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-5);
}

.item__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text);
  line-height: 1.5;
}

.item__body {
  margin-top: var(--sp-1);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: 1.75;
}

/* ===========================================================================
 * 页脚
 * ======================================================================== */
.foot {
  position: relative;
  z-index: 2;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-4);
  padding: 0 var(--sp-6) var(--sp-6);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.foot__note {
  color: var(--c-text-3);
}

/* ===========================================================================
 * 减少动效 —— 降级到"可用形态"，不是"关掉就白一块"
 * ---------------------------------------------------------------------------
 * 上一版这里是 `.bg { display: none }`，理由写得挺诚实（"SMIL 没法用 CSS 停"），
 * 但结果是：用户在系统里开了"减少动态效果"，看到的是一个**光秃秃的静态排版**——
 * 背景层次、构图、两条路线全没了。设计语言 §7.4 明确禁止这种做法。
 *
 * 现在整页**本来就没有持续运动**（光晕 / 网格 / 路线 / 颗粒全是静止图形），
 * 所以减少动效下不需要关掉任何东西：只需要把"交互与一次性"的动效停掉，静态形态原样保留。
 * 于是 reduced-motion 与正常模式的观感一致，页面仍然是一个完整的门户。
 * ======================================================================== */
@media (prefers-reduced-motion: reduce) {
  .top__login,
  .hero__cta {
    transition: none;
  }

  .hero__cta:active {
    transform: none;
  }
}

/* ===========================================================================
 * 断点 —— 只有 1120 / 768 两档（项目契约 §2.7）
 * ---------------------------------------------------------------------------
 * 上一版是 1180 / 1000 / 760 / 600 四档，其中 1000 与 600 并不承担独立职责：
 *   · 1180（收起两侧竖排）→ 1120，与全站宽屏断点对齐
 *   · 1000（通栏 4→2 列）→ 1120，和"收起竖排"同一时刻发生：窄了就先减列、再收竖排
 *   · 760 / 600（窄屏顶栏收信息、通栏 1 列）→ 768，合并成一档
 * 于是四档收敛为两档。注意：workspace.css 已经按 1120 / 768 走（min-width:1120 与 max-width:1119），
 * 本页与之对齐；PortalProposalView.vue 还是 1100 / 760 / 360，那一份不归本次改动，见交付说明。
 * ======================================================================== */
@media (max-width: 1120px) {
  .sides {
    display: none;
  }

  .band__list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--sp-5) var(--sp-4);
  }
}

@media (max-width: 768px) {
  .pc-controls {
    gap: 10px;
  }

  .pc-account-name,
  .top__context,
  .top__divider {
    display: none;
  }

  .band__list {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
