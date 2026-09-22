<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Bubble from '@/components/console/Bubble.vue'
import { useSessionStore } from '@/stores/session'
import { groupIntel, readFetched, readIntelText, readShares } from '@/lib/intel'

/**
 * 外部情报 —— 画布上的那一块"外面正在发生什么"。
 *
 * 内容是从公开渠道（学职平台 · 学信网等）按**你的方向**取回的事实：
 * 你这个专业对口哪些职业、这些职业要求什么、走过这条路的人后来怎么样。
 * 每条都带原页面链接 —— 这类信息"凭什么这么说"就是那个链接。
 *
 * 【这一版怎么摆】上一版是一块"标题 + 一段截断的正文 + 剩下几条的标题"，
 * 看起来像一张被打断的清单。情报的原文其实**自带结构**（`字段：值` 一行一行），
 * 所以这一版把它读出来摆成三样东西：
 *
 *   1. **一行链条**：专业 → 职业 → 校友案例，各几条。这是这份数据天然的关系，
 *      也是这块唯一需要一眼看懂的东西；
 *   2. **一个数字**：第一份专业的"对口职业"占比。它是全屏最有分量的一条事实
 *      （"学这个的人后来去干了什么"），所以给它条，不给它一句被截断的话；
 *   3. **一个动作**：看全部（开浮层）/ 现在去取一次。
 *
 * 三条口径没变：**不编**（取不到就说取不到）、**不重复打扰**（打开只读缓存，
 * 只有点"去取"才真去打外部站点）、**来源可点**（浮层里逐条能回原页面）。
 */
const session = useSessionStore()
const emit = defineEmits<{ (e: 'close'): void; (e: 'resolve'): void }>()

/** 这一块可以收起来：只留标题那一行，别在画布上占一大块 */
const folded = ref(false)

const items = computed(() => session.intel?.items ?? [])
const groups = computed(() => groupIntel(items.value))
const stamp = computed(() => readFetched(session.intel?.fetchedAt ?? ''))

/** 第一条"专业"—— 它是这一批里最该给结论的一条 */
const lead = computed(
  () => items.value.find((i) => i.kind === 'speciality') ?? items.value[0] ?? null,
)

/**
 * 领衔那条的对口职业。
 *
 * 读不出占比（老页面只有名字）就退回前几个名字 —— 不猜数字、也不占着位置空着。
 */
const shares = computed(() => {
  const item = lead.value
  if (!item) return []
  const { fields } = readIntelText(item.text ?? '', item.title ?? '')
  const row = fields.find((f) => /对口职业|相关职业/.test(f.label))
  return row ? readShares(row.value).slice(0, 4) : []
})

const maxShare = computed(() => Math.max(...shares.value.map((s) => s.percent ?? 0), 1))

function open() {
  session.openOverlay('intel')
}

onMounted(() => {
  /* 打开只读缓存；真正的抓取留给"现在去取一次"（和 45 秒一次的轮询） */
  void session.loadIntel()
})
</script>

<template>
  <Bubble
    size="sm"
    tone="plain"
    interactive
    resolvable
    :tilt="0.5"
    label="外部情报"
    @click="open"
    @close="emit('close')"
    @resolve="emit('resolve')"
  >
    <header class="head" @click.stop="folded = !folded">
      <span class="label head__k">外部情报</span>
      <span class="label head__t">
        {{ session.intelBusy ? '正在取…' : items.length ? `${items.length} 条 · ${stamp}` : '等着取' }}
      </span>
      <button
        class="head__fold"
        type="button"
        :aria-expanded="!folded"
        :aria-label="folded ? '展开' : '收起'"
        @click.stop="folded = !folded"
      >
        <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M2.6 4.4 6 7.8l3.4-3.4" fill="none" stroke="currentColor" stroke-width="1.6"
                stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </header>

    <template v-if="!folded && items.length">
      <!-- 链条：专业 → 职业 → 校友案例。顺序本身就是这份数据的关系 -->
      <ol class="chain">
        <li v-for="(group, i) in groups" :key="group.kind">
          <span class="chain__k label">{{ group.label }}</span>
          <span class="chain__n mono">{{ group.items.length }}</span>
          <span v-if="i < groups.length - 1" class="chain__arrow" aria-hidden="true">→</span>
        </li>
      </ol>

      <!-- 领衔那条：一句话 + 对口职业的占比 -->
      <h3 class="lead">{{ lead?.title }}</h3>

      <div v-if="shares.length" class="shares">
        <span class="label shares__k">学这个的人后来去干了什么</span>
        <ul>
          <li v-for="share in shares" :key="share.name">
            <span class="shares__n">{{ share.name }}</span>
            <span class="shares__track">
              <i :style="{ width: `${Math.max(6, ((share.percent ?? 0) / maxShare) * 100)}%` }" />
            </span>
            <span class="mono shares__p">{{ share.percent === null ? '—' : share.percent + '%' }}</span>
          </li>
        </ul>
      </div>

      <!--
        没有占比（校友案例 / 没有数字的条目）时退回一句摘要。
        用行数钳住而不是切字符串 —— 切字符串会在半句上断掉，
        而且中文没有空格，"…"落在哪儿全靠运气。
      -->
      <p v-else-if="lead" class="note note--clamp">
        {{ readIntelText(lead.text ?? '', lead.title ?? '').intro }}
      </p>
    </template>

    <template v-else-if="!folded">
      <h3 class="lead">正在盯着和你方向相关的公开信息。</h3>
      <p class="note">
        它按你的专业与目标去公开渠道读：专业对口的职业、这些职业要求什么、
        走过这条路的人后来怎么样。每 45 秒自己看一次，有新的就冒出来。
      </p>
    </template>

    <p v-if="!folded && session.intelError && !items.length" class="label note note--dim">
      {{ session.intelError }}
    </p>

    <footer class="acts">
      <button
        class="act act--go"
        type="button"
        :disabled="session.intelBusy"
        @click.stop="session.loadIntel(true)"
      >
        {{ session.intelBusy ? '正在取…' : '现在去取一次' }}
      </button>
      <button v-if="items.length" class="act" type="button" @click.stop="open">看全部 →</button>
    </footer>
  </Bubble>
