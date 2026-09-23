<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import CanvasMenu, { type MenuItem } from '@/components/console/CanvasMenu.vue'
import { dayAdviceTask, type DayAdvice } from '@/ai/registry'
import { useDayPlan, ymd, weekdayOf } from '@/composables/useDayPlan'
import { useSessionStore } from '@/stores/session'

/**
 * 日历 —— 左边一个月，右边那一天。
 *
 * 分工写死在这里：
 *   · 左半边是**事实**：哪几天有东西（点），哪一天被选中；
 *   · 右半边上半是那一天的**安排**（课表里星期几对得上的课、到期日正好是这一天
 *     的节点、到期没做完的任务）——全部读库，一条都不编；
 *   · 右半边下半是**怎么用这一天**：那一段是模型写的（`day.advice`），
 *     也只写这一段。
 *
 * 为什么按天也要生成一次：事实能自己看，但"课多的时候少排一件事""两个截止撞在
 * 同一天先动哪个"这种话，得有人替他说 —— 这正是这一页存在的理由。
 */
const { ensure, of, markOf, selectedDay } = useDayPlan()
const session = useSessionStore()

const today = new Date()

/** 选中的那一天（`YYYY-MM-DD` → Date）。它是这一屏**唯一**的日期真状态。 */
const selected = computed(() => {
  const [y, m, d] = selectedDay.value.split('-').map(Number)
  return new Date(y, (m ?? 1) - 1, d ?? 1)
})

/**
 * 左边那个月**不是**独立状态 —— 它由"选中的那一天"推出来。
 *
 * 之前是两份状态各改各的：`shift()` 只动月份游标，`回到今天` 只动选中日期。
 * 于是切到上个月之后，左边写着「2026 年 8 月」、右边还是「9 月 23 日」，
 * 而且"回到今天"那颗按钮根本不出现（它还认为选中的就是今天）——
 * 用户被卡在一个自相矛盾的月份里，退不回来。
 *
 * 现在唯一的真状态是 `selectedDay`（它同时被日历气泡共享）：
 * 翻月 = 把选中日挪到目标月，选某一天 = 选中日就是那一天。
 * 左边月份、右侧事实与建议、AI 那段话永远属于同一天。
 */
const cursor = computed(() => {
  const d = selected.value
  return new Date(d.getFullYear(), d.getMonth(), 1)
})

onMounted(() => void ensure())
// 数据一变就重拉：日历是常驻挂载的，等下一次"打开"可能一整页会话都不会发生
watch(() => session.dataVersion, () => void ensure())

const WEEK = ['一', '二', '三', '四', '五', '六', '日']
const WEEK_FULL = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const cells = computed(() => {
  const first = cursor.value
  const offset = first.getDay() === 0 ? 6 : first.getDay() - 1
  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(first.getFullYear(), first.getMonth(), 1 - offset + i)
    return {
      date,
      key: ymd(date),
      day: date.getDate(),
      inMonth: date.getMonth() === first.getMonth(),
      mark: markOf(date),
    }
  })
})

const plan = computed(() => of(selected.value))
const isEmpty = computed(
  () =>
    !plan.value.courses.length &&
    !plan.value.nodes.length &&
    !plan.value.tasks.length &&
    !plan.value.myTodos.length,
)

/** 勾掉/找回自己记的待办：按文字与日期对上 store 里那一条 */
async function toggleMyTodo(text: string) {
  const todo = session.customTodos.find((t) => t.label === text && t.due === selectedDay.value)
  if (todo) await session.toggleCustomTodo(todo.id)
}

const stamp = computed(
  () => `${selected.value.getMonth() + 1} 月 ${selected.value.getDate()} 日 · ${WEEK_FULL[weekdayOf(selected.value) - 1]}`,
)
const isToday = (date: Date) => ymd(date) === ymd(today)

/**
 * 翻月 = **把选中的那一天挪到目标月**（同一号，越界就落在该月最后一天）。
 *
 * 为什么不改成"只翻月份、选中日期不动"：那样左侧月份与右侧那一天会分成两个上下文，
 * 而右侧的事实（课、到期的事）和 AI 建议全是**按选中那一天**算的 ——
 * 用户看着 8 月的日历、读着 9 月 23 日的课，两边都不是错的，但合起来没法用。
 */
function shift(months: number) {
  const from = selected.value
  const target = new Date(from.getFullYear(), from.getMonth() + months, 1)
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  selectedDay.value = ymd(
    new Date(target.getFullYear(), target.getMonth(), Math.min(from.getDate(), lastDay)),
  )
}

