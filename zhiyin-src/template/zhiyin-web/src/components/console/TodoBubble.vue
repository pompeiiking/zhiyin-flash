<script setup lang="ts">
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import GlyphIcon from '@/components/ui/GlyphIcon.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import type { ActionTask } from '@/api/client'
import { useSessionStore } from '@/stores/session'

/**
 * 待办气泡 —— 现在该做的那一件事。
 *
 * "这一件事"是**待办自己**：行动计划里第一条还没勾掉的任务，没有计划时才是
 * 自己写的那一条。工作台那句阶段评价（`action_panel.evaluation`）只当来源说明。
 *
 * 之前在本地写死了五套阶段文案 —— 算不出来时界面上照样有一条很像样的待办，
 * 那恰好把"这里其实没有依据"盖住了。所以反过来：没有待办才说没有待办，
 * 而且判据必须是**待办本身**，不能是任何一句评价的缺失。
 */
const session = useSessionStore()

/**
 * 工作台对当前这一步的评价（`action_panel.evaluation`）。
 *
 * 它回答的是"**这个阶段**在做什么"，不是"**这一件**是什么" ——
 * 所以它当不了标题：它非空而计划为空时，卡片看上去有依据；
 * 它是空串而计划里明明排着任务时，卡片却说"今天这一件还没定下来"
 * （后端 degraded 时 `wsPanels.action` 就是空串，这条路径必现）。
 * 现在它退到标题下面，只当一条来源说明。
 */
const liveAction = computed(() => session.wsPanels?.action || '')

/**
 * 一行待办在界面上的统一形状 —— 两个来源先摊成同一个形状，再决定谁当"现在这一件"。
 *
 * 为什么必须先摊平：计划任务（`actionPlan.phases[].tasks`）与自建待办
 * （`customTodos`）的字段完全不同（`task_id/text/due_date` 对 `id/label/due`），
 * 之前只有自建那一边被数了个数（"N 件自建待办"），**两个来源一条都没渲染出来**。
 */
interface Line {
  key: string
  title: string
  done: boolean
  /** 格式化好的截止日（`YYYY-MM-DD`），没有就是空串 */
  due: string
  /** 来源，写在行上：计划排的 / 自己写的 */
  from: '行动计划' | '你自己'
  /** 计划任务的 task_id（阶段名:任务文本）—— 勾选与溯源都要靠它；自建待办为空串 */
  taskId: string
  /** 所属阶段名（自建待办为空串） */
  phase: string
}

function fromPlan(task: ActionTask): Line {
  return {
    key: `plan:${task.task_id}`,
    title: task.text,
    done: !!task.done,
    due: task.due_date ? task.due_date.slice(0, 10) : '',
    from: '行动计划',
    taskId: task.task_id,
    phase: task.phase ?? '',
  }
}

function fromTodo(todo: { id: string; label: string; done: boolean; due?: string }): Line {
  return {
    key: `todo:${todo.id}`,
    title: todo.label,
    done: todo.done,
    due: todo.due ?? '',
    from: '你自己',
    taskId: '',
    phase: '',
  }
}

/** 计划里全部任务，按阶段顺序摊平 —— `next_task` 只是后端算的第一条，前端自己也要能算 */
const planLines = computed<Line[]>(() =>
  (session.actionPlan?.phases ?? []).flatMap((p) => (p.tasks ?? []).map(fromPlan)),
)
const todoLines = computed<Line[]>(() => session.customTodos.map(fromTodo))
/** 两个来源合起来才是"我的待办"——少算一边，主界面就会在有待办时显示空状态 */
const allLines = computed<Line[]>(() => [...planLines.value, ...todoLines.value])
const pending = computed<Line[]>(() => allLines.value.filter((t) => !t.done))

/**
 * "现在这一件"。
 *
 * 优先级：后端给的 `next_task`（它就是"第一条还没勾掉的"）→ 计划里第一条没勾的
 * → 自建待办里第一条没勾的。
 *
 * **判据里没有 `wsPanels.action`** —— 它是这个阶段的评价，缺失不等于没有待办；
 * 这正是这个 bug 的机制：卡片此前只读它，空串就直接落进空状态。
 */
const current = computed<Line | null>(() => {
  const next = session.actionPlan?.next_task
  if (next && !next.done) return fromPlan(next)
  return planLines.value.find((t) => !t.done) ?? todoLines.value.find((t) => !t.done) ?? null
})

