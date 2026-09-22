<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

/**
 * 画像还没有内容时，这一屏说什么。
 *
 * 【为什么它是一个**状态**，而不是"把三个模块都画成空的样子"】此前空画像进来看到
 * 的是完整的一页骨架：覆盖率 0% 的环、三档统计全 0、一句读法提示、搜索框、
 * 三个筛选、排序下拉，再加两句意思一样的"这里是空的" —— **全是零，还要用户自己
 * 从里面找出一句"到底该干嘛"**。真正该出现的只有两件事：这里为什么是空的，
 * 以及现在点哪里能让它有内容。
 *
 * 【这一稿：一张"还没写字的登记卡"】上一版是一小块居中虚线框，
 * 四周是几百像素的白 —— 打开面板看到的是"一大片空白中间钉着一张小纸"，
 * 那不是"空状态"，那是"没做完"。现在把它当作**海报**来排：
 *
 *   · 左边一块平涂的色块（这是全屏唯一的大色块），写"为什么是空的 + 现在做什么"；
 *   · 右边三步，把"画像是怎么长出来的"讲成一条时间线 ——
 *     空状态最该回答的不是"这里没有东西"，而是"东西是怎么来的"。
 *
 * 没有数字、没有筛选器：一个 0% 的环只会让人觉得自己做错了什么。
 */
const session = useSessionStore()

/** 三步：这一页是怎么从空到有的。它是解释，不是待办 —— 所以不给勾选框。 */
const STEPS = [
  { k: '说一句', d: '不用组织语言。这句话会变成画像里的第一条记录。' },
  { k: '我记一条', d: '记下的是"你说了什么 + 我凭什么这么理解"，两样都留着。' },
  { k: '你随时能追回去', d: '每一条都能点开看它的出处和把握程度，改没改过一目了然。' },
]
</script>

<template>
  <section class="blank">
    <!-- 左：这块纸是空的，以及现在该做什么 -->
    <div class="lead">
      <span class="sticker">空的</span>
      <h3 class="lead__t">还没有你的画像</h3>
      <p class="lead__p">
        画像不是你填表填出来的，是你聊出来的 —— 每说一句、每导一次，
        这里就多一条记录。
      </p>
      <div class="lead__acts">
        <button class="primary" type="button" @click="session.openOverlay('talk')">开始一次对话</button>
        <button class="ghost" type="button" @click="session.openOverlay('collect')">看看先补哪一条</button>
      </div>
      <!--
        一笔涂鸦：在这张卡右下角划一道没画好的箭头。
        它是这一页唯一的"手"，位置在色块内部，压不到任何一行字。
      -->
      <svg class="lead__scrawl" viewBox="0 0 120 70" fill="none" aria-hidden="true">
        <path d="M6 60 C 34 56, 52 40, 74 20" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" />
        <path d="M72 26 C 70 19, 76 16, 82 21" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        <path d="M30 64 L 60 52" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" opacity=".7" />
      </svg>
    </div>

    <!-- 右：这一页是怎么从空到有的 -->
    <ol class="steps">
      <li v-for="(s, i) in STEPS" :key="s.k">
        <span class="steps__n" aria-hidden="true">{{ i + 1 }}</span>
        <div class="steps__body">
          <span class="steps__k">{{ s.k }}</span>
          <span class="steps__d">{{ s.d }}</span>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
/*
 * 两栏：左色块，右三步。
 * 宽度跟着浮层走（1180 或 760 都可以），窄到放不下就落成一栏。
 */
.blank { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: var(--s5); align-items: start; }

.lead {
  position: relative;
  display: grid; gap: var(--s3); justify-items: start;
  /* 底部留 56px：给右下角那一笔涂鸦腾地方，不让它压到按钮行 */
  padding: var(--s6) var(--s5) 56px;
  /* 一块平涂的浅绿：这张纸还是空的，但它是"这一页" */
  background: var(--g-10);
  border-radius: var(--r-md);
  transform: rotate(-0.3deg);
  overflow: hidden;
}
.lead__t { font-size: 26px; line-height: 1.24; color: var(--ink-1); }
.lead__p { font-size: var(--t-sm); color: var(--ink-2); line-height: 1.8; max-width: 34ch; }
.lead__acts { display: flex; flex-wrap: wrap; gap: var(--s2); margin-top: var(--s2); }
.lead__scrawl {
  position: absolute; right: 14px; bottom: 10px;
  /* 收小一档：它是一笔批注，不是插图 —— 大了就变成"贴纸" */
  width: 84px; height: auto;
  color: var(--accent);
  opacity: 0.42;
  pointer-events: none;
}

.primary {
  display: inline-flex; align-items: center;
  min-height: 38px; padding: 8px var(--s4);
  border: 1px solid var(--accent);
  border-radius: var(--r-sm);
  background: var(--accent); color: var(--accent-ink);
  font-family: var(--font-display);
  font-size: var(--t-sm); line-height: 1.25;
  transition: background 160ms var(--ease-out), transform 160ms var(--ease-out);
}
.primary:hover { background: var(--accent-deep); transform: translateY(-1px); }

/* 次级入口：白纸上的一条墨线，不是又一块色 */
.ghost {
  display: inline-flex; align-items: center;
  min-height: 38px; padding: 8px var(--s4);
  border: 1px solid var(--line-3);
  border-radius: var(--r-sm);
  background: var(--n-1);
  font-size: var(--t-sm); font-weight: 500; color: var(--ink-2); line-height: 1.25;
  transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out);
}
.ghost:hover { border-color: var(--ink-1); color: var(--ink-1); }

/*
 * 三步：序号是**贴纸**（一小块平涂色 + 墨线），不是圆圈数字。
 * 每一步两行：一句动作 + 一句"这一步在解决什么疑问"。
 */
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s4); }
.steps li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--s3); align-items: start; }
.steps__n {
  display: grid; place-items: center;
  width: 26px; height: 26px;
  border: var(--bw) solid var(--line-3);
  border-radius: 5px;
  background: var(--mk-green-soft);
  font-family: var(--font-display);
  font-size: var(--t-xs);
  line-height: 1;
  transform: rotate(-2deg);
}
.steps li:nth-child(2) .steps__n { background: var(--mk-yellow-soft); transform: rotate(1.6deg); }
.steps li:nth-child(3) .steps__n { background: var(--mk-purple-soft); transform: rotate(-1deg); }
.steps__body { display: grid; gap: 3px; }
.steps__k { font-family: var(--font-display); font-size: var(--t-h4); line-height: 1.3; color: var(--ink-1); }
.steps__d { font-size: var(--t-sm); color: var(--ink-2); line-height: 1.75; }

@media (max-width: 900px) {
  .blank { grid-template-columns: minmax(0, 1fr); }
}
</style>