/** 回到今天：月份与选中日期一起回去（游标是从它推出来的，所以只要设这一个） */
function goToday() {
  selectedDay.value = ymd(today)
}
const slot = (c: { start: number; span: number }) => `第 ${c.start}-${c.start + c.span - 1} 节`

/*
 * 右键某一天 → 记一条那天的待办。
 *
 * 日历和待办从此是同一本账：右键 11 日 → 写一句 → 那天的清单与月历上的橙点
 * 立刻多一件事（归属日存在本地，见 store.todoDue）。
 */
const dayMenu = ref<{ x: number; y: number; key: string } | null>(null)
const dayMenuItems = computed<MenuItem[]>(() => [
  { id: 'todo', label: `这天记一条待办`, hint: '写进那一天的清单', tone: 'accent' },
  { id: 'open', label: `看这天的安排`, hint: '左侧选中它' },
])

function openDayMenu(e: MouseEvent, key: string) {
  dayMenu.value = { x: e.clientX, y: e.clientY, key }
  selectedDay.value = key
}

/** 记一条：写完立刻落到那一天（输入框挂在那一天的页头下面） */
const composer = ref<{ day: string; text: string } | null>(null)

function runDayMenu(id: string) {
  const at = dayMenu.value
  dayMenu.value = null
  if (!at) return
  if (id === 'todo') {
    composer.value = { day: at.key, text: '' }
    requestAnimationFrame(() => composerInput.value?.focus())
  }
}

const composerInput = ref<HTMLInputElement | null>(null)

async function saveTodo() {
  const at = composer.value
  if (!at) return
  const text = at.text.trim()
  if (!text) {
    composer.value = null
    return
  }
  await session.addTodo(text, at.day)
  composer.value = null
}
</script>

