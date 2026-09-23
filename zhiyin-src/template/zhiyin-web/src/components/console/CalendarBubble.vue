<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import { useDayPlan, ymd, weekdayOf } from '@/composables/useDayPlan'
import { useSessionStore } from '@/stores/session'

/**
 * 日历气泡 —— 一块"按天看"的入口。
 *
 * 为什么要有它：画布上原来只有"本周课表"（一张周历，看的是重复的课）
 * 和"行动计划"（一串阶段任务，看的是整条线）。**"今天/这一天到底有什么"**
 * 没有一块地方说得清 —— 而这一天才是一个人真正要面对的东西。
 *
 * 它是一块真日历，不是装饰：每个日子下面有内容就有一个点（课 / 到期的事 / 任务），
 * 点某一天直接进浮层看那一天的安排和怎么用。点今天最省事，所以今天那一格
 * 加了实心底。
 *
 * 它自己不做判断 —— 那天的安排是读来的事实，判断在浮层里的那一段 AI 建议。
 */
const session = useSessionStore()
/*
 * 格位可能又矮又宽（实测 604×212）。矮的时候不再硬塞整月 ——
 * 6 行挤进 87px，一行 13px，日号会糊成一团。改成"今天所在的这一周 + 前后各一周"
 * （4 行 28 天），行高翻倍，仍然是一张能读的日历。
 */
const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const emit = defineEmits<{ (e: 'close'): void }>()
const { ensure, markOf, selectedDay } = useDayPlan()

const today = new Date()
/** 气泡里固定看当月：翻月是浮层的事，画布上这一块只回答"这个月大概什么样" */
const month = ref(new Date(today.getFullYear(), today.getMonth(), 1))

onMounted(() => void ensure())
// 数据一变就重拉：这块气泡随画布常驻，计划/节点变了它得跟着变（见 store.dataVersion）
watch(() => session.dataVersion, () => void ensure())

const WEEK = ['一', '二', '三', '四', '五', '六', '日']
/** 点读给屏幕阅读器听的解释 */
const MARK_TEXT = { due: '有事到期', class: '有课', none: '没有安排' } as const

/** 42 格（6 周）从周一排起：月历的格子数必须固定，否则换月时整块会跳 */
const cells = computed(() => {
  if (props.compact) {
    // 今天那一周的周一，往前推一周，共 4 周
    const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (weekdayOf(today) - 1) - 7)
    return Array.from({ length: 28 }, (_, i) => {
      const date = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i)
      return { date, day: date.getDate(), inMonth: true, mark: markOf(date) }
    })
  }
  const first = month.value
  const offset = first.getDay() === 0 ? 6 : first.getDay() - 1
  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(first.getFullYear(), first.getMonth(), 1 - offset + i)
    return {
      date,
      day: date.getDate(),
      inMonth: date.getMonth() === first.getMonth(),
      mark: markOf(date),
    }
  })
})

const monthLabel = computed(() =>
  props.compact ? '这四周' : `${month.value.getMonth() + 1} 月`,
)
/** 网格的行数：4 行是紧凑格位里的"这四周"，6 行是整月 */
const rows = computed(() => (props.compact ? 4 : 6))
const isToday = (date: Date) => ymd(date) === ymd(today)
const weekend = (date: Date) => weekdayOf(date) >= 6

function open(date: Date) {
  selectedDay.value = ymd(date)
  session.openOverlay('calendar')
}
</script>

<template>
  <!--
    根节点不是 button（interactive=false）：里面的每一格都要能点，
    button 里再套 button 是无效结构，键盘也会乱。
  -->
  <Bubble size="md" tone="raised" :tilt="-0.4" label="日历" @close="emit('close')">
    <header class="head">
      <span class="label">日历</span>
      <span class="label head__meta">{{ monthLabel }}</span>
    </header>

    <p class="lead">点某一天，看那天的安排和怎么用。</p>

    <ol class="week">
      <li v-for="w in WEEK" :key="w">{{ w }}</li>
    </ol>

    <ol class="grid" :style="{ gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))` }">
      <li v-for="cell in cells" :key="cell.date.toISOString()">
        <button
          class="day"
          type="button"
          :class="{ dim: !cell.inMonth, today: isToday(cell.date), week: weekend(cell.date) }"
          :aria-label="`${cell.day} 日 · ${MARK_TEXT[cell.mark]}`"
          @click.stop="open(cell.date)"
        >
          <span class="day__num">{{ cell.day }}</span>
          <span class="day__dot" :class="cell.mark" aria-hidden="true" />
        </button>
      </li>
    </ol>

    <footer class="foot">
      <button class="chip" type="button" @click.stop="open(today)">看今天</button>
      <span class="label foot__cta">打开日历 →</span>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__meta { color: var(--ink-3); }
.lead { font-size: var(--t-h4); line-height: 1.4; letter-spacing: -0.012em; color: var(--ink-1); }

.week, .grid { list-style: none; margin: 0; padding: 0; }
.week {
  display: grid; grid-template-columns: repeat(7, 1fr);
  font-size: var(--fs-label); color: var(--ink-3); text-align: center;
}
/*
 * 网格吃掉剩下的高度：格位是平铺算法按权重分的，可能又矮又宽（实测 604×212）。
 * 所以行高用 1fr 跟着容器缩，而不是按 aspect-ratio 长成固定方块 ——
 * 固定方块在矮格位里会把后几周直接顶出气泡（overflow: hidden 一裁，日历就残了）。
 */
.grid {
  display: grid; grid-template-columns: repeat(7, 1fr);
  grid-template-rows: repeat(6, minmax(0, 1fr));
  gap: 2px; flex: 1; min-height: 0;
}

.day {
  position: relative;
  width: 100%; height: 100%; min-height: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px;
  border-radius: var(--r-xs);
  font-size: var(--fs-small);
  color: var(--ink-2);
  transition: background var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.day:hover { background: var(--fill-hover); color: var(--ink-1); }
.day.dim { color: var(--ink-4); }
.day.week { color: var(--ink-3); }
/* 今天：实心底。一周里"今天"是唯一一个会自己变的参照点，值得占住 */
.day.today { background: var(--ink-1); color: var(--n-0); }
.day.today .day__dot.class,
.day.today .day__dot.due { background: var(--n-0); }

.day__num { line-height: 1; font-variant-numeric: tabular-nums; }
.day__dot {
  width: 4px; height: 4px; border-radius: 50%;
  background: transparent;
}
/* 有课：绿点（每周重复）；有到期的事：橙点（一次性，最该被看见） */
.day__dot.class { background: var(--mk-green); }
.day__dot.due { background: var(--mk-orange); }

/*
 * 紧凑格位（高度不够）：把说明那行收起来、字号降一档 ——
 * 日历本身在，比"每样都完整但被裁掉一半"有用。
 */
.is-compact .lead { display: none; }
.is-compact .day { font-size: var(--fs-label); gap: 1px; }
.is-compact .day__dot { width: 3px; height: 3px; }
.is-compact .head { gap: var(--s2); }

.foot {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s3);
  margin-top: auto;
}
.foot__cta { color: var(--ink-3); transition: color var(--dur-fast) var(--ease-out); }
.bubble:hover .foot__cta { color: var(--accent); }
</style>
