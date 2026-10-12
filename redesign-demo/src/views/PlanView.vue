<script setup lang="ts">
import { computed } from 'vue'
import GuideNote from '../components/GuideNote.vue'
import { demo } from '../store'
import { GUIDES } from '../data/copy'
import { CALENDAR_MARKS } from '../data/student'

/**
 * 计划与行动。
 *
 * 注意：这个文件是**从构建产物重建**的（2026-10-11）。
 * 我在此之前用 Set-Content 往这个文件里改类名，而它正被 Vite 开发服务器占用：
 * Set-Content 会先截断再写，写入失败就留下了一个空文件。它未纳入 git，没有版本可回退，
 * 于是按 dist/assets/PlanView-*.js 与 PlanView-*.css 的分块逐字重建，
 * 并用 public/shots/plan.png 核对渲染结果。
 *
 * 重建后多做了一件事：按内页"一屏一个焦点"的口径给三张卡分了层 ——
 * 「本周要做的」是焦点（`focal`），另外两张退成安静的块（`quiet`）。
 */

const scenario = computed(() => demo.use.scenario.value)
const now = computed(() => demo.use.now.value)
const waiting = computed(() => demo.use.waiting.value)
const done = computed(() => demo.use.done.value)

/**
 * 三本账：按"谁放进来的"拆开。
 * 这是这个产品的一条边界 —— 系统建议的、从计划拆下来的、用户自己写的，不能混成一堆。
 */
const books = computed(() => [
  {
    key: '计划拆下来的',
    items: [...now.value, ...waiting.value, ...done.value].filter((t) => t.origin === '计划拆下来的'),
  },
  {
    key: '建议的',
    items: [...now.value, ...waiting.value].filter((t) => t.origin === '建议的'),
  },
  {
    key: '自己写的',
    items: [...now.value, ...waiting.value, ...done.value].filter((t) => t.origin === '自己写的'),
  },
])

/**
 * 关键节点日历。月份写死为 2026 年 10 月 —— 演示环境的数据就是这个月，
 * 不是"当前月份"，所以不能拿 new Date() 去算，否则演示会在别的日子穿帮。
 */
const YEAR = 2026
const MONTH = 10
const TODAY = 8

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

const cells = computed(() => {
  // 周一为一周之首：getDay() 的周日是 0，所以要 +6 再取模
  const lead = (new Date(YEAR, MONTH - 1, 1).getDay() + 6) % 7
  const days = new Date(YEAR, MONTH, 0).getDate()
  const out: { day: number | null; marks: typeof CALENDAR_MARKS }[] = []
  for (let i = 0; i < lead; i += 1) out.push({ day: null, marks: [] })
  for (let d = 1; d <= days; d += 1) out.push({ day: d, marks: CALENDAR_MARKS.filter((m) => m.day === d) })
  return out
})

function markClass(kind: string) {
  return kind === 'deadline' ? 'cal__mark--accent' : kind === 'review' ? 'cal__mark--muted' : ''
}

/**
 * 索引栏的目录。条目与右上角的计数全部取自这一页已有的数据：
 * 里程碑条数、本周任务条数、三本账的名字、本月关键节点的条数。
 */
/**
 * 账页没有索引栏，所以不再有"只看一块"的焦点状态 —— 五行全部显示。
 * 索引与内容合成了一件事：左边那格写"这一行是什么 + 计数"。
 */
</script>