/**
 * 全都勾完了的时候，仍然要指出"最后一件是什么"。
 *
 * 空状态只留给**真的没有任务**的账号（没有计划、也没有自建待办）：
 * 有计划但全勾完，还说"今天这一件还没定下来"是假话 ——
 * 用户会以为那一版计划丢了，而它只是做完了。
 */
const justDone = computed<Line | null>(() => {
  if (current.value) return null
  const done = allLines.value.filter((t) => t.done)
  return done.length ? done[done.length - 1] : null
})

/** 这一块里要显示的那一条（在办的，或者刚办完的） */
const head = computed<Line | null>(() => current.value ?? justDone.value)

/** 其余还压着的条数 —— 标题只推一条，剩下的用数字交代，整份清单在「全部任务 →」里 */
const others = computed(() => Math.max(0, pending.value.length - (current.value ? 1 : 0)))

/**
 * 事实行：完成状态 · 截止时间 · 还有几件。
 *
 * 这三件事是这一块的验收项，所以它**不参与紧凑形态的收缩**（见下面的样式）：
 * 篇幅不够时先舍"工作台评价"和后面的清单，不砍这一行。
 */
const facts = computed(() => {
  const t = head.value
  if (!t) return ''
  const status = t.done ? '已经勾掉' : '还没勾掉'
  const due = t.due ? `截止 ${t.due}` : t.from === '行动计划' ? '计划里没写截止时间' : '你写的'
  const more = others.value ? `另有 ${others.value} 件待办` : t.done ? '这一版都勾完了' : '没有别的待办'
  return [status, due, more].join(' · ')
})

/** 后面还排着的（最多三条）—— 完整清单在「全部任务 →」，这里不铺开 */
const rest = computed<Line[]>(() =>
  pending.value.filter((t) => t.key !== current.value?.key).slice(0, 3),
)

/** 真的没有任务时才用得上：有计划但没拆出任务，与还没有计划，是两句话 */
const emptyTitle = computed(() =>
  session.actionPlan?.has_plan ? '这一版计划里还没有拆出任务。' : '今天这一件还没定下来。',
)

/**
 * 打开"为什么是这一件"。
 *
 * 以前这里传的是 `stage.question`（一句固定的阶段文案，比如"窗口期里怎么推进"），
 * 抽屉里一条依据都没有 —— 用户点开看到的还是那个问题本身。
 * 现在摊开的全部是**这一版计划的实测事实**：这一件是什么、属于哪一段、
 * 什么时候到期、为什么排在第一位、做完之后轮到谁。
 */
