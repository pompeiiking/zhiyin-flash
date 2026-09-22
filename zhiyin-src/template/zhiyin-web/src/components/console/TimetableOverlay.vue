<script setup lang="ts">
import { computed } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import Timetable from '@/components/charts/Timetable.vue'
import { PERIODS, WEEKDAYS, type Course } from '@/data/student'
import { timetableTask, type TimetablePlan } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'
import { revokeAcademic } from '@/api/client'

/**
 * 课表 —— 来自**学校的教务系统**，不是学信网。
 *
 * 关键不是"排得好看"，是**把课表翻译成时间**：
 * 哪几段没课、那几段能干什么、为什么是这几段。
 * 每门课也能点开：它撑着画像里的哪一条、和你的目标岗位是什么关系。
 *
 * 这份数据必须来自后端快照（`session.academic`）：
 * 以前这里画的是写死在前端的演示课程，标题却写着"从学信网导入"——
 * 而学信网根本没有课程表。没授权就如实说没授权。
 */
const session = useSessionStore()

/** 后端快照 → 界面的课。排不进格子的（没读出周几/第几节）不画，不硬塞。 */
const courses = computed<Course[]>(() =>
  (session.academic?.courses ?? [])
    .filter((c) => c.weekday >= 1 && c.weekday <= 7 && c.start_period >= 1)
    .map((c, i) => ({
      id: `academic-${i}`,
      name: c.name,
      teacher: c.teacher,
      day: c.weekday,
      start: c.start_period,
      span: Math.max(1, (c.end_period || c.start_period) - c.start_period + 1),
      place: c.place,
      credit: Number(c.credit) || 0,
      type: (c.category.includes('必修')
        ? '必修'
        : c.category.includes('选修') || c.category.includes('任选')
          ? '选修'
          : c.category.includes('实践') || c.category.includes('实验')
            ? '实践'
            : '必修') as Course['type'],
      why: '',
      supports: [],
    })),
)

const unplaced = computed(
  () =>
    (session.academic?.courses ?? []).filter(
      (c) => c.weekday < 1 || c.weekday > 7 || c.start_period < 1,
    ).length,
)

const source = computed(() => {
  const a = session.academic
  if (!a) return '还没有导入课表'
  const when = a.imported_at ? a.imported_at.slice(0, 10) : ''
  return [a.school || '你学校', a.term, when ? `${when} 导入` : '自己导入']
    .filter(Boolean)
    .join(' · ')
})

function openBind() {
  session.bindMode = 'academic'
  session.openOverlay('bind')
}

/**
 * 撤销授权。
 *
 * 给出去过一次密码的人，必须能收回来 —— 而且撤回时数据一起删掉。
 * 只删本地状态、后端还留着那份课表，那叫"看不见了"，不叫撤销。
 */
async function revoke() {
  try {
    await revokeAcademic()
  } catch {
    // 后端不可达时不清本地：这时候"看起来清掉了"是最糟的结果
    return
  }
  session.academic = null
  session.academicBound = false
  await session.loadBackend()
}

function pickCourse(c: Course) {
  session.openDrawer(`${c.name} · ${c.teacher}`, `${WEEKDAYS[c.day - 1]} ${PERIODS[Math.ceil(c.start / 2) - 1]} · ${c.place}`, [
    { source: '你导入的课表', detail: `${c.type || '未标性质'} · ${c.credit} 学分`, confidence: 1, at: session.academic?.imported_at?.slice(0, 10) ?? '' },
    {
      source: '这门课与方向的关系',
      detail: c.why || '还没算过 —— 等画像与方向齐了，这一步会给出这门课撑起哪一条。',
      confidence: 0.8,
      at: '待算',
    },
  ])
}

function pickGap(day: number, period: number) {
  /*
   * 空档是**算出来的**，不是写好的四句话。
   *
   * 而且"这段能用来干什么"这件事要有依据才算得出来：
   * 课表（来自教务系统）+ 窗口期（来自学籍与方向）。
   * 依据不齐时直说还缺什么，别塞一句听起来很懂的排课建议。
   */
  const basedOn = session.academic
    ? `从教务系统取回的 ${courses.value.length} 门课排出来的空档`
    : '还没有课表 —— 空档暂时没法算'
  const canPlan = !!session.academic && !!session.chsiBound
  session.openDrawer(`${WEEKDAYS[day - 1]} ${PERIODS[period - 1]} 没课`, '这一段能用来干什么', [
    { source: '空档', detail: `${WEEKDAYS[day - 1]} ${PERIODS[period - 1]} 这段时间没有排课。`, confidence: 1, at: '本周' },
    {
      source: '怎么算的',
      detail: `${basedOn}。`,
      confidence: 0.9,
      at: '规则',
    },
    {
      source: '这段该放什么',
      detail: canPlan
        ? '交给路径规划师 —— 它会按你这周的目标和剩余窗口排。'
        : '还差依据：要有课表（教务系统）与窗口期（学籍），才能算出这段该放什么。',
      confidence: canPlan ? 0.84 : 0.4,
      at: '待算',
    },
  ])
}
</script>

