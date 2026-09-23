<script setup lang="ts">
import { computed } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import NextAsk from '@/components/console/NextAsk.vue'
import { useSessionStore } from '@/stores/session'

/**
 * 谁在帮你（显式交接）。
 *
 * 这一块对应"换人"那件事：用户不该好奇"刚才那个是谁、怎么突然换了人"。
 * 所以这里把当前接手的角色、上一次为什么换人、下一次谁接手，直接写在脸上，
 * 点开就是完整的时间轴。
 */
const emit = defineEmits<{ (e: 'close'): void; (e: 'resolve'): void }>()
const session = useSessionStore()

/**
 * 交接记录来自**这一轮的回复**（`TurnView.badge` 与 `disclosure`），不是本地脚本。
 * 没有回包时这里就是空的，如实说"还没有交接记录" —— 不再编一条出来。
 */
const lead = computed(() => session.rail?.leadName ?? '')
const why = computed(() => session.rail?.disclosure ?? '')

function openTimeline() {
  session.openDrawer(
    '这一轮谁做了什么',
    '走到哪一环、谁接手、为什么换人',
    (session.railCards ?? []).map((c) => ({
      source: c.title || c.stage,
      detail: c.active ? '这一环正在进行' : c.status === 'done' ? '已经完成' : '还没开始',
      confidence: c.active ? 1 : 0.6,
      at: c.stage,
    })),
  )
}

/**
 * "知道" —— 交接这件事读过了。
 *
 * 它和右上角那颗「解决」不是同一个意思：解决是"这件事办完了"，
 * 知道是"我看见了，别再提醒我"。所以这里除了播那段"知道了"的反馈，
 * 还要**在状态里记一笔**（`session.ackBlock`）—— 只做视觉动画的话，
 * 40 秒后同一张卡又飘回来，用户会以为刚才那一下没生效。
 */
function acknowledge() {
  session.ackBlock('people')
  emit('resolve')
}
</script>

<template>
  <Bubble
    size="sm"
    tone="plain"
    resolvable
    resolved-label="知道了 · 不再提醒"
    :tilt="-0.5"
    label="谁在帮你"
    @close="emit('close')"
    @resolve="emit('resolve')"
  >
    <header class="head">
      <span class="label head__k">交接</span>
      <span class="label head__t">当前接手</span>
    </header>

    <h3 class="title">接手的是<span class="who">{{ lead || '还没开始' }}</span></h3>
    <p v-if="why" class="why">{{ why }}</p>
    <p v-else class="why why--empty">还没有交接记录。开始对话后，谁把结论交给了谁，会记在这里。</p>

    <div class="acts">
      <NextAsk compact />
      <button class="act act--go" type="button" @click="openTimeline">看交接</button>
      <button class="act act--ack" type="button" @click="acknowledge">知道</button>
    </div>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s2); }
.head__k { color: var(--mk-purple); }
.head__t { color: var(--ink-3); }
.title { font-size: var(--t-body); font-weight: 600; line-height: 1.4; }
.who { color: var(--mk-purple); font-weight: 600; }
.why { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.why--empty { color: var(--ink-3); font-style: normal; }
.acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.act {
  flex: 1; height: 30px; border-radius: var(--r-pill);
  border: 1px solid var(--line-2); font-size: var(--fs-small); color: var(--ink-2);
  transition: border-color var(--mo-fast) var(--mo-out), color var(--mo-fast) var(--mo-out);
}
.act:hover { border-color: var(--ink-1); color: var(--ink-1); }
.act--go { border-color: var(--mk-purple); color: var(--mk-purple); }
.act--go:hover { background: var(--mk-purple-soft); color: var(--mk-purple); }

/*
 * 紧凑形态：这一块在 1440 以下的画布上只有 190px 上下高（实测），
 * 完整形态要 213px —— 差的那 20px 会把最后一行按钮切掉一半。
 * 先舍元信息，再舍次要动作；"谁在接手"和主入口留着。
 */
.bubble.is-compact { gap: var(--s2); }
.bubble.is-compact .head__t { display: none; }
.bubble.is-compact .title { font-size: var(--t-sm); }
.bubble.is-compact .why { -webkit-line-clamp: 1; }
/*
 * 紧凑形态里仍保留「知道」。
 *
 * 收掉的是次要动作，而"知道"是**读过之后唯一能让这张卡不再回来的动作**：
 * 收掉它，用户就只剩右上角那颗「解决」—— 那颗是"这件事办完了"，语义并不一样
 * （实测里用户找不到"我已读过"这个出口）。真正矮到放不下时（is-tiny）才收。
 */
.bubble.is-compact .act:not(.act--go):not(.act--ack) { display: none; }

/* 再小一档（<200px）：说明句整句收掉，只留"谁接手 + 一个动作" */
.bubble.is-tiny .why { display: none; }
.bubble.is-tiny .head { display: none; }
.bubble.is-tiny .act { height: 26px; }
.bubble.is-tiny .acts { gap: 4px; }
.bubble.is-tiny .title { line-height: 1.25; }
</style>