function openWhy() {
  const plan = session.actionPlan
  const task = current.value

  if (!task) {
    /*
     * "没有现在这一件"有两种，不能共用一句话：
     * 一种是真没有计划，另一种是计划做完了 —— 后者说"还没定下来"是假话。
     */
    const allDone = allLines.value.some((t) => t.done)
    session.openDrawer('为什么是这一件', allDone ? '这一版计划里的任务都勾完了' : '现在这一件还没定下来', [
      allDone
        ? {
            source: '为什么没有了',
            detail: '这一版计划里的任务都已经勾掉了。'
              + '跟主理说一句"接下来怎么做"，它会按你的新情况重排下一段。',
            confidence: 1,
            at: '行动计划',
          }
        : {
            source: '为什么还没有',
            detail: '行动计划是「行动」这一步的产物：方向定下来之后才会排出来。'
              + '现在还没有这一版计划 —— 先跟主理说一句"接下来怎么做"，它会拆到今天能勾掉的粒度。',
            confidence: 1,
            at: liveAction.value || '现在',
          },
    ])
    return
  }

  if (task.from === '你自己') {
    /*
     * 自建待办不在计划里：它没有阶段、没有依赖。
     * 所以这里不该套用"它是这一版计划里第一条没勾掉的任务"那套解释 —— 那是假的。
     */
    session.openDrawer(`为什么是「${task.title}」`, '你自己写的一条 · 不在这一版行动计划里', [
      { source: '现在这一件', detail: task.title, confidence: 1, at: task.due || '你写的' },
      {
        source: '为什么排在计划后面',
        detail: '计划里的任务带阶段与截止，先按那些排；这一条是你自己加进来的，'
          + '计划里没有别的任务时，才轮到它当"现在这一件"。',
        confidence: 1,
        at: '你自己',
      },
      ...(liveAction.value
        ? [{ source: '依据', detail: `工作台对当前这一步的评价：${liveAction.value}`, confidence: 1, at: '工作台' }]
        : []),
    ])
    return
  }

  const phase = (plan?.phases ?? []).find((p) => p.name === task.phase) ?? null
  const siblings = (plan?.phases ?? []).flatMap((p) => p.tasks ?? [])
  const index = siblings.findIndex((t) => t.task_id === task.taskId)
  const next = index >= 0 ? siblings.slice(index + 1).find((t) => !t.done) ?? null : null
  const pendingPlan = siblings.filter((t) => !t.done).length

  session.openDrawer(
    `为什么是「${task.title}」`,
    `${task.phase || '当前阶段'}${phase?.date_range ? ` · ${phase.date_range}` : ''}`,
    [
      { source: '现在这一件', detail: task.title, confidence: 1, at: task.phase || '这一版计划' },
      ...(phase
        ? [
            {
              source: '属于哪一段',
              detail: [phase.tag, phase.date_range].filter(Boolean).join(' · ') || phase.name,
              confidence: 1,
              at: phase.name,
            },
          ]
        : []),
      {
        source: '什么时候做',
        detail: task.due
          ? `这一版计划给的截止时间是 ${task.due}。`
          : '这一版计划没有给它写截止时间 —— 你可以跟主理说一句，让它把时间补上。',
        confidence: 1,
        at: '计划',
      },
      {
        source: '为什么排在它前面',
        detail: `它是这一版计划里第一条还没勾掉的任务${pendingPlan > 1 ? `，后面还排着 ${pendingPlan - 1} 条` : ''}；`
          + '顺序是按阶段与截止时间排的，先做它，后面的依赖才动得了。',
        confidence: 1,
        at: '行动计划',
      },
      {
        source: '做完之后',
        detail: next
          ? `轮到下一件：${next.text}`
          : '这一版计划里的任务就都勾完了 —— 跟主理说一句，它会按你的新情况重排下一段。',
        confidence: 1,
        at: next ? next.phase || '下一件' : '这一版的末尾',
      },
      {
        source: '依据',
        detail: liveAction.value
          ? `工作台对当前这一步的评价：${liveAction.value}`
          : '这一版行动计划的顺序（还没有工作台评价）。',
        confidence: 1,
        at: '工作台',
      },
      {
        source: '日历',
        detail: plan?.reminders_synced
          ? '它的关键节点已经写进你的日历，到期会在那一天出现。'
          : '它的关键节点还没写进日历 —— 现在只在待办里。',
        confidence: 1,
        at: '关键节点',
      },
    ],
  )
}

const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <Bubble size="lg" tone="plain" :tilt="-0.4" label="待办" @close="emit('close')">
    <header class="head">
      <span class="label">待办</span>
      <span class="label head__meta">{{ session.customTodos.length }} 件自建待办</span>
    </header>

    <!--
      有待办就必须看见待办：标题是**任务本身**，不是工作台那句阶段评价。
      `head` 为空只可能是"计划里没有任务、也没写过自建待办"。
    -->
    <div v-if="head" class="now">
      <div class="now__head">
        <span class="now__label label">{{ current ? '现在' : '最后一件' }}</span>
        <span class="now__meta label">{{ facts }}</span>
      </div>
      <p class="now__title">{{ head.title }}</p>
      <!-- 工作台评价退到标题下面：它是来源说明，不是这一件本身 -->
      <p v-if="liveAction" class="now__why">{{ liveAction }}</p>
      <div v-if="rest.length" class="rest">
        <p class="label rest__k">后面还排着</p>
        <ul class="rest__list">
          <li v-for="t in rest" :key="t.key" class="rest__row">
            <span class="rest__title">{{ t.title }}</span>
            <span class="label rest__meta">{{ t.due ? `截止 ${t.due}` : t.from === '行动计划' ? '计划里没写截止' : '你写的' }}</span>
          </li>
        </ul>
      </div>
    </div>

    <div v-else class="now">
      <span class="now__label label">现在</span>
      <p class="now__title">{{ emptyTitle }}</p>
      <p class="now__note">先开一次对话；有了画像与窗口期，这里才会有内容。</p>
    </div>

    <footer class="foot">
      <!-- 有待办就先把那一条做掉；真的没有下一件时，才轮到 AI 推的"下一步" -->
      <NextAsk v-if="!current" compact />
      <button class="label foot__why" type="button" @click="openWhy">
        为什么这一件
      </button>
      <button class="label foot__cta" type="button" @click="session.openOverlay('tasks')">
        全部任务 <GlyphIcon name="arrow-right" :size="12" />
      </button>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__meta { color: var(--ink-faint); }