</template>

<style scoped>
.head { display: flex; align-items: baseline; gap: var(--s2); cursor: pointer; }
.head__k { color: var(--mk-orange); }
.head__t { color: var(--ink-3); margin-left: auto; }
.head__fold {
  display: grid; place-items: center; width: 20px; height: 20px;
  border-radius: 50%; color: var(--ink-3);
  transition: transform var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.head__fold:hover { color: var(--ink-1); background: var(--fill-hover); }
.head__fold[aria-expanded="false"] { transform: rotate(-90deg); }

/*
 * 链条：专业 3 → 职业 2 → 校友案例 2。
 * 它不是导航，是"这一批里有什么"的一句话，所以小、紧、不抢标题。
 */
.chain { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
.chain li { display: inline-flex; align-items: baseline; gap: 4px; }
.chain__k { color: var(--ink-2); }
.chain__n { color: var(--ink-1); }
.chain__arrow { color: var(--ink-4); margin-left: 2px; }

.lead { font-size: var(--t-h3); line-height: 1.35; letter-spacing: -0.012em; }

.shares { display: grid; gap: 5px; }
.shares__k { color: var(--ink-3); }
.shares ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.shares li { display: grid; grid-template-columns: minmax(0, 1fr) 64px auto; align-items: center; gap: var(--s2); }
.shares__n {
  font-size: var(--fs-label); color: var(--ink-2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
/* 条的长度是相对值（最大那条占满），右侧给的是绝对占比 —— 两个数都在，不骗人 */
.shares__track { height: 5px; border-radius: 3px; background: var(--line-1); overflow: hidden; }
.shares__track i { display: block; height: 100%; background: var(--mk-blue); border-radius: 3px; }
.shares__p { color: var(--ink-3); }

.note { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.65; }
/*
 * 摘要压到**两行**，用确切高度而不是 line-clamp。
 *
 * 两行是从格位反推的：这一块实测 381×218（1600 屏），
 * 头 22 + 链条 20 + 标题 24 + 摘要 + 动作 30 + 几道间距 + 内边距 ≈ 218 ——
 * 摘要能用的正好是两行。给三行，动作栏就会把第三行啃掉（实测过）。
 * 用 `max-height: 行高 × 2`：它是精确的两行高度，不会切出半行字。
 */
.note--clamp {
  max-height: calc(1.65em * 2);
  overflow: hidden;
}
.note--dim { color: var(--ink-3); }

.acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.act {
  flex: 1; min-height: 30px; padding: 4px 10px; border-radius: var(--r-pill);
  border: 1px solid var(--line-2); font-size: var(--fs-small); color: var(--ink-2);
  line-height: 1.3;
  transition: border-color var(--mo-fast) var(--mo-out), background var(--mo-fast) var(--mo-out),
              color var(--mo-fast) var(--mo-out);
}
.act:hover { border-color: var(--ink-1); color: var(--ink-1); }
.act--go { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 500; }
.act--go:hover { background: var(--accent-deep); border-color: var(--accent-deep); color: var(--accent-ink); }
.act:disabled { opacity: 0.5; cursor: not-allowed; }

/* 矮格位：链条与占比先收，标题与入口留着 */
.bubble.is-compact .shares li:nth-child(n + 3) { display: none; }
.bubble.is-tiny .shares { display: none; }
.bubble.is-tiny .chain { display: none; }
</style>