<template>
  <Overlay
    title="你的日历"
    subtitle="哪一天有什么 · 那一天该怎么用"
    from="calendar"
    size="wide"
    @close="session.closeOverlay()"
  >
    <div class="wrap">
      <!-- 左：一个月 -->
      <nav class="month sheet sheet--quiet" aria-label="日历">
        <header class="month__bar">
          <button class="step" type="button" aria-label="上个月" @click="shift(-1)">←</button>
          <span class="month__label">
            {{ cursor.getFullYear() }} 年 {{ cursor.getMonth() + 1 }} 月
          </span>
          <button class="step" type="button" aria-label="下个月" @click="shift(1)">→</button>
        </header>

        <ol class="week">
          <li v-for="w in WEEK" :key="w">{{ w }}</li>
        </ol>

        <ol class="grid">
          <li v-for="cell in cells" :key="cell.key">
            <button
              class="day"
              type="button"
              :class="{
                dim: !cell.inMonth,
                today: isToday(cell.date),
                on: cell.key === selectedDay,
              }"
              :title="`${cell.day} 日 · 右键可记一条这天的待办`"
              @click="selectedDay = cell.key"
              @contextmenu.prevent="openDayMenu($event, cell.key)"
            >
              <span class="day__num">{{ cell.day }}</span>
              <span class="day__dot" :class="cell.mark" aria-hidden="true" />
            </button>
          </li>
        </ol>

        <p class="month__foot label">橙点＝那天有事到期（自己记的待办也算） · 右键某天可记一条</p>
      </nav>

      <!-- 右：这一天 -->
      <section class="day-sheet sheet">
        <header class="day__head">
          <h3 class="day__date">{{ stamp }}</h3>
          <button
            v-if="!isToday(selected)"
            class="chip"
            type="button"
            @click="goToday"
          >
            回到今天
          </button>
        </header>

        <!-- 记一条那天的待办：右键日期格唤出，Enter 落账，Esc 收起 -->
        <form v-if="composer" class="composer" @submit.prevent="saveTodo">
          <span class="label composer__k">{{ composer.day }} · 记一条</span>
          <input
            ref="composerInput"
            v-model="composer.text"
            type="text"
            placeholder="这天要做什么？写一句就行"
            @keydown.esc.prevent="composer = null"
          >
          <button class="btn primary composer__save" type="submit">记下</button>
        </form>

        <div v-if="isEmpty" class="facts fact-empty">
          这一天没有课、没有到期的事 —— 是一整块能自己用的时间。
        </div>

        <template v-else>
          <div v-if="plan.courses.length" class="facts">
            <span class="label">这一天的课</span>
            <ul>
              <li v-for="c in plan.courses" :key="c.name + c.start">
                <span class="fact__when">{{ slot(c) }}</span>
                <span class="fact__what">{{ c.name }}</span>
                <span class="fact__where">{{ [c.place, c.teacher].filter(Boolean).join(' · ') }}</span>
              </li>
            </ul>
          </div>

          <div v-if="plan.nodes.length" class="facts">
            <span class="label">这一天到期的事</span>
            <ul>
              <li v-for="n in plan.nodes" :key="n.title">
                <span class="fact__when">截止</span>
                <span class="fact__what">{{ n.title }}</span>
                <span class="fact__where">{{ n.task }}</span>
              </li>
            </ul>
          </div>

          <div v-if="plan.tasks.length" class="facts">
            <span class="label">这一天的任务</span>
            <ul>
              <li v-for="t in plan.tasks" :key="t.text">
                <span class="fact__when" :class="{ done: t.done }">{{ t.done ? '已做' : '待做' }}</span>
                <span class="fact__what" :class="{ done: t.done }">{{ t.text }}</span>
                <span class="fact__where">{{ t.phase }}</span>
              </li>
            </ul>
          </div>

          <!-- 自己记的：能勾掉，勾了月历上的点也跟着变 -->
          <div v-if="plan.myTodos.length" class="facts">
            <span class="label">自己记的</span>
            <ul>
              <li v-for="t in plan.myTodos" :key="t.text" class="my">
                <button
                  class="my__check"
                  type="button"
                  :aria-pressed="t.done"
                  :title="t.done ? '改成没做' : '做成'"
                  @click="toggleMyTodo(t.text)"
                >
                  <svg v-if="t.done" width="11" height="11" viewBox="0 0 14 14" aria-hidden="true">
                    <path d="M2.6 7.4 5.6 10.4 11.4 3.8" fill="none" stroke="currentColor"
                          stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
                <span class="fact__what" :class="{ done: t.done }">{{ t.text }}</span>
              </li>
            </ul>
          </div>
        </template>

        <!--
          这一天怎么用 —— 唯一由模型写的一段。
          key 带上日期：换一天就重新生成一次，缓存按天存（后端也按天缓存）。
        -->
        <div class="advice">
          <span class="label">这一天怎么用</span>
          <AiFrame :key="selectedDay" :task="() => dayAdviceTask(selectedDay) as never">
            <template #default="{ data }">
              <div v-if="data" class="advice__body">
                <h4 class="advice__head">{{ (data as DayAdvice).headline }}</h4>
                <p class="advice__reading">{{ (data as DayAdvice).reading }}</p>
                <ul v-if="(data as DayAdvice).plan.length" class="advice__plan">
                  <li v-for="p in (data as DayAdvice).plan" :key="p.label">
                    <span class="plan__when">{{ p.label }}</span>
                    <span class="plan__why">{{ p.why }}</span>
                  </li>
                </ul>
                <p v-if="(data as DayAdvice).watch" class="advice__watch">
                  <span class="label">要小心</span>{{ (data as DayAdvice).watch }}
                </p>
              </div>
            </template>
          </AiFrame>
        </div>
      </section>
    </div>

    <!-- 某一天的右键菜单：记一条那天的待办 / 选中它 -->
    <CanvasMenu
      v-if="dayMenu"
      :x="dayMenu.x"
      :y="dayMenu.y"
      :title="`${dayMenu.key} 这一天`"
      :items="dayMenuItems"
      @pick="runDayMenu"
      @close="dayMenu = null"
    />
    <button v-if="dayMenu" class="day-menu-veil" type="button" aria-label="关闭菜单" @click="dayMenu = null" />
  </Overlay>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: var(--s4); align-items: start; }

.month { padding: var(--s4) var(--s3); display: flex; flex-direction: column; gap: var(--s3); }
.month__bar { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); }
.month__label { font-size: var(--fs-small); color: var(--ink-1); }
.step {
  width: 28px; height: 28px; border-radius: var(--r-xs);
  color: var(--ink-2);
  transition: background var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.step:hover { background: var(--fill-hover); color: var(--ink-1); }
.month__foot { color: var(--ink-3); line-height: 1.6; }

.week, .grid { list-style: none; margin: 0; padding: 0; }
.week {
  display: grid; grid-template-columns: repeat(7, 1fr);
  font-size: var(--fs-label); color: var(--ink-3); text-align: center;
}
.grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }

.day {
  width: 100%; aspect-ratio: 1 / 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
  border-radius: var(--r-xs);
  font-size: var(--fs-small); color: var(--ink-2);
  transition: background var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.day:hover { background: var(--fill-hover); color: var(--ink-1); }
.day.dim { color: var(--ink-4); }
.day.today .day__num { text-decoration: underline; text-underline-offset: 3px; }
.day.on { background: var(--ink-1); color: var(--n-0); }
.day.on .day__dot.class,
.day.on .day__dot.due { background: var(--n-0); }
.day.today.on .day__num { text-decoration: none; }
.day__num { line-height: 1; font-variant-numeric: tabular-nums; }
.day__dot { width: 4px; height: 4px; border-radius: 50%; background: transparent; }
.day__dot.class { background: var(--mk-green); }
.day__dot.due { background: var(--mk-orange); }

.day-sheet { padding: var(--s5); display: flex; flex-direction: column; gap: var(--s4); }
.day__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.day__date { font-size: var(--t-h3); color: var(--ink-1); }

.facts { display: flex; flex-direction: column; gap: var(--s2); }
.facts ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s1); }

/* 自己记的待办：前面一颗手绘方框勾 */
.facts li.my { grid-template-columns: auto minmax(0, 1fr); align-items: center; }
.my__check {
  width: 18px; height: 18px; flex: 0 0 auto;
  display: grid; place-items: center;
  border: var(--bw) solid var(--line-3);
  border-radius: var(--r-sketch-sm);
  color: var(--mk-green);
  transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.my__check:hover { border-color: var(--mk-green); background: var(--mk-green-soft); }
.facts li {
  display: grid; grid-template-columns: 96px minmax(0, 1fr) auto;
  gap: var(--s3); align-items: baseline;
}
.fact__when { font-size: var(--fs-small); color: var(--mk-green); font-variant-numeric: tabular-nums; }
.fact__when.done { color: var(--ink-3); }
.fact__what { font-size: var(--fs-small); color: var(--ink-1); }
.fact__what.done { color: var(--ink-3); text-decoration: line-through; }
.fact__where { font-size: var(--fs-label); color: var(--ink-3); }
.fact-empty {
  font-size: var(--fs-small); color: var(--ink-2); line-height: 1.8;
  padding: var(--s3) var(--s4);
  border-left: 3px solid var(--line-3);
  background: var(--fill-subtle);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}

.advice { display: flex; flex-direction: column; gap: var(--s2); }

/* 记一条那天的待办：一行输入，Enter 落账 */
.composer {
  display: flex; align-items: center; gap: var(--s2);
  padding: var(--s2) var(--s3);
  border: var(--bw) dashed var(--line-3);
  border-radius: var(--r-sketch-md);
  background: var(--fill-subtle);
}
.composer__k { color: var(--mk-green); flex: 0 0 auto; }
.composer input {
  flex: 1; min-width: 0; height: 34px;
  border: 0; outline: none; background: none;
  font-size: var(--fs-small); color: var(--ink-1);
}
.composer__save { height: 32px; flex: 0 0 auto; }

.day-menu-veil {
  position: fixed; inset: 0; z-index: calc(var(--z-toast) - 1);
  background: none; cursor: default;
}
.advice__body { display: grid; gap: var(--s3); }
.advice__head { font-size: var(--fs-body); color: var(--ink-1); line-height: 1.5; }
.advice__reading { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.85; max-width: 66ch; }
.advice__plan { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.advice__plan li {
  display: grid; grid-template-columns: minmax(120px, max-content) minmax(0, 1fr);
  gap: var(--s3); align-items: baseline;
}
.plan__when { font-size: var(--fs-small); color: var(--ink-1); }
.plan__why { font-size: var(--fs-small); color: var(--ink-3); line-height: 1.7; }
.advice__watch {
  display: flex; align-items: baseline; gap: var(--s3);
  padding: var(--s3) var(--s4);
  border-left: 3px solid var(--warn);
  background: rgba(194, 90, 18, 0.06);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
  font-size: var(--fs-small); color: var(--ink-1);
}
.advice__watch .label { color: var(--warn); flex: 0 0 auto; }

@media (max-width: 900px) {
  .wrap { grid-template-columns: minmax(0, 1fr); }
  .facts li { grid-template-columns: minmax(0, 1fr); }
}
</style>