.now { display: flex; flex-direction: column; gap: 4px; }
/*
 * 「现在」与事实共用一行。
 *
 * 事实（完成状态 · 截止 · 还有几件）是这一块的验收项，一个字都不能少；
 * 但格位是平铺引擎给的固定高度，单独一行就会把页脚的「全部任务 →」挤出去。
 * 所以让它和"现在"同占一个行高 —— 任何尺寸下都不增加这块的高度。
 */
.now__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s2); min-width: 0; }
.now__label { color: var(--accent); flex: 0 0 auto; }
.now__meta {
  min-width: 0; color: var(--ink-dim); font-size: var(--fs-small);
  /* 一行封顶：这是事实的摘要，宁可省略号，也不允许它换行去挤标题与页脚 */
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.now__title {
  font-size: clamp(18px, 1.7vw, var(--t-h2));
  line-height: 1.35;
  letter-spacing: -0.015em;
  max-width: 24ch;
}
/* 工作台评价（"这个阶段在做什么"）：来源说明，紧凑形态里第一个被舍掉 */
.now__why {
  color: var(--ink-faint); font-size: var(--fs-small); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.now__note { color: var(--ink-dim); font-size: var(--fs-small); }
/* 后面还排着的：完整清单在「全部任务 →」，这里只报前三条，免得这一块变成一张清单 */
.rest { display: flex; flex-direction: column; gap: 2px; margin-top: 2px; }
.rest__k { color: var(--ink-faint); }
.rest__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.rest__row { display: flex; align-items: baseline; gap: var(--s2); min-width: 0; }
.rest__title {
  flex: 1; min-width: 0;
  font-size: var(--fs-small); color: var(--ink-dim);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rest__meta { flex: 0 0 auto; color: var(--ink-faint); }
.options { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.opt {
  padding: 7px 14px; border-radius: var(--r-pill);
  border: var(--bw) solid var(--line-2); background: var(--n-1);
  font-size: var(--fs-small); color: var(--ink-dim);
  transition: color var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out),
              background var(--dur-fast) var(--ease-out),
              transform var(--dur-fast) var(--ease-out);
}
.opt:hover { color: var(--ink); border-color: var(--ink-dim); transform: translateY(-1px); }
.opt.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
/*
 * 页脚钉在气泡底部（margin-top: auto）。
 * 气泡高度是平铺引擎给的固定值，正文短的时候页脚会紧贴上一段文字 ——
 * "开始对话"整个贴在字下面，既不像底部动作，也失去了它的位置含义。
 */
.foot { display: flex; align-items: center; justify-content: space-between; gap: var(--s3); margin-top: auto; }
.foot__why { color: var(--ink-faint); }
.foot__why:hover { color: var(--ink); }
.foot__why.is-off { opacity: 0.45; }
.foot__cta { color: var(--ink-dim); }
.bubble:hover .foot__cta { color: var(--accent); }

/*
 * 紧凑形态 —— 平铺引擎给到矮格位（实测 380×146）时的那一套排版。
 *
 * 为什么必须写这一条：这一块的内容是"标题 + 现在这一件 + 一行说明 + 页脚"，
 * 完整形态要 246px 高。格位只有 146px 时浏览器只能按 overflow: hidden 裁掉，
 * 用户看到的就是"字被切掉了半句"（历史 bug 的其中一处）。
 *
 * 判据由外层给（shouldCompact 按**像素**算，不看格子数），这里只负责
 * "矮下来之后先舍掉哪一层"：先舍解释（工作台评价、空状态说明、后面的清单），
 * 再舍次要动作，但**任务标题、事实行、主入口一个字都不能少** ——
 * 那是这块存在的理由（事实行本来就只占一行，收掉它换不回高度，只会又变成"看不出待办是什么"）。
 */
.bubble.is-compact { gap: 6px; }
.bubble.is-compact .head__meta { display: none; }
.bubble.is-compact .now__why,
.bubble.is-compact .now__note,
.bubble.is-compact .rest { display: none; }
.bubble.is-compact .now__title {
  font-size: var(--t-h3);
  line-height: 1.3;
  max-width: none;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
/*
 * 紧凑形态里保留「为什么这一件」。
 *
 * 它原来是跟着一起收掉的，而它是**这一块唯一能问"为什么"的入口**：
 * 收掉之后，用户看着一条待办，没有任何地方能问出它是怎么排出来的。
 * 再小一档（is-tiny）才收 —— 那时候连标题都只剩一行的余地。
 */
.bubble.is-tiny .foot__why { display: none; }
.bubble.is-compact .foot { gap: var(--s2); }
</style>