<template>
  <Overlay
    title="本周课表"
    :subtitle="source"
    from="timetable"
    @close="session.closeOverlay()"
  >
    <div class="tt-wrap">
      <!--
        没授权就直说，并且给出那一个动作。
        画一张空格子加一句"这周没课"，用户会以为自己在放假 —— 这是最糟的一种错。
      -->
      <div v-if="!session.academic" class="empty sheet">
        <h3 class="empty__t editorial">课表还没有导入。</h3>
        <p class="empty__d">
          课程表和成绩单在<b>你学校的教务系统</b>里，学信网只有学籍、没有这两样。
          在教务系统里把课表页全选复制，贴进来就行 —— 不用登录我们这里，也不用给账号。
        </p>
        <button class="btn primary" type="button" @click="openBind">导入我的课表</button>
      </div>

      <template v-else>
      <div class="tt-wrap__grid sheet">
        <Timetable :courses="courses" @pick-course="pickCourse" @pick-gap="pickGap" />
      </div>

      <aside class="tt-wrap__side sheet">
        <p v-if="unplaced" class="tt-wrap__warn label">
          有 {{ unplaced }} 门课没读出上课时间，没有排进格子（学校页面上就没给）。
        </p>
        <p v-else-if="!courses.length" class="tt-wrap__warn label">
          这份课表里没有课程 —— 可能是这学期还没排课，或者学校没放开课表查询。
        </p>
        <AiFrame :task="() => timetableTask() as never" :compact="true">
          <template #default="{ data }">
            <div v-if="data" class="plan">
              <h3 class="plan__head">{{ (data as TimetablePlan).headline }}</h3>

              <span class="label">这周能用的四段</span>
              <ul class="wins">
                <li v-for="w in (data as TimetablePlan).windows" :key="w.day + w.slot">
                  <span class="wins__when mono">{{ w.day }} {{ w.slot }}</span>
                  <span class="wins__why">{{ w.why }}</span>
                </li>
              </ul>

              <span class="label">路径规划师建议这样用</span>
              <ul class="moves">
                <li v-for="m in (data as TimetablePlan).moves" :key="m.at">
                  <span class="moves__at mono">{{ m.at }}</span>
                  <span class="moves__what">{{ m.what }}</span>
                  <span class="moves__why">{{ m.why }}</span>
                </li>
              </ul>
            </div>
          </template>
        </AiFrame>
        <p class="label tt-wrap__revoke">
          这份课表是你自己导进来的。
          <button class="tt-wrap__link" type="button" @click="revoke">清空课表与成绩</button>
        </p>
      </aside>
      </template>
    </div>
  </Overlay>
</template>

<style scoped>
/*
 * 课表与"这周怎么用"分成两块薄片浮着（底板已经拿掉）。
 * 左边是图，右边是话 —— 它们本来就是两件事，各出一张纸反而更清楚。
 */
.tt-wrap { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: var(--s4); }

/* 没授权时占满整块：这是一件事，不是一个"空状态插画" */
.empty { grid-column: 1 / -1; display: flex; flex-direction: column; gap: var(--s3); align-items: flex-start; padding: var(--s6); align-self: start; }
.empty__t { font-size: var(--t-h3); line-height: 1.42; }
.empty__d { font-size: var(--fs-small); line-height: 1.8; color: var(--ink-2); max-width: 56ch; }
.tt-wrap__warn { color: var(--ink-3); line-height: 1.7; margin-bottom: var(--s2); }
.tt-wrap__revoke { color: var(--ink-faint); line-height: 1.7; margin-top: var(--s3); }
.tt-wrap__link { color: var(--ink-2); text-decoration: underline; }
.tt-wrap__link:hover { color: var(--warn); }
.tt-wrap__grid { overflow: auto; display: flex; align-items: flex-start; padding: var(--s4) var(--s5); }
.tt-wrap__side { overflow: auto; padding: var(--s5); }

.plan { display: flex; flex-direction: column; gap: var(--s3); }
.plan__head { font-size: var(--t-h3); line-height: 1.45; }
.wins, .moves { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.wins li, .moves li { display: grid; gap: 2px; padding: var(--s3) var(--s3) var(--s3) var(--s4); border-left: 3px solid var(--mk-green); border-radius: 0 var(--r-sm) var(--r-sm) 0; }
.moves li { border-left-color: var(--mk-purple); }
.wins li:nth-child(even), .moves li:nth-child(even) { background: var(--fill-subtle); }
.wins__when, .moves__at { color: var(--ink-3); }
.wins__why, .moves__why { font-size: var(--fs-small); color: var(--ink-2); }
.moves__what { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }

@media (max-width: 900px) {
  .tt-wrap { grid-template-columns: minmax(0, 1fr); }
}
</style>