<template>
  <div class="page">
    <header class="page__head">
      <div class="hstack hstack-3 between wrap">
        <div>
          <h1 class="page__title">计划与行动</h1>
          <p class="page__sub">
            {{ scenario.grade }}这一年的里程碑在下面。任务都拆到能勾掉的大小 —— 做不动可以点"改小"，那不是失败，是设计好的。
          </p>
        </div>
        <RouterLink class="btn btn--primary" to="/home">回到任务与计划</RouterLink>
      </div>
    </header>

    <div class="ledger">
      <!-- 账页：左边那格写"这一行是什么 + 计数"，右边是内容。索引不再另占一栏。 -->
      <section class="ledger__row">
        <p class="ledger__label">阶段里程碑 · {{ scenario.milestones.length }}</p>
        <div class="ledger__body">
          <p class="ledger__hint">由"帮你排计划的人"写入，不是前端写死</p>
          <div class="stack stack-4">
            <div v-for="m in scenario.milestones" :key="m.id" class="milestone">
              <div class="hstack hstack-3 between">
                <div>
                  <p class="milestone__title">{{ m.title }}</p>
                  <p class="milestone__window">{{ m.window }}</p>
                </div>
                <span class="milestone__pct t-num">{{ Math.round(m.progress * 100) }}%</span>
              </div>
              <div class="meter" style="margin-top: var(--sp-3)">
                <div class="meter__fill" :style="{ '--meter': m.progress }" />
              </div>
              <p class="milestone__note">{{ m.note }}</p>
            </div>
          </div>
        </div>
      </section>

      <section class="ledger__row">
        <p class="ledger__label">本周要做的 · {{ now.length + waiting.length }}</p>
        <div class="ledger__body">
          <p class="ledger__hint">什么 + 多久 + 为什么是现在</p>
          <table class="table">
            <thead>
              <tr>
                <th>做什么</th>
                <th class="t-num-nowrap">多久</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in [...now, ...waiting]" :key="t.id">
                <td>
                  <span class="t-strong">{{ t.title }}</span>
                  <span v-if="t.due" class="chip chip--attention" style="margin-left: 8px">
                    {{ t.due }}
                  </span>
                  <span class="why t-dim">{{ t.why }}</span>
                </td>
                <td class="t-num t-num-nowrap">{{ t.minutes ? `${t.minutes} 分钟` : '不用动' }}</td>
                <td>
                  <button class="btn btn--sm" @click="demo.completeTask(t.id)">勾掉</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="done.length" class="t-note" style="margin-top: var(--sp-3)">
            已完成 {{ done.length }} 件 —— 完成记录只由行为日志驱动，勾了才算。
          </p>
        </div>
      </section>

      <section class="ledger__row">
        <p class="ledger__label">待办与计划 · {{ books.length }} 本</p>
        <div class="ledger__body">
          <p class="ledger__hint">谁放进来的，分得清</p>
          <div class="books">
            <div v-for="l in books" :key="l.key" class="book">
              <div class="hstack hstack-2 between">
                <span class="book__title">{{ l.key }}</span>
                <span class="chip">{{ l.items.length }}</span>
              </div>
              <ul class="book__list">
                <li v-for="it in l.items.slice(0, 4)" :key="it.id" class="book__item">
                  {{ it.title }}
                </li>
                <li v-if="!l.items.length" class="book__item t-dim">还没有</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section class="ledger__row">
        <p class="ledger__label">关键节点 · {{ CALENDAR_MARKS.length }} 个</p>
        <div class="ledger__body">
          <p class="ledger__hint">{{ YEAR }} 年 {{ MONTH }} 月</p>
          <div class="cal">
            <span v-for="w in WEEKDAYS" :key="w" class="cal__wd">{{ w }}</span>
            <div
              v-for="(c, i) in cells"
              :key="i"
              class="cal__cell"
              :class="{ 'cal__cell--empty': c.day === null, 'cal__cell--today': c.day === TODAY }"
            >
              <span v-if="c.day" class="cal__day t-num">{{ c.day }}</span>
              <span
                v-for="mk in c.marks"
                :key="mk.label"
                class="cal__mark"
                :class="markClass(mk.kind)"
                :title="mk.label"
              />
            </div>
          </div>
        </div>
      </section>

      <section class="ledger__row">
        <p class="ledger__label">做不动的时候</p>
        <div class="ledger__body">
          <p class="ledger__hint">三条出路都写在界面上，不用用户自己想</p>
          <ul class="outs">
            <li>当场把任务拆到 5 分钟</li>
            <li>承认问题在方法上，换一种做法</li>
            <li>承认方向要重估，交回给你判断方向的人</li>
          </ul>
          <p class="t-note" style="margin-top: var(--sp-3)">回退是设计好的，不是故障。</p>
        </div>
      </section>

      <GuideNote gkey="plan" :text="GUIDES.plan" to="/review" to-label="去复盘记录" />
    </div>
  </div>
</template>

<style scoped>
/* 次块与明细块里的标题行：块自己已经有内距，标题不再缩进第二次 */
.side__head,
.detail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 0 0 var(--sp-3);
}

.detail__head {
  border-bottom: var(--bw-1) solid var(--c-border);
}

.milestone {
  padding-bottom: var(--sp-4);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.milestone:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.milestone__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
}

.milestone__window {
  margin-top: 2px;
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.milestone__pct {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  color: var(--c-primary);
}

.milestone__note {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* 「多久」这一列的值很短（"15 分钟"／"不用动"），被折成"15 分／钟"只是难读。
   短值一律不折行 —— 折行该发生在长句上，不该发生在度量上。 */
.table .t-num {
  white-space: nowrap;
}

/* 「为什么是现在」从独立一列收进"做什么"那一格的第二行：
   次块只有 4 栏，四列横排会把每个词都挤断；而这一句本来就属于那件事，不属于表格。 */
.why {
  display: block;
  margin-top: 4px;
  font-size: var(--fs-12);
  line-height: var(--lh-snug);
}

.books {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
}

.book {
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
}

.book__title {
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
}

.book__list {
  margin-top: var(--sp-2);
}

.book__item {
  padding: var(--sp-2) 0;
  border-bottom: var(--bw-1) dashed var(--c-border);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  line-height: 1.5;
}

.book__item:last-child {
  border-bottom: none;
}

/* ---- 日历 ---- */
.cal {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 2px;
}

.cal__wd {
  text-align: center;
  font-size: var(--fs-12);
  color: var(--c-text-3);
  padding-bottom: var(--sp-2);
}

.cal__cell {
  position: relative;
  aspect-ratio: 1 / 1;
  display: grid;
  place-items: center;
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  color: var(--c-text-2);
}

.cal__cell--empty {
  visibility: hidden;
}

.cal__cell--today {
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-weight: var(--fw-semibold);
}

.cal__mark {
  position: absolute;
  bottom: 5px;
  width: 4px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--c-primary);
}

.cal__cell--today .cal__mark {
  background: var(--c-on-primary);
}

.cal__mark--accent {
  background: var(--c-attention);
}

.cal__mark--muted {
  background: var(--c-text-4);
}

.marks {
  margin-top: var(--sp-4);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
}

.marks__item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) 0;
  font-size: var(--fs-12);
  color: var(--c-text-2);
}

.cal__dot {
  width: 6px;
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--c-primary);
}

.marks__label {
  color: var(--c-text-3);
}

/* ---- 做不动的时候 ---- */
.outs {
  margin-top: var(--sp-3);
}

.outs li {
  position: relative;
  padding: var(--sp-2) 0 var(--sp-2) var(--sp-4);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.outs li:last-child {
  border-bottom: none;
}

.outs li::before {
  content: '→';
  position: absolute;
  left: 0;
  color: var(--c-primary);
}

@media (max-width: 1080px) {
  .books {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
