<script setup lang="ts">
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import { useSessionStore } from '@/stores/session'

/**
 * 待办气泡 —— 现在该做的那一件事。
 *
 * "这一件事"由工作台算出来（action_panel.evaluation）。
 * 之前在本地写死了五套阶段文案 —— 算不出来时界面上照样有一条很像样的待办，
 * 那恰好把"这里其实没有依据"盖住了。现在没数据就直说没数据。
 */
const session = useSessionStore()
const liveAction = computed(() => session.wsPanels?.action || '')

/**
 * "现在这一件"的**权威来源**：行动计划里第一条还没勾掉的任务。
 *
 * 工作台那句评价说的是"这个阶段在做什么"，而这里要回答的是
 * "为什么是**这一件**、不是别的" —— 那只有计划本身说得清：
 * 它带阶段、带截止、也能指出后面还排着几条。
 */
const now = computed(() => session.actionPlan?.next_task ?? null)

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
  const task = now.value
  const phase = (plan?.phases ?? []).find((p) => p.name === task?.phase) ?? null

  if (!task) {
    session.openDrawer('为什么是这一件', '现在这一件还没定下来', [
      {
        source: '为什么还没有',
        detail: '行动计划是「行动」这一步的产物：方向定下来之后才会排出来。'
          + '现在还没有这一版计划 —— 先跟主理说一句"接下来怎么做"，它会拆到今天能勾掉的粒度。',
        confidence: 1,
        at: liveAction.value || '现在',
      },
    ])
    return
  }

  const siblings = (plan?.phases ?? []).flatMap((p) => p.tasks ?? [])
  const index = siblings.findIndex((t) => t.task_id === task.task_id)
  const next = index >= 0 ? siblings.slice(index + 1).find((t) => !t.done) ?? null : null
  const pending = siblings.filter((t) => !t.done).length

  session.openDrawer(
    `为什么是「${task.text}」`,
    `${task.phase || '当前阶段'}${phase?.date_range ? ` · ${phase.date_range}` : ''}`,
    [
      { source: '现在这一件', detail: task.text, confidence: 1, at: task.phase || '这一版计划' },
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
        detail: task.due_date
          ? `这一版计划给的截止时间是 ${task.due_date.slice(0, 10)}。`
          : '这一版计划没有给它写截止时间 —— 你可以跟主理说一句，让它把时间补上。',
        confidence: 1,
        at: '计划',
      },
      {
        source: '为什么排在它前面',
        detail: `它是这一版计划里第一条还没勾掉的任务${pending > 1 ? `，后面还排着 ${pending - 1} 条` : ''}；`
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

    <div v-if="liveAction" class="now">
      <span class="now__label label">现在</span>
      <p class="now__title">{{ liveAction }}</p>
    </div>

    <div v-else class="now">
      <span class="now__label label">现在</span>
      <p class="now__title">今天这一件还没定下来。</p>
      <p class="now__meta">先开一次对话；有了画像与窗口期，这里才会有内容。</p>
    </div>

    <footer class="foot">
      <!-- 待办不是让用户自己想的 —— AI 指哪件就做哪件，指不动就先把话说清楚 -->
      <NextAsk v-if="!liveAction" compact />
      <button class="label foot__why" type="button" @click="openWhy">
        为什么这一件
      </button>
      <button class="label foot__cta" type="button" @click="session.openOverlay('tasks')">
        全部任务 →
      </button>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); }
.head__meta { color: var(--ink-faint); }
.now { display: flex; flex-direction: column; gap: 4px; }
.now__label { color: var(--accent); }
.now__title {
  font-size: clamp(18px, 1.7vw, var(--t-h2));
  line-height: 1.35;
  letter-spacing: -0.015em;
  max-width: 24ch;
}
.now__meta { color: var(--ink-dim); font-size: var(--fs-small); }
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
 * "矮下来之后先舍掉哪一层"：先舍元信息，再舍次要动作，
 * 但"现在这一件"和主入口一个字都不能少 —— 那是这块存在的理由。
 */
.bubble.is-compact { gap: 6px; }
.bubble.is-compact .head__meta { display: none; }
.bubble.is-compact .now__meta { display: none; }
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
